"""
Human annotation script for top5 product recommendations.

Usage:
    python annotate_top5.py

Rating:
    | 등급 | 정의 | 예시 |
    |---|---|---|
    | 2 (정확히 맞음) | 페르소나의 핵심 니즈를 직접 해결 | 각질 개선 세럼 → 각질 고민 페르소나 |
    | 1 (관련 있음) | 도움은 되지만 핵심이 아님 | 보습 크림 → 같은 페르소나 |
    | 0 (관련 없음) | 다른 고민/카테고리 | 바디로션 → 얼굴 각질 페르소나 |

Output: annotated_results.jsonl (이어쓰기 지원)
"""

import sys
import json
import signal
import os

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

TOP5_FILE = os.path.join(BASE_DIR, "human_annotated_top5_results_v3.jsonl")
PERSONA_FILE = os.path.join(
    os.path.dirname(BASE_DIR), "human_annotated_eval_data_set.jsonl"
)
OUTPUT_FILE = os.path.join(BASE_DIR, "annotated_results.jsonl")

PRODUCT_FILES = [
    os.path.join(DATA_DIR, f)
    for f in os.listdir(DATA_DIR)
    if f.endswith(".jsonl")
]

STRUCTURED_EXCLUDE = {"_original_semantic"}

# ── 데이터 로드 ────────────────────────────────────────────────────────────────

def load_jsonl(path):
    items = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def build_product_index():
    """모든 제품 파일을 읽어 product_id → product 딕셔너리 구성"""
    index = {}
    for path in PRODUCT_FILES:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                p = json.loads(line)
                pid = p.get("product_id")
                if pid:
                    index[pid] = p
    return index


def load_persona_index():
    """persona_id → information 딕셔너리"""
    index = {}
    for item in load_jsonl(PERSONA_FILE):
        key = (item["persona_id"], item["product_tag"])
        index[key] = item["information"]
    return index


