"""
Human annotation 결과 분석 스크립트
- 기본 통계 / 합의율 / Cohen's Kappa (pairwise) / Fleiss' Kappa
- Gwet's AC1 / Krippendorff's Alpha / Precision@k / nDCG@k
"""

import sys
import statistics
from collections import defaultdict, Counter

from agreement import (
    load_jsonl,
    ndcg,
    cohen_kappa,
    weighted_kappa,
    fleiss_kappa,
    build_fleiss_matrix,
    kappa_interpretation,
    gwet_ac1,
    krippendorff_alpha,
)

sys.stdout.reconfigure(encoding="utf-8")

# ── 파일 경로 ─────────────────────────────────────────────────────────────────

import os

BASE = os.path.dirname(os.path.abspath(__file__))

FILES = {
    1: os.path.join(BASE, "result", "annotated_results_1.jsonl"),
    2: os.path.join(BASE, "result", "annotated_results_2.jsonl"),
    3: os.path.join(BASE, "result", "annotated_results_3.jsonl"),
}

# ── 로드 ──────────────────────────────────────────────────────────────────────

data = {fid: load_jsonl(path) for fid, path in FILES.items()}

key_fn = lambda r: (r["persona_id"], r["product_tag"], r["product_id"], r["rank"])
sets = {fid: {key_fn(r): r["rating"] for r in recs} for fid, recs in data.items()}

common_keys = set(sets[1].keys()) & set(sets[2].keys()) & set(sets[3].keys())
common_keys_sorted = sorted(common_keys)

SEP  = "─" * 70
SEP2 = "═" * 70

# ── 출력 ──────────────────────────────────────────────────────────────────────

print(SEP2)
print("  Human Annotation 결과 분석")
print(SEP2)

# 1. 기본 현황
print()
print("[ 1. 기본 현황 ]")
print(SEP)
total_all = sum(len(recs) for recs in data.values())
print(f"  총 평가 레코드        : {total_all}개 (3명 합산)")
for fid, recs in data.items():
    print(f"    어노테이터 {fid}        : {len(recs)}개")

persona_data = defaultdict(list)
for fid, recs in data.items():
    for r in recs:
        key = (r["persona_id"], r["product_tag"])
        if not any(x["rank"] == r["rank"] and x.get("_fid") == fid for x in persona_data[key]):
            persona_data[key].append({**r, "_fid": fid})

# top3 all-2 스킵 집계
skip_count = 0
for key in common_keys:
    pid, tag, prod, rank = key
    pass  # 아래에서 따로 집계

# 페르소나별로 집계
persona_keys = set((k[0], k[1]) for k in common_keys)
skip_personas = 0
for pk in persona_keys:
    top3_keys = [k for k in common_keys if k[0] == pk[0] and k[1] == pk[1] and k[3] <= 3]
    has_rank4 = any(k for k in common_keys if k[0] == pk[0] and k[1] == pk[1] and k[3] == 4)
    if len(top3_keys) == 3 and not has_rank4:
        all2 = all(
            sets[1].get(k) == 2 and sets[2].get(k) == 2 and sets[3].get(k) == 2
            for k in top3_keys
        )
        if all2:
            skip_personas += 1

print(f"  페르소나-태그 쌍       : {len(persona_keys)}개")
print(f"  Top3 all-2 스킵 페르소나: {skip_personas}개 ({skip_personas/len(persona_keys)*100:.1f}%)")
print(f"  4~5위까지 진행 페르소나 : {len(persona_keys)-skip_personas}개")
print(f"  3파일 공통 항목         : {len(common_keys)}개")

# 2. 어노테이터별 평점 분포
print()
print("[ 2. 어노테이터별 평점 분포 ]")
print(SEP)
print(f"  {'구분':<15}  {'0점':>8}  {'1점':>8}  {'2점':>8}  {'합계':>8}")
print(f"  {'-'*15}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*8}")
for fid, recs in data.items():
    dist = Counter(r["rating"] for r in recs)
    total = len(recs)
    print(
        f"  어노테이터 {fid}     "
        f"  {dist[0]:>4}({dist[0]/total*100:4.1f}%)"
        f"  {dist[1]:>4}({dist[1]/total*100:4.1f}%)"
        f"  {dist[2]:>4}({dist[2]/total*100:4.1f}%)"
        f"  {total:>8}"
    )

# 3. 합의율
print()
print("[ 3. 어노테이터 간 합의율 (공통 항목 기준) ]")
print(SEP)

