# QueryForge

> Сервис для превращения «сырых» запросов (в стиле Sonnet) в подзапросы для Composer 1.5.

**Sonnet не используется.** Вся декомпозиция — через OpenAI. Выполнение — только Composer.

**Побочный эффект:** новички учатся — видят, как сырой запрос превращается в структурированный, привыкают к языку и формату, учатся экономить токены и не перегружать Cursor.

📄 **Подробное описание:** [SERVICE_OVERVIEW.md](SERVICE_OVERVIEW.md) — проблема, механизм, сравнение «с» и «без», надёжность, слабые места и направления роста.

## Быстрый старт

```bash
cp .env.example .env
# Отредактируй .env и вставь OPENAI_API_KEY=sk-...
touch CONTEXT.md   # обязателен перед первым docker compose (иначе монтирование упадёт)
docker compose up -d
```

Открой в браузере: **http://localhost:8001**

---

## Распаковка на другом проекте

Сервис автономен. Скопируй этот репозиторий в любой проект — больше ничего не нужно.

**Шаги:**

1. Скопировать папку `query-forge` (или клонировать репозиторий) в корень проекта.
2. Создать `.env` и вписать API-ключ:
   ```bash
   cp .env.example .env
   # Открыть .env и вставить: OPENAI_API_KEY=sk-...
   ```
3. Запустить: `docker compose up -d` (или `uvicorn server:app --host 0.0.0.0 --port 8000`).
4. Открыть http://localhost:8001 (Docker) или http://localhost:8000 (uvicorn)

**Опционально:** создать `CONTEXT.md` по шаблону `CONTEXT_TEMPLATE.md` — для более точных подзапросов. Без контекста сервис тоже работает. Перед первым `docker compose up` выполни `touch CONTEXT.md` (или `cp CONTEXT_TEMPLATE.md CONTEXT.md`) — иначе Docker создаст директорию вместо файла и контейнер не запустится.

---

## Проблема

- Ты пишешь запрос свободно, как для Sonnet — с неявным контекстом, без детализации
- Composer 1.5 требует явных указаний, разбиения на шаги, указания файлов
- Вручную переписывать каждый запрос — утомительно

## Решение

1. Ты даёшь запрос в своём стиле
2. **OpenAI** (GPT-4o) анализирует его, понимает, как Sonnet бы его разбил и что бы изучил
3. QueryForge выдаёт готовые подзапросы для Composer — с контекстом, порядком, критериями
4. Ты копируешь каждый подзапрос в Composer в условиях проекта
5. Composer выполняет

**Наблюдаемые эффекты:** меньше rollback, меньше повторных запросов, меньше hallucinated решений (когда Composer «придумывает» несуществующие файлы или паттерны).

## Использование

### Веб-интерфейс (Docker)

```bash
# Создать .env с API-ключом
cp .env.example .env
# Отредактируй .env и вставь OPENAI_API_KEY=sk-...
touch CONTEXT.md   # перед первым запуском

# Запуск
docker compose up -d

# Перезапуск (после изменений в коде)
docker compose down && docker compose build --no-cache && docker compose up -d

# Остановка
docker compose down
```

Открой в браузере: **http://localhost:8001** (порт задаётся в `docker-compose.yml`)

**Проверка работы:** `GET /health` — возвращает `{"status": "ok"}`. Docker использует это для healthcheck.

**Порт:** 8001 (внешний). Если 8000 свободен — в `docker-compose.yml` укажи `"8000:8000"`.

**Надёжность:** retry при сбоях API (3 попытки), timeout 120 с, лимиты ввода (запрос до 50k символов, контекст до 100k).

### Веб-интерфейс (локально)

```bash
pip install -r requirements.txt
cp .env.example .env
# Вставь OPENAI_API_KEY в .env

uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

### Деплой на Vercel (через GitHub)

1. Форкни или клонируй репозиторий.
2. Подключи репозиторий к [Vercel](https://vercel.com) (New Project → Import Git Repository).
3. Деплой — без дополнительной конфигурации. Vercel автоматически определит FastAPI.

**Особенности облачной версии:**

- **API-ключ:** вводится в поле интерфейса (хранится в localStorage браузера). На Vercel нет доступа к `.env` — ключ передаётся с каждым запросом.
- **Контекст:** `CONTEXT.md` не подтягивается автоматически. Вставь контекст вручную по структуре из `CONTEXT_TEMPLATE.md` (кнопка «CONTEXT_TEMPLATE.md» в секции контекста открывает шаблон).

### CLI

```bash
pip install -r requirements.txt
export OPENAI_API_KEY="sk-..."

python decompose.py "Хочу добавить подписку — месячная оплата, пробный период, отмена"
```

Вывод — JSON с `composer_queries`: готовые тексты для копирования в Composer.

### Без API (ChatGPT)

Если нет API-ключа — скопируй промпт из `PROMPT_TEMPLATE.md` в ChatGPT (GPT-4o), вставь свой запрос, получи план. Затем копируй подзапросы в Composer.

### Ошибка 403 (регион не поддерживается)

Если видишь `unsupported_country_region_territory` — OpenAI блокирует API в твоём регионе. Варианты: VPN, или используй `PROMPT_TEMPLATE.md` в ChatGPT без API.

## Архитектура

```
Твой запрос (стиль Sonnet)
         ↓
    [OpenAI GPT-4o]  ← декомпозиция, типы задач, риски, артефакты
         ↓
План: composer_queries[]
  - query, context, done_when
  - risk_level, rollback_hint, depends_on
  - expected_artifacts, verify_hint
         ↓
    [Composer 1.5]  ← выполнение в проекте, по одному запросу
```

## Формат вывода

```json
{
  "analysis": {
    "goal": "итоговая цель",
    "task_type": "Feature|Refactor|Infra|Bugfix",
    "needs_decomposition": true,
    "reason": "почему разбиваем или почему не разбиваем",
    "what_to_add_explicitly": ["что Composer не найдёт сам"],
    "risks_covered": ["env", "UI", "тесты"],
    "missing_risks": ["риски без декомпозиции"]
  },
  "composer_queries": [
    {
      "step": 1,
      "query": "Изучи структуру auth в @src/auth/ и добавь OAuth-провайдер Google",
      "context": "@src/auth/",
      "done_when": "OAuth-провайдер добавлен",
      "risk_level": "medium",
      "depends_on": [],
      "rollback_hint": "удалить добавленные файлы",
      "expected_artifacts": ["auth/google.py", "GOOGLE_CLIENT_ID в .env"],
      "verify_hint": "pytest auth/test_oauth.py"
    }
  ]
}
```

- **query** — готовый текст для Composer. Копируй и вставляй.
- **Auto-plan diff** — в веб-интерфейсе показывается сравнение «без декомпозиции» vs «с декомпозицией» и риски.
- **Демо** — кнопка «Демо (подписка)» показывает предзагруженный результат без вызова API (экономия токенов). Обновить ответ: `python decompose.py "демо-запрос"` и вставить JSON в `DEMO_RESPONSE` в `static/index.html`.

## Контекст проекта

Для более точных подзапросов загружай **контекст** — описание структуры, стека, ключевых файлов.

- **Локально / Docker:** кнопка «Загрузить CONTEXT.md» подставляет `CONTEXT.md` из папки сервиса.
- **Vercel (облако):** контекст не подтягивается автоматически — вставь вручную по структуре из `CONTEXT_TEMPLATE.md`.
- Или вставь текст вручную в любое время.

Создай `CONTEXT.md` по шаблону `CONTEXT_TEMPLATE.md`. Контекст сохраняется в браузере (localStorage).
