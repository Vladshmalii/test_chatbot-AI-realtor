# AI Рієлтор Бот

Інтелектуальний Telegram-бот для пошуку нерухомості з підтримкою української мови, діалогового інтерфейсу та автоматичного парсингу параметрів пошуку.

## Основні можливості

- **Діалоговий збір параметрів** - бот ставить питання та розпізнає відповіді на природній мові
- **Парсинг складних запитів** - розуміє "Центр, до 50000, 2 кімнати, від 50м², останній поверх"
- **Збір імені користувача** - персоналізація спілкування
- **Управління фільтрами** - зміна параметрів на льоту
- **Запис на перегляд** - збір контактів та запис у Google Sheets
- **Історія діалогів** - повне логування у PostgreSQL

## Технології

- **Фреймворк**: aiogram 3.7+
- **База даних**: PostgreSQL + asyncpg + Alembic
- **Інтеграція**: Google Sheets API, зовнішній API нерухомості
- **Deployment**: Docker + docker-compose

## Структура проєкту

```
app/
├── bot/
│   ├── handlers.py      # Обробники повідомлень
│   ├── states.py        # FSM стани
│   └── loader.py        # Ініціалізація бота
├── core/
│   ├── config.py        # Налаштування
│   ├── sheets.py        # Google Sheets клієнт
│   ├── llm.py           # Парсинг природної мови
│   ├── rules.py         # Правила діалогу
│   ├── questions.py     # Потік питань
│   └── section_parser.py # Парсинг секцій
├── db/
│   ├── models.py        # SQLAlchemy моделі
│   ├── crud.py          # CRUD операції
│   └── base.py          # Налаштування БД
└── services/
    └── api_client.py    # HTTP клієнт для API нерухомості
```

## Встановлення

### Локальне середовище

1. **Клонувати репозиторій**
```bash
git clone <repo-url>
cd <project-dir>
```

2. **Створити `.env` файл**
```env
TELEGRAM_TOKEN=your_bot_token
DATABASE_URL=postgresql://user:password@localhost:5432/realtor
GOOGLE_SPREADSHEET_ID=your_spreadsheet_id
GOOGLE_SERVICE_ACCOUNT_FILE=./secrets/google_sa.json
LISTINGS_API_URL=https://api.example.com/listings
LISTINGS_API_KEY=your_api_key
LISTINGS_MEDIA_BASE=https://media.example.com/
LISTINGS_LIMIT=3
LISTINGS_OFFSET=0
SHEETS_CACHE_TTL=300
```

3. **Встановити залежності**
```bash
pip install -r requirements.txt
```

4. **Застосувати міграції**
```bash
alembic upgrade head
```

5. **Запустити бота**
```bash
python -m app.main
```

### Docker

1. **Налаштувати `.env` (як вище)**

2. **Додати Google Service Account JSON**
```bash
mkdir -p secrets
# Помістіть файл google_sa.json у ./secrets/
```

3. **Запустити**
```bash
docker compose up -d
```

## Google Sheets структура

### Таблиця `weclome_messages`
| key | text |
|-----|------|
| greeting | Вітальне повідомлення |
| instructions | Інструкції |
| example | Приклад запиту |
| ask_name | Як можу до вас звертатись? |

### Таблиця `bot_messages`
| key | text |
|-----|------|
| no_results | Нічого не знайдено |
| search_updated | Пошук оновлено |
| clarify_name | Вкажіть своє ім'я |
| ... | ... |

### Таблиця `questions`
| order | question_key | question_text |
|-------|--------------|---------------|
| 1 | district | У якому районі шукаєте? |
| 2 | rooms | Скільки кімнат? |
| 3 | state | У якому стані житло? |
| ... | ... | ... |

### Таблиця `filter_patterns`
| filter_key | pattern_type | pattern_text | value_min | value_max | value_list |
|------------|--------------|--------------|-----------|-----------|------------|
| floor | special | останній поверх,последний этаж | | | LAST |
| rooms | word | двокімнатна,двушка | | | 2 |
| ... | ... | ... | ... | ... | ... |

### Таблиця `districts`
| type | synonym | official_name | target_id |
|------|---------|---------------|-----------|
| district | центр | Центральний район | 1 |
| microarea | салтівка | Салтівка | 102 |
| street | сумська | вул. Сумська | 5001 |
| ... | ... | ... | ... |

### Таблиця `keywords`
| type | values |
|------|--------|
| viewing | перегляд,хочу подивитися,записатись |
| more | ще,більше,показати ще |
| new_search | новий пошук,спочатку,заново |
| skip_filter | пропустити,неважливо,без різниці |
| continue | продовжити,так,далі |

### Таблиця `objections`
| trigger | response | key |
|---------|----------|-----|
| дорого | Можу підібрати дешевше. Який бюджет? | price |
| далеко | У якому районі зручніше? | district |
| ... | ... | ... |

### Таблиця `viewings` (вихідна)
| timestamp | user_id | username | phone | name | listing_ids | listing_titles | filters |
|-----------|---------|----------|-------|------|-------------|----------------|---------|
| 2025-01-15 12:00 | 123456 | @user | +380... | Влад | 1001,1002 | Центр 2к 50м² | Район: Центр... |

## Приклади використання

### Простий запит
```
Користувач: Влад, Центр, до 50000, 2 кімнати
Бот: Приємно, Влад! У якому стані житло хочете?
```

### Складний запит
```
Користувач: 3к від 60м² до 30000 Салтівка останній поверх
Бот: [показує результати з фільтром floor_only_last=True]
```

### Зміна параметрів
```
Користувач: інший район
Бот: У якому районі шукаєте?
Користувач: Північна Салтівка
```

## Міграції Alembic

### Створити нову міграцію
```bash
alembic revision -m "add name field"
```

### Застосувати
```bash
alembic upgrade head
```

### Відкотити
```bash
alembic downgrade -1
```

## Логування

Логи зберігаються в:
- `stdout` (Docker)
- Console (локально)

Рівні логування:
- `INFO` - основні події
- `ERROR` - помилки

## Моніторинг

- **База даних**: всі діалоги, повідомлення, фільтри, запити API
- **Google Sheets**: заявки на перегляд, аналітика
- **Логи**: детальна інформація про парсинг та API

## Розробка

### Додати нове питання
1. Додати рядок у Google Sheets `questions`
2. Додати обробку у `llm.py` → `parse_to_filters()`
3. Оновити `questions.py` → `_key_mapping()`

### Додати новий паттерн
1. Додати рядок у Google Sheets `filter_patterns`
2. Обробка автоматично підхопиться через `_load_filter_patterns()`

### Додати новий район/вулицю
1. Додати рядок у Google Sheets `districts`
2. Перезапустити бота або викликати `reload_lookups()`

## Troubleshooting

### Бот не відповідає
- Перевірте `TELEGRAM_TOKEN`
- Перевірте логи: `docker compose logs bot`

### Не парсяться фільтри
- Перевірте Google Sheets з'єднання
- Перевірте формат таблиць `filter_patterns`, `districts`

### Помилка з БД
- Перевірте `DATABASE_URL`
- Застосуйте міграції: `alembic upgrade head`

### Не записується у Sheets
- Перевірте права Google Service Account
- Переконайтеся що таблиця `viewings` існує

## Ліцензія

Тестове завдання

## Автор

Vladshmalii