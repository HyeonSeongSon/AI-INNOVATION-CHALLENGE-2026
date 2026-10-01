"""
플랜 검증 1·2 — 본 실행 전에 게이트 1·2단계 재현을 확인한다. LLM 호출 없음.

검증 1 (2단계 기준점): 35차 기록의 (생성 문장, 금지 문장) 쌍별 점수를 전수 검색(top_k=100)으로
    ±0.003 안에서 재현해야 한다. 1위만 보지 않고 쌍별로 본다(idx 69 의 0.858 은 2위 매칭).
    ANN(k=3, 게이트 경로) 점수도 나란히 적는다.
검증 2 (override 기대값): override 를 켰을 때 53-2 · 97 은 해당 문장이 2단계를 통과하고,
    53-1 · 69 는 계속 불통과. idx 29("피부가 검은")는 1단계에서 떨어진다.
    idx 85 는 35차 기록에 문장 원문이 일부만 있어("...") 검증하지 않는다.

출처: Desktop/2026ai프로젝트 진행 md파일/LOAD_TEST_35차_결과_2026-06-24.md (idx 29 · 53 · 69 · 97).
    idx 97 문장의 "00·저자극"은 기록 원문 그대로다.

사용법 (Python 3.11, 로컬 도커 OpenSearch API :8010 필요):
    python verify_stage2.py
종료 코드: 모두 통과 0, 하나라도 실패 1 (플랜: 벗어나면 진행하지 않는다).
"""

import asyncio
import sys

from _common import bootstrap, stage2_topk

bootstrap()

import httpx  # noqa: E402

from app.config.settings import settings  # noqa: E402
from app.agents.generate_message_agent.services import quality_check as qc  # noqa: E402

TOL = 0.003
GRANDMA = "할머니 같은 주름진 피부를 가진 분들에게 강력히 추천드립니다"
PERFECT = "알레르기 체질이신 분도 안심하고 쓸 수 있는 완전 무자극 제품입니다"
GUARANTEE = "민감성 피부와 아토피 피부에도 100% 무자극임을 보장합니다"

S53_1 = "건성 피부와 저자극을 선호하시는 분께 특히 권합니다"
S53_2 = "무향·무첨가 설계이며, 소아과·피부과·알러지 테스트를 통해 사용 적합성을 확인했습니다"
S69 = "무향·무첨가 설계로 자극에 민감한 보호자와 건성 피부에 맞춘 데일리 케어를 제공합니다"
S97 = "00·저자극 테스트 완료로 민감한 건성 피부와 온 가족 사용을 고려해 만들었습니다"

# (라벨, 생성 문장, 금지 문장, 35차 기록 점수)
ANCHORS = [
    ("53-1", S53_1, GRANDMA, 0.868),
    ("53-2", S53_2, PERFECT, 0.869),
    ("69 (1위)", S69, PERFECT, 0.863),
    ("69 (2위)", S69, GUARANTEE, 0.858),
    ("97", S97, GUARANTEE, 0.851),
]
# (라벨, 문장, override 켰을 때 2단계 통과 기대)
OVERRIDE_EXPECT = [("53-1", S53_1, False), ("53-2", S53_2, True), ("69", S69, False), ("97", S97, True)]


def score_of(results: list[dict], target: str) -> float | None:
    return next((r["score"] for r in results if r["sentence"] == target), None)


async def main_async() -> int:
    failures = 0
    queries = sorted({s for _, s, _, _ in ANCHORS})
    async with httpx.AsyncClient(timeout=60, headers={"X-Internal-Token": settings.internal_token}) as http:
        exact = dict(zip(queries, await stage2_topk(http, queries, 100)))
        ann = dict(zip(queries, await stage2_topk(http, queries, settings.quality_check_semantic_top_k)))

    print("## 검증 1 — 2단계 기준점 (쌍별, 전수 top_k=100)")
    print("| 쌍 | 기록 | 전수 | 차이 | ANN(k=3) | 판정 |")
    print("|---|---|---|---|---|---|")
    for label, sent, forbidden, recorded in ANCHORS:
        ex = score_of(exact[sent], forbidden)
        an = score_of(ann[sent], forbidden)
        ok = ex is not None and abs(ex - recorded) <= TOL
        failures += not ok
        ex_s = "없음" if ex is None else f"{ex:.4f}"
        diff = "–" if ex is None else f"{ex - recorded:+.4f}"
        an_s = "k=3 밖" if an is None else f"{an:.4f}"
        print(f"| {label} | {recorded:.3f} | {ex_s} | {diff} | {an_s} | {'통과' if ok else '실패'} |")

    print("\n## 검증 2 — override 기대값 (전수 1위 기준, 켬)")
    thr = settings.quality_check_semantic_threshold
    print("| 문장 | 전수 1위 | override 조건 | 켬 2단계 | 기대 | 판정 |")
    print("|---|---|---|---|---|---|")
    for label, sent, expect_pass in OVERRIDE_EXPECT:
        top = exact[sent][0]["score"] if exact[sent] else 0.0
        cond = qc._is_hedge_without_assertion(sent)
        passed = not (top > thr and not cond)
        ok = passed == expect_pass
        failures += not ok
        print(f"| {label} | {top:.4f} | {'성립' if cond else '불성립'} | {'통과' if passed else '불통과'} | "
              f"{'통과' if expect_pass else '불통과'} | {'통과' if ok else '실패'} |")

    checker = qc.QualityChecker.__new__(qc.QualityChecker)
    checker._forbidden_expressions = checker._extract_forbidden_expressions()
    from kiwipiepy import Kiwi

    checker._kiwi = Kiwi()
    checker._automaton = checker._build_automaton()
    hits = checker._detect_forbidden_expressions("피부가 검은 분들도 환하게")
    ok = "피부가 검은" in hits
    failures += not ok
    print(f"\n- idx 29 1단계: 검출 {hits} → {'통과' if ok else '실패'}")
    print("- idx 85: 35차 기록에 문장 원문이 일부만 있어 검증하지 않음")
    print(f"\n결과: {'모두 통과' if failures == 0 else f'실패 {failures}건 — 원인 확인 전 본 실행 금지'}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main_async()))
