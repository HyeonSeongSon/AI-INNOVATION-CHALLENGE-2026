"""
Persona Pipeline API (port 8006)
텍스트/파일 기반 페르소나 생성 엔드포인트.
파일 업로드는 두 단계로 처리된다:
  1. POST /personas/create-from-file/upload  → job_id 즉시 반환
  2. GET  /personas/jobs/{job_id}/stream     → SSE 진행상황 스트리밍 (재연결 지원)
"""

import asyncio
import csv
import io
import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field, field_validator

from ..agents.shared.persona.generate_persona_and_query import (
    generate_structured_persona_info,
    generate_search_query,
)
from ..core.llm_factory import get_llm
from ..config.settings import settings, ALLOWED_MODEL_PREFIXES
from ..core.logging import get_logger
from ..core.auth import UserContext
from .deps import get_user_from_headers
from .upload_jobs import UploadJob, append_event, create_job, get_events_after, get_job

logger = get_logger("persona_pipeline")

router = APIRouter(prefix="/api/pipeline", tags=["Persona Pipeline"])



# ──────────────────────────────────────────────────────
# 단건 처리 (내부 공통 함수)
# ──────────────────────────────────────────────────────

async def _process_one_text(index: int, text: str, llm, persona_client, user_id: str | None = None) -> Dict[str, Any]:
    """단일 텍스트로 페르소나 생성 — register_personas_tool._process_one과 동일한 파이프라인"""
    try:
        messages = [HumanMessage(content=text)]
        structured_persona, raw_queries = await asyncio.gather(
            generate_structured_persona_info(messages, llm),
            generate_search_query(messages, llm),
        )
        persona_id = await persona_client.save_persona(structured_persona, user_id=user_id)
        try:
            await persona_client.save_product_search_query(persona_id, raw_queries, user_id=user_id)
        except Exception as original_exc:
            logger.warning("compensating_delete", index=index, persona_id=persona_id, error_type=type(original_exc).__name__)
            try:
                await persona_client.delete_persona(persona_id, user_id=user_id)
            except Exception:
                logger.error("compensating_delete_failed", index=index, persona_id=persona_id)
            raise original_exc
        return {
            "index": index,
            "success": True,
            "persona_id": persona_id,
            "name": structured_persona.get("name"),
        }
    except Exception as e:
        logger.error("persona_pipeline_record_failed", index=index, error_type=type(e).__name__)
        return {"index": index, "success": False, "error": "페르소나 생성 중 오류가 발생했습니다.", "name": None}


# ──────────────────────────────────────────────────────
# 파일 파싱
# ──────────────────────────────────────────────────────

