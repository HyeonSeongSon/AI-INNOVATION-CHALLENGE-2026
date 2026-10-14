"""
가중치 그리드 + 풀 구성 상수 — build_pool.py / score_weight_grid.py 공유.

Phase 1: 카테고리 오버라이드는 무시하고 전역 _DIMENSION_WEIGHTS 하나만
60개 페르소나 전체에 균일 적용해 튜닝한다 (근거: 태그당 페르소나 최대 4개뿐이라
카테고리별 그리드서치는 아직 통계적으로 무의미).

10개 컨피그 = ① 현재 기본값 ② 균등 가중치(비교 기준선)
             ③ need/preference/persona 각각 ±0.2 로컬 섭동 6개
             ④ 기존 _CATEGORY_WEIGHTS에서 그대로 가져온 아키타입 2개
"""

RRF_K = 10                       # settings.rrf_k 고정 — 별도 축이라 이번 그리드에서 스윕하지 않음
TOP_K_PER_CONFIG = 6             # 컨피그당 풀에 담을 후보 수 (작업량 사전 예산)
N_HARD_NEGATIVES = 4
HARD_NEG_RANK_RANGE = (20, 50)   # retrieval_result_ids 내 1-idx 구간 (포함)

GRID_CONFIGS: dict[str, dict[str, float]] = {
    "current_default":            {"retrieval": 1.0, "need": 1.2, "preference": 1.1, "persona": 1.0},
    "equal_baseline":              {"retrieval": 1.0, "need": 1.0, "preference": 1.0, "persona": 1.0},
    "need_low":                    {"retrieval": 1.0, "need": 1.0, "preference": 1.1, "persona": 1.0},
    "need_high":                   {"retrieval": 1.0, "need": 1.4, "preference": 1.1, "persona": 1.0},
    "preference_low":              {"retrieval": 1.0, "need": 1.2, "preference": 0.9, "persona": 1.0},
    "preference_high":             {"retrieval": 1.0, "need": 1.2, "preference": 1.3, "persona": 1.0},
    "persona_low":                 {"retrieval": 1.0, "need": 1.2, "preference": 1.1, "persona": 0.8},
    "persona_high":                {"retrieval": 1.0, "need": 1.2, "preference": 1.1, "persona": 1.2},
    "archetype_functional_device": {"retrieval": 1.3, "need": 1.2, "preference": 1.0, "persona": 0.6},  # = 기존 전동마사지기 가중치
    "archetype_preference_taste":  {"retrieval": 1.0, "need": 0.9, "preference": 1.2, "persona": 1.0},  # = 기존 파운데이션 가중치
}
