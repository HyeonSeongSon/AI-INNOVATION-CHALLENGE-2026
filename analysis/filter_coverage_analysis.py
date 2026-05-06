"""
Filter Coverage Analysis
========================
과도 필터링(Over-Filtering) 문제 원인 파악을 위한 데이터 분포 분석 스크립트.

실행:
    cd AI-INNOVATION-CHALLENGE-2026
    python analysis/filter_coverage_analysis.py

출력:
    - 각 필터 필드의 값 분포
    - 필터 조합별 결과 상품 수
    - 페르소나 vs 상품 값 불일치 현황
"""

import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from collections import Counter, defaultdict
from dotenv import load_dotenv
from pathlib import Path

# .env 로드 (database/.env 기준)
env_path = Path(__file__).parent.parent / "database" / ".env"
load_dotenv(env_path)

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", 5432)),
    "database": os.getenv("POSTGRES_DB", "ai_innovation_db"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}

SEPARATOR = "=" * 70


def connect():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)


def section(title: str):
    print(f"\n{SEPARATOR}")
    print(f"  {title}")
    print(SEPARATOR)


# ─────────────────────────────────────────────
# 1. 기본 분포 분석
# ─────────────────────────────────────────────

def analyze_basic_distributions(conn):
    section("1. 기본 통계")
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS total FROM products")
        total = cur.fetchone()["total"]
        print(f"  전체 상품 수: {total}개")

        cur.execute("SELECT COUNT(DISTINCT brand) AS brands FROM products")
        print(f"  브랜드 수: {cur.fetchone()['brands']}개")

        cur.execute("SELECT COUNT(DISTINCT product_tag) AS cats FROM products")
        print(f"  카테고리 수: {cur.fetchone()['cats']}개")


def analyze_array_field(conn, field_name: str, display_name: str, top_n: int = 20):
    """배열 필드의 값 분포를 분석"""
    section(f"2. {display_name} ({field_name}) 분포")
    with conn.cursor() as cur:
        # null / empty array 비율
        cur.execute(f"""
            SELECT
                COUNT(*) FILTER (WHERE {field_name} IS NULL OR array_length({field_name},1) IS NULL) AS empty_count,
                COUNT(*) FILTER (WHERE {field_name} IS NOT NULL AND array_length({field_name},1) > 0) AS has_value_count
            FROM products
        """)
        row = cur.fetchone()
        print(f"  값 없음(null/빈배열): {row['empty_count']}개")
        print(f"  값 있음: {row['has_value_count']}개")

        # 값 분포 (unnest)
        cur.execute(f"""
            SELECT unnest({field_name}) AS val, COUNT(*) AS cnt
            FROM products
            WHERE {field_name} IS NOT NULL
            GROUP BY val
            ORDER BY cnt DESC
            LIMIT {top_n}
        """)
        rows = cur.fetchall()
        if rows:
            print(f"\n  상위 {top_n}개 값:")
            for r in rows:
                print(f"    {r['val']:<30} {r['cnt']:>5}개")
        else:
            print("  (데이터 없음)")


def analyze_personal_color(conn):
    section("3. personal_color 분포")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE personal_color IS NULL OR array_length(personal_color,1) IS NULL) AS empty_count,
                COUNT(*) FILTER (WHERE personal_color IS NOT NULL AND array_length(personal_color,1) > 0) AS has_value_count
            FROM products
        """)
        row = cur.fetchone()
        print(f"  값 없음(null/빈배열): {row['empty_count']}개")
        print(f"  값 있음: {row['has_value_count']}개")

        cur.execute("""
            SELECT unnest(personal_color) AS val, COUNT(*) AS cnt
            FROM products
            WHERE personal_color IS NOT NULL
            GROUP BY val ORDER BY cnt DESC
        """)
        rows = cur.fetchall()
        print("\n  personal_color 값 목록:")
        for r in rows:
            print(f"    '{r['val']}'  →  {r['cnt']}개")

    # 페르소나의 personal_color 값 목록
    section("3b. 페르소나 personal_color 값 목록")
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT personal_color FROM personas WHERE personal_color IS NOT NULL ORDER BY personal_color")
        rows = cur.fetchall()
        print("  페르소나 personal_color 값:")
        for r in rows:
            print(f"    '{r['personal_color']}'")


def analyze_brands(conn):
    section("4. 브랜드별 상품 수 (상위 20개)")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT brand, COUNT(*) AS cnt FROM products
            GROUP BY brand ORDER BY cnt DESC LIMIT 20
        """)
        for r in cur.fetchall():
            print(f"    {r['brand']:<20} {r['cnt']:>5}개")


