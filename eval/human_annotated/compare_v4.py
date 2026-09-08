"""
judge_v4 채점 vs 사람 3인 채점 비교 분석.

analyze_annotations.py 가 확인한 것 : 사람 3인끼리의 일치도 (rubric 신뢰도)
이 스크립트가 확인하는 것          : judge_v4 가 그 기준선에 얼마나 근접하는가

판정 규칙은 실행 전에 확정된 것이며 결과를 본 뒤 바꾸지 않는다.
  · 척도 접기        agreement.JUDGE_TO_HUMAN = {1:0, 2:1, 3:2, 4:2, 5:2}
  · Fold A / Fold B  avoid_violated 를 0으로 볼지 1로 볼지 두 값을 모두 보고한다
  · 성공/실패 판정   두 Fold 중 낮은 쪽(보수적인 값)을 쓴다
  · 민감도           |κ_A - κ_B| > 0.1 이면 "사람 라벨에 회피 조건 기준이 없었음"의 관측치

사용법:
    python compare_v4.py
    python compare_v4.py --judge-file judged_v5.jsonl --subset heldout
    python compare_v4.py --judge-file judged_v5.jsonl --subset dev
"""

import argparse
import random
import sys
import statistics
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from agreement import (
    RATINGS,
    FOLDS,
    JUDGE_TO_HUMAN,
    load_jsonl,
    fold_judge_score,
    cohen_kappa,
    weighted_kappa,
    fleiss_kappa,
    build_fleiss_matrix,
    kappa_interpretation,
    gwet_ac1,
    krippendorff_alpha,
)

BASE_DIR = Path(__file__).parent
RESULT_DIR = BASE_DIR / "result"

HUMAN_FILES = {
    1: RESULT_DIR / "annotated_results_1.jsonl",
    2: RESULT_DIR / "annotated_results_2.jsonl",
    3: RESULT_DIR / "annotated_results_3.jsonl",
}
SPLIT_FILE = RESULT_DIR / "split.json"

SEP = "─" * 74
SEP2 = "═" * 74

SENSITIVITY_THRESHOLD = 0.1  # 사전 확정


def key_fn(r):
    return (r["persona_id"], r["product_tag"], r["product_id"], r["rank"])


# ── 로드 ──────────────────────────────────────────────────────────────────────

_p = argparse.ArgumentParser()
_p.add_argument("--judge-file", default="judged_v4.jsonl")
_p.add_argument("--subset", choices=["all", "dev", "heldout"], default="all")
_args = _p.parse_args()

JUDGE_FILE = RESULT_DIR / _args.judge_file
if not JUDGE_FILE.exists():
    sys.exit(f"{JUDGE_FILE.name} 이 없습니다. 채점 스크립트를 먼저 실행하세요.")

human_sets = {
    fid: {key_fn(r): r["rating"] for r in load_jsonl(path)}
    for fid, path in HUMAN_FILES.items()
}
judge_records = {key_fn(r): r for r in load_jsonl(JUDGE_FILE)}

common = (
    set(human_sets[1]) & set(human_sets[2]) & set(human_sets[3]) & set(judge_records)
)
if _args.subset != "all":
    import json as _json
    if not SPLIT_FILE.exists():
        sys.exit(f"{SPLIT_FILE.name} 이 없습니다. --subset 을 쓰려면 분할을 먼저 만드세요.")
    with open(SPLIT_FILE, encoding="utf-8") as f:
        _split = _json.load(f)
    common &= {tuple(k) for k in _split[_args.subset]}
keys = sorted(common)
JUDGE_NAME = JUDGE_FILE.stem.replace("judged_", "judge_")

judge_folded = {
    fold: {
        k: fold_judge_score(
            judge_records[k]["score"], judge_records[k].get("gate_reason"), fold
        )
        for k in keys
    }
    for fold in FOLDS
}

print(SEP2)
print(f"  {_args.judge_file} vs 사람 3인 채점 비교   [subset={_args.subset}]")
print(SEP2)

# ── 0. 대상 ───────────────────────────────────────────────────────────────────

print()
print("[ 0. 대상 항목 ]")
print(SEP)
print(f"  사람 3인 공통       : {len(set(human_sets[1]) & set(human_sets[2]) & set(human_sets[3]))}개")
print(f"  {JUDGE_NAME} 채점 완료  : {len(judge_records)}개")
print(f"  4자 공통(비교 대상) : {len(keys)}개")

# ── 1. 점수 분포 ──────────────────────────────────────────────────────────────

print()
print(f"[ 1. {JUDGE_NAME} 원점수(1~5) 분포 ]")
print(SEP)
raw_dist = Counter(judge_records[k]["score"] for k in keys)
for s in range(1, 6):
    c = raw_dist.get(s, 0)
    print(f"  {s}점: {c:>4} ({c / len(keys) * 100:5.1f}%)", end="   ")
