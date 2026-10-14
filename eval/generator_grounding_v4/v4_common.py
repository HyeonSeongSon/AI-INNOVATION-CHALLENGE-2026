"""
생성기 근거 개선 V4 — 하네스 공통 경로.

v1 · v2 · v3 하네스의 모듈은 import 만 한다(잠긴 파일은 고치지 않는다). 기록은 v1 의 AMENDMENTS.md 사슬에 이어 쓴다.
예약 상품(v4_reserved_final_products.json, AMENDMENTS 21)은 최종 시험 전까지 열지 않는다 — 섞이면 바로 중단한다.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
V3 = HERE.parent / "generator_grounding_v3"
sys.path.insert(0, str(V3))

import v3_common as v3  # noqa: E402 — v1 · v2 경로도 함께 잡는다
from v3_common import gg, vc  # noqa: E402

RESULT = HERE / "result"
RESULT.mkdir(exist_ok=True)
STAGE0 = RESULT / "stage0"
V3_RESULT = V3 / "result"
RESERVED = V3 / "v4_reserved_final_products.json"

# 단계 0 · 1 에서 쓰는 저장된 결과(210 메시지: v3R N 70 + v3R F 70 + v0 F 70)
STORED = {
    "v3r_N": (V3_RESULT / "dev" / "v3r" / "messages.jsonl", V3_RESULT / "dev" / "v3r" / "measure.jsonl"),
    "v3r_F": (V3_RESULT / "final" / "final" / "messages.jsonl", V3_RESULT / "final" / "final" / "measure.jsonl"),
    "v0_F": (V3_RESULT / "final" / "v0" / "messages.jsonl", V3_RESULT / "final" / "v0" / "measure.jsonl"),
}


def load_jsonl(p: Path) -> list[dict]:
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(p: Path, rows: list[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def reserved_ids() -> set[str]:
    data = json.loads(RESERVED.read_text(encoding="utf-8"))
    return set(data["product_ids"] if isinstance(data, dict) else data)


def assert_not_reserved(product_ids) -> None:
    hit = set(product_ids) & reserved_ids()
    if hit:
        raise SystemExit(f"예약 상품이 섞였습니다({len(hit)}개) — V4 개발에는 쓰지 않는다(AMENDMENTS 21)")


def stored(key: str) -> tuple[dict[str, dict], dict[str, dict]]:
    """저장된 (messages, measure) 를 item_id 로 묶어 돌려준다."""
    mp, sp = STORED[key]
    msgs = {r["item_id"]: r for r in load_jsonl(mp)}
    meas = {r["item_id"]: r for r in load_jsonl(sp)}
    assert_not_reserved(r.get("product_id") or r["product_snapshot"].get("product_id") for r in msgs.values())
    return msgs, meas
