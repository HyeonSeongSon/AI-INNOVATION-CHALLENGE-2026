"""
파일럿 재주석 UI — 순위 앵커링의 영향 크기를 재기 위한 소규모 재채점.

annotate_top5.py 와 달라진 점 (전부 의도된 변경):
    1. 순위·RRF 점수를 화면에 표시하지 않는다            (기존 D9)
    2. 항목을 전역으로 셔플해 제시한다 — 순서로도 순위가 새지 않게
    3. top3 all-2 조기종료를 제거한다                    (기존 D8)
    4. 참조 파일 자동 채움을 제거한다                     ← 아래 주의 참조
    5. PersonaSpec 을 함께 표시한다 — judge_v4 와 같은 기준

주의 — 기존 스크립트의 참조 자동 채움:
    annotate_top5.py 는 result/annotated_results_1.jsonl 이 존재하면
    같은 product_id의 rating을 자동으로 복사한다.
    1~3차 주석 당시에는 그 파일이 없어서 발동하지 않았다(파일1과 파일2·3의
    공통 product_id 184개 중 17개가 서로 다른 값 → 복사가 없었다는 증거).
    그러나 지금은 파일이 존재하므로 그대로 재실행하면 독립성이 깨진다.
    이 스크립트에는 그 로직이 없다.

측정상의 한계:
    5번(PersonaSpec 표시)을 켜면 앵커링 외의 변수가 하나 더 바뀐다.
    순위 앵커링만 순수하게 재려면 --no-spec 으로 실행한다.
    각 레코드에 shown_spec 을 남겨 어느 조건에서 채점했는지 구분한다.

사용법:
    python annotate_v2.py                 # 40건 표집, spec 표시
    python annotate_v2.py --n 30 --seed 7
    python annotate_v2.py --no-spec       # 앵커링만 격리
"""

import argparse
import json
import os
import random
import signal
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
RESULT_DIR = BASE_DIR / "result"

HUMAN_FILES = [
    RESULT_DIR / "annotated_results_1.jsonl",
    RESULT_DIR / "annotated_results_2.jsonl",
    RESULT_DIR / "annotated_results_3.jsonl",
]
PERSONA_FILE = BASE_DIR / "human_annotated_eval_data_set.jsonl"
SPEC_FILE = RESULT_DIR / "persona_specs.json"
OUTPUT_FILE = RESULT_DIR / "annotated_v2_pilot.jsonl"

STRUCTURED_EXCLUDE = {"_original_semantic"}
SEP = "─" * 70


def load_jsonl(path: Path) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def build_product_index() -> dict[str, dict]:
    index = {}
    for path in sorted(DATA_DIR.glob("*.jsonl")):
        for rec in load_jsonl(path):
            pid = rec.get("product_id")
            if pid:
                index[pid] = rec
    return index


def load_persona_text() -> dict[str, str]:
    return {r["persona_id"]: r["information"] for r in load_jsonl(PERSONA_FILE)}


def load_common_keys() -> list[tuple]:
    """사람 3인이 모두 채점한 항목 — 기존 라벨과 대조할 수 있는 범위."""
    key_fn = lambda r: (r["persona_id"], r["product_tag"], r["product_id"], r["rank"])
    sets = [{key_fn(r) for r in load_jsonl(p)} for p in HUMAN_FILES]
    return sorted(sets[0] & sets[1] & sets[2])


def load_done_keys() -> set:
    if not OUTPUT_FILE.exists():
        return set()
    return {
        (r["persona_id"], r["product_tag"], r["product_id"], r["rank"])
        for r in load_jsonl(OUTPUT_FILE)
    }


# ── 출력 ──────────────────────────────────────────────────────────────────────

def print_persona(persona_id, product_tag, information, spec, show_spec):
    print(SEP)
    print(f"  페르소나 ID : {persona_id}")
    print(f"  추천 태그   : {product_tag}")
    print(SEP)
    for line in information.splitlines():
        if line.strip():
            print(f"  {line.strip()}")
    if show_spec and spec:
        print()
        print("  [요구 명세]")
        for field in ("core_needs", "preferences", "self_conditions", "avoid"):
            print(f"    {field:<16}: {spec.get(field) or []}")
    print()


