"""
v2 사람 확인 (축소, 약 30건) — 표본 추출과 확인 도구.

    python human_v2.py sample     # 층화 눈가림 표본 → result/main/human/{check_items.jsonl, sample_map.json}
    python human_v2.py serve      # 확인 도구(127.0.0.1:8769) — v1 check_tool 화면을 재사용, 정의는 주 지표 두 유형만

배분(PREREG_v2): v1 · v2 각 양성 8 · 재검토 3 · 음성 2, nofit 양성 4(모자라면 전부). 시드 20261009.
층은 주 지표 유형(특성어긋남 · 근거없는고민연결)만으로 계산한 LLM 판정(class_primary).
"""

import json
import random
import sys

import v2_common as vc
from gg_common import load_jsonl, write_jsonl

import grounding_def_v2 as gd  # noqa: E402

MAIN = vc.RESULT / "main"
HUMAN = MAIN / "human"
SEED = 20261009
TARGET = {"v1": {"양성": 8, "재검토": 3, "음성": 2}, "v2": {"양성": 8, "재검토": 3, "음성": 2}, "nofit": {"양성": 4}}


def sample() -> None:
    if (HUMAN / "sample_map.json").exists():
        raise SystemExit("이미 표본이 있습니다")
    rng = random.Random(SEED)
    chosen = []
    for cond, tgt in TARGET.items():
        meas = {r["item_id"]: r for r in load_jsonl(MAIN / cond / "measure.jsonl")}
        msgs = {r["item_id"]: r for r in load_jsonl(MAIN / cond / "messages.jsonl")}
        for stratum, k in tgt.items():
            pool = sorted(i for i, r in meas.items() if r["verifier"] and r["verifier"]["class_primary"] == stratum)
            pick = pool if len(pool) <= k else rng.sample(pool, k)
            chosen += [{"tag": cond, "item_id": i, "stratum": stratum, "msg": msgs[i]} for i in pick]
    rng.shuffle(chosen)
    HUMAN.mkdir(parents=True, exist_ok=True)
    mapping, rows = {}, []
    for n, c in enumerate(chosen, 1):
        code = f"P{n:03d}"
        mapping[code] = {"tag": c["tag"], "item_id": c["item_id"], "stratum": c["stratum"]}
        m = c["msg"]
        rows.append({"code": code, "purpose": m["purpose"], "brand": m["brand"], "persona_info": m["persona_info"],
                     "product_snapshot": m["product_snapshot"], "title": m["title"], "message": m["message"]})
    (HUMAN / "sample_map.json").write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    write_jsonl(HUMAN / "check_items.jsonl", rows)
    print(f"사람 확인 {len(rows)}건 → {HUMAN}")


def serve() -> None:
    import check_tool as ct  # v1 확인 도구(화면 · 저장 로직 재사용, 파일은 고치지 않음)
    ct.HUMAN, ct.ITEMS, ct.CSV_PATH, ct.BACKUP = HUMAN, HUMAN / "check_items.jsonl", HUMAN / "human_check.csv", HUMAN / "backup"
    ct.PORT = 8769
    # 화면의 정의를 주 지표 두 유형으로 바꾼다
    ct.gd.GROUNDING_DEF = gd.primary_definition_text()
    ct.gd.BOUNDARY_CASES = gd.BOUNDARY_CASES[6:11]
    sys.argv = [sys.argv[0]]
    ct.main()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    {"sample": sample, "serve": serve}[sys.argv[1]]()
