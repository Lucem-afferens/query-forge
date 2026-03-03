#!/usr/bin/env python3
"""
QueryForge — превращает «сырой» запрос в подзапросы для слабых моделей Cursor (Composer, Agent).

Принцип: сильная модель (Chat: Sonnet, Opus) понимает размытое; слабая (Composer, Agent) — нужны явные шаги.
Декомпозиция — через OpenAI (GPT-4o). Выполнение — в Composer/Agent.

Использование:
    python decompose.py "Хочу добавить подписку — месячная оплата, пробный период"
    echo "Рефакторинг auth модуля" | python decompose.py

Требует: OPENAI_API_KEY в окружении
"""

import json
import logging
import os
import sys
import time

logger = logging.getLogger(__name__)

# Лимиты для стабильности
API_TIMEOUT = 120
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2

SYSTEM_PROMPT = """Ты — эксперт по декомпозиции задач для слабых моделей Cursor (Composer, Agent).

Пользователь пишет запрос как для сильной модели (Chat: Sonnet, Opus, GPT-4) — свободно, с неявным контекстом. Слабые модели (Composer, Agent) быстрее и дешевле, но нуждаются в явных инструкциях. Твоя задача — разбить запрос на подзапросы, которые слабая модель выполнит по одному.

## Язык ответа

В начале сообщения пользователя указана инструкция по языку ([Язык ответа: ...] или [Response language: ...]). Строго следуй ей — весь текст в полях goal, reason, query, done_when, rollback_hint, expected_artifacts, verify_hint на указанном языке. Если инструкции нет — по умолчанию русский.

## Что Composer/Agent делает САМ (не разбивай и не уточняй это)

Composer/Agent автоматически:
- **Semantic search** — находит код по смыслу ("authentication flow" → находит auth-файлы). Не нужно перечислять файлы.
- **Grep** — ищет по точному тексту
- **Dynamic context discovery** — подтягивает контекст по мере работы, не требует всего заранее
- **Read files, Edit, Run terminal** — выполняет сам
- **Ask questions** — уточняет при неясности

Правило Cursor: "Если знаешь точный файл — укажи @. Если нет — Agent найдёт сам." Лишние @ путают.

## Типы задач (task_type)

Классифицируй задачу: Feature | Refactor | Infra | Bugfix | Review. Это влияет на план:
- **Feature** — новая функциональность (OAuth, платежи)
- **Refactor** — переработка кода без изменения поведения
- **Infra** — инфраструктура (Redis, миграции, CI)
- **Bugfix** — исправление бага
- **Review** — ревью кода, аудит, поиск багов/конфликтов по всему проекту

## Задача: Code Review (task_type: Review)

Если запрос про ревью, аудит, поиск багов/конфликтов по коду — это Review. **Всегда разбивай** (needs_decomposition: true): один запрос "проверь всё" приведёт к пропускам.

**Разбивка по модулям:** Обязательно используй контекст проекта (структура папок). Каждый composer_query — один модуль/слой с точным @path: @auth/, @services/, @api/, @frontend/components/ и т.д. Если контекста нет — разбей по типичным слоям (auth, api, services, db, frontend, config, tests). Ни один модуль не должен остаться без шага.

**Чеклист для каждого query:** Включай в текст запроса, что именно проверять. Слабая модель не догадается — укажи явно:
- **Безопасность:** SQL injection, XSS, секреты в коде, обход авторизации
- **Баги:** null/undefined, race conditions, необработанные исключения, утечки памяти
- **Производительность:** N+1 запросы, тяжёлые циклы, блокирующие операции
- **Конфликты:** merge conflicts, конфликты версий зависимостей, несовместимые API
- **Консистентность:** именование, паттерны, мёртвый код, дублирование
- **Тесты:** покрытие, граничные случаи, моки
- **Конфиг:** хардкод, env-переменные, секреты

**Формат вывода:** "Return Markdown report: file:line, severity (critical/high/medium/low), finding, fix suggestion."

**Пример query для Review:** "Review @backend/auth/ for: security (SQL injection, XSS, token handling), error handling, null checks. Return Markdown report: file:line, severity, finding, fix suggestion."

**expected_artifacts** для Review: "Markdown report with findings", "List of bugs with locations"

## Когда НЕ разбивать (модель справится одним запросом)

- **Исключение:** Review ("ревью всего кода", "найди баги везде") — всегда разбивай по модулям.
- Быстрые/знакомые задачи
- Чётко определённая задача с понятной областью
- Один или несколько связанных файлов
- Задача, где модель найдёт нужное через semantic search ("добавь кнопку логина", "рефакторинг auth")

В таких случаях: needs_decomposition: false, один элемент в composer_queries — готовый запрос как есть (возможно слегка уточнённый).

## Когда разбивать (модели нужна помощь)

- Архитектурно сложно (много систем, несколько подходов)
- Неясные требования (нужно исследование)
- Очень длинный горизонт (>10–15 шагов)
- Задача затрагивает много несвязанных модулей

## Формат подзапросов (query)

Каждый query — короткий, прямой, без лишнего. Composer/Agent лучше реагирует на инструкции, чем на разговорный стиль.

**Структура:** [Действие] + [Объект] + [Ограничение]. Глагол: refactor, optimize, fix, add, remove, review.
**Длина:** 1–3 предложения. Цель в одной строке.
**Без:** "please", "could you", "I hope" — только инструкции.

**Ограничение объёма** (добавляй когда уместно): minimal changes, return only diff, lightweight reasoning — меньше токенов, быстрее.
**Формат вывода** (если нужен): "Return only Git diff", "Return JSON", "Code block only, no explanation" — укажи явно.

**Не включать:** не вставляй код — Cursor читает файлы сам. Не объясняй архитектуру/стек — Composer/Agent видит проект. Не добавляй стиль/формат, если проект уже consistent.

**Пример хорошего query:** "Optimize @dbClient.ts queryUsers() for performance. Minimal changes, return only Git diff."

Отвечай в JSON:
{
  "analysis": {
    "goal": "итоговая цель",
    "task_type": "Feature|Refactor|Infra|Bugfix|Review",
    "needs_decomposition": true/false,
    "reason": "почему разбиваем или почему не разбиваем",
    "what_to_add_explicitly": ["что модель не найдёт сама и нужно указать явно"],
    "risks_covered": ["какие риски план покрывает: env, UI, тесты, миграции и т.д."],
    "missing_risks": ["какие риски могли бы быть, но не вошли в план (пустой массив если всё покрыто)"]
  },
  "composer_queries": [
    {
      "step": 1,
      "query": "Короткий прямой запрос: [Действие] [Объект] [Ограничение]. 1–3 предложения.",
      "context": "@path — только если в контексте проекта есть точный путь. Иначе пусто или null.",
      "done_when": "критерий готовности",
      "risk_level": "low|medium|high",
      "depends_on": [],
      "rollback_hint": "как откатить при ошибке",
      "expected_artifacts": ["новый файл X", "env ключ Y", "тест Z"],
      "verify_hint": "команда или действие для проверки: pytest path, grep KEY .env"
    }
  ]
}

Важно:
- Язык: следуй инструкции по языку в начале сообщения пользователя.
- query — коротко, по делу, без "please". Добавляй minimal changes / return only diff когда уместно. Для Review — включай чеклист (security, bugs, performance...) и формат отчёта в каждый query.
- needs_decomposition: false → один запрос в composer_queries, risks_covered и missing_risks всё равно заполни
- needs_decomposition: true → несколько запросов
- "context" — только ключевые @ из контекста проекта. Не перечисляй файлы "на всякий случай"
- depends_on — номера шагов, от которых зависит текущий (пустой массив для первого шага)
- expected_artifacts — конкретные артефакты (файлы, ключи, UI элементы), по которым можно проверить "появилось ли"
- verify_hint — как проверить шаг (команда, grep, проверка файла)
- Не дроби простые задачи: "добавь кнопку" не нужно разбивать на "изучи структуру" + "добавь кнопку".
- composer_queries — подзапросы для Composer/Agent в Cursor."""


