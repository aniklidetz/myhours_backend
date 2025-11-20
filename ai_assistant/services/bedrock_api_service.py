"""
Bedrock API Service - Orchestration layer for AI Lambda calls.

This service abstracts the communication with AWS API Gateway,
which invokes the Lambda function for salary explanations using
Amazon Bedrock (Claude) with RAG.
"""

import json
import logging
from typing import Any, Dict

import requests

from django.conf import settings

from .mock_data import get_mock_salary_data
from .real_data import get_real_salary_data

logger = logging.getLogger(__name__)

# API Gateway URL - deployed in US East-1
# In production, this should come from settings or environment variables
BASE_API_URL = getattr(
    settings,
    "BEDROCK_API_GATEWAY_URL",
    "https://pxddvm9n35.execute-api.us-east-1.amazonaws.com/prod",
)

# Request timeout in seconds
API_TIMEOUT = 30


def invoke_ai_explainer_lambda(
    employee_id: int, query_text: str, period: str, language: str = "en"
) -> Dict[str, Any]:
    """
    Invoke the Lambda function for AI salary explanation via API Gateway.

    This function:
    1. Collects salary context (currently mock, will be real data)
    2. Formats the payload for Lambda
    3. Calls API Gateway
    4. Parses and returns the response

    Args:
        employee_id: ID of the employee requesting explanation
        query_text: User's question (e.g., "Explain my Shabbat pay")
        period: Period for the query (e.g., "October 2025")
        language: Response language code ("en", "he", "ru")

    Returns:
        Dictionary with:
        - explanation_text: AI-generated explanation
        - citations: Legal sources used
        - status: "success" or "error"
    """

    # 1. Collect salary context from real database
    try:
        salary_data = get_real_salary_data(employee_id, period)
        logger.info(f"Using real data for employee {employee_id}")
    except Exception as e:
        # Fallback to mock data if real data fails
        logger.warning(f"Falling back to mock data: {e}")
        salary_data = get_mock_salary_data(employee_id, period)

    # 2. Transform to simple format expected by Lambda
    simple_salary_data = _transform_for_lambda(salary_data, period)

    # 3. Format payload for Lambda
    payload = {
        "user_id": employee_id,
        "query": query_text,
        "salary_details": simple_salary_data,
        "language": language,
    }

    try:
        # 3. Call API Gateway
        logger.info(
            f"Calling AI Explainer for employee {employee_id}",
            extra={
                "employee_id": employee_id,
                "query": query_text[:50],
                "language": language,
            },
        )

        response = requests.post(
            f"{BASE_API_URL}/explain",
            json=payload,
            timeout=API_TIMEOUT,
            headers={
                "Content-Type": "application/json",
                # TODO: Add API Key when enabled
                # "x-api-key": settings.BEDROCK_API_KEY,
            },
        )

        # 4. Process response
        if response.status_code == 200:
            return _parse_success_response(response)

        # Handle error responses
        logger.error(
            f"API Gateway error: {response.status_code}",
            extra={
                "status_code": response.status_code,
                "response_text": response.text[:500],
            },
        )

        return {
            "explanation_text": _get_error_message(response.status_code, language),
            "citations": [],
            "status": "error",
            "error_code": f"API_ERROR_{response.status_code}",
        }

    except requests.exceptions.Timeout:
        logger.error(f"API Gateway timeout after {API_TIMEOUT}s")
        return {
            "explanation_text": _get_timeout_message(language),
            "citations": [],
            "status": "error",
            "error_code": "TIMEOUT",
        }

    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error to API Gateway: {e}")
        return {
            "explanation_text": _get_connection_error_message(language),
            "citations": [],
            "status": "error",
            "error_code": "CONNECTION_ERROR",
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"Request error calling API Gateway: {e}", exc_info=True)
        return {
            "explanation_text": _get_generic_error_message(language),
            "citations": [],
            "status": "error",
            "error_code": "REQUEST_ERROR",
        }


def _parse_success_response(response: requests.Response) -> Dict[str, Any]:
    """
    Parse successful API Gateway response.

    The response structure from API Gateway wraps the Lambda response:
    {
        "statusCode": 200,
        "body": "{\"assistant_response\": \"...\"}"
    }
    """
    try:
        gateway_response = response.json()

        # API Gateway wraps Lambda response in 'body' as string
        body = gateway_response.get("body", "{}")
        if isinstance(body, str):
            lambda_response = json.loads(body)
        else:
            lambda_response = body

        return {
            "explanation_text": lambda_response.get("assistant_response", ""),
            "status": "success",
        }

    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Failed to parse Lambda response: {e}")
        return {
            "explanation_text": "Error parsing AI response",
            "status": "error",
            "error_code": "PARSE_ERROR",
        }