print()

print()
print("[ 1-b. 접기 후 분포 (사람 척도 0/1/2) ]")
print(SEP)
print(f"  {'구분':<16}  {'0점':>12}  {'1점':>12}  {'2점':>12}")
print(f"  {'-' * 16}  {'-' * 12}  {'-' * 12}  {'-' * 12}")
for fold in FOLDS:
    d = Counter(judge_folded[fold][k] for k in keys)
    row = "  ".join(f"{d.get(r, 0):>4}({d.get(r, 0) / len(keys) * 100:5.1f}%)" for r in RATINGS)
    print(f"  judge Fold {fold:<5}  {row}")
for fid in sorted(human_sets):
    d = Counter(human_sets[fid][k] for k in keys)
    row = "  ".join(f"{d.get(r, 0):>4}({d.get(r, 0) / len(keys) * 100:5.1f}%)" for r in RATINGS)
    print(f"  사람 {fid}          {row}")

# ── 2. 사람-사람 기준선 ───────────────────────────────────────────────────────

print()
print("[ 2. 사람-사람 기준선 (동일 항목 기준) ]")
print(SEP)
human_pairs = [(1, 2), (1, 3), (2, 3)]
hk, hwk, hac = [], [], []
print(f"  {'쌍':<14}  {'Po':>7}  {'κ':>9}  {'κ(w)':>9}  {'AC1':>9}  해석")
print(f"  {'-' * 14}  {'-' * 7}  {'-' * 9}  {'-' * 9}  {'-' * 9}  {'-' * 16}")
for a, b in human_pairs:
    ra = [human_sets[a][k] for k in keys]
    rb = [human_sets[b][k] for k in keys]
    po = sum(x == y for x, y in zip(ra, rb)) / len(keys)
    k_, w_, a_ = cohen_kappa(ra, rb), weighted_kappa(ra, rb), gwet_ac1(ra, rb)
    hk.append(k_); hwk.append(w_); hac.append(a_)
    print(f"  사람 {a} vs 사람 {b}  {po:>7.3f}  {k_:>9.4f}  {w_:>9.4f}  {a_:>9.4f}  {kappa_interpretation(k_)}")
human_k_min, human_k_max = min(hk), max(hk)
human_k_avg = statistics.mean(hk)
print(SEP)
print(f"  {'평균':<14}  {'':>7}  {human_k_avg:>9.4f}  {statistics.mean(hwk):>9.4f}  {statistics.mean(hac):>9.4f}  {kappa_interpretation(human_k_avg)}")
print(f"  사람-사람 κ 범위 : {human_k_min:.4f} ~ {human_k_max:.4f}   ← judge가 진입해야 할 구간")

# ── 3. judge vs 사람 (Fold별) ─────────────────────────────────────────────────

print()
print(f"[ 3. {JUDGE_NAME} vs 사람 (Pairwise) ]")
print(SEP)
fold_avg_kappa = {}
for fold in FOLDS:
    jf = judge_folded[fold]
    ks, ws, acs = [], [], []
    print(f"  ── Fold {fold} " + ("(avoid_violated → 0)" if fold == "A" else "(avoid_violated → 1)"))
    print(f"     {'쌍':<16}  {'Po':>7}  {'κ':>9}  {'κ(w)':>9}  {'AC1':>9}  해석")
    for fid in sorted(human_sets):
        rj = [jf[k] for k in keys]
        rh = [human_sets[fid][k] for k in keys]
        po = sum(x == y for x, y in zip(rj, rh)) / len(keys)
        k_, w_, a_ = cohen_kappa(rj, rh), weighted_kappa(rj, rh), gwet_ac1(rj, rh)
        ks.append(k_); ws.append(w_); acs.append(a_)
        print(f"     judge vs 사람 {fid}  {po:>7.3f}  {k_:>9.4f}  {w_:>9.4f}  {a_:>9.4f}  {kappa_interpretation(k_)}")
    avg = statistics.mean(ks)
    fold_avg_kappa[fold] = avg
    print(f"     {'평균':<16}  {'':>7}  {avg:>9.4f}  {statistics.mean(ws):>9.4f}  {statistics.mean(acs):>9.4f}  {kappa_interpretation(avg)}")
    print()

# ── 4. 다수결 대비 정확도 + 혼동행렬 ──────────────────────────────────────────

print("[ 4. 사람 다수결 대비 정확도 · 혼동행렬 ]")
print(SEP)
majority = {}
for k in keys:
    votes = Counter(human_sets[fid][k] for fid in human_sets)
    top, cnt = votes.most_common(1)[0]
    majority[k] = top if cnt >= 2 else None
maj_keys = [k for k in keys if majority[k] is not None]

