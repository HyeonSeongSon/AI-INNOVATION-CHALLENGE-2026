"""
구성 필드 전수 점검 (2 · 3단계, Docker 불필요) — persona_fit 필드 분류표(product_fields.FIELD_CLASS)에 빠진 키가 0개인지.

    python field_census.py

키를 모으는 곳
- DB 시드 원본(database/seed_products.py 의 SOURCE_FILES)의 structured 키(시드가 빼는 _EXCLUDED_STRUCTURED_KEYS 제외)
  → 스냅숏에서 product_details 로 펼쳐지는 필드
- 원본 70 + 1라운드 보류 70 스냅숏의 키(테이블 열에서 온 필드 포함)
결과: result/field_census.json (빠진 키, 분류별 개수, 스냅숏 키가 시드 키 ∪ 테이블 열에 모두 드는지)
"""

import ast
import json
import sys
from collections import Counter

import v2_common as vc
from gg_common import load_jsonl

from app.agents.generate_message_agent.prompts.product_fields import FIELD_CLASS  # noqa: E402

SEED = vc.gg.REPO / "database" / "seed_products.py"
DATA = vc.gg.REPO / "data"


def seed_info() -> tuple[list[str], set[str]]:
    tree = ast.parse(SEED.read_text(encoding="utf-8"))
    files, excluded = [], set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = {getattr(t, "id", "") for t in node.targets}
            if "SOURCE_FILES" in names:
                files = list(ast.literal_eval(node.value))
            if "_EXCLUDED_STRUCTURED_KEYS" in names:
                excluded = set(ast.literal_eval(node.value))
    return files, excluded


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    files, excluded = seed_info()
    seed_keys: Counter = Counter()
    n = 0
    for fname in files:
        path = DATA / fname
        if not path.exists():
            raise SystemExit(f"시드 원본 없음: {path}")
        for line in open(path, encoding="utf-8"):
            if not line.strip():
                continue
            st = json.loads(line).get("structured")
            n += 1
            if isinstance(st, dict):
                seed_keys.update(k for k, v in st.items() if k not in excluded and v not in (None, "", [], {}))
    snap_keys: Counter = Counter()
    for src in (vc.gg.INSAMPLE_SOURCE, vc.gg.RESULT / "holdout" / "inputs.jsonl"):
        for r in load_jsonl(src):
            snap_keys.update(r["product_snapshot"].keys())
    table_cols = set(snap_keys) - set(seed_keys)
    all_keys = set(seed_keys) | set(snap_keys)
    missing = sorted(k for k in all_keys if k not in FIELD_CLASS)
    out = {"seed_records": n, "seed_structured_keys": len(seed_keys), "snapshot_keys": len(snap_keys),
           "table_columns_in_snapshot": sorted(table_cols), "missing_from_field_class": missing,
           "missing_with_counts": {k: seed_keys.get(k, 0) for k in missing},
           "class_counts": dict(Counter(FIELD_CLASS[k] for k in all_keys if k in FIELD_CLASS))}
    (vc.RESULT / "field_census.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"시드 레코드 {n} · structured 키 {len(seed_keys)} · 스냅숏 키 {len(snap_keys)} · 분류표에 빠진 키 {len(missing)}")
    if missing:
        print("빠진 키(시드 등장 수):", out["missing_with_counts"])
        raise SystemExit(1)


if __name__ == "__main__":
    main()
