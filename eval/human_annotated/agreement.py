"""
채점자 간 일치도 지표 모듈.

analyze_annotations.py 에 있던 지표 함수를 그대로 옮겨온 것이다.
judge_v4 / compare_v4 가 같은 정의를 쓰기 위해 분리했으며, 계산식은 변경하지 않았다.

추가로 judge_v4(1~5) → 사람(0/1/2) 척도 접기 상수를 여기에 둔다.
"""

import json
import math
from collections import Counter

RATINGS = [0, 1, 2]


# ── 로드 ──────────────────────────────────────────────────────────────────────

def load_jsonl(path):
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


# ── 척도 접기 (judge_v4 1~5 → 사람 0/1/2) ─────────────────────────────────────
#
# 경계는 core_need_met 하나다.
#   5·4·3 = core_need_met True  → 사람 2 (핵심 니즈를 직접 해결)
#   2     = core_need_met False → 사람 1 (도움은 되지만 핵심이 아님)
#   1     = 게이트 탈락          → 사람 0 (다른 고민이나 카테고리)
#
# 이 매핑은 S4 실행 전에 확정된 것이며 결과를 본 뒤 바꾸지 않는다.

JUDGE_TO_HUMAN = {1: 0, 2: 1, 3: 2, 4: 2, 5: 2}

# 게이트 탈락(1점)에는 성격이 다른 두 사유가 섞인다.
#   category_mismatch : 사람 rubric "0 = 다른 고민이나 카테고리" 에 문자 그대로 대응
#   avoid_violated    : 카테고리는 맞으나 명시적 회피 조건 위반. 가이드라인 문서에
#                       지침이 없으면 사람이 0으로 봤는지 1로 봤는지 알 수 없다.
# 그래서 두 접기를 모두 산출해 나란히 보고한다. 유리한 쪽만 고르지 않는다.
FOLDS = ("A", "B")


def fold_judge_score(score, gate_reason=None, fold="A"):
    """judge_v4 점수(1~5)를 사람 척도(0/1/2)로 접는다.

    fold "A": avoid_violated → 0 (기본)
    fold "B": avoid_violated → 1 (카테고리는 맞으므로 "도움은 되지만 핵심 아님")
    """
    if fold not in FOLDS:
        raise ValueError(f"fold는 {FOLDS} 중 하나여야 한다: {fold!r}")
    if fold == "B" and gate_reason == "avoid_violated":
        return 1
    return JUDGE_TO_HUMAN[score]


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

def dcg(ratings, k):
    return sum(r / math.log2(i + 2) for i, r in enumerate(ratings[:k]))


def ndcg(ratings, k):
    ideal = dcg(sorted(ratings, reverse=True), k)
    return dcg(ratings, k) / ideal if ideal > 0 else 0.0


# ── Cohen's Kappa (pairwise) ──────────────────────────────────────────────────

def cohen_kappa(ratings_a, ratings_b):
    """
    ratings_a, ratings_b: 동일 길이의 평점 리스트 (값 범주형)
    반환: kappa 값
    """
    n = len(ratings_a)
    assert n == len(ratings_b) and n > 0

    categories = sorted(set(ratings_a) | set(ratings_b))

    # 관찰 합의율 (Po)
    po = sum(a == b for a, b in zip(ratings_a, ratings_b)) / n

    # 기대 합의율 (Pe)
    count_a = Counter(ratings_a)
    count_b = Counter(ratings_b)
    pe = sum((count_a[c] / n) * (count_b[c] / n) for c in categories)

    if pe == 1.0:
        return 1.0  # 완전 편향
    return (po - pe) / (1 - pe)


def weighted_kappa(ratings_a, ratings_b, max_val=2):
    """
    Linear weighted Cohen's Kappa
    가중치 w_ij = |i - j| / max_val
    """
    n = len(ratings_a)
    assert n == len(ratings_b) and n > 0

    categories = RATINGS

    # 관찰 가중 불일치율
    wo = sum(abs(a - b) / max_val for a, b in zip(ratings_a, ratings_b)) / n

    count_a = Counter(ratings_a)
    count_b = Counter(ratings_b)

    # 기대 가중 불일치율
    we = sum(
        (count_a.get(i, 0) / n) * (count_b.get(j, 0) / n) * (abs(i - j) / max_val)
        for i in categories
        for j in categories
    )

    if we == 0:
        return 1.0
    return 1 - wo / we


# ── Fleiss' Kappa (3명 이상) ──────────────────────────────────────────────────

def fleiss_kappa(matrix):
    """
    matrix: list of lists, shape (N, k)
      N = 항목 수, k = 범주 수
      matrix[i][j] = i번째 항목에 j번째 범주를 매긴 평가자 수
    """
    N = len(matrix)
    k = len(matrix[0])
    n = sum(matrix[0])  # 항목당 평가자 수 (동일하다고 가정)

    # p_j: 범주 j의 전체 비율
    p_j = [sum(matrix[i][j] for i in range(N)) / (N * n) for j in range(k)]

    # P_i: i번째 항목의 관찰 합의율
    P_i = [
        (sum(matrix[i][j] ** 2 for j in range(k)) - n) / (n * (n - 1))
        for i in range(N)
    ]

    P_bar = sum(P_i) / N
    P_e = sum(p ** 2 for p in p_j)

    if P_e == 1.0:
        return 1.0
    return (P_bar - P_e) / (1 - P_e)


