# 🔧 Улучшения API для расчёта зарплаты

## Проблема
Текущий API возвращает упрощённые данные, не отражающие сложность расчётов согласно израильскому трудовому законодательству.

## Предлагаемая структура ответа

### Расширенный ответ API `/api/v1/payroll/earnings/`

```json
{
  "employee": {
    "id": 1,
    "name": "Yosef Abramov",
    "email": "yosef.abramov@test.com", 
    "role": "employee"
  },
  "period": "monthly",
  "date": "2025-01-15",
  "calculation_type": "hourly",
  "currency": "ILS",
  
  "summary": {
    "total_gross_pay": 12450.00,
    "total_hours": 168.5,
    "worked_days": 21,
    "compensatory_days_earned": 2
  },
  
  "hours_breakdown": {
    "regular_hours": 144.0,
    "overtime": {
      "first_2h_per_day": 14.0,     // 125% rate
      "additional_hours": 8.5,       // 150% rate  
      "holiday_overtime": 0,         // 175% rate
      "sabbath_overtime": 2.0        // 175% rate
    },
    "special_days": {
      "holiday_hours": 8.0,          // 150% base rate
      "sabbath_hours": 12.0,         // 150% base rate
      "regular_friday_evening": 4.0  // After sunset
    }
  },
  
  "pay_breakdown": {
    "regular_pay": 5760.00,          // 144h * ₪40
    "overtime_pay": {
      "first_2h": 700.00,            // 14h * ₪50 (125%)
      "additional": 510.00,          // 8.5h * ₪60 (150%)
      "holiday_overtime": 0,         // 175%
      "sabbath_overtime": 140.00     // 2h * ₪70 (175%)
    },
    "special_day_pay": {
      "holiday_base": 480.00,        // 8h * ₪60 (150%)
      "sabbath_base": 720.00,        // 12h * ₪60 (150%)
      "friday_evening": 240.00       // 4h * ₪60 (150%)
    },
    "bonuses": {
      "attendance_bonus": 0,
      "performance_bonus": 0,
      "other_bonuses": 0
    },
    "minimum_wage_supplement": 0
  },
  
  "compensatory_days": {
    "earned_this_period": 2,
    "total_balance": {
      "unused_holiday": 3,
      "unused_sabbath": 5, 
      "total_unused": 8
    },
    "details": [
      {
        "date_earned": "2025-01-10",
        "reason": "holiday",
        "holiday_name": "Tu BiShvat",
        "is_used": false
      },
      {
        "date_earned": "2025-01-11", 
        "reason": "sabbath",
        "sabbath_start": "2025-01-10T16:26:22+02:00",
        "sabbath_end": "2025-01-11T17:30:15+02:00",
        "is_used": false
      }
    ]
  },
  
  "legal_compliance": {
    "violations": [],
    "warnings": [
      "Exceeded 10 hours on 2025-01-15"
    ],
    "weekly_overtime_status": {
      "current_week_overtime": 12.5,
      "max_allowed": 16.0,
      "remaining": 3.5
    }
  },
  
  "rates_applied": {
    "base_hourly": 40.00,
    "overtime_125": 50.00,
    "overtime_150": 60.00, 
    "overtime_175": 70.00,
    "overtime_200": 80.00,
    "holiday_base": 60.00,
    "sabbath_base": 60.00
  },
  
  "daily_breakdown": [
    {
      "date": "2025-01-01",
      "hours_worked": 8.0,
      "type": "regular",
      "gross_pay": 320.00,
      "breakdown": {
        "regular": 8.0
      }
    },
    {
      "date": "2025-01-10", 
      "hours_worked": 6.0,
      "type": "holiday",
      "holiday_name": "Tu BiShvat",
      "gross_pay": 360.00,
      "breakdown": {
        "holiday_base": 6.0
      },
      "compensatory_day": true
    },
    {
      "date": "2025-01-11",
      "hours_worked": 4.0, 
      "type": "sabbath",
      "sabbath_times": {
        "start": "2025-01-10T16:26:22+02:00",
        "end": "2025-01-11T17:30:15+02:00"
      },
      "gross_pay": 240.00,
      "breakdown": {
        "sabbath_base": 4.0
      },
      "compensatory_day": true
    }
  ],
  
  "attendance": {
    "working_days_in_period": 22,
    "days_worked": 21,
    "days_missed": 1,
    "attendance_rate": 95.45
  }
}
```

## Новые API endpoints

### 1. Детализация компенсационных дней
`GET /api/v1/payroll/compensatory-days/`
- Баланс использованных/неиспользованных дней
- История заработанных дней с причинами
- Возможность отметить день как использованный

### 2. Детализация нарушений
`GET /api/v1/payroll/compliance-report/`
- Превышения максимальных часов
- Недельные лимиты переработок  
- Рекомендации по соблюдению закона

### 3. Настройки ставок
`GET /api/v1/payroll/rates/`
- Текущие ставки для разных типов часов
- История изменений ставок
- Калькулятор для предварительного расчёта

## UI компоненты

### Карточка зарплаты
- **Основная сумма** с разбивкой по типам часов
- **Прогресс бар** недельных переработок  
- **Список заработанных компенсационных дней**
- **Предупреждения** о нарушениях

### Детальный отчёт
- **Календарь** с цветовой кодировкой дней
- **График переработок** по неделям
- **Список праздников и Шабатов** с точными временами

### Настройки
- **Уведомления** о работе в особые дни
- **Экспорт** данных в Excel/PDF
- **История** изменений зарплаты