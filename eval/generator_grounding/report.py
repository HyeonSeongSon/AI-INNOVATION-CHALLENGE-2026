"""
메시지 생성기 근거 개선 — 보고서 · 채택 판정 (사전 등록 파일, baseline_hashes.json 으로 잠근다).

채택 판단은 보류 표본(holdout, 9단계 확장 시 holdout + holdout_ext)으로만 한다. 원본 70건(insample)은 참고.

기준 1 (주 지표 감소)
    - 짝 비교: LLM 판정(양성 = 양성 + 재검토). 불일치 쌍 < 25 이면 정확 이항검정, 아니면 McNemar(연속성 보정). α = 0.029.
    - 사람 가중 추정: 조건(전 · 후) × LLM 판정(양성 · 재검토 · 음성) 층의 크기로 사람 확인 비율을 가중.
      수정 후 / 수정 전 비율의 층별 부트스트랩 97.1% 신뢰구간(시드 20261003, 1만 회).
      확정: 상한 ≤ 0.5 · 시사: 점추정 ≤ 0.5 이고 상한 > 0.5 · 미달: 점추정 > 0.5
    - 판정: 충족 = 확정 이고 p < 0.029. 충족이 아니고 점추정 ≤ 0.5 → 확장(1회). 점추정 > 0.5 → 미달.
      확장 뒤(--with-extension): 충족 / 시사(점추정 ≤ 0.5) / 미달.
기준 2: 날짜 · 판매인기 · 변화 · 검증 · 브랜드 사실 표현(정규식, 메시지 수)이 줄어드는지 — 방향만, 목적별 함께.
기준 3 (비열등, 짝 차이 부트스트랩 단측 95% 하한, 시드 20261003):
    판정기 통과율(회차 평균) > −0.15 · personalization · cta_clarity · tone 평균 > −0.3 ·
    목적 충실도(LLM, 보류 표본 전체) > −0.15 · 형식 위반 증가 ≤ 2 · 수정 후 CTA 존재율 ≥ 95%.
기준 4 (점검, 증거 아님): 수정 후 DB 등록 시각 날짜 0건.
기준 5: LLM 측정의 정밀도 · 재현율(사람 기준, 층 가중)을 조건별로 보고.
정규식과 LLM 이 어긋나면 정규식은 교차 확인용이고 판정은 LLM 과 사람으로 한다.

사용법:
    python report.py                    # 보류 표본 + 표본 내
    python report.py --with-extension   # 9단계: holdout + holdout_ext 합쳐서
"""

import argparse
import csv
import json
import math
import random
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import gg_common as gg
from gg_common import load_jsonl

ALPHA = 0.029
CI_LEVEL = 0.971
BOOT_SEED = 20261003
BOOT_REPS = 10_000
NI_MARGIN = {"pass_rate": -0.15, "personalization": -0.3, "cta_clarity": -0.3, "tone": -0.3, "purpose_conveyed": -0.15}
FORMAT_MAX_INCREASE = 2
CTA_MIN = 0.95
STRATA = ("양성", "재검토", "음성")
REGEX_KEYS = ("date_unsupported", "test_unsupported", "popularity_unsupported", "change_unsupported",
              "verified_unsupported", "brand_fact_unsupported")
HUMAN_DIR = gg.RESULT / "human"


# ── 읽기 ─────────────────────────────────────────────────────────────────────

def measure(set_name: str, tag: str) -> dict[str, dict[str, Any]]:
    path = gg.RESULT / set_name / tag / "measure.jsonl"
    return {r["item_id"]: r for r in load_jsonl(path)} if path.exists() else {}


