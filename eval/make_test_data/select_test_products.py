"""
테스트 데이터 선정 스크립트

각 카테고리에서 쉬움(40%) / 보통(40%) / 어려움(20%) 비율로
총 100개 상품을 선정하여 data/test_products_selected.jsonl 에 출력한다.

난이도 점수 산정 기준:
  서브태그 경쟁 수  : 1~3개 +3 / 4~9개 +2 / 10~19개 +1 / 20개+ +0
  페르소나태그 풍부도: 5개+ +3 / 3~4개 +2 / 1~2개 +1 / 0개 +0
  proof_points 존재 : +2
  고유 기술명 존재  : +1
  모호성 페널티     : 생활가전/세트/이너뷰티푸드 -2, 고경쟁+페르소나태그없음 -1

점수 → 난이도: 7+ 쉬움 / 4~6 보통 / 3이하 어려움
"""

import json
import re
from collections import Counter, defaultdict
from pathlib import Path


BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"

V2_FILES = {
    "스킨케어":  DATA_DIR / "v2_product_data_structured_skincare.jsonl",
    "뷰티툴":   DATA_DIR / "v2_product_data_structured_beauty_tool.jsonl",
    "헤어":     DATA_DIR / "v2_product_data_structured_hair.jsonl",
    "색조":     DATA_DIR / "v2_product_data_structured_color_tone.jsonl",
    "향수/바디": DATA_DIR / "v2_product_data_structured_fragrance_body.jsonl",
    "이너뷰티":  DATA_DIR / "v2_product_data_structured_inner_beauty.jsonl",
    "생활도구":  DATA_DIR / "v2_product_data_structured_living_supplies.jsonl",
}

# 카테고리별 목표 수량 {카테고리: (쉬움, 보통, 어려움)}
TARGET = {
    "스킨케어":  (9, 9, 5),
    "뷰티툴":   (7, 7, 3),
    "헤어":     (6, 6, 3),
    "색조":     (5, 5, 2),
    "향수/바디": (5, 5, 2),
    "이너뷰티":  (4, 5, 2),
    "생활도구":  (4, 4, 2),
}

# 모호성 페널티 대상 서브태그
AMBIGUOUS_SUBTAGS = {"스킨케어세트", "샴푸세트", "향수세트", "차세트", "생활가전"}
AMBIGUOUS_TAGS    = {"이너뷰티푸드", "생활가전"}  # 중태그(태그)

# 고유 기술명 패턴 (™, ®, 영문 고유명사 2단어 이상)
TECH_PATTERN = re.compile(r"[™®]|[A-Z][a-z]+[A-Z]|[A-Z]{2,}")


# ──────────────────────────────────────────────
# 유틸
# ──────────────────────────────────────────────
def load_jsonl(path: Path) -> list[dict]:
    products = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                products.append(json.loads(line))
    return products


def get_structured(product: dict) -> dict:
    s = product.get("structured", {})
    if isinstance(s, str):
        try:
            s = json.loads(s)
        except Exception:
            s = {}
    return s or {}


def persona_tag_count(product: dict) -> int:
    pt = product.get("페르소나태그", {})
    if not isinstance(pt, dict):
        return 0
    return sum(len(v) for v in pt.values() if isinstance(v, list))


def has_proof_points(product: dict) -> bool:
    s = get_structured(product)
    pp = s.get("proof_points", [])
    if isinstance(pp, list):
        return len(pp) > 0
    return bool(pp)


def has_unique_tech(product: dict) -> bool:
    s = get_structured(product)
    attr = s.get("attribute", [])
    if isinstance(attr, list):
        text = " ".join(str(a) for a in attr)
    else:
        text = str(attr)
    return bool(TECH_PATTERN.search(text))


