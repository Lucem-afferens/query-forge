# Контекст проекта (по документации Cursor)

Cursor называет **контекстом** всё, что модель видит: системный промпт, правила, @-упоминания файлов, историю чата. Composer/Agent получает контекст из:

- **Rules** (`.cursor/rules`, `AGENTS.md`) — инструкции в начале каждой сессии
- **@Files & Folders** — путь + обзор содержимого (большие файлы конденсируются)
- **@Code** — конкретные фрагменты кода
- **Semantic search** — Agent сам ищет по смыслу (grep + embeddings)
- **Открытые файлы** — что в табах редактора

Этот документ — то, что мы загружаем в QueryForge, чтобы он генерировал подзапросы с **реальными путями** и **@-упоминаниями** под твой проект.

---

## 1. Проект (базовое)

- **Название:** TeleCheck — персональный AI-слой интеллекта для Telegram
- **Стек:** Python (python-telegram-bot, Telethon/Pyrogram), Redis/RabbitMQ/Kafka, PostgreSQL/MongoDB, Elasticsearch/Pinecone, GPT/LLaMA/Mistral, RuBERT
- **Язык:** Python (бэкенд), русский + английский (контент)

## 2. Структура папок (для @Folders)

Укажи реальные пути. Composer использует @Folders — даёт путь и обзор содержимого.

**Текущая (проект в стадии Planning):**
```
telecheck/
  .cursor/               # правила к проекту
  README.md              # концепция, архитектура, стек, экономика AI
  query-forge/           # утилиты для Cursor (QueryForge, PROMPT_TEMPLATE)
```

**Планируемая (по README):**
```
backend/
  bot/                   # Bot API: команды, webhooks, клавиатуры
  user_api/              # MTProto: Telethon/Pyrogram, доступ к каналам
  queue/                 # очередь сообщений (Redis/RabbitMQ/Kafka)
  ai/                    # NLP-пайплайн: классификация, суммаризация, Q&A
  storage/               # PostgreSQL, MongoDB, vector search
frontend/
  mini_app/              # Web Apps для настроек, дашбордов, фильтров
```

## 3. Ключевые файлы (для @Files)

Файлы, которые стоит явно @-упоминать в подзапросе. Composer читает их целиком (или конденсирует, если большие).

- `README.md` — обзор, архитектура, стек, пользовательский сценарий, экономика AI, ссылки на Telegram API
- `query-forge/CONTEXT_CURSOR_REF.md` — справка по контексту Cursor
- `query-forge/requirements.txt` — зависимости QueryForge
- `query-forge/PROMPT_TEMPLATE.md` — шаблон промптов
- (по мере появления) `backend/bot/`, `backend/ai/` — логика Bot API и AI-пайплайн

## 4. Команды (как в Rules)

Agent знает npm, git, pytest — но не знает твои кастомные скрипты. Укажи:

- `python -m pytest` — тесты
- `uvicorn main:app` — запуск API (если применимо)
- Локальные скрипты для бота и очередей — по мере появления

## 5. Паттерны и канонические примеры

Как в Cursor Rules: **указывай на файлы, не копируй код**. Agent найдёт детали через semantic search.

- **Telegram Bot API:** команды `/start`, `/help`, `/settings`; webhooks vs long polling; [Privacy Mode](https://core.telegram.org/bots/features#privacy-mode)
- **AI-каскад:** keyword/embeddings → RuBERT/локальная модель → LLM по необходимости (см. раздел «Экономика AI» в README)
- **Интерфейс:** Inline-клавиатуры, Mini Apps, Chat and User Selection для подключения источников
- **Именование:** snake_case для Python

## 6. Текущий фокус

- **Статус:** Planning
- Над чем работаешь: архитектура, интеграция с Telegram, AI-пайплайн
- Какие модули затронуты: `backend/`, `README.md` (концепция и стек)