def regen_meta(set_name: str, tag: str) -> dict[str, Any]:
    path = gg.RESULT / set_name / tag / "regen_meta.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def human_rows() -> list[dict[str, Any]]:
    """사람 확인 결과 + 대응표(조건 · 항목 · 층). 대응표는 확인 도구가 읽지 않는 파일이다."""
    map_path, csv_path = HUMAN_DIR / "sample_map.json", HUMAN_DIR / "human_check.csv"
    if not (map_path.exists() and csv_path.exists()):
        return []
    mapping = json.loads(map_path.read_text(encoding="utf-8"))
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        checked = {r["code"]: r for r in csv.DictReader(f)}
    out = []
    for code, m in mapping.items():
        r = checked.get(code, {})
        val = (r.get("unsupported_claim(O/X)") or "").strip().upper()
        out.append({**m, "code": code, "human": val if val in ("O", "X") else None,
                    "purpose_human": (r.get("purpose_conveyed(O/X)") or "").strip().upper() or None})
    return out


# ── 통계 ─────────────────────────────────────────────────────────────────────

def paired_test(b: int, c: int) -> dict[str, Any]:
    """b = 전 양성 · 후 음성, c = 전 음성 · 후 양성."""
    n = b + c
    if n == 0:
        return {"method": "불일치 없음", "b": b, "c": c, "p": 1.0}
    if n < 25:
        k = min(b, c)
        p = min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)
        return {"method": "정확 이항검정", "b": b, "c": c, "p": p}
    x = (abs(b - c) - 1) ** 2 / n
    return {"method": "McNemar(연속성 보정)", "b": b, "c": c, "p": math.erfc(math.sqrt(x / 2))}


