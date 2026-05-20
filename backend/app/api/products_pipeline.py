"""
Products Pipeline API (port 8005)
파일 업로드 → 상품 일괄 등록 SSE 스트리밍
ProductRegistrationService를 직접 호출하여 8020 경유 없이 처리한다.
"""

import asyncio
import csv
import io
import json

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from typing import Any, Dict, List

from ..core.logging import get_logger

logger = get_logger("products_pipeline")

router = APIRouter(prefix="/api/pipeline", tags=["Products Pipeline"])

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50MB


# ──────────────────────────────────────────────────────
# 파일 파싱
# ──────────────────────────────────────────────────────

def _parse_image_field(value: Any) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return []
        if value.startswith("["):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                pass
        return [u.strip() for u in value.split(",") if u.strip()]
    return []


def _normalize_record(record: Dict[str, Any]) -> Dict[str, Any]:
    for key in ("상품상세_이미지", "상품이미지", "image_urls"):
        if key in record:
            record[key] = _parse_image_field(record[key])
    return record


def _parse_file_to_records(filename: str, content: bytes) -> List[Dict[str, Any]]:
    name_lower = filename.lower()

    if name_lower.endswith(".jsonl"):
        records = []
        skipped = 0
        for line_no, raw in enumerate(content.decode("utf-8").splitlines(), start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                skipped += 1
                logger.warning(
                    "jsonl_parse_error",
                    filename=filename,
                    line_no=line_no,
                    preview=line[:50],
                    error=str(exc),
                )
        if skipped:
            logger.warning(
                "jsonl_lines_skipped",
                filename=filename,
                skipped=skipped,
                parsed=len(records),
            )
        return records

    if name_lower.endswith(".csv"):
        text_io = io.StringIO(content.decode("utf-8-sig"))
        reader = csv.DictReader(text_io)
        return [_normalize_record(dict(row)) for row in reader]

    if name_lower.endswith(".xlsx"):
        try:
            import openpyxl
        except ImportError as e:
            raise ValueError("XLSX 처리를 위해 openpyxl 패키지가 필요합니다: pip install openpyxl") from e
        wb = openpyxl.load_workbook(io.BytesIO(content))
        ws = wb.active
        headers = [cell.value for cell in ws[1]]
        records = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            record = {k: v for k, v in zip(headers, row) if k is not None}
            records.append(_normalize_record(record))
        return records

    raise ValueError(f"지원하지 않는 파일 형식: {filename} (JSONL, CSV, XLSX만 허용)")


# ──────────────────────────────────────────────────────
# SSE 엔드포인트
# ──────────────────────────────────────────────────────

@router.post("/products/register")
async def register_products_from_file(file: UploadFile = File(...), request: Request = None):
    """
    JSONL / CSV / XLSX 파일 업로드로 상품 일괄 등록 (SSE 스트리밍)

    진행 이벤트: {"type":"progress","current":N,"total":N,"name":"...","success":bool,"product_id":"...","error":"..."}
    완료 이벤트: {"type":"done","total":N,"succeeded":N,"failed":N}
    오류 이벤트: {"type":"error","detail":"..."}
    """
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="파일 크기는 50MB를 초과할 수 없습니다.")

    try:
        records = _parse_file_to_records(file.filename or "", content)
    except ValueError as e:
        async def error_stream():
            yield f"data: {json.dumps({'type': 'error', 'detail': str(e)}, ensure_ascii=False)}\n\n"
        return StreamingResponse(error_stream(), media_type="text/event-stream")

    if not records:
        async def empty_stream():
            yield f"data: {json.dumps({'type': 'error', 'detail': '파일에서 유효한 레코드를 찾을 수 없습니다.'}, ensure_ascii=False)}\n\n"
        return StreamingResponse(empty_stream(), media_type="text/event-stream")

    total = len(records)
    service = request.app.state.registration

    async def generate():
        queue: asyncio.Queue = asyncio.Queue()
        semaphore = asyncio.Semaphore(3)

        async def process_and_enqueue(record: dict):
            try:
                async with semaphore:
                    result = await service.register_product(record)
            except Exception as e:
                result = {
                    "success": False,
                    "product_name": record.get("product_name"),
                    "error": str(e),
                }
            await queue.put(result)

        tasks = [asyncio.create_task(process_and_enqueue(r)) for r in records]

        try:
            succeeded = 0
            failed = 0
            for _ in range(total):
                result = await queue.get()
                if result.get("success"):
                    succeeded += 1
                else:
                    failed += 1
                event = {
                    "type": "progress",
                    "current": succeeded + failed,
                    "total": total,
                    "name": result.get("product_name"),
                    "success": result.get("success", False),
                    "product_id": result.get("product_id"),
                    "error": result.get("error"),
                }
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            await asyncio.gather(*tasks, return_exceptions=True)

            logger.info(
                "register_products_completed",
                filename=file.filename,
                total=total,
                succeeded=succeeded,
                failed=failed,
            )
            yield f"data: {json.dumps({'type': 'done', 'total': total, 'succeeded': succeeded, 'failed': failed}, ensure_ascii=False)}\n\n"
        finally:
            for task in tasks:
                task.cancel()
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            except asyncio.CancelledError:
                pass

    return StreamingResponse(generate(), media_type="text/event-stream")
