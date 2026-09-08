"""
풀(Pool) 채점 UI — 여러 가중치 컨피그의 후보 합집합을 사람이 채점한다.

annotate_v2.py 를 기반으로 하되 annotate_top5.py 의 두 동작은 명시적으로 배제한다:
    · top3-all-2 조기종료 없음 — 그리드 각 컨피그의 후보가 전부 라벨돼야 한다는
      풀링의 전제를 깨뜨리기 때문 (지금 없애려는 풀링 편향이 재발한다).
    · product_id 단독 기준 무조건 자동 채움 없음 — 대신 (persona_id, product_id)
      키로 자동 채움한다 (annotate_v2.py 헤더 코멘트가 지적한 독립성 문제 회피).

configs / n_configs_hit / is_hard_negative 는 화면에 절대 노출하지 않는다
(순위·RRF 비노출과 같은 이유 — 알면 그 자체가 채점 편향이 된다). 다만 출력
레코드에는 사후 분석(층화 재채점, score_weight_grid.py)을 위해 기록한다.

티어링(--tier)은 채점 "순서"일 뿐 종료 조건이 아니다. n_configs_hit==1 후보
(Tier 2, "싱글턴")는 ±0.2 로컬 섭동 컨피그끼리의 승부를 가르는 항목이라, 컨피그
간 최종 비교는 Tier 2까지 전량 완료한 뒤에만 신뢰한다.

사용법:
    python annotate_pool.py                        # Tier 1 (하드네거티브 + multi-hit)
    python annotate_pool.py --tier 2                # Tier 2 (싱글턴) — 반드시 완료해야 함
    python annotate_pool.py --tier all
    python annotate_pool.py --second-pass                          # 3층 층화 ~40건 재채점
    python annotate_pool.py --second-pass --stratum singleton --n 15  # Tier2 직후 드리프트 체크
"""

import argparse
import json
import random
import signal
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
RESULT_DIR = BASE_DIR / "result"

PERSONA_FILE = BASE_DIR / "human_annotated_eval_data_set.jsonl"
POOL_FILE = RESULT_DIR / "pool.jsonl"
SPEC_FILE = RESULT_DIR / "persona_specs.json"
OUTPUT_FILE = RESULT_DIR / "annotated_pool.jsonl"
SECOND_PASS_FILE = RESULT_DIR / "annotated_pool_2nd.jsonl"

# 자동 채움 참조 우선순위 — (persona_id, product_id) 키, 앞쪽 파일이 우선
REFERENCE_FILES = [
    RESULT_DIR / "annotated_results_1.jsonl",
    RESULT_DIR / "annotated_results_2.jsonl",
    RESULT_DIR / "annotated_results_3.jsonl",
    RESULT_DIR / "annotated_v2_pilot.jsonl",
]

STRUCTURED_EXCLUDE = {"_original_semantic"}
SEP = "─" * 70


# ─────────────────────────────────────────────
# 데이터 로드
# ─────────────────────────────────────────────

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


def load_specs(show_spec: bool) -> dict:
    if not SPEC_FILE.exists():
        if show_spec:
            sys.exit(f"{SPEC_FILE.name} 이 없습니다. --no-spec 으로 실행하거나 추출을 먼저 하세요.")
        return {}
    with open(SPEC_FILE, encoding="utf-8") as f:
        return {k: v["spec"] for k, v in json.load(f).items()}


def load_pool() -> list[dict]:
    if not POOL_FILE.exists():
        sys.exit(f"{POOL_FILE.name} 이 없습니다. build_pool.py 를 먼저 실행하세요.")
    return load_jsonl(POOL_FILE)


def key_of(r: dict) -> tuple:
    return (r["persona_id"], r["product_tag"], r["product_id"])


def build_autofill_map() -> dict[tuple, int]:
    """(persona_id, product_id) → rating. 우선순위: results_1 > _2 > _3 > v2_pilot."""
    autofill: dict[tuple, int] = {}
    for path in REFERENCE_FILES:
        for r in load_jsonl(path):
            key = (r["persona_id"], r["product_id"])
            if key not in autofill:
                autofill[key] = r["rating"]
    return autofill