def print_product(product):
    """순위와 RRF는 표시하지 않는다."""
    print(f"  상품명     : {product.get('상품명', '')}")
    print(f"  서브태그   : {product.get('서브태그', '')}")
    print(f"  상품페이지 : {product.get('product_url', '')}")
    imgs = product.get("상품상세_이미지") or []
    print(f"  상세이미지 : {imgs[0] if imgs else ''}")
    print()
    print("  ▶ Structured")
    structured = {
        k: v for k, v in (product.get("structured") or {}).items()
        if k not in STRUCTURED_EXCLUDE
    }
    for k, v in structured.items():
        if isinstance(v, list):
            v_str = ", ".join(str(x) for x in v[:10])
            if len(v) > 10:
                v_str += f" ... (+{len(v) - 10})"
        elif isinstance(v, str) and len(v) > 200:
            v_str = v[:200] + "..."
        else:
            v_str = str(v)
        print(f"    {k}: {v_str}")
    print()


def ask_rating(idx, total):
    while True:
        try:
            raw = input(f"  평점 입력 [{idx}/{total}] (0=부적합 / 1=보통 / 2=적합)  → ").strip()
        except EOFError:
            return None
        if raw in ("0", "1", "2"):
            return int(raw)
        print("  ⚠  0, 1, 2 중 하나를 입력하세요.")


def save_result(record: dict) -> None:
    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def handle_interrupt(sig, frame):
    print("\n\n  ⚠  중단됨. 진행된 결과는 이미 저장되었습니다.")
    print(f"  저장 위치: {OUTPUT_FILE}")
    sys.exit(0)


signal.signal(signal.SIGINT, handle_interrupt)


# ── 메인 ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=40, help="표집 건수")
    parser.add_argument("--seed", type=int, default=42, help="표집 시드 (재현용)")
    parser.add_argument("--no-spec", action="store_true", help="PersonaSpec 미표시 — 앵커링만 격리")
    args = parser.parse_args()

    show_spec = not args.no_spec

    products = build_product_index()
    persona_text = load_persona_text()
    specs = {}
    if SPEC_FILE.exists():
        with open(SPEC_FILE, encoding="utf-8") as f:
            specs = {k: v["spec"] for k, v in json.load(f).items()}
    elif show_spec:
        sys.exit(f"{SPEC_FILE.name} 이 없습니다. --no-spec 으로 실행하거나 추출을 먼저 하세요.")

    common = load_common_keys()
    rng = random.Random(args.seed)
    sample = rng.sample(common, min(args.n, len(common)))
    rng.shuffle(sample)  # 제시 순서로 순위가 새지 않게

    done = load_done_keys()
    todo = [k for k in sample if k not in done]

    print("=" * 70)
    print(f"  파일럿 재주석  |  표집 {len(sample)}건 (seed={args.seed})  |  남은 {len(todo)}건")
    print(f"  조건: 순위·RRF 미표시 · 순서 셔플 · 조기종료 없음 · "
          f"PersonaSpec {'표시' if show_spec else '미표시'}")
    print("=" * 70)

    if not todo:
        print("  모두 완료되었습니다.")
        return

    for i, key in enumerate(todo, 1):
        persona_id, product_tag, product_id, rank = key
        product = products.get(product_id)
        if not product:
            print(f"\n  ⚠  product_id {product_id} 데이터 없음 — 건너뜀")
            continue

        print("\n" + "=" * 70)
        print_persona(
            persona_id, product_tag,
            persona_text.get(persona_id, "(페르소나 정보 없음)"),
            specs.get(persona_id), show_spec,
        )
        print_product(product)

        rating = ask_rating(i, len(todo))
        if rating is None:
            print("\n  ⚠  입력 스트림 종료. 저장 후 종료합니다.")
            print(f"  저장 위치: {OUTPUT_FILE}")
            sys.exit(0)

        save_result({
            "persona_id": persona_id,
            "product_tag": product_tag,
            "product_id": product_id,
            "rank": rank,          # 기록만 한다. 화면에는 보이지 않았다.
            "rating": rating,
            "shown_spec": show_spec,
            "seed": args.seed,
        })
        print(f"  ✓ 저장됨 (rating={rating})")

    print("\n" + "=" * 70)
    print("  파일럿 완료")
    print(f"  저장 위치: {OUTPUT_FILE}")
    print("=" * 70)


if __name__ == "__main__":
    main()