def load_completed_keys():
    """이미 완료된 (persona_id, product_tag, product_id) 세트 반환"""
    if not os.path.exists(OUTPUT_FILE):
        return set()
    completed = set()
    with open(OUTPUT_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            completed.add((r["persona_id"], r["product_tag"], r["product_id"]))
    return completed


# ── 출력 헬퍼 ─────────────────────────────────────────────────────────────────

SEP = "─" * 70


def print_sep():
    print(SEP)


def print_persona(persona_id, product_tag, information):
    print_sep()
    print(f"  페르소나 ID : {persona_id}")
    print(f"  추천 태그   : {product_tag}")
    print_sep()
    for line in information.splitlines():
        print(f"  {line.strip()}")
    print()


def print_product(rank, product, rrf_score):
    pid = product.get("product_id", "")
    name = product.get("상품명", "")
    subtag = product.get("서브태그", "")
    product_url = product.get("product_url", "")

    detail_imgs = product.get("상품상세_이미지") or []
    detail_img = detail_imgs[0] if detail_imgs else ""

    structured = {
        k: v
        for k, v in (product.get("structured") or {}).items()
        if k not in STRUCTURED_EXCLUDE
    }

    print(f"\n  [{rank}] {name}  (ID: {pid}  RRF: {rrf_score:.4f})")
    print(f"  서브태그   : {subtag}")
    print(f"  상품페이지 : {product_url}")
    print(f"  상세이미지 : {detail_img}")
    print()
    print("  ▶ Structured")
    for k, v in structured.items():
        # 리스트는 한 줄로 요약
        if isinstance(v, list):
            v_str = ", ".join(str(x) for x in v[:10])
            if len(v) > 10:
                v_str += f" ... (+{len(v)-10})"
        elif isinstance(v, str) and len(v) > 200:
            v_str = v[:200] + "..."
        else:
            v_str = str(v)
        print(f"    {k}: {v_str}")
    print()


# ── 입력 헬퍼 ─────────────────────────────────────────────────────────────────

def ask_rating(persona_id, product_tag, rank, total):
    while True:
        try:
            raw = input(f"  평점 입력 [{rank}/{total}] (0=부적합 / 1=보통 / 2=적합)  → ").strip()
        except EOFError:
            return None
        if raw in ("0", "1", "2"):
            return int(raw)
        print("  ⚠  0, 1, 2 중 하나를 입력하세요.")


# ── 저장 ──────────────────────────────────────────────────────────────────────

results_buffer = []  # 세션 중 저장된 결과


def flush_buffer():
    if not results_buffer:
        return
    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        for r in results_buffer:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    results_buffer.clear()


def save_result(persona_id, product_tag, product_id, rank, rating, rrf_score):
    record = {
        "persona_id": persona_id,
        "product_tag": product_tag,
        "product_id": product_id,
        "rank": rank,
        "rating": rating,
        "rrf_score": rrf_score,
    }
    results_buffer.append(record)
    # 즉시 파일에 기록 (중단 대비)
    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    results_buffer.clear()


# ── 시그널 핸들러 ─────────────────────────────────────────────────────────────

def handle_interrupt(sig, frame):
    print("\n\n  ⚠  중단됨. 진행된 결과는 이미 저장되었습니다.")
    print(f"  저장 위치: {OUTPUT_FILE}")
    sys.exit(0)


signal.signal(signal.SIGINT, handle_interrupt)


# ── 메인 ──────────────────────────────────────────────────────────────────────

def main():
    print("제품 데이터 로딩 중...")
    product_index = build_product_index()
    print(f"  → {len(product_index)}개 제품 로드 완료")

    persona_index = load_persona_index()
    top5_list = load_jsonl(TOP5_FILE)
    completed = load_completed_keys()

    if completed:
        print(f"  → 이전 진행분 {len(completed)}개 항목 이어서 진행합니다.\n")

    total_personas = len(top5_list)

    for p_idx, entry in enumerate(top5_list):
        persona_id = entry["persona_id"]
        product_tag = entry["product_tag"]
        top5 = entry["top5"]  # list of {product_id, rrf_score}

        # 페르소나 정보
        information = persona_index.get((persona_id, product_tag), "(페르소나 정보 없음)")

        # 이미 완료된 항목 파악
        completed_in_persona = [
            t for t in top5
            if (persona_id, product_tag, t["product_id"]) in completed
        ]
        remaining = [
            t for t in top5
            if (persona_id, product_tag, t["product_id"]) not in completed
        ]

        if not remaining:
            # 이 페르소나는 전부 완료
            continue

        # ── top3 all-2 조기종료 판정 ──
        # 이미 저장된 top3 결과 확인
        saved_top3_ratings = []
        if completed_in_persona:
            if os.path.exists(OUTPUT_FILE):
                with open(OUTPUT_FILE, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        r = json.loads(line)
                        if r["persona_id"] == persona_id and r["product_tag"] == product_tag and r["rank"] <= 3:
                            saved_top3_ratings.append(r["rating"])

        print(f"\n{'='*70}")
        print(f"  페르소나 [{p_idx+1}/{total_personas}]")
        print_persona(persona_id, product_tag, information)

        session_top3_ratings = list(saved_top3_ratings)  # 이미 저장된 것 포함

        for item in remaining:
            product_id = item["product_id"]
            rrf_score = item["rrf_score"]

            # rank 계산 (top5에서 몇 번째인지)
            rank = next(
                (i + 1 for i, t in enumerate(top5) if t["product_id"] == product_id),
                0,
            )

            # top3 all-2 조기종료 체크 (rank 4, 5 진입 전)
            if rank > 3 and len(session_top3_ratings) >= 3 and all(r == 2 for r in session_top3_ratings[:3]):
                print(f"\n  ✓ Top3 모두 적합(2) → 이 페르소나 평가 완료 (4, 5위 스킵)\n")
                break

            product = product_index.get(product_id)
            if not product:
                print(f"\n  ⚠  product_id {product_id} 데이터 없음 — 건너뜀")
                continue

            print_sep()
            print_product(rank, product, rrf_score)

            rating = ask_rating(persona_id, product_tag, rank, len(top5))
            if rating is None:
                print("\n  ⚠  입력 스트림 종료. 저장 후 종료합니다.")
                print(f"  저장 위치: {OUTPUT_FILE}")
                sys.exit(0)

            save_result(persona_id, product_tag, product_id, rank, rating, rrf_score)
            print(f"  ✓ 저장됨 (rating={rating})\n")

            if rank <= 3:
                session_top3_ratings.append(rating)

            # top3 평가 직후 all-2 체크
            if rank == 3 and len(session_top3_ratings) >= 3 and all(r == 2 for r in session_top3_ratings[:3]):
                print(f"\n  ✓ Top3 모두 적합(2) → 이 페르소나 평가 완료 (4, 5위 스킵)\n")
                break

    print("\n" + "=" * 70)
    print("  모든 평가 완료!")
    print(f"  저장 위치: {OUTPUT_FILE}")
    print("=" * 70)


if __name__ == "__main__":
    main()
