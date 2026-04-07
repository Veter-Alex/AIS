import json
import os
from typing import Any, Dict, List, Optional
from urllib import error, request

# LLM-сервис для AI-агента.
#
# Назначение модуля:
# 1) собрать структурированный prompt из retrieval-контекста;
# 2) запросить локальный Ollama runtime;
# 3) вернуть безопасный fallback-ответ, если провайдер недоступен.
#
# Принятый стиль комментариев:
# - короткие пояснения перед архитектурно важными блоками;
# - акцент на причины решений (почему так), а не на очевидный синтаксис.
DEFAULT_LLM_PROVIDER = os.getenv("LLM_PROVIDER", "mock")
DEFAULT_LLM_MODEL = os.getenv("LLM_MODEL", "llama3.2:3b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434").rstrip("/")
OLLAMA_TIMEOUT_SEC = int(os.getenv("OLLAMA_TIMEOUT_SEC", "120"))
OLLAMA_PULL_TIMEOUT_SEC = int(os.getenv("OLLAMA_PULL_TIMEOUT_SEC", "1800"))


class LlmProviderError(Exception):
    # Единый формат исключения для передачи корректного HTTP-кода наверх.
    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.status_code = status_code


def _normalize_provider(provider: Optional[str]) -> str:
    # Нормализуем провайдера к ограниченному набору допустимых значений.
    # Неизвестные значения переводим в mock для безопасного поведения по умолчанию.
    value = (provider or DEFAULT_LLM_PROVIDER).strip().lower()
    if value in {"mock", "ollama"}:
        return value
    return "mock"


def _clean_line(text: str) -> str:
    # Унифицируем строки контекста: убираем лишние переводы строк,
    # чтобы источник компактно отображался в prompt.
    return text.strip().replace("\n", " ")


def _extract_relevant_lines(
    content: str, question: str, max_lines: int = 3
) -> List[str]:
    # Локальный extractive-механизм:
    # - ищем строки, содержащие токены вопроса;
    # - если совпадений нет, берем первые информативные строки как fallback.
    q_tokens = {
        token.strip(" ,.:;!?()[]{}\"'").lower()
        for token in question.split()
        if token.strip()
    }
    lines = [line.strip() for line in content.splitlines() if line.strip()]

    hits: List[str] = []
    for line in lines:
        low = line.lower()
        if any(token and token in low for token in q_tokens):
            hits.append(_clean_line(line))
        if len(hits) >= max_lines:
            break

    if hits:
        return hits
    return [_clean_line(line) for line in lines[:max_lines]]


def _build_context_block(question: str, chunk: Dict[str, Any], index: int) -> str:
    # Строим компактный и структурированный блок контекста для LLM.
    title = str(chunk.get("title") or "Unknown vessel").strip()
    imo = str(chunk.get("document_imo") or "").strip()
    mmsi = str(chunk.get("document_mmsi") or "").strip()
    flag = str(chunk.get("document_flag") or "").strip()
    vessel_type = str(chunk.get("document_general_type") or "").strip()
    lines = _extract_relevant_lines(
        str(chunk.get("content") or ""), question, max_lines=4
    )

    header_parts = [f"title={title}"]
    if imo:
        header_parts.append(f"imo={imo}")
    if mmsi:
        header_parts.append(f"mmsi={mmsi}")
    if flag:
        header_parts.append(f"flag={flag}")
    if vessel_type:
        header_parts.append(f"type={vessel_type}")

    body = "\n".join(f"- {line}" for line in lines) if lines else "- Нет явных строк"
    return f"[Source {index}] " + "; ".join(header_parts) + "\n" + body


def _build_mock_answer(
    question: str, chunks: List[Dict[str, Any]], max_chars: int
) -> str:
    # Fallback-ответ без генеративной модели:
    # кратко агрегируем релевантные строки по найденным chunks.
    if not chunks:
        return (
            "Не нашел релевантный контекст в индексе chunks. "
            "Попробуйте уточнить запрос или расширить индексацию."
        )

    parts: List[str] = ["Найденный контекст по вашему вопросу:"]
    for idx, chunk in enumerate(chunks, start=1):
        title = str(chunk.get("title") or "Unknown vessel").strip()
        lines = _extract_relevant_lines(str(chunk.get("content") or ""), question)
        if not lines:
            continue
        parts.append(f"{idx}. {title}: " + " | ".join(lines))

    answer = "\n".join(parts).strip()
    if len(answer) > max_chars:
        answer = answer[: max_chars - 3].rstrip() + "..."
    return answer