def _parse_file_to_texts(filename: str, content: bytes) -> List[str]:
    name_lower = filename.lower()

    if name_lower.endswith(".csv"):
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = content.decode("euc-kr")
            except UnicodeDecodeError:
                raise ValueError("지원하지 않는 인코딩입니다. UTF-8 또는 EUC-KR을 사용해주세요.")
        text_io = io.StringIO(text)
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
                logger.warning("jsonl_parse_error", preview=line[:50])
                continue
        return texts

    if name_lower.endswith(".json"):
        try:
            data = json.loads(content.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError("JSON 파일 파싱 실패")
        if isinstance(data, list):
            return [json.dumps(item, ensure_ascii=False) for item in data]
        return [json.dumps(data, ensure_ascii=False)]

    raise ValueError(f"지원하지 않는 파일 형식: {filename} (CSV, JSON, JSONL만 허용)")


# ──────────────────────────────────────────────────────
# 백그라운드 워커
# ──────────────────────────────────────────────────────

async def _run_persona_job(
    job: UploadJob,
    texts: List[str],
    llm: Any,
    persona_client: Any,
    creator_user_id: str,
) -> None:
    """파일 내 모든 텍스트를 처리하고 결과를 job 이벤트 버퍼에 기록한다."""
    queue: asyncio.Queue = asyncio.Queue()
    semaphore = asyncio.Semaphore(settings.upload_persona_concurrency)
    chunk_size = settings.upload_persona_concurrency * 4
    active_tasks: list[asyncio.Task] = []

    async def process_and_enqueue(i: int, text: str) -> None:
        try:
            async with semaphore:
                result = await _process_one_text(i, text, llm, persona_client, user_id=creator_user_id)
        except Exception:
            logger.error("process_persona_text_failed", index=i, exc_info=True)
            result = {"success": False, "name": None, "error": "페르소나 생성 중 오류가 발생했습니다."}
        await queue.put(result)

    try:
        succeeded = 0
        failed = 0
        for chunk_start in range(0, len(texts), chunk_size):
            chunk = texts[chunk_start : chunk_start + chunk_size]
            active_tasks = [
                asyncio.create_task(process_and_enqueue(chunk_start + i, t))
                for i, t in enumerate(chunk)
            ]
            for _ in range(len(chunk)):
                result = await queue.get()
                if result["success"]:
                    succeeded += 1
                else:
                    failed += 1
                await append_event(job, {
                    "type": "progress",
                    "current": succeeded + failed,
                    "total": job.total,
                    "name": result.get("name"),
                    "success": result["success"],
                    "persona_id": result.get("persona_id"),
                    "error": result.get("error"),
                })
            await asyncio.gather(*active_tasks, return_exceptions=True)
            active_tasks = []

        logger.info(
            "create_personas_job_completed",
            job_id=job.job_id,
            total=job.total,
            succeeded=succeeded,
            failed=failed,
        )
        await append_event(job, {
            "type": "done",
            "total": job.total,
            "succeeded": succeeded,
            "failed": failed,
        })
    except Exception:
        logger.error("create_personas_job_failed", job_id=job.job_id, exc_info=True)
        await append_event(job, {
            "type": "error",
            "detail": "페르소나 생성 중 오류가 발생했습니다.",
        })
    finally:
        for task in active_tasks:
            task.cancel()
        if active_tasks:
            await asyncio.gather(*active_tasks, return_exceptions=True)


async def _guarded_run_persona_job(
    job: UploadJob,
    texts: list[str],
    llm: Any,
    persona_client: Any,
    creator_user_id: str,
) -> None:
    try:
        await asyncio.wait_for(
            _run_persona_job(job, texts, llm, persona_client, creator_user_id),
            timeout=settings.upload_job_max_seconds,
        )
    except asyncio.TimeoutError:
        logger.error(
            "persona_job_timed_out",
            job_id=job.job_id,
            timeout=settings.upload_job_max_seconds,
        )
        try:
            await append_event(job, {"type": "error", "detail": "페르소나 생성 시간이 초과됐습니다."})
        except Exception:
            logger.error("persona_job_status_update_failed", job_id=job.job_id)
    except Exception:
        logger.error("persona_job_outer_crashed", job_id=job.job_id, exc_info=True)
        try:
            await append_event(job, {"type": "error", "detail": "페르소나 생성 중 오류가 발생했습니다."})
        except Exception:
            logger.error("persona_job_status_update_failed", job_id=job.job_id)


# ──────────────────────────────────────────────────────
# SSE 스트림 제너레이터
# ──────────────────────────────────────────────────────

async def _stream_job_events(job: UploadJob):
    """
    재연결을 지원하는 SSE 이벤트 스트림 (PostgreSQL polling).
    Phase A: 기존 이벤트 즉시 replay → Phase B: 0.5초 간격으로 새 이벤트 polling.
    sse_keepalive_timeout초마다 keepalive 코멘트를 전송해 프록시 타임아웃을 방지한다.
    sse_stream_max_seconds 경과 시 error 이벤트를 전송하고 종료해 orphan 연결을 방지한다.
    """
    last_id = 0
    keepalive_ticks = 0
    keepalive_interval = max(1, int(settings.sse_keepalive_timeout / 0.5))
    first = True
    deadline = asyncio.get_event_loop().time() + settings.sse_stream_max_seconds

    while True:
        if asyncio.get_event_loop().time() >= deadline:
            yield f"data: {json.dumps({'type': 'error', 'detail': '스트림 최대 시간이 초과됐습니다.'}, ensure_ascii=False)}\n\n"
            return
        if not first:
            await asyncio.sleep(0.5)
        first = False

        event_rows = await get_events_after(job.job_id, after_id=last_id)
        if event_rows:
            for event_id, event in event_rows:
                last_id = event_id
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get("type") in ("done", "error"):
                    return
            keepalive_ticks = 0
        else:
            keepalive_ticks += 1
            if keepalive_ticks >= keepalive_interval:
                yield ": keepalive\n\n"
                keepalive_ticks = 0


# ──────────────────────────────────────────────────────
# 엔드포인트
# ──────────────────────────────────────────────────────

class CreateFromTextRequest(BaseModel):
    text: str = Field(..., max_length=50_000)
    model: Optional[str] = None

    @field_validator("model")
    @classmethod
    def validate_model(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not any(v.startswith(p) for p in ALLOWED_MODEL_PREFIXES):
            raise ValueError(f"지원하지 않는 모델명: {v}")
        return v


@router.post("/personas/create-from-text")
async def create_persona_from_text(
    request: CreateFromTextRequest,
    req: Request,
    current_user: UserContext = Depends(get_user_from_headers),
):
    """자유 텍스트 입력으로 페르소나 1개 생성"""
    persona_client = req.app.state.persona_client
    llm = get_llm(request.model or settings.chatgpt_model_name, temperature=settings.llm_temperature_persona)
    result = await _process_one_text(0, request.text, llm, persona_client, user_id=current_user.user_id)
    if not result["success"]:
        raise HTTPException(status_code=500, detail="페르소나 생성 중 오류가 발생했습니다.")
    return {
        "persona_id": result["persona_id"],
        "name": result["name"],
    }


@router.post("/personas/create-from-file/upload")
async def upload_personas_file(
    file: UploadFile = File(...),
    req: Request = None,
    current_user: UserContext = Depends(get_user_from_headers),
) -> Dict[str, Any]:
    """
    CSV / JSONL / JSON 파일을 업로드하고 백그라운드 처리를 시작한다.
    즉시 job_id를 반환하며, 진행상황은 /personas/jobs/{job_id}/stream 으로 수신한다.
    """
    try:
        content = await asyncio.wait_for(
            file.read(settings.max_upload_bytes + 1),
            timeout=settings.upload_file_read_timeout,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=408, detail="파일 읽기 시간이 초과되었습니다.")

    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="파일 크기는 50MB를 초과할 수 없습니다.")

    try:
        texts = await asyncio.wait_for(
            asyncio.to_thread(_parse_file_to_texts, file.filename or "", content),
            timeout=settings.upload_file_parse_timeout,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=408, detail="파일 파싱 시간이 초과되었습니다.")
    except ValueError:
        logger.warning("file_parse_failed", filename=file.filename)
        raise HTTPException(status_code=422, detail="파일 형식이 올바르지 않습니다.")

    if not texts:
        raise HTTPException(status_code=422, detail="파일에서 유효한 레코드를 찾을 수 없습니다.")

    if len(texts) > settings.max_records_per_upload:
        raise HTTPException(
            status_code=422,
            detail=f"레코드 수가 최대 허용치({settings.max_records_per_upload}개)를 초과합니다. 현재: {len(texts)}개",
        )

    llm = get_llm(settings.chatgpt_model_name, temperature=settings.llm_temperature_persona)
    persona_client = req.app.state.persona_client
    job = await create_job("persona", len(texts), creator_user_id=current_user.user_id)
    if job is None:
        raise HTTPException(
            status_code=409,
            detail="활성 업로드 작업이 너무 많습니다. 기존 작업이 완료된 후 다시 시도하세요.",
        )

    asyncio.create_task(
        _guarded_run_persona_job(job, texts, llm, persona_client, current_user.user_id)
    )

    return {"job_id": job.job_id, "total": job.total}


@router.get("/personas/jobs/{job_id}/stream")
async def stream_persona_job(
    job_id: str,
    req: Request = None,
    current_user: UserContext = Depends(get_user_from_headers),
) -> StreamingResponse:
    """job_id에 해당하는 파일 처리 진행상황을 SSE로 스트리밍한다. 재연결 시 처음부터 replay된다."""
    job = await get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    if job.job_type != "persona":
        raise HTTPException(status_code=400, detail="잘못된 작업 유형입니다.")
    if current_user.role != "admin" and job.creator_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")
    return StreamingResponse(
        _stream_job_events(job),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
