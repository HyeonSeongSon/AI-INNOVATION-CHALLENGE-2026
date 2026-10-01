"""
메시지 생성기 근거 개선 — 전후 비교 하네스 공통 경로 · 해시 · 입력 로더.

eval/quality_gate 의 모듈은 import 만 한다(그 폴더는 게이트 실험이 진행 중이라 고치지 않는다).
"""

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
QG = REPO / "eval" / "quality_gate"
RESULT = HERE / "result"
sys.path.insert(0, str(QG))
sys.path.insert(0, str(QG / "data"))

from _common import bootstrap, load_jsonl, write_jsonl  # noqa: E402

bootstrap()

PROMPTS_DIR = REPO / "backend" / "app" / "agents" / "generate_message_agent" / "prompts"
PURPOSE_PROMPT = PROMPTS_DIR / "purpose_prompt.py"
PRODUCT_FIELDS = PROMPTS_DIR / "product_fields.py"
GATE_FILES = [
    REPO / "backend" / "app" / "agents" / "generate_message_agent" / "services" / "quality_check.py",
    PROMPTS_DIR / "quality_check_prompt.py",
    PROMPTS_DIR / "apply_feedback_prompt.py",
    REPO / "backend" / "app" / "agents" / "generate_message_agent" / "nodes.py",
]
PREREG_FILES = [HERE / "grounding_def.py", HERE / "measure.py", HERE / "report.py", HERE / "PREREG.md"]
BASELINE = HERE / "baseline_hashes.json"
AMENDMENTS = HERE / "AMENDMENTS.md"
INSAMPLE_SOURCE = QG / "result" / "main" / "originals.jsonl"
SETS = ("holdout", "holdout_ext", "insample")  # holdout_ext: 9단계 확장 표본(1회)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_hashes(paths: list[Path]) -> dict[str, str | None]:
    return {str(p.relative_to(REPO)).replace("\\", "/"): (sha256(p) if p.exists() else None) for p in paths}


def load_baseline() -> dict[str, Any]:
    if not BASELINE.exists():
        raise SystemExit(f"{BASELINE.name} 없음 — baseline.py 를 먼저 돌린다")
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def set_dir(set_name: str) -> Path:
    if set_name not in SETS:
        raise SystemExit(f"--set 은 {SETS} 중 하나")
    path = RESULT / set_name
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_inputs(set_name: str) -> list[dict[str, Any]]:
    """표본 입력: item_id · persona_id · persona_info · purpose · brand · product_snapshot."""
    if set_name == "insample":
        rows = load_jsonl(INSAMPLE_SOURCE)
        return [{"item_id": o["original_id"], "persona_id": o["persona_id"], "persona_info": o["persona_info"],
                 "purpose": o["purpose"], "brand": o["brand"], "product_snapshot": o["product_snapshot"]}
                for o in sorted(rows, key=lambda x: x["original_id"])]
    path = set_dir(set_name) / "inputs.jsonl"
    if not path.exists():
        raise SystemExit(f"{path} 없음 — sample_holdout.py 를 먼저 돌린다")
    return load_jsonl(path)


def amendments_entries() -> list[dict[str, Any]]:
    """AMENDMENTS.md 의 항목(JSON 줄)을 읽고 사슬(prev_hash)을 확인한다."""
    if not AMENDMENTS.exists():
        return []
    entries = []
    prev = "GENESIS"
    for line in AMENDMENTS.read_text(encoding="utf-8").splitlines():
        if not line.startswith("- `{"):
            continue
        raw = line[3:-1]
        entry = json.loads(raw)
        if entry.get("prev_hash") != prev:
            raise SystemExit(f"AMENDMENTS.md 사슬이 끊겼습니다: {entry.get('id')}")
        prev = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        entries.append(entry)
    return entries


def append_amendment(kind: str, content: str, new_hashes: dict[str, str] | None = None) -> dict[str, Any]:
    """AMENDMENTS.md 에 추가만 한다. 각 항목은 이전 항목(JSON 문자열)의 sha256 을 담는다."""
    from datetime import datetime, timezone
    entries = amendments_entries()
    prev = "GENESIS"
    if entries:
        last_raw = json.dumps(entries[-1], ensure_ascii=False, sort_keys=True)
        prev = hashlib.sha256(last_raw.encode("utf-8")).hexdigest()
    entry = {"id": len(entries) + 1, "at": datetime.now(timezone.utc).isoformat(), "kind": kind,
             "content": content, "new_hashes": new_hashes or {}, "prev_hash": prev}
    raw = json.dumps(entry, ensure_ascii=False, sort_keys=True)
    if not AMENDMENTS.exists():
        AMENDMENTS.write_text("# AMENDMENTS — 잠금 뒤 기록 (추가만 가능, 각 항목은 이전 항목의 sha256 을 담는다)\n\n",
                              encoding="utf-8")
    with open(AMENDMENTS, "a", encoding="utf-8") as f:
        f.write(f"- `{raw}`\n")
    return entry


def prereg_status() -> dict[str, Any]:
    """사전 등록 파일 해시를 기준과 대조한다. 다르면 AMENDMENTS 에 그 해시가 있는지 본다."""
    base = load_baseline()
    now = file_hashes(PREREG_FILES)
    amended = {k: v for e in amendments_entries() for k, v in e.get("new_hashes", {}).items()}
    status = {}
    for k, v in now.items():
        b = base["prereg"].get(k)
        if v == b:
            status[k] = "기준과 같음"
        elif amended.get(k) == v:
            status[k] = "AMENDMENTS 에 기록된 수정"
        else:
            status[k] = "기록 없는 변경(탐색적)"
    return {"files": now, "status": status}
