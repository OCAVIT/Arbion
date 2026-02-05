# Руководство по тестированию AI-переговорщика Arbion

## Архитектура системы

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Telegram   │────>│   Parser     │────>│   Orders    │
│  Messages   │     │  (AI GPT)    │     │  (buy/sell) │
└─────────────┘     └──────────────┘     └──────┬──────┘
                                                │
                    ┌──────────────┐     ┌──────▼──────┐
                    │   Matcher    │<────│   Orders    │
                    │   Service    │     │   Match     │
                    └──────┬───────┘     └─────────────┘
                           │
                    ┌──────▼──────┐
                    │  Detected   │
                    │    Deal     │
                    │  (COLD)     │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │     AI      │  ──> Telegram сообщения продавцу
                    │ Negotiator  │  <── Ответы продавца
                    │(IN_PROGRESS)│
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │    WARM     │  ──> Готов для менеджера
                    │    Deal     │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Manager    │  ──> Панель менеджера
                    │  Assigned   │
                    └─────────────┘
```

## Статусы сделки (Deal Status)

| Статус | Описание |
|--------|----------|
| `COLD` | Сделка создана, AI ещё не связался с продавцом |
| `IN_PROGRESS` | AI ведёт переговоры с продавцом |
| `WARM` | Продавец заинтересован, готов для менеджера |
| `HANDED_TO_MANAGER` | Сделка передана менеджеру |
| `WON` | Сделка успешно закрыта |
| `LOST` | Сделка не состоялась |

---

## Шаг 1: Проверка Railway базы данных

### Проблема: База недоступна

Railway может "усыпить" неактивную базу. Проверь:

1. Открой [Railway Dashboard](https://railway.app/dashboard)
2. Выбери проект с PostgreSQL
3. Убедись, что сервис **запущен** (зелёная точка)
4. Проверь **Variables** → `DATABASE_URL`
5. Нажми **Connect** → проверь, что порт открыт

### Альтернатива: Локальная база

Если Railway недоступен, используй локальный PostgreSQL:

```bash
# Docker
docker run -d --name arbion-db \
  -e POSTGRES_USER=arbion \
  -e POSTGRES_PASSWORD=arbion123 \
  -e POSTGRES_DB=arbion \
  -p 5432:5432 \
  postgres:15

# Обнови .env
DATABASE_URL=postgresql+asyncpg://arbion:arbion123@localhost:5432/arbion
```

---

## Шаг 2: Настройка Telegram

### 2.1 Получи API credentials

1. Зайди на https://my.telegram.org/apps
2. Создай приложение
3. Скопируй `api_id` и `api_hash`

### 2.2 Получи Session String для бота

У тебя есть **2 аккаунта**:
- **Основной** (твой личный) - сюда бот будет писать
- **Бот** (отдельный аккаунт) - от имени которого работает AI

Для бота нужен session string:

```bash
# Установи переменные для бот-аккаунта
set TG_API_ID=твой_api_id
set TG_API_HASH=твой_api_hash
set TG_PHONE=+номер_бота

# Запусти скрипт
python scripts/get_telegram_id.py
```

Скрипт выведет:
- **User ID** бота
- **Session String** (сохрани в .env как `TG_SESSION_STRING`)
- Список чатов с их ID

### 2.3 Получи ID основного аккаунта

Повтори с основным аккаунтом (можно через @userinfobot в Telegram):
- Напиши `/start` боту @userinfobot
- Он покажет твой User ID

---

## Шаг 3: Конфигурация .env

```env
# Database
DATABASE_URL=postgresql+asyncpg://postgres:password@host:port/database

# Telegram (от бот-аккаунта!)
TG_API_ID=12345678
TG_API_HASH=abcdef1234567890
TG_SESSION_STRING=сессия_бот_аккаунта

# OpenAI (для AI-переговорщика)
OPENAI_API_KEY=sk-...

# Auth
SECRET_KEY=сгенерируй_случайный_ключ
OWNER_USERNAME=admin
OWNER_PASSWORD=твой_пароль
```

---

## Шаг 4: Миграции базы данных

```bash
# Применить миграции
cd e:\VibeProjects\Arbion
alembic upgrade head
```

---

## Шаг 5: Загрузка тестовых данных

```bash
# С Railway (когда заработает)
python scripts/seed_test_data.py \
  --main-id ТВОЙ_TELEGRAM_ID \
  --bot-id BOT_TELEGRAM_ID \
  --chat-id -100CHAT_ID

# Пример с реальными ID
python scripts/seed_test_data.py \
  --main-id 123456789 \
  --bot-id 987654321 \
  --chat-id -1001234567890
```

Скрипт создаст:
- Тестового менеджера: `test_manager` / `test123`
- 3 сделки: COLD, IN_PROGRESS, WARM
- Переговоры с тестовыми сообщениями

---

## Шаг 6: Тестирование чата между аккаунтами

### Запуск теста

```bash
python scripts/test_chat_flow.py --seller-id ТВОЙ_ОСНОВНОЙ_ID
```

Этот скрипт:
1. Подключится к Telegram от имени бота
2. Отправит тестовое сообщение на твой основной аккаунт
3. Будет слушать твои ответы
4. Автоматически ответит (симуляция AI)

### Что проверить:
- [ ] Бот успешно отправляет сообщение
- [ ] Ты получаешь сообщение на основном аккаунте
- [ ] Твой ответ доходит до бота
- [ ] Бот отвечает автоматически

---

## Шаг 7: Запуск полного приложения

```bash
# Запуск FastAPI + Telegram listener
uvicorn src.main:app --reload --port 8000
```

### Доступные панели:
- **Admin Panel**: http://localhost:8000/admin/
- **Manager Panel**: http://localhost:8000/panel/
- **API Docs**: http://localhost:8000/docs

---

## Шаг 8: Полный E2E тест

### Сценарий 1: Холодный лид → Тёплый

1. Создай COLD deal через seed script
2. Запусти приложение
3. Система отправит сообщение продавцу (твой основной аккаунт)
4. Ответь как продавец: "Да, актуально"
5. AI продолжит диалог
6. После нескольких сообщений deal станет WARM
7. Проверь в admin panel

### Сценарий 2: Менеджер берёт сделку

1. Войди в panel как `test_manager` / `test123`
2. Увидишь WARM сделки в списке
3. Возьми сделку в работу
4. Напиши сообщение продавцу через panel
5. Ответ продавца появится в чате

---

## Troubleshooting

### Railway база недоступна
```
OSError: [WinError 121] Превышен таймаут семафора
```
→ Проверь Railway dashboard, что сервис запущен

### Telegram "User not found"
```
ERROR: User 123456789 not found
```
→ Бот-аккаунт должен сначала "увидеть" пользователя (быть в общем чате или иметь диалог)

### OpenAI API error
```
openai.AuthenticationError
```
→ Проверь OPENAI_API_KEY в .env

### Миграции не применяются
```bash
# Проверь статус
alembic current

# Принудительно
alembic upgrade head --sql  # посмотреть SQL
alembic upgrade head        # применить
```

---

## Скрипты

| Скрипт | Описание |
|--------|----------|
| `scripts/check_db.py` | Проверка подключения к БД |
| `scripts/get_telegram_id.py` | Получение Telegram ID и session string |
| `scripts/seed_test_data.py` | Загрузка тестовых данных |
| `scripts/test_chat_flow.py` | Тест отправки/получения сообщений |