def percentile(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    if not xs:
        return float("nan")
    pos = (len(xs) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def weighted_rate(sizes: dict[str, int], samples: dict[str, list[int]], fallback: dict[str, float]) -> float:
    total = sum(sizes.values())
    if not total:
        return float("nan")
    s = 0.0
    for h, n_h in sizes.items():
        vals = samples.get(h, [])
        p = (sum(vals) / len(vals)) if vals else fallback[h]
        s += n_h * p
    return s / total


def human_weighted(cond_sizes: dict[str, dict[str, int]], cond_samples: dict[str, dict[str, list[int]]]) -> dict[str, Any]:
    """조건별 사람 가중 비율과 수정 후 / 수정 전 비율의 층별 부트스트랩 신뢰구간."""
    fallback = {"양성": 1.0, "재검토": 1.0, "음성": 0.0}  # 사람 확인이 없는 층은 LLM 판정으로 대신한다(표시함)
    point = {c: weighted_rate(cond_sizes[c], cond_samples[c], fallback) for c in ("before", "after")}
    ratio = point["after"] / point["before"] if point["before"] else float("nan")
    rng = random.Random(BOOT_SEED)
    ratios = []
    for _ in range(BOOT_REPS):
        rates = {}
        for c in ("before", "after"):
            res = {h: [rng.choice(v) for _ in v] for h, v in cond_samples[c].items() if v}
            rates[c] = weighted_rate(cond_sizes[c], res, fallback)
        if rates["before"]:
            ratios.append(rates["after"] / rates["before"])
    lo_q, hi_q = (1 - CI_LEVEL) / 2, 1 - (1 - CI_LEVEL) / 2
    lo, hi = percentile(ratios, lo_q), percentile(ratios, hi_q)
    if not (ratio == ratio):
        grade = "판정 불가(수정 전 비율 0)"
    elif hi <= 0.5:
        grade = "확정"
    elif ratio <= 0.5:
        grade = "시사"
    else:
        grade = "미달"
    missing = {c: [h for h, n in cond_sizes[c].items() if n and not cond_samples[c].get(h)] for c in ("before", "after")}
    return {"rate": point, "ratio": ratio, "ci": (lo, hi), "grade": grade, "unchecked_strata": missing}


def paired_boot_lower(diffs: list[float]) -> tuple[float, float]:
    """짝 차이 평균과 부트스트랩 단측 95% 하한."""
    if not diffs:
        return float("nan"), float("nan")
    rng = random.Random(BOOT_SEED)
    means = []
    n = len(diffs)
    for _ in range(BOOT_REPS):
        means.append(sum(diffs[rng.randrange(n)] for _ in range(n)) / n)
    return sum(diffs) / n, percentile(means, 0.05)


def pr_recall(sizes: dict[str, int], samples: dict[str, list[int]]) -> dict[str, Any]:
    est = {h: sizes.get(h, 0) * (sum(v) / len(v)) for h, v in samples.items() if v}
    pos_n = sizes.get("양성", 0) + sizes.get("재검토", 0)
    tp = est.get("양성", 0) + est.get("재검토", 0)
    total_pos = tp + est.get("음성", 0)
    checked = all(samples.get(h) for h in STRATA if sizes.get(h))
    return {"precision": (tp / pos_n) if pos_n and checked else None,
            "recall": (tp / total_pos) if total_pos and checked else None,
            "by_stratum": {h: (f"{sum(v)}/{len(v)}" if v else "-") for h, v in samples.items()}}


# ── 집계 ─────────────────────────────────────────────────────────────────────

def item_judge(r: dict[str, Any]) -> dict[str, float] | None:
    runs = [j for j in r.get("judge", []) if not j.get("missing")]
    if not runs:
        return None
    out = {"pass_rate": sum(1.0 if j["passed"] else 0.0 for j in runs) / len(runs)}
    for k in ("personalization", "cta_clarity", "tone", "accuracy"):
        out[k] = sum(j["scores"][k] for j in runs) / len(runs)
    return out


def section(sets: list[str], L: list[str], decisive: bool, with_ext: bool) -> dict[str, Any]:
    before = {k: v for s in sets for k, v in measure(s, "before").items()}
    after = {k: v for s in sets for k, v in measure(s, "after").items()}
    common = sorted(set(before) & set(after))
    res: dict[str, Any] = {"n_pairs": len(common)}
    L += [f"- 짝 수: {len(common)} (수정 전 {len(before)} · 수정 후 {len(after)})", ""]
    if not common:
        L += ["측정 결과 없음", ""]
        return res

    # 기준 1 — LLM 짝 비교
    ver = [i for i in common if before[i]["verifier"] and after[i]["verifier"]]
    if ver:
        pb = {i: before[i]["verifier"]["llm_positive"] for i in ver}
        pa = {i: after[i]["verifier"]["llm_positive"] for i in ver}
        b = sum(1 for i in ver if pb[i] and not pa[i])
        c = sum(1 for i in ver if not pb[i] and pa[i])
        test = paired_test(b, c)
        cls_b = Counter(before[i]["verifier"]["class"] for i in ver)
        cls_a = Counter(after[i]["verifier"]["class"] for i in ver)
        res["llm"] = {"before": sum(pb.values()) / len(ver), "after": sum(pa.values()) / len(ver), "test": test}
        L += ["### 기준 1 — 주 지표 (근거 없는 상품 사실 주장이 있는 메시지 비율)", "",
              "| | 수정 전 | 수정 후 |", "|---|---|---|",
              f"| LLM 양성(재검토 포함) | {sum(pb.values())}/{len(ver)} ({res['llm']['before']:.1%}) | "
              f"{sum(pa.values())}/{len(ver)} ({res['llm']['after']:.1%}) |",
              f"| LLM 판정 층 (양성 · 재검토 · 음성) | {cls_b['양성']} · {cls_b['재검토']} · {cls_b['음성']} | "
              f"{cls_a['양성']} · {cls_a['재검토']} · {cls_a['음성']} |", "",
              f"- 짝 비교: {test['method']} — 개선 {b} · 악화 {c}, p = {test['p']:.4f} (α = {ALPHA})", ""]
    else:
        L += ["- LLM 근거 검증 결과 없음", ""]

    if decisive:
        hr = [h for h in human_rows() if h["set"] in sets and h["human"] is not None]
        sizes = {c: {h: Counter((before if c == "before" else after)[i]["verifier"]["class"] for i in ver)[h]
                     for h in STRATA} for c in ("before", "after")} if ver else {}
        samples: dict[str, dict[str, list[int]]] = {"before": defaultdict(list), "after": defaultdict(list)}
        for h in hr:
            samples[h["tag"]][h["stratum"]].append(1 if h["human"] == "O" else 0)
        if ver and hr:
            hw = human_weighted(sizes, samples)
            res["human"] = hw
            p_ok = res["llm"]["test"]["p"] < ALPHA
            if hw["grade"] == "확정" and p_ok:
                decision = "충족"
            elif hw["ratio"] == hw["ratio"] and hw["ratio"] <= 0.5:
                decision = "시사" if with_ext else "확장(9단계, 1회)"
            else:
                decision = "미달"
            res["decision"] = decision
            lo, hi = hw["ci"]
            L += ["**사람 가중 추정 (층 크기로 가중)**", "",
                  "| | 수정 전 | 수정 후 |", "|---|---|---|",
                  f"| 사람 기준 비율 | {hw['rate']['before']:.1%} | {hw['rate']['after']:.1%} |", "",
                  f"- 수정 후 / 수정 전 = {hw['ratio']:.2f}, 층별 부트스트랩 {CI_LEVEL:.1%} 신뢰구간 [{lo:.2f}, {hi:.2f}]"
                  f" → **{hw['grade']}**",
                  f"- 사람 확인이 없는 층(LLM 판정으로 대신함): {hw['unchecked_strata']}",
                  f"- **기준 1 판정: {decision}** (충족 = 확정 이고 p < {ALPHA})", ""]
            L += ["### 기준 5 — LLM 측정의 정밀도 · 재현율 (사람 기준, 층 가중)", "",
                  "| 조건 | 정밀도 | 재현율 | 층별 사람 O/확인 |", "|---|---|---|---|"]
            for cnd in ("before", "after"):
                pr = pr_recall(sizes[cnd], samples[cnd])
                fmt = lambda x: "-" if x is None else f"{x:.0%}"  # noqa: E731
                L.append(f"| {'수정 전' if cnd == 'before' else '수정 후'} | {fmt(pr['precision'])} | {fmt(pr['recall'])} | "
                         f"{pr['by_stratum']} |")
            L.append("")
        else:
            L += ["- 사람 확인 결과 없음 — 기준 1 판정 보류", ""]

    # 기준 2 — 정규식 지표 (교차 확인)
    L += ["### 기준 2 — 유형별 근거 없는 표현 (정규식, 해당 메시지 수, 교차 확인용)", "",
          "| 지표 | 수정 전 | 수정 후 |", "|---|---|---|"]
    for k in REGEX_KEYS:
        L.append(f"| {k} | {sum(1 for i in common if before[i]['regex'][k])} | {sum(1 for i in common if after[i]['regex'][k])} |")
    L += ["", "**목적별 (정규식 any · LLM 양성)**", "", "| 목적 | n | 정규식 전 → 후 | LLM 전 → 후 |", "|---|---|---|---|"]
    for p in sorted({before[i]["purpose"] for i in common}):
        ids = [i for i in common if before[i]["purpose"] == p]
        rb = sum(before[i]["regex"]["any_unsupported"] for i in ids)
        ra = sum(after[i]["regex"]["any_unsupported"] for i in ids)
        lb = sum(1 for i in ids if before[i]["verifier"] and before[i]["verifier"]["llm_positive"])
        la = sum(1 for i in ids if after[i]["verifier"] and after[i]["verifier"]["llm_positive"])
        L.append(f"| {p} | {len(ids)} | {rb} → {ra} | {lb} → {la} |")
    L.append("")

    # 기준 3 — 비열등
    L += ["### 기준 3 — 비열등 (짝 차이, 부트스트랩 단측 95% 하한)", "",
          "| 지표 | 수정 전 | 수정 후 | 차이 | 단측 95% 하한 | 여유 | 판정 |", "|---|---|---|---|---|---|---|"]
    ni_ok = True
    jb = {i: item_judge(before[i]) for i in common}
    ja = {i: item_judge(after[i]) for i in common}
    jc = [i for i in common if jb[i] and ja[i]]
    for k in ("pass_rate", "personalization", "cta_clarity", "tone"):
        if not jc:
            L.append(f"| {k} | - | - | - | - | {NI_MARGIN[k]} | 판정기 결과 없음 |")
            ni_ok = False if decisive else ni_ok
            continue
        diffs = [ja[i][k] - jb[i][k] for i in jc]
        mean, lower = paired_boot_lower(diffs)
        ok = lower > NI_MARGIN[k]
        ni_ok &= ok
        mb = sum(jb[i][k] for i in jc) / len(jc)
        ma = sum(ja[i][k] for i in jc) / len(jc)
        L.append(f"| {k} | {mb:.3f} | {ma:.3f} | {mean:+.3f} | {lower:+.3f} | {NI_MARGIN[k]} | {'통과' if ok else '미달'} |")
    pc = [i for i in ver] if ver else []
    if pc:
        diffs = [(after[i]["verifier"]["purpose_conveyed"] == "O") - (before[i]["verifier"]["purpose_conveyed"] == "O")
                 for i in pc]
        mean, lower = paired_boot_lower([float(d) for d in diffs])
        ok = lower > NI_MARGIN["purpose_conveyed"]
        ni_ok &= ok
        L.append(f"| purpose_conveyed(LLM) | {sum(before[i]['verifier']['purpose_conveyed'] == 'O' for i in pc)}/{len(pc)} | "
                 f"{sum(after[i]['verifier']['purpose_conveyed'] == 'O' for i in pc)}/{len(pc)} | {mean:+.3f} | {lower:+.3f} | "
                 f"{NI_MARGIN['purpose_conveyed']} | {'통과' if ok else '미달'} |")
    fv = lambda r: (not r["format"]["json_ok"]) or r["format"]["title_over"] or r["format"]["body_over"]  # noqa: E731
    fb, fa = sum(fv(before[i]) for i in common), sum(fv(after[i]) for i in common)
    cta = sum(after[i]["format"]["cta_last"] for i in common) / len(common)
    ok_f, ok_c = fa - fb <= FORMAT_MAX_INCREASE, cta >= CTA_MIN
    ni_ok &= ok_f and ok_c
    L += [f"| 형식 위반 수 | {fb} | {fa} | {fa - fb:+d} | - | +{FORMAT_MAX_INCREASE} | {'통과' if ok_f else '미달'} |",
          f"| 수정 후 CTA 존재율 | {sum(before[i]['format']['cta_last'] for i in common) / len(common):.0%} | {cta:.0%} | - | - | "
          f"≥{CTA_MIN:.0%} | {'통과' if ok_c else '미달'} |", ""]
    res["noninferior"] = ni_ok
    L += ["- 판정기는 23개 필드만 본다. 생성기가 쓴 finish_type 같은 필드는 수정 전 · 후 모두 감점된다(상쇄).", ""]

    # 기준 4 · 기술 지표
    created = sum(after[i]["regex"]["date_from_created_at"] for i in common)
    res["sanity_created_at"] = created
    L += [f"### 기준 4 — 점검 (증거 아님): 수정 후 DB 등록 시각 날짜 {created}건 "
          f"(수정 전 {sum(before[i]['regex']['date_from_created_at'] for i in common)}건)", ""]
    if ver:
        sb = sum(before[i]["verifier"]["n_supported"] for i in ver) / len(ver)
        sa = sum(after[i]["verifier"]["n_supported"] for i in ver) / len(ver)
        L += [f"### 기술 지표 (판정 기준 아님): 근거 있는 구체 주장 수 평균 {sb:.2f} → {sa:.2f}, "
              f"본문 길이 평균 {sum(before[i]['format']['body_len'] for i in common) / len(common):.0f} → "
              f"{sum(after[i]['format']['body_len'] for i in common) / len(common):.0f}자", ""]
    return res


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-extension", action="store_true")
    args = parser.parse_args()
    holdout_sets = ["holdout", "holdout_ext"] if args.with_extension else ["holdout"]

    L = ["# 메시지 생성기 근거 개선 — 전후 비교 보고서", "",
         f"- 작성: {datetime.now(timezone.utc).isoformat()} · 성과 문구는 '프롬프트 · 입력 개선 전체'(묶음 개입)",
         f"- 기준: α = {ALPHA}(Pocock식, 순차 확인 대비) · 신뢰구간 {CI_LEVEL:.1%} · 부트스트랩 시드 {BOOT_SEED} · {BOOT_REPS}회", ""]

    # 사전 등록 · 게이트 무결성
    base = gg.load_baseline()
    prereg = gg.prereg_status()
    gate_now = gg.file_hashes(gg.GATE_FILES)
    gate_ok = gate_now == base["gate"]
    after_meta = regen_meta("holdout", "after")
    first_after = after_meta.get("generated_from")
    late = [e for e in gg.amendments_entries() if e.get("new_hashes") and first_after and e["at"] > first_after]
    exploratory = any(v == "기록 없는 변경(탐색적)" for v in prereg["status"].values()) or bool(late)
    L += ["## 무결성", "",
          f"- backend 게이트 파일 4개: {'기준과 같음' if gate_ok else '기준과 다름 — 확인 필요'}",
          f"- 사전 등록 파일: {prereg['status']}",
          f"- 보류 표본 수정 후 생성 시작 뒤의 정의 수정: {len(late)}건",
          f"- **결과 성격: {'탐색적(채택 판단에 쓰지 않음)' if exploratory else '사전 등록대로'}**", ""]

    L += [f"## 보류 표본 ({' + '.join(holdout_sets)}) — 채택 판단", ""]
    res = section(holdout_sets, L, decisive=True, with_ext=args.with_extension)
    adopt = (not exploratory and gate_ok and res.get("decision") == "충족" and res.get("noninferior")
             and res.get("sanity_created_at") == 0)
    L += ["## 채택 판정", "",
          f"- 기준 1: {res.get('decision', '보류')} · 기준 3(비열등): {'통과' if res.get('noninferior') else '미달 또는 보류'} · "
          f"기준 4(점검): {res.get('sanity_created_at')}건",
          f"- **채택: {'예' if adopt else '아니오(또는 보류)'}** — 기준 2는 방향 보고, 기준 5는 측정 신뢰도 보고", ""]

    L += ["## 원본 70건 (표본 내 — 수정할 때 본 사례, 참고)", ""]
    section(["insample"], L, decisive=False, with_ext=False)

    L += ["## 한계", "",
          "- 묶음 개입: 입력 필터 · 사실 규칙 · 목적별 수정 · 브랜드 톤 지시가 한꺼번에 바뀌어 개별 효과는 구분되지 않는다.",
          "- 눈가림이 완전하지 않다: 수정 후 메시지는 날짜 · 인기 표현이 사라져 내용으로 구분될 수 있다.",
          "- 판정기는 23개 필드만 본다(카테고리별 필드는 전후 모두 감점).",
          "- 보류 표본의 페르소나는 원본과 겹쳐 쓰일 수 있다. 목적 분포가 표본 내(무작위)와 보류(각 10건)가 다르다.",
          "- 확장(9단계)에서 상품을 다시 썼다면 독립성이 약하다.", ""]
    out = gg.RESULT / "report.md"
    out.write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    print(f"→ {out}")


if __name__ == "__main__":
    main()