def load_done_keys(path: Path) -> set[tuple]:
    return {key_of(r) for r in load_jsonl(path)}


# ─────────────────────────────────────────────
# 출력
# ─────────────────────────────────────────────

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
    """순위·RRF·컨피그 정보는 절대 표시하지 않는다."""
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


def save_record(path: Path, record: dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


_CURRENT_OUTPUT_FILE = [OUTPUT_FILE]


def handle_interrupt(sig, frame):
    print("\n\n  ⚠  중단됨. 진행된 결과는 이미 저장되었습니다.")
    print(f"  저장 위치: {_CURRENT_OUTPUT_FILE[0]}")
    sys.exit(0)


signal.signal(signal.SIGINT, handle_interrupt)


# ─────────────────────────────────────────────
# 1차(주) 채점
# ─────────────────────────────────────────────

def build_tier_queue(pool: list[dict], tier: str) -> list[dict]:
    if tier == "1":
        return [r for r in pool if r["is_hard_negative"] or r["n_configs_hit"] >= 2]
    if tier == "2":
        return [r for r in pool if not r["is_hard_negative"] and r["n_configs_hit"] == 1]
    return list(pool)  # "all"


def run_primary(args) -> None:
    _CURRENT_OUTPUT_FILE[0] = OUTPUT_FILE
    show_spec = not args.no_spec

    products = build_product_index()
    persona_text = load_persona_text()
    specs = load_specs(show_spec)
    pool = load_pool()
    autofill = build_autofill_map()

    queue = build_tier_queue(pool, args.tier)
    rng = random.Random(args.seed)
    rng.shuffle(queue)  # 전역 플랫 셔플 — 페르소나 내부만 셔플하는 게 아님

    done = load_done_keys(OUTPUT_FILE)
    todo = [r for r in queue if key_of(r) not in done]

    n_hard = sum(1 for r in queue if r["is_hard_negative"])
    n_single = sum(1 for r in queue if not r["is_hard_negative"] and r["n_configs_hit"] == 1)
    n_multi = len(queue) - n_hard - n_single

    print("=" * 70)
    print(f"  풀 채점  |  tier={args.tier}  |  대상 {len(queue)}건 "
          f"(하드네거티브 {n_hard} / 싱글턴 {n_single} / multi-hit {n_multi})")
    print(f"  남은 {len(todo)}건  |  PersonaSpec {'표시' if show_spec else '미표시'}")
    if args.tier == "1":
        print("  ※ Tier 1만으로는 컨피그 간 최종 비교를 신뢰할 수 없다 — "
              "이어서 --tier 2 를 전량 완료할 것.")
    print("=" * 70)

    if not todo:
        print("  모두 완료되었습니다.")
        return

    n_auto = 0
    n_manual = 0
    for i, rec in enumerate(todo, 1):
        persona_id, product_tag, product_id = key_of(rec)

        autofill_key = (persona_id, product_id)
        if autofill_key in autofill:
            rating = autofill[autofill_key]
            save_record(OUTPUT_FILE, {
                "persona_id": persona_id, "product_tag": product_tag, "product_id": product_id,
                "rating": rating, "shown_spec": show_spec, "seed": args.seed,
                "is_hard_negative": rec["is_hard_negative"], "n_configs_hit": rec["n_configs_hit"],
                "auto_filled": True,
            })
            n_auto += 1
            print(f"  ↩  [{i}/{len(todo)}] {persona_id} {product_id} — 참조 자동 채움 (rating={rating})")
            continue

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

        save_record(OUTPUT_FILE, {
            "persona_id": persona_id, "product_tag": product_tag, "product_id": product_id,
            "rating": rating, "shown_spec": show_spec, "seed": args.seed,
            "is_hard_negative": rec["is_hard_negative"], "n_configs_hit": rec["n_configs_hit"],
            "auto_filled": False,
        })
        n_manual += 1
        print(f"  ✓ 저장됨 (rating={rating})")

    print("\n" + "=" * 70)
    print(f"  풀 채점(tier={args.tier}) 완료 — 자동 채움 {n_auto}건 / 직접 채점 {n_manual}건")
    print(f"  저장 위치: {OUTPUT_FILE}")
    print("=" * 70)


# ─────────────────────────────────────────────
# 2차 재채점 (드리프트 체크)
# ─────────────────────────────────────────────

def stratum_of(key: tuple, pool_by_key: dict) -> str | None:
    rec = pool_by_key.get(key)
    if rec is None:
        return None
    if rec["is_hard_negative"]:
        return "hard_negative"
    return "singleton" if rec["n_configs_hit"] == 1 else "multi"


def print_second_pass_report(pool_by_key: dict) -> None:
    from agreement import cohen_kappa, gwet_ac1, kappa_interpretation

    primary = {
        key_of(r): r["rating"] for r in load_jsonl(OUTPUT_FILE) if not r.get("auto_filled")
    }
    second = {key_of(r): r["rating"] for r in load_jsonl(SECOND_PASS_FILE)}

    print()
    print("  ⚠  아래 kappa는 동일 채점자의 자기일치도(test-retest)이며 진짜 평가자간")
    print("     신뢰도가 아니다 — 자기일치도는 통상 크로스 채점자 kappa보다 높게 나오는")
    print("     경향이 있어 기존 3인 채점의 사람-사람 기준선(0.616~0.672)과 같은 잣대로")
    print("     pass/fail 판정하지 않는다.")
    print()

    by_stratum: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for key, r2 in second.items():
        if key in primary:
            s = stratum_of(key, pool_by_key)
            if s:
                by_stratum[s].append((primary[key], r2))

    print(f"  {'층':<14}  {'n':>4}  {'kappa':>8}  {'AC1':>8}  해석")
    print(f"  {'-' * 14}  {'-' * 4}  {'-' * 8}  {'-' * 8}  {'-' * 16}")
    all_pairs: list[tuple[int, int]] = []
    for stratum in ("hard_negative", "singleton", "multi"):
        pairs = by_stratum.get(stratum, [])
        all_pairs.extend(pairs)
        if not pairs:
            print(f"  {stratum:<14}  {0:>4}  {'-':>8}  {'-':>8}  (표본 없음)")
            continue
        ra = [p[0] for p in pairs]
        rb = [p[1] for p in pairs]
        k = cohen_kappa(ra, rb)
        ac1 = gwet_ac1(ra, rb)
        print(f"  {stratum:<14}  {len(pairs):>4}  {k:>8.4f}  {ac1:>8.4f}  {kappa_interpretation(k)}")
        if stratum == "hard_negative":
            same_zero = sum(1 for a, b in pairs if a == 0 and b == 0)
            print(
                f"      └ 원 라벨 분포: {len(pairs)}개 중 {same_zero}개가 두 패스 모두 0점 "
                f"— kappa=1.0이 '변별력 있는 일치'인지 '변별할 게 없었던 것'인지는 이 숫자로 판단할 것"
            )

    if all_pairs:
        ra = [p[0] for p in all_pairs]
        rb = [p[1] for p in all_pairs]
        k = cohen_kappa(ra, rb)
        print(f"  {'전체':<14}  {len(all_pairs):>4}  {k:>8.4f}  {'':>8}  {kappa_interpretation(k)}")
        if k < 0.5:
            print()
            print("  ⚠  전체 자기일치도가 0.5 미만 — 방향성 경고로만 해석하고, 진짜 신뢰도")
            print("     확인이 필요하면 별도(2번째) 채점자를 투입할 것.")
    else:
        print("\n  (아직 1차·2차 공통으로 채점된 항목이 없어 리포트를 계산할 수 없습니다.)")


def run_second_pass(args) -> None:
    _CURRENT_OUTPUT_FILE[0] = SECOND_PASS_FILE
    show_spec = not args.no_spec

    products = build_product_index()
    persona_text = load_persona_text()
    specs = load_specs(show_spec)
    pool = load_pool()
    pool_by_key = {key_of(r): r for r in pool}

    # 1차에서 "직접 채점"(자동 채움 아님)한 항목만 재채점 대상 — 자동 채움 항목은
    # 이 채점자가 실제로 판단한 적이 없어 자기일치도 측정 대상이 될 수 없다.
    primary_manual_keys = [
        key_of(r) for r in load_jsonl(OUTPUT_FILE) if not r.get("auto_filled")
    ]

    candidates_by_stratum: dict[str, list[tuple]] = defaultdict(list)
    for key in primary_manual_keys:
        s = stratum_of(key, pool_by_key)
        if s:
            candidates_by_stratum[s].append(key)

    rng = random.Random(args.seed + 1)  # 주 패스와 다른 셔플 순서

    if args.stratum == "all":
        n_total = args.n or 40
        # 예시 비율(하드네거티브10 : 싱글턴15 : multi15 / n=40)을 n_total로 스케일
        targets = {
            "hard_negative": round(n_total * 10 / 40),
            "singleton": round(n_total * 15 / 40),
            "multi": round(n_total * 15 / 40),
        }
        sample_keys: list[tuple] = []
        for stratum, n_target in targets.items():
            pool_keys = list(candidates_by_stratum[stratum])
            rng.shuffle(pool_keys)
            sample_keys.extend(pool_keys[:n_target])
    else:
        n_target = args.n or 15
        pool_keys = list(candidates_by_stratum[args.stratum])
        rng.shuffle(pool_keys)
        sample_keys = pool_keys[:n_target]

    rng.shuffle(sample_keys)  # 층별로 뭉쳐 제시되지 않도록 다시 섞음

    done2 = load_done_keys(SECOND_PASS_FILE)
    todo = [k for k in sample_keys if k not in done2]

    print("=" * 70)
    print(
        f"  2차 재채점(드리프트 체크)  |  표집 {len(sample_keys)}건 "
        f"(stratum={args.stratum}, seed={args.seed + 1})  |  남은 {len(todo)}건"
    )
    print("=" * 70)

    if not todo:
        print("  표집분 모두 완료 — 자기일치도 리포트:")
        print_second_pass_report(pool_by_key)
        return

    for i, key in enumerate(todo, 1):
        persona_id, product_tag, product_id = key
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
            print(f"  저장 위치: {SECOND_PASS_FILE}")
            sys.exit(0)

        save_record(SECOND_PASS_FILE, {
            "persona_id": persona_id, "product_tag": product_tag, "product_id": product_id,
            "rating": rating, "shown_spec": show_spec, "seed": args.seed + 1,
        })
        print(f"  ✓ 저장됨 (rating={rating})")

    print("\n" + "=" * 70)
    print("  2차 재채점 완료 — 자기일치도 리포트:")
    print_second_pass_report(pool_by_key)


# ─────────────────────────────────────────────
# main
# ─────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tier", choices=["1", "2", "all"], default="1",
                         help="1=하드네거티브+multi-hit 우선 착수, 2=싱글턴, all=전체 "
                              "(1만 채점하고 끝내도 된다는 뜻이 아니다 — 최종 비교 전 2까지 필수)")
    parser.add_argument("--seed", type=int, default=42, help="표집·셔플 시드 (재현용)")
    parser.add_argument("--no-spec", action="store_true", help="PersonaSpec 미표시")
    parser.add_argument("--second-pass", action="store_true", help="드리프트 체크용 재채점 모드")
    parser.add_argument("--stratum", choices=["all", "hard_negative", "singleton", "multi"],
                         default="all", help="second-pass 표집 층 (기본 all=3층 층화 ~40건)")
    parser.add_argument("--n", type=int, default=None, help="second-pass 표집 수")
    args = parser.parse_args()

    if args.second_pass:
        run_second_pass(args)
    else:
        run_primary(args)


if __name__ == "__main__":
    main()