agree_cnt = sum(1 for k in common_keys if sets[1][k] == sets[2][k] == sets[3][k])
disagree_cnt = len(common_keys) - agree_cnt
print(f"  공통 항목 수    : {len(common_keys)}개")
print(f"  완전 합의       : {agree_cnt}개 ({agree_cnt/len(common_keys)*100:.1f}%)")
print(f"  불일치          : {disagree_cnt}개 ({disagree_cnt/len(common_keys)*100:.1f}%)")

patterns = Counter()
for k in common_keys:
    r1, r2, r3 = sets[1][k], sets[2][k], sets[3][k]
    if not (r1 == r2 == r3):
        patterns[tuple(sorted([r1, r2, r3]))] += 1

print()
print("  불일치 패턴:")
for pat, cnt in patterns.most_common():
    print(f"    {list(pat)}: {cnt}개")

# 4. Cohen's Kappa
print()
print("[ 4. Cohen's Kappa (Pairwise) ]")
print(SEP)

pairs = [(1, 2), (1, 3), (2, 3)]
pair_kappas = {}

print(f"  {'쌍':<12}  {'Po(합의율)':>10}  {'κ(unweighted)':>14}  {'κ(linear weighted)':>18}  {'해석'}")
print(f"  {'-'*12}  {'-'*10}  {'-'*14}  {'-'*18}  {'-'*20}")

for a, b in pairs:
    shared = sorted(set(sets[a].keys()) & set(sets[b].keys()))
    ra = [sets[a][k] for k in shared]
    rb = [sets[b][k] for k in shared]

    po = sum(x == y for x, y in zip(ra, rb)) / len(ra)
    kappa = cohen_kappa(ra, rb)
    wkappa = weighted_kappa(ra, rb)

    pair_kappas[(a, b)] = (kappa, wkappa)
    print(
        f"  Ann {a} vs Ann {b}  "
        f"  {po:>9.3f}"
        f"  {kappa:>14.4f}"
        f"  {wkappa:>18.4f}"
        f"  {kappa_interpretation(kappa)}"
    )

# 평균 kappa
avg_k  = statistics.mean(v[0] for v in pair_kappas.values())
avg_wk = statistics.mean(v[1] for v in pair_kappas.values())
print(SEP)
print(f"  {'평균':<12}  {'':>10}  {avg_k:>14.4f}  {avg_wk:>18.4f}  {kappa_interpretation(avg_k)}")

# 5. Fleiss' Kappa
print()
print("[ 5. Fleiss' Kappa (3명 전체) ]")
print(SEP)

matrix = build_fleiss_matrix(common_keys_sorted, sets)
fk = fleiss_kappa(matrix)
print(f"  Fleiss' κ (공통 {len(common_keys)}개 항목) : {fk:.4f}  →  {kappa_interpretation(fk)}")

# 6. Gwet's AC1 / AC2
print()
print("[ 6. Gwet's AC1 / AC2  ※ Kappa Paradox 보정 지표 ]")
print(SEP)
print("  ※ 평점이 특정 등급에 편중될 때 Cohen's Kappa가 낮아지는 문제(Prevalence Paradox)를")
print("     해결하기 위한 지표. Pe를 marginal 분포가 아닌 범주 분산으로 추정.")
print()

pairs = [(1, 2), (1, 3), (2, 3)]
ac1_vals, ac2_vals = [], []

print(f"  {'쌍':<12}  {'Po(합의율)':>10}  {'AC1(unweighted)':>16}  {'AC2(linear w.)':>15}  {'해석(AC1)'}")
print(f"  {'-'*12}  {'-'*10}  {'-'*16}  {'-'*15}  {'-'*20}")

for a, b in pairs:
    shared = sorted(set(sets[a].keys()) & set(sets[b].keys()))
    ra = [sets[a][k] for k in shared]
    rb = [sets[b][k] for k in shared]

    po = sum(x == y for x, y in zip(ra, rb)) / len(ra)
    ac1 = gwet_ac1(ra, rb, weights=None)
    ac2 = gwet_ac1(ra, rb, weights="linear")

    ac1_vals.append(ac1)
    ac2_vals.append(ac2)
    print(
        f"  Ann {a} vs Ann {b}  "
        f"  {po:>9.3f}"
        f"  {ac1:>16.4f}"
        f"  {ac2:>15.4f}"
        f"  {kappa_interpretation(ac1)}"
    )

