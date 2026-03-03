"""
QueryForge — веб-сервер.
Запуск: uvicorn server:app --reload --host 0.0.0.0 --port 8000
"""

import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from decompose import decompose

logger = logging.getLogger(__name__)

app = FastAPI(title="QueryForge", version="1.0")

# Лимиты для стабильности
MAX_QUERY_LENGTH = 50_000
MAX_CONTEXT_LENGTH = 100_000

STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class DecomposeRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=MAX_QUERY_LENGTH)
    context: str | None = Field(None, max_length=MAX_CONTEXT_LENGTH)
    language: str = Field(default="ru", description="Код языка ISO 639-1 (ru, en, da, zh, ...)")
    api_key: str | None = Field(None, description="OpenAI API key (для облачной версии; локально — из .env)")


class DecomposeResponse(BaseModel):
    success: bool
    raw: str
    data: dict | None = None
    error: str | None = None


CONTEXT_FILE = Path(__file__).parent / "CONTEXT.md"
CONTEXT_TEMPLATE_FILE = Path(__file__).parent / "CONTEXT_TEMPLATE.md"
PROMPT_TEMPLATE_FILE = Path(__file__).parent / "PROMPT_TEMPLATE.md"
PLACEHOLDER = "[ВСТАВЬ СВОЙ ЗАПРОС СЮДА]"


def _extract_prompt_template() -> str:
    """Извлекает текст промпта между ``` из PROMPT_TEMPLATE.md."""
    if not PROMPT_TEMPLATE_FILE.exists():
        return ""
    try:
        text = PROMPT_TEMPLATE_FILE.read_text(encoding="utf-8")
        if "```" in text:
            for part in text.split("```"):
                p = part.strip()
                if PLACEHOLDER in p:
                    return p
        return text
    except OSError:
        return ""


@app.get("/api/languages")
async def get_languages():
    """Список языков (ISO 639-1) для переключателя и режим деплоя."""
    from languages import LANGUAGES
    return {
        "languages": [{"code": k, "name": v} for k, v in sorted(LANGUAGES.items(), key=lambda x: x[1])],
        "deployment": "vercel" if _is_vercel() else "local",
    }


@app.get("/api/prompt-template")
async def get_prompt_template():
    """Возвращает шаблон промпта для ChatGPT (без API)."""
    template = _extract_prompt_template()
    return {"template": template, "placeholder": PLACEHOLDER}


def _is_vercel() -> bool:
    """Проверка, что сервис запущен на Vercel."""
    return os.environ.get("VERCEL") == "1"


@app.get("/health")
async def health():
    """Проверка работоспособности сервиса."""
    return {
        "status": "ok",
        "service": "QueryForge",
        "deployment": "vercel" if _is_vercel() else "local",
    }


@app.get("/api/context-template")
async def get_context_template():
    """Возвращает шаблон CONTEXT_TEMPLATE.md для облачной версии."""
    if not CONTEXT_TEMPLATE_FILE.exists():
        return {"content": None}
    try:
        content = CONTEXT_TEMPLATE_FILE.read_text(encoding="utf-8")
        return {"content": content}
    except OSError as e:
        logger.warning("Cannot read CONTEXT_TEMPLATE.md: %s", e)
        return {"content": None}


@app.get("/api/context-file")
async def get_context_file():
    """Проверка наличия CONTEXT.md и его содержимое. На Vercel — всегда exists: false (нет доступа к файловой системе проекта)."""
    if _is_vercel():
        return {"exists": False, "content": None, "deployment": "vercel"}
    if not CONTEXT_FILE.exists():
        return {"exists": False, "content": None}
    try:
        content = CONTEXT_FILE.read_text(encoding="utf-8")
        return {"exists": True, "content": content}
    except OSError as e:
        logger.warning("Cannot read CONTEXT.md: %s", e)
        return {"exists": True, "content": None}


@app.get("/", response_class=HTMLResponse)
async def index():
    """Главная страница."""
    html_path = STATIC_DIR / "index.html"
    if html_path.exists():
        return FileResponse(html_path)
    return HTMLResponse("<h1>QueryForge</h1><p>Static files not found.</p>")


@app.post("/api/decompose", response_model=DecomposeResponse)
async def api_decompose(req: DecomposeRequest):
    """Декомпозиция запроса. Возвращает план подзапросов для Composer."""
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Запрос не может быть пустым")

    context = (req.context or "").strip() or None
    language = (req.language or "ru").strip().lower() or "ru"
    api_key = (req.api_key or "").strip() or None
    try:
        raw = decompose(query, api_key=api_key, context=context, language=language)
    except Exception as e:
        logger.exception("Decompose failed")
        return DecomposeResponse(
            success=False,
            raw="",
            data=None,
            error=f"[QueryForge] Внутренняя ошибка: {e}",
        )

    # Пытаемся распарсить JSON
    data = None
    error = None
    if raw.strip().startswith("{"):
        try:
            data = json.loads(raw)
            success = True
        except json.JSONDecodeError:
            success = True  # всё равно вернём raw
    elif "[QueryForge]" in raw or "Ошибка API" in raw:
        success = False
        error = raw.strip()
    else:
        success = True

    return DecomposeResponse(
        success=success,
        raw=raw,
        data=data,
        error=error,
    )