# ──────────────────────────────────────────────
# 핵심 로직
# ──────────────────────────────────────────────
def score_product(product: dict, subtag_count: Counter) -> tuple[int, str]:
    """난이도 점수와 사유를 반환한다."""
    score = 0
    reasons = []
    subtag = product.get("서브태그", "")
    tag = product.get("태그", "")
    comp = subtag_count.get(subtag, 1)

    # 1. 서브태그 경쟁 수
    if comp <= 3:
        score += 3; reasons.append(f"서브태그경쟁{comp}개(+3)")
    elif comp <= 9:
        score += 2; reasons.append(f"서브태그경쟁{comp}개(+2)")
    elif comp <= 19:
        score += 1; reasons.append(f"서브태그경쟁{comp}개(+1)")
    else:
        reasons.append(f"서브태그경쟁{comp}개(+0)")

    # 2. 페르소나태그 풍부도
    ptc = persona_tag_count(product)
    if ptc >= 5:
        score += 3; reasons.append(f"페르소나태그{ptc}개(+3)")
    elif ptc >= 3:
        score += 2; reasons.append(f"페르소나태그{ptc}개(+2)")
    elif ptc >= 1:
        score += 1; reasons.append(f"페르소나태그{ptc}개(+1)")
    else:
        reasons.append(f"페르소나태그{ptc}개(+0)")

    # 3. proof_points
    if has_proof_points(product):
        score += 2; reasons.append("proof_points있음(+2)")

    # 4. 고유 기술명
    if has_unique_tech(product):
        score += 1; reasons.append("기술명있음(+1)")

    # 5. 모호성 페널티
    if subtag in AMBIGUOUS_SUBTAGS or tag in AMBIGUOUS_TAGS:
        score -= 2; reasons.append(f"모호성태그(-2)")
    elif comp >= 20 and ptc == 0:
        score -= 1; reasons.append("고경쟁+페르소나없음(-1)")

    return score, ", ".join(reasons)


def classify(score: int) -> str:
    if score >= 7:
        return "쉬움"
    elif score >= 4:
        return "보통"
    else:
        return "어려움"


def select_from_bucket(
    products: list[dict],
    n: int,
    max_per_subtag: int = 2,
) -> list[dict]:
    """
    서브태그 다양성을 최대화하며 n개 선정.
    같은 서브태그에서 max_per_subtag 이상 선택하지 않는다.
    """
    subtag_used: Counter = Counter()
    selected = []

    # 서브태그 경쟁이 낮은(고유한) 상품 우선 정렬
    sorted_products = sorted(
        products,
        key=lambda p: (subtag_used.get(p.get("서브태그", ""), 0),),
    )

    for product in sorted_products:
        if len(selected) >= n:
            break
        subtag = product.get("서브태그", "")
        if subtag_used[subtag] < max_per_subtag:
            selected.append(product)
            subtag_used[subtag] += 1

    # 부족하면 max_per_subtag 제한 없이 채움
    if len(selected) < n:
        for product in sorted_products:
            if len(selected) >= n:
                break
            if product not in selected:
                selected.append(product)

    return selected


