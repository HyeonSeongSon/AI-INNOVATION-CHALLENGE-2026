"""
Persona Pipeline API (port 8005)
텍스트/파일 기반 페르소나 생성 엔드포인트.
bulk_persona_node의 _process_one 로직을 HTTP API로 노출한다.
"""

import asyncio
import csv
import io
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from ..agents.marketing_assistant.services.generate_persona_and_query import (
    generate_structured_persona_info,
    generate_search_query,
)
from ..agents.marketing_assistant.services.persona_client import PersonaClient
from ..core.llm_factory import get_llm
from ..config.settings import settings
from ..core.logging import get_logger

logger = get_logger("persona_pipeline")

router = APIRouter(prefix="/api/pipeline", tags=["Persona Pipeline"])

_persona_client = PersonaClient()


# ──────────────────────────────────────────────────────
# 단건 처리 (내부 공통 함수)
# ──────────────────────────────────────────────────────

async def _process_one_text(index: int, text: str, llm) -> Dict[str, Any]:
    """단일 텍스트로 페르소나 생성 — bulk_persona_node._process_one과 동일한 파이프라인"""
    try:
        messages = [HumanMessage(content=text)]
        structured_persona = await generate_structured_persona_info(messages, llm)
        persona_id = await _persona_client.save_persona(structured_persona)
        raw_queries = await generate_search_query(messages, llm)
        await _persona_client.save_product_search_query(persona_id, raw_queries)
        return {
            "index": index,
            "success": True,
            "persona_id": persona_id,
            "name": structured_persona.get("name"),
        }
    except Exception as e:
        logger.error("persona_pipeline_record_failed", index=index, error=str(e))
        return {"index": index, "success": False, "error": str(e), "name": None}


# ──────────────────────────────────────────────────────
# 파일 파싱 (database pipeline_router의 _parse_file_to_texts와 동일)
# ──────────────────────────────────────────────────────

def _parse_file_to_texts(filename: str, content: bytes) -> List[str]:
    name_lower = filename.lower()

    if name_lower.endswith(".csv"):
        text_io = io.StringIO(content.decode("utf-8-sig"))
        reader = csv.DictReader(text_io)
        texts = []
        for row in reader:
            texts.append(", ".join(f"{k}: {v}" for k, v in row.items() if v))
        return texts

    if name_lower.endswith(".jsonl"):
        texts = []
        for line in content.decode("utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                texts.append(json.dumps(obj, ensure_ascii=False))
            except json.JSONDecodeError:
                texts.append(line)
        return texts

    if name_lower.endswith(".json"):
        data = json.loads(content.decode("utf-8"))
        if isinstance(data, list):
            return [json.dumps(item, ensure_ascii=False) for item in data]
        return [json.dumps(data, ensure_ascii=False)]

    raise ValueError(f"지원하지 않는 파일 형식: {filename} (CSV, JSON, JSONL만 허용)")


# ──────────────────────────────────────────────────────
# 엔드포인트
# ──────────────────────────────────────────────────────

class CreateFromTextRequest(BaseModel):
    text: str
    model: Optional[str] = None


@router.post("/personas/create-from-text")
async def create_persona_from_text(request: CreateFromTextRequest):
    """자유 텍스트 입력으로 페르소나 1개 생성"""
    llm = get_llm(request.model or settings.chatgpt_model_name, temperature=0.3)
    result = await _process_one_text(0, request.text, llm)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("error", "페르소나 생성 실패"))
    return {
        "persona_id": result["persona_id"],
        "name": result["name"],
    }


@router.post("/personas/create-from-file")
async def create_personas_from_file(file: UploadFile = File(...)):
    """
    CSV / JSONL / JSON 파일 업로드로 페르소나 일괄 생성 (SSE 스트리밍)

    진행 이벤트: {"type":"progress","current":N,"total":N,"name":"...","success":bool,"persona_id":"...","error":"..."}
    완료 이벤트: {"type":"done","total":N,"succeeded":N,"failed":N}
    오류 이벤트: {"type":"error","detail":"..."}
    """
    content = await file.read()

    try:
        texts = _parse_file_to_texts(file.filename or "", content)
    except ValueError as e:
        async def error_stream():
            yield f"data: {json.dumps({'type': 'error', 'detail': str(e)}, ensure_ascii=False)}\n\n"
        return StreamingResponse(error_stream(), media_type="text/event-stream")

    if not texts:
        async def empty_stream():
            yield f"data: {json.dumps({'type': 'error', 'detail': '파일에서 유효한 레코드를 찾을 수 없습니다.'}, ensure_ascii=False)}\n\n"
        return StreamingResponse(empty_stream(), media_type="text/event-stream")

    total = len(texts)
    llm = get_llm(settings.chatgpt_model_name, temperature=0.3)

    async def generate():
        queue: asyncio.Queue = asyncio.Queue()
        semaphore = asyncio.Semaphore(5)

        async def process_and_enqueue(i: int, text: str):
            async with semaphore:
                result = await _process_one_text(i, text, llm)
            await queue.put(result)

        tasks = [asyncio.create_task(process_and_enqueue(i, t)) for i, t in enumerate(texts)]

        succeeded = 0
        failed = 0
        for _ in range(total):
            result = await queue.get()
            if result["success"]:
                succeeded += 1
            else:
                failed += 1
            event = {
                "type": "progress",
                "current": succeeded + failed,
                "total": total,
                "name": result.get("name"),
                "success": result["success"],
                "persona_id": result.get("persona_id"),
                "error": result.get("error"),
            }
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        await asyncio.gather(*tasks, return_exceptions=True)

        logger.info(
            "create_personas_from_file_completed",
            filename=file.filename,
            total=total,
            succeeded=succeeded,
            failed=failed,
        )
        yield f"data: {json.dumps({'type': 'done', 'total': total, 'succeeded': succeeded, 'failed': failed}, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