# ─────────────────────────────────────────────
# 2. 필터 조합 시뮬레이션
# ─────────────────────────────────────────────

def simulate_filter_combinations(conn):
    section("5. 필터 조합별 상품 수 시뮬레이션")

    # 대표 브랜드 5개 추출
    with conn.cursor() as cur:
        cur.execute("SELECT brand FROM products GROUP BY brand ORDER BY COUNT(*) DESC LIMIT 5")
        top_brands = [r["brand"] for r in cur.fetchall()]

    # 대표 personal_color 값
    with conn.cursor() as cur:
        cur.execute("""
            SELECT unnest(personal_color) AS val, COUNT(*) AS cnt
            FROM products WHERE personal_color IS NOT NULL
            GROUP BY val ORDER BY cnt DESC LIMIT 5
        """)
        top_colors = [r["val"] for r in cur.fetchall()]

    # 대표 skin_concerns 값
    with conn.cursor() as cur:
        cur.execute("""
            SELECT unnest(skin_concerns) AS val, COUNT(*) AS cnt
            FROM products WHERE skin_concerns IS NOT NULL
            GROUP BY val ORDER BY cnt DESC LIMIT 5
        """)
        top_concerns = [r["val"] for r in cur.fetchall()]

    print(f"  테스트 브랜드: {top_brands}")
    print(f"  테스트 personal_color: {top_colors}")
    print(f"  테스트 skin_concerns: {top_concerns}")
    print()

    results = []

    # 조합 1: 브랜드만
    for brand in top_brands:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM products WHERE brand = %s", (brand,))
            cnt = cur.fetchone()["cnt"]
        results.append((f"brand='{brand}'", cnt))

    # 조합 2: 브랜드 + personal_color
    for brand in top_brands:
        for color in top_colors:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) AS cnt FROM products
                    WHERE brand = %s AND personal_color @> ARRAY[%s]::TEXT[]
                """, (brand, color))
                cnt = cur.fetchone()["cnt"]
            results.append((f"brand='{brand}' + personal_color='{color}'", cnt))

    # 조합 3: 브랜드 + skin_concerns
    for brand in top_brands:
        for concern in top_concerns:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) AS cnt FROM products
                    WHERE brand = %s AND skin_concerns && ARRAY[%s]::TEXT[]
                """, (brand, concern))
                cnt = cur.fetchone()["cnt"]
            results.append((f"brand='{brand}' + skin_concerns='{concern}'", cnt))

    # 조합 4: personal_color만
    for color in top_colors:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) AS cnt FROM products
                WHERE personal_color @> ARRAY[%s]::TEXT[]
            """, (color,))
            cnt = cur.fetchone()["cnt"]
        results.append((f"personal_color='{color}' (브랜드 없음)", cnt))

    # 조합 5: skin_concerns만
    for concern in top_concerns:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) AS cnt FROM products
                WHERE skin_concerns && ARRAY[%s]::TEXT[]
            """, (concern,))
            cnt = cur.fetchone()["cnt"]
        results.append((f"skin_concerns='{concern}' (브랜드 없음)", cnt))

    # 결과 출력 (0개 케이스 강조)
    zero_count = 0
    print(f"  {'조합':<55} {'결과':>6}")
    print(f"  {'-'*55} {'------':>6}")
    for combo, cnt in results:
        marker = "  ← 0건!" if cnt == 0 else ""
        print(f"  {combo:<55} {cnt:>6}개{marker}")
        if cnt == 0:
            zero_count += 1

    print(f"\n  *** 총 {len(results)}개 조합 중 {zero_count}개가 0건 ***")