for fold in FOLDS:
    jf = judge_folded[fold]
    hit = sum(jf[k] == majority[k] for k in maj_keys)
    print(f"  Fold {fold} 정확도 : {hit}/{len(maj_keys)} = {hit / len(maj_keys) * 100:.1f}%")

print()
print(f"  혼동행렬 (Fold A · 행=다수결, 열={JUDGE_NAME})")
print(f"    {'':>10}  {'judge=0':>9}  {'judge=1':>9}  {'judge=2':>9}")
cm = defaultdict(int)
for k in maj_keys:
    cm[(majority[k], judge_folded["A"][k])] += 1
for t in RATINGS:
    row = "  ".join(f"{cm[(t, p)]:>9}" for p in RATINGS)
    print(f"    {'정답=' + str(t):>10}  {row}")

off_down = sum(cm[(t, p)] for t in RATINGS for p in RATINGS if p < t)
off_up = sum(cm[(t, p)] for t in RATINGS for p in RATINGS if p > t)
print()
print(f"  하향 오분류(judge가 더 낮게) : {off_down}건")
print(f"  상향 오분류(judge가 더 높게) : {off_up}건")
print("  ※ 한 방향으로 크게 쏠리면 캘리브레이션 오프셋이 남아 있다는 뜻이다.")

# ── 5. judge를 4번째 평가자로 ─────────────────────────────────────────────────

print()
print("[ 5. judge를 4번째 평가자로 포함 ]")
print(SEP)
h_only = {f"h{fid}": {k: human_sets[fid][k] for k in keys} for fid in human_sets}
print(f"  {'지표':<34}  {'사람 3인':>10}  {'+Fold A':>10}  {'+Fold B':>10}")
print(f"  {'-' * 34}  {'-' * 10}  {'-' * 10}  {'-' * 10}")
fk_h = fleiss_kappa(build_fleiss_matrix(keys, h_only))
ka_h = krippendorff_alpha(h_only, keys, metric="ordinal")
fk_f, ka_f = {}, {}
for fold in FOLDS:
    withj = {**h_only, "judge": judge_folded[fold]}
    fk_f[fold] = fleiss_kappa(build_fleiss_matrix(keys, withj))
    ka_f[fold] = krippendorff_alpha(withj, keys, metric="ordinal")
print(f"  {'Fleiss Kappa':<34}  {fk_h:>10.4f}  {fk_f['A']:>10.4f}  {fk_f['B']:>10.4f}")
print(f"  {'Krippendorff Alpha (ordinal)':<34}  {ka_h:>10.4f}  {ka_f['A']:>10.4f}  {ka_f['B']:>10.4f}")

# ── 6. gate_reason ────────────────────────────────────────────────────────────

print()
print("[ 6. 게이트 발동 현황 ]")
print(SEP)
gate_counts = Counter(judge_records[k].get("gate_reason") for k in keys)
for reason in ("category_mismatch", "avoid_violated", None):
    c = gate_counts.get(reason, 0)
    label = reason or "(게이트 미발동)"
    print(f"  {label:<24} : {c:>4}건")
    if reason and c:
        hd = Counter(majority[k] for k in keys if judge_records[k].get("gate_reason") == reason and majority[k] is not None)
        print(f"      └ 해당 항목에 사람 다수결이 준 라벨 : {dict(sorted(hd.items()))}")

avoid_keys = [k for k in keys if judge_records[k].get("gate_reason") == "avoid_violated"]
if avoid_keys:
    print()
    print("  avoid_violated 발동 건 — evidence 전수 (근거 인용이 없으면 오발동)")
    for k in avoid_keys:
        r = judge_records[k]
        ev = (r.get("judgement") or {}).get("avoid_evidence", "")
        print(f"    {r['persona_id']} {r['product_id']} : {ev}")

# ── 7. Fold 민감도 · 성공 판정 ────────────────────────────────────────────────

print()
print("[ 7. Fold 민감도 및 판정 ]")
print(SEP)
diff = abs(fold_avg_kappa["A"] - fold_avg_kappa["B"])
conservative = min(fold_avg_kappa["A"], fold_avg_kappa["B"])
print(f"  Fold A 평균 κ : {fold_avg_kappa['A']:.4f}")
print(f"  Fold B 평균 κ : {fold_avg_kappa['B']:.4f}")
print(f"  |차이|        : {diff:.4f}  (임계값 {SENSITIVITY_THRESHOLD})")
if diff <= SENSITIVITY_THRESHOLD:
    print("  → 접기 선택이 결론을 바꾸지 않는다.")
else:
    print("  → 사람 라벨에 회피 조건 기준이 없었음을 시사한다 (관측치로 보고).")

print()
print("  ── 부트스트랩 95% 신뢰구간 (항목 재표집, B=2000)")
_rng = random.Random(7)
_B = 2000


