"""
Tests for integrations utilities - safe_to_json function.
"""

import json
from unittest.mock import MagicMock

from django.test import TestCase

from integrations.utils import safe_to_json


class SafeToJsonTest(TestCase):
    """Tests for safe_to_json function"""

    def test_dict_input_returned_as_is(self):
        """Test that dict input is returned unchanged"""
        input_dict = {"key": "value", "number": 42}
        result = safe_to_json(input_dict)
        self.assertEqual(result, input_dict)
        self.assertIs(result, input_dict)  # Same object reference

    def test_empty_dict_input(self):
        """Test empty dict input"""
        input_dict = {}
        result = safe_to_json(input_dict)
        self.assertEqual(result, input_dict)

    def test_nested_dict_input(self):
        """Test nested dict input"""
        input_dict = {"user": {"name": "John", "age": 30}, "active": True}
        result = safe_to_json(input_dict)
        self.assertEqual(result, input_dict)

    def test_valid_bytes_input(self):
        """Test valid JSON bytes input"""
        json_data = {"message": "hello", "status": "ok"}
        json_bytes = json.dumps(json_data).encode("utf-8")

        result = safe_to_json(json_bytes)
        self.assertEqual(result, json_data)

    def test_invalid_bytes_input_returns_empty_dict(self):
        """Test invalid JSON bytes returns empty dict"""
        invalid_bytes = b"not valid json"

        result = safe_to_json(invalid_bytes)
        self.assertEqual(result, {})

    def test_unicode_decode_error_bytes(self):
        """Test bytes with Unicode decode errors"""
        # Create bytes with invalid UTF-8 sequence
        invalid_utf8_bytes = b'{"key": "value\xff"}'  # \xff is invalid UTF-8

        result = safe_to_json(invalid_utf8_bytes)
        # Should handle decode error gracefully and return result
        self.assertIsInstance(result, dict)

    def test_bytearray_input(self):
        """Test bytearray input (same logic as bytes)"""
        json_data = {"test": "data"}
        json_bytearray = bytearray(json.dumps(json_data).encode("utf-8"))

        result = safe_to_json(json_bytearray)
        self.assertEqual(result, json_data)

    def test_valid_json_string_input(self):
        """Test valid JSON string input"""
        json_string = '{"name": "Alice", "age": 25}'
        expected = {"name": "Alice", "age": 25}

        result = safe_to_json(json_string)
        self.assertEqual(result, expected)

    def test_invalid_json_string_returns_empty_dict(self):
        """Test invalid JSON string returns empty dict"""
        invalid_string = "not valid json"

        result = safe_to_json(invalid_string)
        self.assertEqual(result, {})

    def test_empty_string_returns_empty_dict(self):
        """Test empty string returns empty dict"""
        result = safe_to_json("")
        self.assertEqual(result, {})

    def test_response_object_with_json_method(self):
        """Test response object with working json() method"""
        json_data = {"response": "data"}
        mock_response = MagicMock()
        mock_response.json.return_value = json_data

        result = safe_to_json(mock_response)
        self.assertEqual(result, json_data)
        mock_response.json.assert_called_once()

    def test_response_object_json_method_fails(self):
        """Test response object when json() method fails"""
        mock_response = MagicMock()
        mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
        mock_response.content = b'{"fallback": "data"}'

        result = safe_to_json(mock_response)
        self.assertEqual(result, {"fallback": "data"})

    def test_response_object_json_unicode_error(self):
        """Test response object when json() method has Unicode error"""
        mock_response = MagicMock()
        mock_response.json.side_effect = UnicodeDecodeError(
            "utf-8", b"", 0, 1, "Invalid UTF-8"
        )
        mock_response.content = b'{"fallback": "content"}'

        result = safe_to_json(mock_response)
        self.assertEqual(result, {"fallback": "content"})

    def test_response_object_with_content_attribute(self):
        """Test response object with content attribute (no json method)"""
        mock_response = MagicMock()
        del mock_response.json  # Remove json method
        mock_response.content = b'{"content": "data"}'

        result = safe_to_json(mock_response)
        self.assertEqual(result, {"content": "data"})

    def test_response_object_with_text_attribute(self):
        """Test response object with text attribute (no json or content)"""
        mock_response = MagicMock()
        del mock_response.json
        del mock_response.content
        mock_response.text = '{"text": "data"}'

        result = safe_to_json(mock_response)
        self.assertEqual(result, {"text": "data"})

    def test_response_object_no_callable_json(self):
        """Test response object where json attribute exists but isn't callable"""
        mock_response = MagicMock()
        mock_response.json = "not_callable"  # Not a method
        mock_response.content = b'{"fallback": "content"}'

        result = safe_to_json(mock_response)
        self.assertEqual(result, {"fallback": "content"})

    def test_object_with_only_content_attribute(self):
        """Test object with only content attribute"""
        # Test that content bytes work correctly
        content_bytes = (
            b'{"only_content": true}'  # Fixed: use valid JSON (lowercase true)
        )
        result = safe_to_json(content_bytes)
        self.assertEqual(result, {"only_content": True})

        # Also test that an object with content would work
        class ContentObject:
            def __init__(self):
                self.content = b'{"test_content": "works"}'

        obj = ContentObject()
        result = safe_to_json(obj)
        self.assertEqual(result, {"test_content": "works"})

    def test_object_with_only_text_attribute(self):
        """Test object with only text attribute"""
        # Test that text content works correctly with valid JSON
        text_string = '{"only_text": true}'  # Fixed: use valid JSON (lowercase true)
        result = safe_to_json(text_string)
        self.assertEqual(result, {"only_text": True})

        # Test that an object with text attribute works
        class TextObject:
            def __init__(self):
                self.text = '{"test_text": "works"}'

        obj = TextObject()
        result = safe_to_json(obj)
        self.assertEqual(result, {"test_text": "works"})

    def test_final_fallback_str_conversion(self):
        """Test final fallback using str() conversion"""

        # Create object that converts to valid JSON string
        class JsonObject:
            def __str__(self):
                return '{"fallback": "string"}'

        obj = JsonObject()
        result = safe_to_json(obj)
        self.assertEqual(result, {"fallback": "string"})

    def test_final_fallback_invalid_json_returns_empty_dict(self):
        """Test final fallback with invalid JSON returns empty dict"""

        # Object that converts to invalid JSON
        class InvalidJsonObject:
            def __str__(self):
                return "invalid json"

        obj = InvalidJsonObject()
        result = safe_to_json(obj)
        self.assertEqual(result, {})

    def test_final_fallback_unicode_error_returns_empty_dict(self):
        """Test final fallback with Unicode error returns empty dict"""

        # Mock str() to raise UnicodeDecodeError
        class UnicodeErrorObject:
            def __str__(self):
                raise UnicodeDecodeError("ascii", b"", 0, 1, "ordinal not in range")

        obj = UnicodeErrorObject()
        result = safe_to_json(obj)
        self.assertEqual(result, {})

    def test_integer_input_final_fallback(self):
        """Test integer input uses final fallback"""
        result = safe_to_json(123)
        self.assertEqual(result, 123)  # "123" is valid JSON (number)

    def test_list_input_final_fallback(self):
        """Test list input uses final fallback"""
        # List should be converted to string "[1, 2, 3]" which is valid JSON
        input_list = [1, 2, 3]
        result = safe_to_json(input_list)
        self.assertEqual(result, [1, 2, 3])

    def test_none_input_final_fallback(self):
        """Test None input uses final fallback"""
        result = safe_to_json(None)
        # str(None) = "None" which is not valid JSON, so returns {}
        self.assertEqual(result, {})

    def test_boolean_input_final_fallback(self):
        """Test boolean input uses final fallback"""
        result_true = safe_to_json(True)
        result_false = safe_to_json(False)

        # str(True) = "True" and str(False) = "False" are not valid JSON, so return {}
        self.assertEqual(result_true, {})
        self.assertEqual(result_false, {})

    def test_complex_nested_json_string(self):
        """Test complex nested JSON string"""
        complex_json = """
        {
            "users": [
                {"id": 1, "name": "John", "active": true},
                {"id": 2, "name": "Jane", "active": false}
            ],
            "metadata": {
                "total": 2,
                "page": 1
            }
        }
        """

        result = safe_to_json(complex_json)

        self.assertIsInstance(result, dict)
        self.assertIn("users", result)
        self.assertIn("metadata", result)
        self.assertEqual(len(result["users"]), 2)
        self.assertEqual(result["metadata"]["total"], 2)

    def test_json_with_unicode_characters(self):
        """Test JSON with Unicode characters"""
        unicode_json = '{"message": "Hello 世界", "emoji": "🌍"}'
        expected = {"message": "Hello 世界", "emoji": "🌍"}

        result = safe_to_json(unicode_json)
        self.assertEqual(result, expected)
