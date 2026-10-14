"""
annotated_pool.jsonl의 라벨 분포를 하드네거티브/그리드 후보로 나눠서 확인한다.

목적: 그리드 후보(각 가중치 컨피그가 실제로 뽑은 상품)의 라벨이 "2"에 쏠려 있으면
NDCG가 모든 컨피그에서 천장(≈1)에 수렴해 컨피그 간 비교력이 사라진다. 하드네거티브는
의도적으로 낮은 점수를 유도하려고 섞은 것이라 전체 분포에 포함시키면 이 쏠림이 가려지므로
반드시 분리해서 봐야 한다.

Tier 1 채점을 100~150건 정도 진행한 시점에 실행해, 그리드 후보의 "2" 비율이 과도하게
높지 않은지 조기 확인하는 용도.

사용법:
    python check_pool_distribution.py
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

RESULT_DIR = Path(__file__).parent / "result"
OUTPUT_FILE = RESULT_DIR / "annotated_pool.jsonl"

WARN_THRESHOLD = 0.80  # 그리드 후보 중 "2" 비율이 이 이상이면 경고


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def print_distribution(label: str, records: list[dict]) -> None:
    total = len(records)
    if total == 0:
        print(f"  {label:<24} (아직 채점된 항목 없음)")
        return
    counts = Counter(r["rating"] for r in records)
    parts = [f"{r}점={counts.get(r, 0)}건({counts.get(r, 0) / total * 100:.0f}%)" for r in (0, 1, 2, 3)]
    print(f"  {label:<24} n={total:<5} " + "  ".join(parts))


def main() -> None:
    records = load_jsonl(OUTPUT_FILE)
    if not records:
        sys.exit(f"{OUTPUT_FILE.name} 이 없거나 비어 있습니다. annotate_pool.py 로 먼저 채점하세요.")

    hard = [r for r in records if r["is_hard_negative"]]
    grid = [r for r in records if not r["is_hard_negative"]]
    grid_auto = [r for r in grid if r.get("auto_filled")]
    grid_manual = [r for r in grid if not r.get("auto_filled")]

    print("=" * 70)
    print(f"  라벨 분포 확인  |  전체 {len(records)}건")
    print("=" * 70)
    print_distribution("전체", records)
    print_distribution("하드네거티브", hard)
    print_distribution("그리드 후보 (전체)", grid)
    print_distribution("  └ 자동 채움", grid_auto)
    print_distribution("  └ 직접 채점", grid_manual)
    print("=" * 70)

    if grid:
        need_met_ratio = sum(1 for r in grid if r["rating"] in (2, 3)) / len(grid)
        n2 = sum(1 for r in grid if r["rating"] == 2)
        n3 = sum(1 for r in grid if r["rating"] == 3)
        print(f"\n  그리드 후보 중 핵심 니즈 충족(2+3) 비율: {need_met_ratio * 100:.0f}%  (2점 {n2}건 / 3점 {n3}건)")
        if need_met_ratio >= WARN_THRESHOLD:
            print(
                f"  ⚠  경고 기준({WARN_THRESHOLD * 100:.0f}%) 이상입니다.\n"
                f"     이 상태로는 가중치 컨피그 간 NDCG가 천장에 수렴해 비교력이 약할 수 있습니다 — "
                f"채점을 계속 진행하며 이 수치를 다시 확인하세요."
            )
        else:
            print(f"  (경고 기준 {WARN_THRESHOLD * 100:.0f}% 미만 — 현재는 양호)")


if __name__ == "__main__":
    main()