avg_ac1 = statistics.mean(ac1_vals)
avg_ac2 = statistics.mean(ac2_vals)
print(SEP)
print(f"  {'평균':<12}  {'':>10}  {avg_ac1:>16.4f}  {avg_ac2:>15.4f}  {kappa_interpretation(avg_ac1)}")

# 7. Krippendorff's Alpha
print()
print("[ 7. Krippendorff's Alpha (3명 전체) ]")
print(SEP)
print("  ※ 평가자 수와 결측값에 강건한 inter-rater reliability 지표.")
print("     ordinal: 등급 간 거리(순서) 반영 / nominal: 범주 일치 여부만 반영.")
print()

ka_nominal  = krippendorff_alpha(sets, common_keys_sorted, metric="nominal")
ka_ordinal  = krippendorff_alpha(sets, common_keys_sorted, metric="ordinal")
ka_interval = krippendorff_alpha(sets, common_keys_sorted, metric="interval")

print(f"  {'지표':<30}  {'값':>8}  {'해석'}")
print(f"  {'-'*30}  {'-'*8}  {'-'*20}")
print(f"  {'α nominal  (범주형)':<30}  {ka_nominal:>8.4f}  {kappa_interpretation(ka_nominal)}")
print(f"  {'α ordinal  (서열형) ★권장':<30}  {ka_ordinal:>8.4f}  {kappa_interpretation(ka_ordinal)}")
print(f"  {'α interval (등간형)':<30}  {ka_interval:>8.4f}  {kappa_interpretation(ka_interval)}")

# 지표 종합 비교
print()
print("[ 종합 비교: Kappa vs AC1 vs Krippendorff's Alpha ]")
print(SEP)
print("  ※ 평점이 2에 82% 편중 → Cohen's/Fleiss' Kappa는 Prevalence Paradox로 낮게 산출.")
print()
print(f"  {'지표':<35}  {'값':>8}  {'해석'}")
print(f"  {'-'*35}  {'-'*8}  {'-'*22}")

avg_k  = statistics.mean(cohen_kappa(
    [sets[a][k] for k in sorted(set(sets[a].keys()) & set(sets[b].keys()))],
    [sets[b][k] for k in sorted(set(sets[a].keys()) & set(sets[b].keys()))]
) for a, b in pairs)
avg_wk = statistics.mean(weighted_kappa(
    [sets[a][k] for k in sorted(set(sets[a].keys()) & set(sets[b].keys()))],
    [sets[b][k] for k in sorted(set(sets[a].keys()) & set(sets[b].keys()))]
) for a, b in pairs)

print(f"  {'Cohen κ (unweighted, 평균)':<35}  {avg_k:>8.4f}  {kappa_interpretation(avg_k)}")
print(f"  {'Cohen κ (linear weighted, 평균)':<35}  {avg_wk:>8.4f}  {kappa_interpretation(avg_wk)}")
print(f"  {'Fleiss κ (3명)':<35}  {fk:>8.4f}  {kappa_interpretation(fk)}")
print(f"  {'Gwet AC1 (unweighted, 평균)':<35}  {avg_ac1:>8.4f}  {kappa_interpretation(avg_ac1)}")
print(f"  {'Gwet AC2 (linear weighted, 평균)':<35}  {avg_ac2:>8.4f}  {kappa_interpretation(avg_ac2)}")
print(f"  {'Krippendorff α ordinal (3명)':<35}  {ka_ordinal:>8.4f}  {kappa_interpretation(ka_ordinal)}")
print()
print("  ※ 해석 기준 (모든 지표 공통)")
print("    < 0.20  : Slight   (거의 우연 수준)")
print("    0.20~0.40 : Fair     (낮은 일치)")
print("    0.40~0.60 : Moderate (보통 일치)")
print("    0.60~0.80 : Substantial (상당한 일치)")
print("    0.80~1.00 : Almost Perfect (거의 완벽)")

# 8. Rank별 평균 평점
print()
print("[ 8. Rank별 평균 평점 (3명 평균, 공통 항목) ]")
print(SEP)

rank_ratings = defaultdict(list)
for k in common_keys:
    rank = k[3]
    avg = (sets[1][k] + sets[2][k] + sets[3][k]) / 3
    rank_ratings[rank].append(avg)

print(f"  {'Rank':<6}  {'평균':>8}  {'중앙값':>8}  {'n':>5}")
print(f"  {'-'*6}  {'-'*8}  {'-'*8}  {'-'*5}")
for rank in sorted(rank_ratings):
    vals = rank_ratings[rank]
    print(f"  {rank:<6}  {statistics.mean(vals):>8.3f}  {statistics.median(vals):>8.3f}  {len(vals):>5}")