# ─────────────────────────────────────────────
# 3. 페르소나 vs 상품 값 불일치 분석
# ─────────────────────────────────────────────

def analyze_value_mismatch(conn):
    section("6. 페르소나 personal_color vs 상품 personal_color 불일치")

    # 페르소나 personal_color 값
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT personal_color FROM personas WHERE personal_color IS NOT NULL")
        persona_colors = {r["personal_color"] for r in cur.fetchall()}

    # 상품 personal_color 값 (unnest)
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT unnest(personal_color) AS val
            FROM products WHERE personal_color IS NOT NULL
        """)
        product_colors = {r["val"] for r in cur.fetchall()}

    print(f"  페르소나 personal_color 값: {sorted(persona_colors)}")
    print(f"  상품 personal_color 값: {sorted(product_colors)}")

    matched = persona_colors & product_colors
    only_persona = persona_colors - product_colors
    only_product = product_colors - persona_colors

    print(f"\n  [매칭] 둘 다 있는 값: {sorted(matched)}")
    print(f"  [불일치] 페르소나에만 있음 (→ 필터 결과 0건 위험): {sorted(only_persona)}")
    print(f"  [참고] 상품에만 있는 값: {sorted(only_product)}")


def analyze_skin_concerns_mismatch(conn):
    section("7. 페르소나 skin_concerns vs 상품 skin_concerns 불일치")

    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT unnest(skin_concerns) AS val
            FROM personas WHERE skin_concerns IS NOT NULL
        """)
        persona_concerns = {r["val"] for r in cur.fetchall()}

    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT unnest(skin_concerns) AS val
            FROM products WHERE skin_concerns IS NOT NULL
        """)
        product_concerns = {r["val"] for r in cur.fetchall()}

    matched = persona_concerns & product_concerns
    only_persona = persona_concerns - product_concerns

    print(f"  페르소나 skin_concerns 값 ({len(persona_concerns)}개): {sorted(persona_concerns)}")
    print(f"\n  상품 skin_concerns 값 ({len(product_concerns)}개): {sorted(product_concerns)}")
    print(f"\n  [매칭] 겹치는 값 ({len(matched)}개): {sorted(matched)}")
    print(f"  [불일치] 페르소나에만 있음 ({len(only_persona)}개): {sorted(only_persona)}")


# ─────────────────────────────────────────────
# 4. 실제 페르소나 3개로 필터 시뮬레이션
# ─────────────────────────────────────────────

def simulate_persona_filters(conn):
    section("8. 실제 페르소나별 필터 시뮬레이션")

    with conn.cursor() as cur:
        cur.execute("""
            SELECT persona_id, name, personal_color, skin_concerns, skin_type, avoided_ingredients
            FROM personas
            ORDER BY persona_id
            LIMIT 5
        """)
        personas = cur.fetchall()

    for p in personas:
        pid = p["persona_id"]
        name = p["name"]
        p_color = p["personal_color"]
        concerns = p["skin_concerns"] or []
        skin_types = p["skin_type"] or []
        avoided = p["avoided_ingredients"] or []

        print(f"\n  [{pid}] {name}")
        print(f"    personal_color={p_color}, skin_concerns={concerns}")
        print(f"    skin_type={skin_types}, avoided_ingredients={avoided}")

        with conn.cursor() as cur:
            # 현재 필터 (브랜드/카테고리 없이 테스트)
            cur.execute("SELECT COUNT(*) AS cnt FROM products")
            total = cur.fetchone()["cnt"]

            # personal_color 필터
            if p_color:
                cur.execute("""
                    SELECT COUNT(*) AS cnt FROM products
                    WHERE personal_color @> ARRAY[%s]::TEXT[]
                """, (p_color,))
                cnt_color = cur.fetchone()["cnt"]
            else:
                cnt_color = total

            # skin_concerns 필터
            if concerns:
                cur.execute("""
                    SELECT COUNT(*) AS cnt FROM products
                    WHERE skin_concerns && %s::TEXT[]
                """, (concerns,))
                cnt_concerns = cur.fetchone()["cnt"]
            else:
                cnt_concerns = total

            # personal_color + skin_concerns AND 조합
            if p_color and concerns:
                cur.execute("""
                    SELECT COUNT(*) AS cnt FROM products
                    WHERE personal_color @> ARRAY[%s]::TEXT[]
                    AND skin_concerns && %s::TEXT[]
                """, (p_color, concerns))
                cnt_and = cur.fetchone()["cnt"]
            else:
                cnt_and = None

            # avoided_ingredients EXCLUDE
            if avoided:
                cur.execute("""
                    SELECT COUNT(*) AS cnt FROM products
                    WHERE NOT (avoided_ingredients && %s::TEXT[])
                """, (avoided,))
                cnt_excluded = cur.fetchone()["cnt"]
            else:
                cnt_excluded = total

        print(f"    전체: {total}개")
        print(f"    personal_color='{p_color}' 만: {cnt_color}개")
        print(f"    skin_concerns 만: {cnt_concerns}개")
        if cnt_and is not None:
            marker = "  ← 문제!" if cnt_and < 10 else ""
            print(f"    personal_color AND skin_concerns: {cnt_and}개{marker}")
        print(f"    avoided_ingredients EXCLUDE 후: {cnt_excluded}개")


# ─────────────────────────────────────────────
# 5. 권장 전략 요약
# ─────────────────────────────────────────────

def print_recommendation():
    section("9. 분석 결과 기반 권장 전략")
    print("""
  [권장 전략: Hybrid 방식]

  1. DB 필터 (하드 필터) — 결과가 줄어도 괜찮은 필터만 적용
     - brands (사용자가 지정한 경우만)
     - product_categories (사용자가 지정한 경우만)
     - exclusive_target (안전 필터)
     - avoided_ingredients (EXCLUDE - 절대 포함 안되는 성분 제외)

  2. 소프트 필터 (벡터 쿼리에 포함) — 랭킹에 반영
     - personal_color → multi-query 텍스트에 포함
     - skin_concerns → multi-query 텍스트에 포함
     - skin_type → multi-query 텍스트에 포함

  3. Fallback 로직 — DB 필터 결과가 N개 미만이면 단계적 완화
     레벨1: brands + categories + excluded_ingredients → 결과 < 임계값(예:20)
     레벨2: categories + excluded_ingredients
     레벨3: excluded_ingredients만
     레벨4: 전체

  [핵심 이유]
  - 868개 상품에서 AND 필터 중첩 시 교집합이 급격히 줄어듦
  - personal_color / skin_concerns는 값 불일치(mismatch) 위험이 높음
  - 벡터 검색은 의미적 유사도로 어차피 관련 상품을 상위에 올림
    → DB 레벨에서 하드 필터링할 필요 없음
""")


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    print(f"\n{'#' * 70}")
    print("  Filter Coverage Analysis - Over-Filtering 원인 파악")
    print(f"{'#' * 70}")

    try:
        conn = connect()
        print(f"\n  DB 연결 성공: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
    except Exception as e:
        print(f"\n  [ERROR] DB 연결 실패: {e}")
        return

    try:
        analyze_basic_distributions(conn)
        analyze_brands(conn)
        analyze_personal_color(conn)
        analyze_array_field(conn, "skin_concerns", "고민키워드(skin_concerns)")
        analyze_array_field(conn, "skin_type", "피부타입(skin_type)")
        analyze_array_field(conn, "avoided_ingredients", "기피성분(avoided_ingredients)", top_n=15)
        simulate_filter_combinations(conn)
        analyze_value_mismatch(conn)
        analyze_skin_concerns_mismatch(conn)
        simulate_persona_filters(conn)
        print_recommendation()
    finally:
        conn.close()

    print(f"\n{'#' * 70}")
    print("  분석 완료")
    print(f"{'#' * 70}\n")


if __name__ == "__main__":
    main()