def _build_rag_prompt(
    question: str, chunks: List[Dict[str, Any]], max_chars: int
) -> str:
    # Строим строгий prompt с ограничителями против галлюцинаций.
    # Контекст дается в формате [Source N], чтобы LLM мог ссылаться на источник.
    context_parts: List[str] = []
    for idx, chunk in enumerate(chunks, start=1):
        content = str(chunk.get("content") or "").strip()
        if not content:
            continue
        context_parts.append(
            _build_context_block(question=question, chunk=chunk, index=idx)
        )

    context_text = "\n\n".join(context_parts)
    prompt = (
        "Ты ассистент по базе AIS-судов. Отвечай только на основе контекста ниже.\n"
        "Правила ответа:\n"
        "1. Не выдумывай факты, которых нет в источниках.\n"
        "2. Если данных недостаточно, так и напиши: 'Недостаточно данных в источниках'.\n"
        "3. Если используешь факт, по возможности укажи источник в формате [Source N].\n"
        "4. Если источники противоречат друг другу, укажи это явно.\n"
        "5. Пиши кратко, конкретно и по-русски, без общих рассуждений.\n\n"
        f"Вопрос пользователя:\n{question}\n\n"
        f"Контекст:\n{context_text}\n\n"
        "Сформируй ответ максимум в 5 предложениях. Сначала дай прямой ответ, затем при необходимости 1-2 подтверждающих факта с указанием [Source N]."
    )
    if len(prompt) > max_chars * 6:
        prompt = prompt[: max_chars * 6]
    return prompt


