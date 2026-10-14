"""
풀 기반 채점을 위한 페르소나 단위 dev/heldout 분할.

기존 result/split.json 은 아이템 단위(persona_id, product_tag, product_id, rank)
4-tuple 분할이라 compare_v4.py --subset 이 계속 쓴다 — 건드리지 않는다.

풀 기반 NDCG@K는 한 페르소나의 풀 전체가 같은 분할에 있어야 하므로(아이템 단위로
쪼개면 리키지 + NDCG@K 자체가 정의 불가) 페르소나 단위로 새로 나눈다. product_tag로
층화한다 — 채점 라벨이 없어도(즉 채점 전에도) 바로 계산 가능하다.

사용법:
    python make_pool_split.py
    python make_pool_split.py --seed 7
"""

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).parent
RESULT_DIR = BASE_DIR / "result"
PERSONA_FILE = BASE_DIR / "human_annotated_eval_data_set.jsonl"
OUTPUT_FILE = RESULT_DIR / "split_pool.json"


def load_jsonl(path: Path) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def make_split(records: list[dict], seed: int) -> dict:
    by_tag: dict[str, list[str]] = defaultdict(list)
    for r in records:
        by_tag[r["product_tag"]].append(r["persona_id"])

    rng = random.Random(seed)
    dev: list[str] = []
    heldout: list[str] = []
    singleton_bucket: list[str] = []

    for tag, persona_ids in sorted(by_tag.items()):
        if len(persona_ids) >= 2:
            ids = list(persona_ids)
            rng.shuffle(ids)
            half = len(ids) // 2
            dev.extend(ids[:half] if half > 0 else ids[:1])
            heldout.extend(ids[half:] if half > 0 else [])
            # 태그당 2개면 1/1, 3개면 1/2 — half=len//2 로 자연 처리됨
        else:
            singleton_bucket.extend(persona_ids)

    # 태그가 1개뿐인 페르소나들은 한 버킷에 모아 셔플 후 번갈아 배정
    # (우연히 한쪽 분할에 쏠리는 것 방지)
    rng.shuffle(singleton_bucket)
    for i, pid in enumerate(singleton_bucket):
        (dev if i % 2 == 0 else heldout).append(pid)

    return {
        "seed": seed,
        "granularity": "persona",
        "stratified_by": "product_tag",
        "dev": sorted(dev),
        "heldout": sorted(heldout),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    records = load_jsonl(PERSONA_FILE)
    split = make_split(records, args.seed)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(split, f, ensure_ascii=False, indent=2)

    overlap = set(split["dev"]) & set(split["heldout"])
    assert not overlap, f"dev/heldout 중복: {overlap}"
    assert len(split["dev"]) + len(split["heldout"]) == len(records), "페르소나 수 불일치"

    print(f"페르소나 {len(records)}건 → dev {len(split['dev'])} / heldout {len(split['heldout'])}")
    print(f"저장: {OUTPUT_FILE.name}")


if __name__ == "__main__":
    main()