def decompose(user_request: str, api_key: str | None = None, context: str | None = None, language: str = "ru") -> str:
    """Вызывает OpenAI для декомпозиции. Возвращает JSON или текст."""
    api_key = api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return _fallback_output(user_request)

    try:
        from openai import OpenAI
        from openai import APIConnectionError, APITimeoutError, RateLimitError
    except ImportError:
        return _fallback_output(user_request)

    from languages import get_language_instruction

    client = OpenAI(api_key=api_key)
    lang_instruction = get_language_instruction(language)
    user_content = f"[{lang_instruction}]\n\n{user_request}"
    if context and context.strip():
        user_content = (
            f"[{lang_instruction}]\n\n"
            "## Контекст проекта (используй для точных путей @):\n\n"
            f"{context.strip()}\n\n"
            "---\n\n"
            "## Запрос пользователя:\n\n"
            f"{user_request}"
        )

    response = None
    for attempt in range(MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                max_tokens=8192,
                timeout=API_TIMEOUT,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
            )
            break
        except (APIConnectionError, APITimeoutError, RateLimitError) as e:
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning("API error (attempt %d/%d): %s. Retry in %.1fs", attempt + 1, MAX_RETRIES, e, delay)
                time.sleep(delay)
            else:
                logger.error("API failed after %d attempts: %s", MAX_RETRIES, e)
                return _error_output(str(e))
        except Exception as e:
            err_str = str(e)
            if "403" in err_str and "unsupported_country_region_territory" in err_str:
                return _region_blocked_output()
            logger.exception("Unexpected error in decompose")
            return _error_output(err_str)

    if response is None:
        return _error_output("Не удалось получить ответ")

    # Проверка структуры ответа
    if not response.choices:
        return _error_output("Пустой ответ от API")
    msg = response.choices[0].message
    if not msg or not msg.content:
        return _error_output("Пустое содержимое ответа")

    text = msg.content.strip()
    if not text:
        return _error_output("Пустой текст в ответе")

    # Извлечение JSON из markdown code block
    if "```" in text:
        for part in text.split("```"):
            p = part.strip()
            if p.startswith("json"):
                text = p[4:].strip()
                break
            elif p.startswith("{"):
                text = p
                break

    try:
        data = json.loads(text)
        return json.dumps(data, ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
        return text


def _error_output(msg: str) -> str:
    """Сообщение об ошибке API."""
    return f"[QueryForge] Ошибка API: {msg}\n\nПроверь OPENAI_API_KEY и сетевое подключение."


def _region_blocked_output() -> str:
    """OpenAI блокирует доступ из региона."""
    return """[QueryForge] OpenAI не поддерживает API в твоём регионе (403 unsupported_country_region_territory).

Варианты:
1. **VPN** — подключись через VPN в поддерживаемую страну (США, ЕС и др.)
2. **Без API** — скопируй промпт из PROMPT_TEMPLATE.md в ChatGPT (GPT-4o), вставь запрос, получи план
3. **Прокси API** — используй прокси-сервис OpenAI (если есть)"""


def _fallback_output(user_request: str) -> str:
    """Вывод при отсутствии API."""
    return f"""
[QueryForge] OPENAI_API_KEY не задан.

Установи: pip install openai
Задай: export OPENAI_API_KEY="sk-..."

Альтернатива: скопируй промпт из PROMPT_TEMPLATE.md в ChatGPT (GPT-4o) и вставь свой запрос.
"""


def main():
    if len(sys.argv) > 1:
        request = " ".join(sys.argv[1:])
    elif not sys.stdin.isatty():
        request = sys.stdin.read().strip()
    else:
        print("Использование: python decompose.py \"твой запрос\"")
        print("          или: echo \"запрос\" | python decompose.py")
        sys.exit(1)

    if not request:
        print("Запрос пуст.")
        sys.exit(1)

    result = decompose(request)
    print(result)


if __name__ == "__main__":
    main()