def _call_ollama(prompt: str, model: str) -> str:
    # Синхронный вызов Ollama API /api/generate.
    # stream=False выбран для простоты интеграции с текущим HTTP-контрактом.
    payload = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2},
        }
    ).encode("utf-8")

    req = request.Request(
        url=f"{OLLAMA_BASE_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=OLLAMA_TIMEOUT_SEC) as resp:
        raw = resp.read().decode("utf-8")
    parsed = json.loads(raw)
    return str(parsed.get("response") or "").strip()


def _fetch_ollama_models() -> List[str]:
    # Получаем список установленных моделей из локального Ollama runtime.
    req = request.Request(
        url=f"{OLLAMA_BASE_URL}/api/tags",
        method="GET",
    )
    with request.urlopen(req, timeout=OLLAMA_TIMEOUT_SEC) as resp:
        raw = resp.read().decode("utf-8")

    parsed = json.loads(raw)
    models = parsed.get("models") or []
    names: List[str] = []
    for item in models:
        name = str(item.get("name") or "").strip()
        if name:
            names.append(name)
    return sorted(set(names))


def _fetch_ollama_models_info() -> List[Dict[str, Any]]:
    # Расширенная информация о моделях: размер, семейство, формат и квантование.
    req = request.Request(
        url=f"{OLLAMA_BASE_URL}/api/tags",
        method="GET",
    )
    with request.urlopen(req, timeout=OLLAMA_TIMEOUT_SEC) as resp:
        raw = resp.read().decode("utf-8")

    parsed = json.loads(raw)
    models = parsed.get("models") or []
    rows: List[Dict[str, Any]] = []
    for item in models:
        details = item.get("details") or {}
        name = str(item.get("name") or "").strip()
        if not name:
            continue

        rows.append(
            {
                "name": name,
                "size_bytes": int(item.get("size") or 0),
                "modified_at": item.get("modified_at"),
                "format": details.get("format"),
                "family": details.get("family"),
                "parameter_size": details.get("parameter_size"),
                "quantization_level": details.get("quantization_level"),
            }
        )

    rows.sort(key=lambda x: x["name"])
    return rows


def get_llm_runtime(provider: Optional[str] = None) -> Dict[str, Any]:
    # Возвращаем состояние runtime для UI/диагностики.
    # Здесь же вычисляем квантование сконфигурированной модели,
    # чтобы пользователь видел реальную загрузку ресурса (например Q4_K_M).
    provider_used = _normalize_provider(provider)
    runtime: Dict[str, Any] = {
        "provider": provider_used,
        "configured_model": DEFAULT_LLM_MODEL,
        "available_models": [],
        "available_models_info": [],
        "configured_model_quantization": None,
        "ollama_reachable": False,
        "error": None,
    }

    if provider_used != "ollama":
        return runtime

    try:
        models_info = _fetch_ollama_models_info()
        runtime["available_models_info"] = models_info
        runtime["available_models"] = [row["name"] for row in models_info]
        for row in models_info:
            if row["name"] == DEFAULT_LLM_MODEL:
                runtime["configured_model_quantization"] = row.get("quantization_level")
                break
        runtime["ollama_reachable"] = True
        return runtime
    except Exception as exc:
        runtime["error"] = str(exc)
        return runtime


def pull_ollama_model(model: str) -> Dict[str, Any]:
    # Загружаем или обновляем модель в локальном Ollama runtime.
    # stream=False позволяет дождаться итогового статуса одним ответом.
    model_name = (model or "").strip()
    if not model_name:
        raise ValueError("Model name must not be empty")

    payload = json.dumps(
        {
            "name": model_name,
            "stream": False,
        }
    ).encode("utf-8")

    req = request.Request(
        url=f"{OLLAMA_BASE_URL}/api/pull",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with request.urlopen(req, timeout=OLLAMA_PULL_TIMEOUT_SEC) as resp:
        raw = resp.read().decode("utf-8")

    parsed = json.loads(raw)
    return {
        "provider": "ollama",
        "model": model_name,
        "status": str(parsed.get("status") or "ok"),
        "detail": parsed,
    }


def delete_ollama_model(model: str) -> Dict[str, Any]:
    # Удаляем модель из локального Ollama runtime.
    model_name = (model or "").strip()
    if not model_name:
        raise ValueError("Model name must not be empty")

    payload = json.dumps({"name": model_name}).encode("utf-8")
    req = request.Request(
        url=f"{OLLAMA_BASE_URL}/api/delete",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="DELETE",
    )

    try:
        with request.urlopen(req, timeout=OLLAMA_TIMEOUT_SEC) as resp:
            raw = resp.read().decode("utf-8")
        parsed = json.loads(raw) if raw else {}
        return {
            "provider": "ollama",
            "model": model_name,
            "status": str(parsed.get("status") or "success"),
            "detail": parsed,
        }
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        message = raw.strip() or f"Ollama delete failed with status {exc.code}"
        if exc.code in {400, 404}:
            raise LlmProviderError(message=message, status_code=exc.code)
        raise LlmProviderError(message=message, status_code=500)


def generate_answer(
    question: str,
    chunks: List[Dict[str, Any]],
    max_chars: int = 1200,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, str]:
    # Оркестратор генерации:
    # 1) mock-режим для разработки/фолбэка;
    # 2) ollama-режим для локальной LLM;
    # 3) при любой ошибке безопасно откатываемся к extractive mock-ответу.
    provider_used = _normalize_provider(provider)
    model_used = (model or DEFAULT_LLM_MODEL).strip() or DEFAULT_LLM_MODEL

    if provider_used == "mock":
        return {
            "answer": _build_mock_answer(
                question=question, chunks=chunks, max_chars=max_chars
            ),
            "provider_used": provider_used,
            "model_used": model_used,
        }

    try:
        prompt = _build_rag_prompt(
            question=question, chunks=chunks, max_chars=max_chars
        )
        answer = _call_ollama(prompt=prompt, model=model_used)
        if not answer:
            answer = _build_mock_answer(
                question=question, chunks=chunks, max_chars=max_chars
            )
            provider_used = "mock"
        if len(answer) > max_chars:
            answer = answer[: max_chars - 3].rstrip() + "..."
        return {
            "answer": answer,
            "provider_used": provider_used,
            "model_used": model_used,
        }
    except Exception:
        return {
            "answer": _build_mock_answer(
                question=question, chunks=chunks, max_chars=max_chars
            ),
            "provider_used": "mock",
            "model_used": model_used,
        }