def _mean_kappa(sample_keys):
    jf = judge_folded["A"]
    return statistics.mean(
        cohen_kappa([jf[k] for k in sample_keys], [human_sets[fid][k] for k in sample_keys])
        for fid in sorted(human_sets)
    )


def _human_mean_kappa(sample_keys):
    return statistics.mean(
        cohen_kappa([human_sets[a][k] for k in sample_keys], [human_sets[b][k] for k in sample_keys])
        for a, b in human_pairs
    )


def _ci(fn):
    vals = []
    for _ in range(_B):
        s = [keys[_rng.randrange(len(keys))] for _ in keys]
        try:
            vals.append(fn(s))
        except Exception:
            pass
    vals.sort()
    return vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals))]


j_lo, j_hi = _ci(_mean_kappa)
h_lo, h_hi = _ci(_human_mean_kappa)
print(f"     judge  κ = {fold_avg_kappa['A']:.4f}   CI [{j_lo:.4f}, {j_hi:.4f}]   폭 {j_hi - j_lo:.4f}")
print(f"     사람   κ = {human_k_avg:.4f}   CI [{h_lo:.4f}, {h_hi:.4f}]   폭 {h_hi - h_lo:.4f}")
if j_hi < h_lo:
    print("     → 두 구간이 겹치지 않는다. judge가 사람 수준에 못 미침이 분명하다.")
else:
    print("     → 두 구간이 겹친다. 이 표본 크기로는 차이를 단정할 수 없다.")
print(f"     ※ CI 폭이 넓은 것은 n={len(keys)} 에 라벨이 한 등급으로 쏠려 있기 때문이다.")
print("       채점기 버전 간 비교도 같은 이유로 불안정하다.")

print()
print(f"  판정에 사용하는 값(낮은 쪽) : {conservative:.4f}")
print(f"  사람-사람 κ 범위            : {human_k_min:.4f} ~ {human_k_max:.4f}")
if conservative >= human_k_min:
    verdict = f"성공 — {JUDGE_NAME}가 사람-사람 일치도 범위에 진입"
elif conservative >= human_k_min - 0.1:
    verdict = "경계 — 범위 하단에 근접하나 진입하지 못함"
else:
    verdict = "미달 — 절대 품질 지표로 쓸 수 없음. 용도를 상대 비교로 제한할 것"
print(f"  판정 : {verdict}")

# ── 8. 카테고리별 분해 ────────────────────────────────────────────────────────

print()
print("[ 8. 카테고리별 분해 ]")
print(SEP)
by_cat = defaultdict(list)
for k in keys:
    by_cat[judge_records[k]["product_tag"]].append(k)

print(f"  {'카테고리':<16} {'건수':>4}  {'judge평균':>9}  {'사람평균':>9}  {'5점':>4}  {'UNK(pref)':>9}  {'CFL(pref)':>9}")
print(f"  {'-' * 16} {'-' * 4}  {'-' * 9}  {'-' * 9}  {'-' * 4}  {'-' * 9}  {'-' * 9}")
for cat in sorted(by_cat, key=lambda c: -len(by_cat[c])):
    ks_ = by_cat[cat]
    raw = [judge_records[k]["score"] for k in ks_]
    hum = [statistics.mean(human_sets[f][k] for f in human_sets) for k in ks_]
    n5 = sum(s == 5 for s in raw)
    js = [judge_records[k].get("judgement") or {} for k in ks_]
    unk = sum(j.get("preference") == "UNKNOWN" for j in js)
    cfl = sum(j.get("preference") == "CONFLICT" for j in js)
    print(f"  {cat:<16} {len(ks_):>4}  {statistics.mean(raw):>9.3f}  {statistics.mean(hum):>9.3f}  {n5:>4}  {unk:>9}  {cfl:>9}")

# ── 9. 축별 판정 분포 ─────────────────────────────────────────────────────────

print()
print("[ 9. 축별 판정 분포 (게이트 미발동 건 기준) ]")
print(SEP)
judged = [judge_records[k]["judgement"] for k in keys if judge_records[k].get("judgement")]
print(f"  대상 {len(judged)}건")
print(f"  core_need_met  : {Counter(j['core_need_met'] for j in judged)}")
for axis in ("preference", "condition"):
    d = Counter(j[axis] for j in judged)
    total = sum(d.values())
    parts = "  ".join(f"{v}={d.get(v, 0)}({d.get(v, 0) / total * 100:.0f}%)" for v in ("MATCH", "UNKNOWN", "CONFLICT"))
    print(f"  {axis:<14} : {parts}")
print()
print("  ※ CONFLICT 비율이 비정상적으로 높으면 '대응 축 없음'을 '불일치'로")
print("     오해하고 있다는 신호다. 점수에는 영향이 없다(가산 0으로 동일).")

print()
print(SEP2)
print("  분석 완료")
print(SEP2)