def main():
    # 전체 데이터 로드
    all_products: list[dict] = []
    for cat, path in V2_FILES.items():
        if not path.exists():
            print(f"[WARNING] 파일 없음: {path}")
            continue
        prods = load_jsonl(path)
        for p in prods:
            p["_category_key"] = cat  # 내부 분류용
        all_products.extend(prods)
        print(f"  로드: {cat} {len(prods)}개")

    print(f"\n전체 상품 수: {len(all_products)}개\n")

    # 서브태그 경쟁 수 집계 (전체 기준)
    subtag_count: Counter = Counter(p.get("서브태그", "") for p in all_products)

    # 각 상품에 점수/난이도 부여
    for p in all_products:
        score, reason = score_product(p, subtag_count)
        p["_score"] = score
        p["_difficulty"] = classify(score)
        p["_reason"] = reason

    # 카테고리 × 난이도 버킷 구성
    buckets: dict[str, dict[str, list]] = {
        cat: {"쉬움": [], "보통": [], "어려움": []}
        for cat in TARGET
    }
    for p in all_products:
        cat = p.get("_category_key", "")
        diff = p.get("_difficulty", "보통")
        if cat in buckets:
            buckets[cat][diff].append(p)

    # 버킷 크기 출력
    print("── 버킷 크기 ──")
    for cat, diffs in buckets.items():
        print(f"  {cat}: " + " / ".join(f"{d} {len(v)}개" for d, v in diffs.items()))
    print()

    # ── 선정 ──
    selected_all: list[dict] = []

    for cat, (n_easy, n_mid, n_hard) in TARGET.items():
        # 카테고리 전체 서브태그 사용 카운터 (쉬움/보통/어려움 통합 관리)
        cat_subtag_used: Counter = Counter()
        cat_selected_ids: set = set()
        cat_selected: list[dict] = []

        def pick(pool: list[dict], n: int, diff_label: str) -> list[dict]:
            """카테고리 공유 서브태그 카운터로 n개 선정."""
            chosen = []
            for p in pool:
                if len(chosen) >= n:
                    break
                pid = p["product_id"]
                subtag = p.get("서브태그", "")
                if pid in cat_selected_ids:
                    continue
                if cat_subtag_used[subtag] < 2:
                    chosen.append(p)
                    cat_subtag_used[subtag] += 1
                    cat_selected_ids.add(pid)
                    p["_selected_difficulty"] = diff_label
            # 서브태그 제한으로 부족할 경우 제한 완화
            if len(chosen) < n:
                for p in pool:
                    if len(chosen) >= n:
                        break
                    pid = p["product_id"]
                    if pid not in cat_selected_ids:
                        chosen.append(p)
                        cat_selected_ids.add(pid)
                        cat_subtag_used[p.get("서브태그", "")] += 1
                        p["_selected_difficulty"] = diff_label
            return chosen

        for diff, n_target in [("쉬움", n_easy), ("보통", n_mid), ("어려움", n_hard)]:
            pool = buckets[cat][diff]
            chosen = pick(pool, n_target, diff)

            # 버킷 수량 부족 -> 인접 난이도에서 보충
            if len(chosen) < n_target:
                shortage = n_target - len(chosen)
                fallback_order = ["보통", "쉬움", "어려움"] if diff == "어려움" else \
                                 ["보통", "어려움", "쉬움"] if diff == "쉬움" else \
                                 ["쉬움", "어려움"]
                for fb_diff in fallback_order:
                    if shortage <= 0:
                        break
                    fb_pool = buckets[cat][fb_diff]
                    fb_chosen = pick(fb_pool, shortage, diff)
                    chosen += fb_chosen
                    shortage -= len(fb_chosen)
                    if fb_chosen:
                        print(f"  [보충] {cat} {diff}: {fb_diff}에서 {len(fb_chosen)}개 보충")

            cat_selected.extend(chosen)

        selected_all.extend(cat_selected)
        n_total = len(cat_selected)
        n_e = sum(1 for p in cat_selected if p.get("_selected_difficulty") == "쉬움")
        n_m = sum(1 for p in cat_selected if p.get("_selected_difficulty") == "보통")
        n_h = sum(1 for p in cat_selected if p.get("_selected_difficulty") == "어려움")
        print(f"  선정: {cat} {n_total}개 (쉬움 {n_e} / 보통 {n_m} / 어려움 {n_h})")

    print(f"\n총 선정: {len(selected_all)}개\n")

    # 출력
    output_path = DATA_DIR / "test_products_selected.jsonl"
    with open(output_path, "w", encoding="utf-8") as f:
        for p in selected_all:
            out = {
                "product_id":              p.get("product_id", ""),
                "카테고리":                p.get("카테고리", p.get("_category_key", "")),
                "태그":                    p.get("태그", ""),
                "서브태그":                p.get("서브태그", ""),
                "상품명":                  p.get("상품명", ""),
                "브랜드":                  p.get("브랜드", ""),
                "difficulty":              p.get("_selected_difficulty", p.get("_difficulty", "")),
                "difficulty_score":        p.get("_score", 0),
                "difficulty_reason":       p.get("_reason", ""),
                "subtag_competition_count": subtag_count.get(p.get("서브태그", ""), 0),
            }
            f.write(json.dumps(out, ensure_ascii=False) + "\n")

    print(f"출력 완료: {output_path}")

    # 검증 요약 
    print("\n── 최종 검증 ──")
    from collections import Counter as C
    cat_diff_counter = C()
    for p in selected_all:
        cat_diff_counter[(p.get("_category_key", ""), p.get("_selected_difficulty", ""))] += 1

    for cat in TARGET:
        easy  = cat_diff_counter.get((cat, "쉬움"), 0)
        mid   = cat_diff_counter.get((cat, "보통"), 0)
        hard  = cat_diff_counter.get((cat, "어려움"), 0)
        total = easy + mid + hard
        print(f"  {cat}: 합계 {total}개  (쉬움 {easy} / 보통 {mid} / 어려움 {hard})")

    subtag_dup_check = defaultdict(list)
    for p in selected_all:
        subtag_dup_check[p.get("서브태그", "")].append(p.get("_category_key", ""))
    print("\n── 서브태그 중복 확인 (2개 초과) ──")
    found_dup = False
    for subtag, cats in subtag_dup_check.items():
        if len(cats) > 2:
            print(f"  {subtag}: {len(cats)}개")
            found_dup = True
    if not found_dup:
        print("  중복 없음 (모든 서브태그 ≤ 2개)")


if __name__ == "__main__":
    main()