def _transform_for_lambda(data: Dict[str, Any], period: str) -> Dict[str, Any]:
    """
    Transform complex salary data to simple format expected by Lambda.

    Lambda expects:
    {
        "employee_name": "Yosef Abramov",
        "base_hourly_rate": "120 Shekels per hour",
        "shabbat_hours": 14.4,
        "multiplier": "x1.50",
        "calculated_amount": "2550.1 Shekels",
        "period": "2025-11"
    }
    """
    employee_info = data.get("employee_info", {})
    summary = data.get("summary", {})
    rates = data.get("rates", {})
    earnings = data.get("earnings", {})

    # Get calculation type and rates
    calculation_type = rates.get("calculation_type", "hourly")

    # Get base rate
    base_rate = rates.get("base_hourly_rate", 0)
    if hasattr(base_rate, "__float__"):
        base_rate = float(base_rate)

    # Format rate string based on calculation type
    if calculation_type == "monthly":
        monthly_salary = rates.get("monthly_salary", 0)
        if hasattr(monthly_salary, "__float__"):
            monthly_salary = float(monthly_salary)
        base_rate_str = f"{monthly_salary:.0f} Shekels per month (effective hourly: {base_rate:.2f})"
    else:
        base_rate_str = f"{base_rate:.2f} Shekels per hour"

    # Get shabbat hours
    shabbat_hours = summary.get("shabbat_hours", 0)
    if hasattr(shabbat_hours, "__float__"):
        shabbat_hours = float(shabbat_hours)

    # Get total gross
    total_gross = earnings.get("total_gross", 0)
    if hasattr(total_gross, "__float__"):
        total_gross = float(total_gross)

    # Format period
    # "November 2025" -> "2025-11"
    # "2025-11-15" stays as is
    period_formatted = period
    try:
        if "-" in period and len(period) == 10:
            # Already in YYYY-MM-DD format
            period_formatted = period
        else:
            import calendar

            parts = period.split()
            if len(parts) == 2:
                month_name, year = parts
                month_names = {
                    name: num for num, name in enumerate(calendar.month_name) if num
                }
                month_num = month_names.get(month_name, 1)
                period_formatted = f"{year}-{month_num:02d}"
    except Exception:
        pass

    # Build pay_components array for Lambda
    regular_hours = float(summary.get("regular_hours", 0))
    ot_125_hours = float(summary.get("overtime_125_hours", 0))
    ot_150_hours = float(summary.get("overtime_150_hours", 0))

    pay_components = []

    # Regular hours
    if regular_hours > 0:
        pay_components.append(
            {
                "type": "REGULAR",
                "hours": regular_hours,
                "multiplier": 1.0,
                "amount": round(regular_hours * base_rate, 2),
            }
        )

    # Overtime 125%
    if ot_125_hours > 0:
        pay_components.append(
            {
                "type": "DAILY_OVERTIME_1",
                "hours": ot_125_hours,
                "multiplier": 1.25,
                "amount": round(ot_125_hours * base_rate * 1.25, 2),
            }
        )

    # Overtime 150%
    if ot_150_hours > 0:
        pay_components.append(
            {
                "type": "DAILY_OVERTIME_2",
                "hours": ot_150_hours,
                "multiplier": 1.5,
                "amount": round(ot_150_hours * base_rate * 1.5, 2),
            }
        )

    # Shabbat hours
    if shabbat_hours > 0:
        pay_components.append(
            {
                "type": "SHABBAT",
                "hours": shabbat_hours,
                "multiplier": 1.5,
                "amount": round(shabbat_hours * base_rate * 1.5, 2),
            }
        )

    total_hours = regular_hours + ot_125_hours + ot_150_hours + shabbat_hours

    return {
        "employee_name": employee_info.get("name", "Employee"),
        "calculation_type": calculation_type,
        "base_hourly_rate": base_rate_str,
        "period": period_formatted,
        "total_amount": f"{total_gross:.2f} Shekels",
        "total_hours": total_hours,
        "pay_components": pay_components,
    }


def _serialize_salary_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Serialize salary data for JSON transmission.

    Converts Decimal objects to floats and handles nested structures.
    """
    from decimal import Decimal

    def convert(obj):
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, dict):
            return {k: convert(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert(item) for item in obj]
        return obj

    return convert(data)


def _get_error_message(status_code: int, language: str) -> str:
    """Get localized error message based on status code."""
    messages = {
        "en": {
            400: "Invalid request. Please try again.",
            401: "Authentication required.",
            403: "Access denied.",
            404: "Service not found.",
            429: "Too many requests. Please wait a moment.",
            500: "Server error. Please try again later.",
            503: "Service temporarily unavailable.",
        },
        "he": {
            400: "בקשה לא תקינה. נסה שוב.",
            401: "נדרש אימות.",
            403: "הגישה נדחתה.",
            404: "השירות לא נמצא.",
            429: "יותר מדי בקשות. אנא המתן.",
            500: "שגיאת שרת. נסה שוב מאוחר יותר.",
            503: "השירות לא זמין זמנית.",
        },
        "ru": {
            400: "Неверный запрос. Попробуйте снова.",
            401: "Требуется аутентификация.",
            403: "Доступ запрещен.",
            404: "Сервис не найден.",
            429: "Слишком много запросов. Подождите.",
            500: "Ошибка сервера. Попробуйте позже.",
            503: "Сервис временно недоступен.",
        },
    }

    lang_messages = messages.get(language, messages["en"])
    return lang_messages.get(status_code, lang_messages.get(500))


def _get_timeout_message(language: str) -> str:
    """Get localized timeout message."""
    messages = {
        "en": "Request timed out. Please try again.",
        "he": "הבקשה נכשלה בגלל זמן המתנה. נסה שוב.",
        "ru": "Время ожидания истекло. Попробуйте снова.",
    }
    return messages.get(language, messages["en"])


def _get_connection_error_message(language: str) -> str:
    """Get localized connection error message."""
    messages = {
        "en": "Unable to connect to AI service. Please check your connection.",
        "he": "לא ניתן להתחבר לשירות AI. בדוק את החיבור.",
        "ru": "Не удалось подключиться к AI сервису. Проверьте соединение.",
    }
    return messages.get(language, messages["en"])


def _get_generic_error_message(language: str) -> str:
    """Get localized generic error message."""
    messages = {
        "en": "An error occurred. Please try again later.",
        "he": "אירעה שגיאה. נסה שוב מאוחר יותר.",
        "ru": "Произошла ошибка. Попробуйте позже.",
    }
    return messages.get(language, messages["en"])