def build_fleiss_matrix(keys, sets_dict, categories=RATINGS):
    """공통 키에 대해 Fleiss' Kappa용 행렬 생성"""
    matrix = []
    cat_idx = {c: i for i, c in enumerate(categories)}
    annotators = sorted(sets_dict.keys())
    for k in keys:
        row = [0] * len(categories)
        for ann in annotators:
            r = sets_dict[ann].get(k)
            if r is not None and r in cat_idx:
                row[cat_idx[r]] += 1
        matrix.append(row)
    return matrix


def kappa_interpretation(k):
    if k < 0:      return "Poor (무작위보다 낮음)"
    if k < 0.20:   return "Slight"
    if k < 0.40:   return "Fair"
    if k < 0.60:   return "Moderate"
    if k < 0.80:   return "Substantial"
    return "Almost Perfect"


# ── Gwet's AC1 (pairwise) ─────────────────────────────────────────────────────

def gwet_ac1(ratings_a, ratings_b, categories=RATINGS, weights=None):
    """
    Gwet's AC1 (unweighted) / AC2 (weighted).

    Kappa Paradox를 해결하기 위해 설계된 지표.
    Pe를 marginal 분포 대신 범주 내 분산(π_k * (1-π_k))으로 추정.

    weights: None → unweighted (AC1)
             'linear' → linear weighted (AC2)
    """
    n = len(ratings_a)
    q = len(categories)
    cat_idx = {c: i for i, c in enumerate(categories)}

    # 가중치 행렬
    if weights == "linear":
        max_diff = max(categories) - min(categories)
        w = [[1 - abs(categories[i] - categories[j]) / max_diff
              for j in range(q)] for i in range(q)]
    else:
        w = [[1 if i == j else 0 for j in range(q)] for i in range(q)]

    # 관찰 가중 합의율 (Po_w)
    po_w = sum(
        w[cat_idx[a]][cat_idx[b]]
        for a, b in zip(ratings_a, ratings_b)
    ) / n

    # π_k : 두 평가자의 범주 k 비율 평균
    count_a = Counter(ratings_a)
    count_b = Counter(ratings_b)
    pi_k = [(count_a.get(c, 0) / n + count_b.get(c, 0) / n) / 2
            for c in categories]

    # 기대 가중 합의율 (Pe_w) — Gwet 방식
    pe_w = sum(
        pi_k[i] * pi_k[j] * w[i][j]
        for i in range(q)
        for j in range(q)
    )

    if pe_w == 1.0:
        return 1.0
    return (po_w - pe_w) / (1 - pe_w)


# ── Krippendorff's Alpha ──────────────────────────────────────────────────────

def krippendorff_alpha(sets_dict, keys, metric="ordinal"):
    """
    Krippendorff's Alpha.

    metric:
      'nominal'  → d²_ij = 0 if i==j else 1
      'ordinal'  → d²_ij = (rank_i - rank_j)² (rank는 정렬 순위)
      'interval' → d²_ij = (v_i - v_j)²

    sets_dict: {annotator_id: {key: rating}}
    keys: 분석할 항목 키 목록
    """
    annotators = sorted(sets_dict.keys())
    # 항목별 유효 평점 리스트 수집
    units = []
    for k in keys:
        vals = [sets_dict[ann][k] for ann in annotators if k in sets_dict[ann]]
        if len(vals) >= 2:
            units.append(vals)

    if not units:
        return float("nan")

    # 모든 유효 평점 목록
    all_vals = [v for u in units for v in u]
    unique_vals = sorted(set(all_vals))

    # 차이 함수
    if metric == "nominal":
        def diff(a, b): return 0.0 if a == b else 1.0
    elif metric == "interval":
        def diff(a, b): return float((a - b) ** 2)
    else:  # ordinal
        # 각 값의 순위(1-based cumulative rank) 계산
        rank_map = {}
        for v in unique_vals:
            cnt_below = sum(1 for x in all_vals if x < v)
            cnt_equal = sum(1 for x in all_vals if x == v)
            rank_map[v] = cnt_below + (cnt_equal + 1) / 2  # midrank
        def diff(a, b):
            return float((rank_map[a] - rank_map[b]) ** 2)

    # 관찰 불일치 (D_o)
    d_o_sum = 0.0
    n_pairs = 0
    for u in units:
        mu = len(u)
        for i in range(mu):
            for j in range(i + 1, mu):
                d_o_sum += diff(u[i], u[j])
                n_pairs += 1
    D_o = d_o_sum / n_pairs if n_pairs > 0 else 0.0

    # 기대 불일치 (D_e) — 전체 값 쌍 기반
    N = len(all_vals)
    d_e_sum = 0.0
    for i in range(N):
        for j in range(i + 1, N):
            d_e_sum += diff(all_vals[i], all_vals[j])
    D_e = d_e_sum / (N * (N - 1) / 2) if N > 1 else 0.0

    if D_e == 0.0:
        return 1.0
    return 1 - D_o / D_e
