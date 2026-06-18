"""22차 부하테스트 — run_chat_stream_test.sh가 저장한 raw 결과를 summary.jsonl로 변환.

사용법:
    python parse_results.py <result_dir>

<result_dir>는 run_chat_stream_test.sh가 출력한 results/<RUN_ID> 디렉터리.
"""

import json
import re
import sys
from pathlib import Path
from typing import Optional

SSE_DATA_RE = re.compile(r"^data:\s*(.*)$")


def parse_sse_file(path: Path) -> dict:
    sse_done_seen = False
    result_status = None

    if not path.exists():
        return {"sse_done_seen": False, "result_status": None}

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = SSE_DATA_RE.match(line)
        if not match:
            continue
        payload = match.group(1).strip()
        if not payload:
            continue
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            continue

        event_type = event.get("type")
        if event_type == "done":
            sse_done_seen = True
        elif event_type == "result":
            result_status = event.get("status")

    return {"sse_done_seen": sse_done_seen, "result_status": result_status}


def parse_send_log_line(line: str) -> Optional[dict]:
    parts = line.strip().split()
    if len(parts) < 2:
        return None

    idx = int(parts[0])
    if parts[1].startswith("skip="):
        return {"idx": idx, "http_code": None, "ttfb_sec": None, "total_sec": None, "skip_reason": parts[1].split("=", 1)[1]}

    if len(parts) < 4:
        return {"idx": idx, "http_code": None, "ttfb_sec": None, "total_sec": None, "skip_reason": "malformed_send_log"}

    return {
        "idx": idx,
        "http_code": parts[1],
        "ttfb_sec": float(parts[2]),
        "total_sec": float(parts[3]),
        "skip_reason": None,
    }


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    result_dir = Path(sys.argv[1])
    send_log = result_dir / "send.log"
    sse_dir = result_dir / "sse"
    summary_path = result_dir / "summary.jsonl"

    if not send_log.exists():
        print(f"send.log를 찾을 수 없습니다: {send_log}")
        sys.exit(1)

    records = []
    for line in send_log.read_text(encoding="utf-8").splitlines():
        parsed = parse_send_log_line(line)
        if parsed is None:
            continue

        sse_info = {"sse_done_seen": False, "result_status": None}
        if parsed["skip_reason"] is None:
            sse_path = sse_dir / f"{parsed['idx']}.sse.log"
            sse_info = parse_sse_file(sse_path)

        records.append({**parsed, **sse_info})

    records.sort(key=lambda r: r["idx"])

    with summary_path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    total = len(records)
    http_200 = sum(1 for r in records if r["http_code"] == "200")
    completed = sum(1 for r in records if r["result_status"] == "completed")
    durations = sorted(r["total_sec"] for r in records if r["total_sec"] is not None)

    def percentile(data: list, p: float) -> Optional[float]:
        if not data:
            return None
        k = (len(data) - 1) * p
        f, c = int(k), min(int(k) + 1, len(data) - 1)
        return data[f] + (data[c] - data[f]) * (k - f)

    print(f"총 요청: {total}")
    print(f"HTTP 200: {http_200} ({http_200 / total * 100:.1f}%)" if total else "HTTP 200: 0")
    print(f"파이프라인 완료(status=completed): {completed} ({completed / total * 100:.1f}%)" if total else "")
    print(f"p50: {percentile(durations, 0.50)}")
    print(f"p99: {percentile(durations, 0.99)}")
    print(f"summary.jsonl 작성 완료: {summary_path}")


if __name__ == "__main__":
    main()
