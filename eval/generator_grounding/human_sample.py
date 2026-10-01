"""
사람 확인 표본 (7단계) — 보류 표본의 수정 전 · 후 메시지에서 층화 추출하고 눈가림 코드를 붙인다.

    python human_sample.py          # 첫 추출 → result/human/
    python human_sample.py --ext    # 9단계 확장 뒤: 첫 확인분은 두고, 합친 층의 모자라는 건수만 확장 표본에서 채운다

- 층: 조건(before · after) × LLM 판정(양성 · 재검토 · 음성)
- 건수: 양성 · 음성 각 10건(모자라면 전부), 재검토는 15건 이하면 전부 · 넘으면 15건. 시드 20261004.
- 눈가림
  - check_items.jsonl: 확인 도구가 읽는 파일. 코드 · 목적 · 페르소나 · 스냅숏 · 브랜드 · 제목 · 본문만 담는다.
  - sample_map.json: 코드 → 조건 · 항목 · 층. 확인 도구는 이 파일을 읽지 않는다(report.py 만 읽음).
  - 코드는 무작위 순서로 붙여, 순서로 조건을 알 수 없게 한다.
"""

import argparse
import json
import random
import sys
from collections import defaultdict

import gg_common as gg
from gg_common import load_jsonl, write_jsonl

SEED = 20261004
TARGET = {"양성": 10, "음성": 10, "재검토": 15}
HUMAN = gg.RESULT / "human"
MAP = HUMAN / "sample_map.json"
ITEMS = HUMAN / "check_items.jsonl"


def strata(set_name: str) -> dict[tuple[str, str], list[dict]]:
    out: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for tag in ("before", "after"):
        msgs = {m["item_id"]: m for m in load_jsonl(gg.RESULT / set_name / tag / "messages.jsonl")}
        for r in load_jsonl(gg.RESULT / set_name / tag / "measure.jsonl"):
            v = r.get("verifier")
            if not v:
                raise SystemExit(f"{set_name}/{tag}/{r['item_id']}: LLM 검증 결과가 없습니다")
            out[(tag, v["class"])].append({"set": set_name, "tag": tag, "item_id": r["item_id"],
                                           "stratum": v["class"], "msg": msgs[r["item_id"]]})
    for v in out.values():
        v.sort(key=lambda x: x["item_id"])
    return out


def pick(pool: list[dict], k: int, rng: random.Random) -> list[dict]:
    return list(pool) if len(pool) <= k else rng.sample(pool, k)


def blind_row(code: str, m: dict) -> dict:
    return {"code": code, "purpose": m["purpose"], "brand": m["brand"], "persona_info": m["persona_info"],
            "product_snapshot": m["product_snapshot"], "title": m["title"], "message": m["message"]}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--ext", action="store_true")
    a = ap.parse_args()
    HUMAN.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED + (1 if a.ext else 0))

    if not a.ext:
        if MAP.exists():
            raise SystemExit(f"{MAP} 이 이미 있습니다(덮어쓰지 않음)")
        chosen = []
        st = strata("holdout")
        for key in sorted(st):
            chosen += pick(st[key], TARGET[key[1]], rng)
        existing_map, existing_rows = {}, []
    else:
        existing_map = json.loads(MAP.read_text(encoding="utf-8"))
        existing_rows = load_jsonl(ITEMS)
        have = defaultdict(int)
        for m in existing_map.values():
            have[(m["tag"], m["stratum"])] += 1
        st = strata("holdout_ext")
        chosen = []
        for key in sorted(st):
            chosen += pick(st[key], max(0, TARGET[key[1]] - have[key]), rng)

    rng.shuffle(chosen)
    start = len(existing_map) + 1
    codes = [f"K{start + i:03d}" for i in range(len(chosen))]
    mapping = dict(existing_map)
    rows = list(existing_rows)
    for code, c in zip(codes, chosen):
        mapping[code] = {"set": c["set"], "tag": c["tag"], "item_id": c["item_id"], "stratum": c["stratum"]}
        rows.append(blind_row(code, c["msg"]))
    MAP.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    write_jsonl(ITEMS, rows)
    print(f"사람 확인 {len(rows)}건(이번 추가 {len(chosen)}건) → {ITEMS}")
    print("층별 건수는 확인이 끝난 뒤 report.py 에서 봅니다(눈가림).")


if __name__ == "__main__":
    main()
