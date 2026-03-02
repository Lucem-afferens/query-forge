"""
QueryForge — веб-сервер.
Запуск: uvicorn server:app --reload --host 0.0.0.0 --port 8000
"""

import json
import logging
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


class DecomposeResponse(BaseModel):
    success: bool
    raw: str
    data: dict | None = None
    error: str | None = None


CONTEXT_FILE = Path(__file__).parent / "CONTEXT.md"
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


@app.get("/api/prompt-template")
async def get_prompt_template():
    """Возвращает шаблон промпта для ChatGPT (без API)."""
    template = _extract_prompt_template()
    return {"template": template, "placeholder": PLACEHOLDER}


@app.get("/health")
async def health():
    """Проверка работоспособности сервиса."""
    return {"status": "ok", "service": "QueryForge"}


@app.get("/api/context-file")
async def get_context_file():
    """Проверка наличия CONTEXT.md и его содержимое."""
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
    try:
        raw = decompose(query, context=context)
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