# 9. Precision@k / nDCG@k
print()
print("[ 9. Precision@k  /  nDCG@k  (relevant = 3명 평균 ≥ 1.5) ]")
print(SEP)

persona_items = defaultdict(list)
for k in common_keys:
    pid, tag, prod, rank = k
    avg = (sets[1][k] + sets[2][k] + sets[3][k]) / 3
    persona_items[(pid, tag)].append((rank, avg, prod))

# 전체 P@3 (스킵 포함 — 스킵된 것은 top3=all2 이므로 P@3=1.0)
all_p3 = []
for key, items in persona_items.items():
    items_s = sorted(items, key=lambda x: x[0])
    avgs3 = [it[1] for it in items_s[:3]]
    p3 = sum(1 for a in avgs3 if a >= 1.5) / 3
    all_p3.append((key, p3, avgs3))

print(f"  전체 60개 페르소나 기준 Precision@3 : {statistics.mean(v for _, v, _ in all_p3):.4f}")
print(f"    P@3 = 1.0  : {sum(1 for _, v, _ in all_p3 if v == 1.0)}개")
print(f"    P@3 = 0.667: {sum(1 for _, v, _ in all_p3 if abs(v - 0.667) < 0.01)}개")
print(f"    P@3 = 0.333: {sum(1 for _, v, _ in all_p3 if abs(v - 0.333) < 0.01)}개")
print(f"    P@3 = 0.0  : {sum(1 for _, v, _ in all_p3 if v == 0.0)}개")

# 4~5위 있는 페르소나만 P@5, nDCG
p3_full, p5_full, ndcg3_full, ndcg5_full = [], [], [], []
for key, items in persona_items.items():
    items_s = sorted(items, key=lambda x: x[0])
    ranks = [it[0] for it in items_s]
    if max(ranks) < 4:
        continue
    avgs = [it[1] for it in items_s]
    p3_full.append(sum(1 for a in avgs[:3] if a >= 1.5) / 3)
    p5_full.append(sum(1 for a in avgs[:5] if a >= 1.5) / 5)
    ndcg3_full.append(ndcg(avgs, 3))
    ndcg5_full.append(ndcg(avgs, 5))

print()
print(f"  4~5위 평가 완료 페르소나 ({len(p3_full)}개) 기준:")
print(f"  {'지표':<14}  {'값':>8}")
print(f"  {'-'*14}  {'-'*8}")
print(f"  {'Precision@3':<14}  {statistics.mean(p3_full):>8.4f}")
print(f"  {'Precision@5':<14}  {statistics.mean(p5_full):>8.4f}")
print(f"  {'nDCG@3':<14}  {statistics.mean(ndcg3_full):>8.4f}")
print(f"  {'nDCG@5':<14}  {statistics.mean(ndcg5_full):>8.4f}")

# 10. 카테고리별 평균 평점
print()
print("[ 10. product_tag별 평균 평점 (3명 평균, 공통 항목, 내림차순) ]")
print(SEP)

tag_ratings = defaultdict(list)
for k in common_keys:
    tag = k[1]
    avg = (sets[1][k] + sets[2][k] + sets[3][k]) / 3
    tag_ratings[tag].append(avg)

print(f"  {'태그':<22}  {'평균':>8}  {'n':>5}")
print(f"  {'-'*22}  {'-'*8}  {'-'*5}")
for tag in sorted(tag_ratings, key=lambda t: -statistics.mean(tag_ratings[t])):
    vals = tag_ratings[tag]
    print(f"  {tag:<22}  {statistics.mean(vals):>8.3f}  {len(vals):>5}")

# 11. P@3 < 1.0 페르소나 상세
print()
print("[ 11. Precision@3 < 1.0 페르소나 상세 ]")
print(SEP)
print(f"  {'페르소나':<16}  {'태그':<20}  {'P@3':>5}  {'top3 avg ratings'}")
print(f"  {'-'*16}  {'-'*20}  {'-'*5}  {'-'*30}")
for (pid, tag), p3, avgs3 in sorted(all_p3, key=lambda x: x[1]):
    if p3 >= 1.0:
        continue
    print(f"  {pid:<16}  {tag:<20}  {p3:>5.3f}  {[round(a, 2) for a in avgs3]}")

print()
print(SEP2)
print("  분석 완료")
print(SEP2)
