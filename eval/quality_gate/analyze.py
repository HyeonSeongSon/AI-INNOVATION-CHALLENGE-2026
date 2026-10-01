"""
저장된 원시 결과에서 보고서 표를 만든다 → result/<run>/report.md. LLM · 네트워크 호출 없음(재현성).
플랜: wiki/dev-tasks/message-quality-gate-defect-injection-plan-20260929.md (8차 검토 반영판)

보고서 앞부분은 **사전 등록한 주 결론 4개**다. 헤드라인은 여기서만 고른다. 나머지는 모두 보조 결과다.
    1. 탐지 — D1: 서로 다른 문구 단위 1·2단계 탐지율(run_d1). D2 · D4: C 원본이 1·2단계를 통과한 원본만,
       운영 설정(low, override 켬)의 3단계 불통과 확률과 C 대비 원본별 차이(D − C).
       대조군 오탐: C 원본 불통과 확률(판정 불가(톤) 포함 / 제외, 전수 / ANN, 기능성 표시 분리).
    2. 점수 신호 — D2 · D4 목표 항목 하락률(D 회차 a · C 회차 b 모든 쌍 중 D < C) −
       기준선(C 회차 순서쌍 i≠j 중 Xᵢ < Xⱼ). 한 방향으로 통일.
    3. 2단계 우회 경로 — override: 조건부 해제 비율 + 표적 시험(존재 증명). 문장 틀 효과: 맨 문구 × 실제 틀 2×2.
    4. 판정 설정 — low 대 minimal · low 대 medium 불통과 확률 짝 차이(반복 1~3회차로 맞춤), 지연 중앙값.

CI 규칙(한 곳): D1 주 지표 = 서로 다른 문구 단위 Wilson. 불통과 확률 · 짝 차이 = 페르소나 단위 군집
부트스트랩(페르소나를 최대 2회 쓰기 때문). 보조 1회 판정 비율 = Wilson. 평균 점수 차이 · McNemar = 보조.
2단계 주 판정은 전수 기준, ANN 은 병기. 전수 기준 탐지율 · 오탐률은 ANN 기준 값의 상한이다.

사용법:
    python analyze.py --run main
"""

import argparse
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from _common import load_jsonl, run_dir

SCORE_KEYS = ("accuracy", "tone", "personalization", "naturalness", "cta_clarity")
TARGET_ITEM = {"D2": "accuracy", "D3": "personalization", "D4": "cta_clarity"}
# D3(개인화 실패)는 헤드라인에서 보조로 사전 강등(2026-09-29 사용자 결정). 근거는 결과가 아니라 예상 표본 크기다:
# 시범 2회차 사용 가능 비율 1/5 → 원본 70건 기준 약 14건, 최대 CI 반폭 약 ±26%. D3 판정 결과를 보기 전에 정했다.
# 측정 · 판정 · 보고는 그대로 하고, 헤드라인 표(1-b · 2 · 4)와 칸별 n 표에서만 뺀다.
HEADLINE_DEFECTS = ("D2", "D4")
SECONDARY_DEFECTS = ("D3",)
MIN_SCORE, MIN_OVERALL = 3, 4.0  # settings.quality_check_llm_min_score / min_overall_score (gate_meta 로 대조)
OPERATING = "low"
DEFECT_ORDER = ["C", "C_repl", "N", "D1", "D2", "D3", "D4"]
SEED = 20260929
BOOT_REPS = 2000


# ── 통계 도구 ─────────────────────────────────────────────────────────────────

def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    if n == 0:
        return math.nan, math.nan, math.nan
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return p, max(0.0, center - half), min(1.0, center + half)


def rate(k: int, n: int) -> str:
    if n == 0:
        return "– (n=0)"
    p, lo, hi = wilson(k, n)
    return f"{k}/{n} ({p:.0%}, CI {lo:.0%}–{hi:.0%})"


def cluster_boot(values: list[tuple[str, float]]) -> tuple[float, float, float]:
    """(군집 id, 값) 목록의 평균과 군집(페르소나) 단위 부트스트랩 95% CI."""
    if not values:
        return math.nan, math.nan, math.nan
    by: dict[str, list[float]] = defaultdict(list)
    for c, v in values:
        by[c].append(v)
    keys = sorted(by)
    rng = np.random.default_rng(SEED)
    boots = []
    for _ in range(BOOT_REPS):
        idx = rng.integers(0, len(keys), len(keys))
        boots.append(np.mean([v for k in idx for v in by[keys[k]]]))
    return float(np.mean([v for _, v in values])), float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def fmt_boot(t: tuple[float, float, float], signed: bool = False) -> str:
    est, lo, hi = t
    if math.isnan(est):
        return "– (n=0)"
    f = "{:+.1%}" if signed else "{:.1%}"
    return f"{f.format(est)} (CI {f.format(lo)} ~ {f.format(hi)})"


def md_table(header: list[str], rows: list[list[Any]]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


# ── 판정 도구 ─────────────────────────────────────────────────────────────────

def schedule_of(meta: dict[str, Any]) -> tuple[dict[str, int], dict[str, int]]:
    if "schedule" in meta:
        return meta["schedule"], meta.get("d1_schedule", {})
    legacy = {e: meta["runs"] for e in meta["efforts"]}  # 시범(2026-09-29 이전 형식)
    return legacy, legacy


def s3(row: dict[str, Any], effort: str, run: int) -> dict[str, Any] | None:
    return next((s for s in row.get("stage3", []) if s["effort"] == effort and s["run"] == run), None)


def tone_undecidable(j: dict[str, Any]) -> bool:
    """판정 불가(톤): 3단계 불통과인데 tone 을 뺀 4항목에 같은 규칙(각 3점 이상, 평균 4점 이상)을 적용하면 통과."""
    if j["missing"] or j["passed"]:
        return False
    others = [j["scores"][k] for k in SCORE_KEYS if k != "tone"]
    return all(v >= MIN_SCORE for v in others) and statistics.mean(others) >= MIN_OVERALL


def s2_pass(row: dict[str, Any], basis: str, override: bool, thr: float) -> bool | None:
    st = row["stage2"]
    if st["api_error"]:
        return None
    if basis == "ann":
        return st["override_on" if override else "override_off"]["passed"]
    return not any(x["exact_top1"] > thr and not (override and x["hedge_override"]) for x in st["sentences"])


def s12_pass(row: dict[str, Any], thr: float, basis: str = "exact", override: bool = True) -> bool | None:
    if not row["stage1"]["passed"]:
        return False
    return s2_pass(row, basis, override, thr)


def s3_fail_prob(row: dict[str, Any], effort: str, runs: list[int], drop_tone: bool = False) -> float | None:
    js = [j for j in (s3(row, effort, r) for r in runs) if j and not j["missing"]]
    if not js:
        return None
    return sum((not j["passed"]) and not (drop_tone and tone_undecidable(j)) for j in js) / len(js)


def pipeline_fail_prob(row: dict[str, Any], effort: str, runs: list[int], thr: float, basis: str = "exact",
                       override: bool = True, drop_tone: bool = False) -> float | None:
    p12 = s12_pass(row, thr, basis, override)
    if p12 is None:
        return None
    return 1.0 if not p12 else s3_fail_prob(row, effort, runs, drop_tone)


def item_scores(row: dict[str, Any], effort: str, runs: list[int], item: str) -> list[int]:
    return [j["scores"][item] for j in (s3(row, effort, r) for r in runs) if j and not j["missing"]]


def is_boundary(j: dict[str, Any]) -> bool:
    sc = j["scores"]
    return 3.6 <= sc["overall"] <= 4.4 or any(sc[k] == 3 for k in SCORE_KEYS)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [{k.strip(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f)]


# ── 보고서 ─────────────────────────────────────────────────────────────────────

def build_report(run: str) -> str:
    out_dir = run_dir(run)
    cases = {c["case_id"]: c for c in load_jsonl(out_dir / "cases.jsonl")}
    rows = {r["case_id"]: r for r in load_jsonl(out_dir / "gate_results.jsonl")}
    meta = json.loads((out_dir / "gate_meta.json").read_text(encoding="utf-8"))
    originals = {o["original_id"]: o for o in load_jsonl(out_dir / "originals.jsonl")}
    thr = meta["gate_settings"]["semantic_threshold"]
    sched, d1_sched = schedule_of(meta)
    low_runs = list(range(1, sched.get(OPERATING, 0) + 1))
    judged = [cid for cid in cases if cid in rows and cases[cid].get("valid", True)]
    persona = {cid: cases[cid].get("persona_id") or originals[cases[cid]["original_id"]]["persona_id"] for cid in judged}
    by_orig: dict[str, dict[str, str]] = defaultdict(dict)
    for cid in judged:
        by_orig[cases[cid]["original_id"]][cases[cid]["defect"]] = cid
    d1_path = out_dir / "d1_results.jsonl"
    d1 = load_jsonl(d1_path) if d1_path.exists() else []
    d1_primary = [r for r in d1 if r["role"] == "primary"]
    d1_meta_path = out_dir / "d1_set_meta.json"
    d1_meta = json.loads(d1_meta_path.read_text(encoding="utf-8")) if d1_meta_path.exists() else {}

    L: list[str] = [f"# 메시지 품질 게이트 결함 주입 실험 — {run}", ""]
    if run in ("pilot", "smoke") or run.startswith("pilot"):
        L += ["> **시범 · 스모크 실행이다. 이 보고서의 수치는 결과로 인용하지 않는다.**", ""]

    L += ["## 실행 정보", ""]
    L += [md_table(["항목", "값"], [
        ["실행 시각 (UTC)", meta["run_at"]],
        ["git commit", f"{meta['git']['commit'][:10]} (추적 파일 변경 {len(meta['git']['tracked_changes'])}개)"],
        ["판정 모델", meta["model"]],
        ["temperature 설정값 → 실제 전송", f"{meta['temperature_setting']} → "
         + ("전송 안 됨" if all("temperature" not in p for p in meta["sent_params"].values()) else "전송됨")],
        ["실제 전송 파라미터", "; ".join(f"{e}: {json.dumps(p, ensure_ascii=False)}" for e, p in meta["sent_params"].items())],
        ["판정 프롬프트 sha256", meta["prompt"]["system_prompt_sha256"][:16]],
        ["게이트 설정", json.dumps(meta["gate_settings"], ensure_ascii=False)],
        ["2단계 경로", meta["stage2_path"]],
        ["3단계 반복", f"{json.dumps(sched)} · 원본 속 D1 {json.dumps(d1_sched)}"],
        ["케이스 / 판정 작업", f"{meta['n_cases']} / {meta['n_judge_jobs']}"],
        ["3단계 총 호출 / 결측", f"{meta['judge_attempts_total']} / {meta['judge_missing']}"],
    ])]

    # ═══ 사전 등록 주 결론 ═══════════════════════════════════════════════════════
    L += ["", "# 사전 등록 주 결론 (헤드라인은 여기서만)", ""]

    # 1-a D1
    L += ["## 1-a. D1 규제 위반 — 서로 다른 문구 단위 1·2단계 탐지율", ""]
    if d1_primary:
        n = len(d1_primary)

        def cnt(key: str, which: str = "templated") -> int:
            return sum(r[which][key] for r in d1_primary)

        L += [md_table(["기준", "실제 문장 틀(주)", "맨 문구(상한)"], [
            ["전수 · override 켬(운영)", rate(cnt("detected_exact_on"), n), rate(cnt("detected_exact_on", "bare"), n)],
            ["ANN · override 켬", rate(cnt("detected_ann_on"), n), rate(cnt("detected_ann_on", "bare"), n)],
            ["전수 · override 끔", rate(cnt("detected_exact_off"), n), rate(cnt("detected_exact_off", "bare"), n)],
        ])]
        L += ["", f"- n = 서로 다른 문구 {n}개(원본 수가 아님). 제외 {len(d1_meta.get('excluded', []))}개 — 사유는 d1_set_meta.json.",
              f"- 틀 유형 빈도(생성 원본): {json.dumps(d1_meta.get('template_type_freq', {}), ensure_ascii=False)}", ""]
        strata = []
        for key, label in (("stratum", "층"), ("category", "금지어 카테고리"), ("source", "보도자료 분류"),
                           ("kind", "서술어 규칙"), ("keyword_in_phrase", "1단계 키워드 포함"), ("template_type", "틀 유형")):
            for val in sorted({str(r.get(key)) for r in d1_primary}):
                rs = [r for r in d1_primary if str(r.get(key)) == val]
                strata.append([label, val, rate(sum(r["templated"]["detected_exact_on"] for r in rs), len(rs)),
                               rate(sum(r["templated"]["detected_ann_on"] for r in rs), len(rs))])
        L += [md_table(["층화", "값", "전수 · 켬", "ANN · 켬"], strata)]
    else:
        L += ["d1_results.jsonl 없음 — make_d1_set.py → run_d1.py 를 먼저 돌린다(정답 근거 문구 필요)."]

    # 1-b D2 · D4 (D3 는 보조 절)
    L += ["", f"## 1-b. D2 · D4 — 3단계 불통과 확률, C 대비 원본별 차이 ({OPERATING}, override 켬)", ""]
    L += ["- 대상: C 원본이 1·2단계(전수 기준)를 통과한 원본만. 주 값은 원본별 차이(D − C).",
          "- D3(개인화 실패)는 사전 강등 — 보조 결과 절에 같은 표로 싣는다.", ""]

    def row_1b(d: str) -> list[Any]:
        diffs, pd, pc, excluded = [], [], [], 0
        for oid, m in by_orig.items():
            if d not in m or "C" not in m:
                continue
            c_row, d_row = rows[m["C"]], rows[m[d]]
            if not s12_pass(c_row, thr):
                excluded += 1
                continue
            a, b = s3_fail_prob(d_row, OPERATING, low_runs), s3_fail_prob(c_row, OPERATING, low_runs)
            if a is None or b is None:
                continue
            key = persona[m["C"]]
            pd.append((key, a))
            pc.append((key, b))
            diffs.append((key, a - b))
        return [d, len(diffs), excluded, fmt_boot(cluster_boot(pd)), fmt_boot(cluster_boot(pc)),
                fmt_boot(cluster_boot(diffs), signed=True)]

    h1b = ["결함", "원본 n", "제외(C 가 1·2단계 불통과)", "D 불통과 확률", "C 불통과 확률", "차이 D − C (주)"]
    t1b = [row_1b(d) for d in HEADLINE_DEFECTS]
    L += [md_table(h1b, t1b)]

    # 1-c 대조군 오탐
    L += ["", f"## 1-c. 대조군 오탐 — C 원본 파이프라인 불통과 확률 ({OPERATING}, override 켬)", ""]
    fp = []
    c_cids = [cid for cid in judged if cases[cid]["defect"] == "C"]
    for label, subset in (("전체", c_cids),
                          ("기능성 표시 상품", [c for c in c_cids if cases[c].get("functional_certified")]),
                          ("기능성 표시 없음", [c for c in c_cids if not cases[c].get("functional_certified")]),
                          ("판정기에 안 보이는 필드 인용", [c for c in c_cids if cases[c].get("invisible_field_citation")]),
                          ("근거 없는 구체 사실 있음", [c for c in c_cids if cases[c].get("unsupported_fact")]),
                          ("근거 없는 구체 사실 뺀 값", [c for c in c_cids if not cases[c].get("unsupported_fact")])):
        cells = [label, len(subset)]
        for basis in ("exact", "ann"):
            for drop in (False, True):
                vals = [(persona[c], p) for c in subset
                        if (p := pipeline_fail_prob(rows[c], OPERATING, low_runs, thr, basis, True, drop)) is not None]
                cells.append(fmt_boot(cluster_boot(vals)))
        fp.append(cells)
    L += [md_table(["집단", "n", "전수 · 톤 포함", "전수 · 판정 불가(톤) 제외", "ANN · 톤 포함", "ANN · 판정 불가(톤) 제외"], fp)]

    # 2 점수 신호
    L += ["", f"## 2. 점수 신호 — 목표 항목 하락률 − 잡음 기준선 ({OPERATING}, D2 · D4)", ""]

    def row_2(d: str) -> list[Any]:
        item = TARGET_ITEM[d]
        drop_pool, base_pool, diffs, mean_diffs = [0, 0], [0, 0], [], []
        for oid, m in by_orig.items():
            if d not in m or "C" not in m or not s12_pass(rows[m["C"]], thr):
                continue
            xd = item_scores(rows[m[d]], OPERATING, low_runs, item)
            xc = item_scores(rows[m["C"]], OPERATING, low_runs, item)
            if not xd or len(xc) < 2:
                continue
            pairs = [(a, b) for a in xd for b in xc]
            ordered = [(xc[i], xc[j]) for i in range(len(xc)) for j in range(len(xc)) if i != j]
            dr = sum(a < b for a, b in pairs) / len(pairs)
            br = sum(a < b for a, b in ordered) / len(ordered)
            drop_pool[0] += sum(a < b for a, b in pairs)
            drop_pool[1] += len(pairs)
            base_pool[0] += sum(a < b for a, b in ordered)
            base_pool[1] += len(ordered)
            key = persona[m["C"]]
            diffs.append((key, dr - br))
            mean_diffs.append((key, statistics.mean(xd) - statistics.mean(xc)))
        return [d, item, len(diffs),
                f"{drop_pool[0]}/{drop_pool[1]} ({drop_pool[0] / drop_pool[1]:.0%})" if drop_pool[1] else "–",
                f"{base_pool[0]}/{base_pool[1]} ({base_pool[0] / base_pool[1]:.0%})" if base_pool[1] else "–",
                fmt_boot(cluster_boot(diffs), signed=True),
                "–" if not mean_diffs else f"{cluster_boot(mean_diffs)[0]:+.2f}점"]

    h2 = ["결함", "목표 항목", "원본 n", "하락률(D<C, 모든 회차 쌍)", "기준선(C 순서쌍 Xᵢ<Xⱼ)",
          "하락률 − 기준선 (주)", "평균 점수 차이(D − C, 보조)"]
    L += [md_table(h2, [row_2(d) for d in HEADLINE_DEFECTS])]

    # 3 RQ2
    L += ["", "## 3. 2단계 우회 경로", ""]
    if d1_primary:
        rq2 = []
        for basis in ("exact", "ann"):
            caught_off = [r for r in d1_primary if r["templated"][f"s2_{basis}_off"]]
            released = [r for r in caught_off if not r["templated"][f"s2_{basis}_on"]]
            rq2.append([f"{'전수' if basis == 'exact' else 'ANN'}", len(caught_off),
                        rate(len(released), len(caught_off)) if caught_off else "측정 불가(분모 0)"])
        L += ["### (a) override 조건부 해제 비율 — 분모: override 를 끄면 2단계가 잡는 D1(실제 틀)", "",
              md_table(["기준", "분모 n", "override 가 풀어 준 비율"], rq2), ""]
        hedge = [r for r in d1_primary if r["stratum"] == "hedge" and r.get("hedge_basis")]
        proofs = []
        for r in hedge:
            seen = set()
            for v in [r["bare"], r["templated"], *r["targeted"]]:
                if v["sentence"] in seen:
                    continue
                seen.add(v["sentence"])
                if v["exact_top1"] > thr and v["override_condition"]:
                    proofs.append([r["phrase_id"], v.get("type", "주/맨"), f"{v['exact_top1']:.3f}",
                                   f"{v['ann_top1']:.3f}", v["sentence"][:60]])
        L += [f"### (b) 표적 시험 — 헷지 근거가 있는 문구 {len(hedge)}개 중, 틀 하나에서라도 전수 > {thr} 이면서 "
              "override 조건 성립(=2단계 우회)", ""]
        L += [md_table(["문구", "틀", "전수", "ANN", "문장"], proofs) if proofs else "존재 사례 없음", ""]
        cond = Counter(r["bare"]["override_condition"] for r in hedge)
        L += [f"### (c) 헷지 층 override 조건: 성립 {cond[True]} · 불성립 {cond[False]}", ""]
        L += ["### (d) 문장 틀 효과 — 맨 문구 × 실제 틀, 2단계 불통과(override 켬)", ""]
        for basis in ("exact", "ann"):
            tab = Counter((r["bare"][f"s2_{basis}_on"], r["templated"][f"s2_{basis}_on"]) for r in d1_primary)
            L += [f"**{'전수' if basis == 'exact' else 'ANN'}** (n={len(d1_primary)})", "",
                  md_table(["", "실제 틀: 잡힘", "실제 틀: 놓침"], [
                      ["맨 문구: 잡힘", tab[(True, True)], tab[(True, False)]],
                      ["맨 문구: 놓침", tab[(False, True)], tab[(False, False)]],
                  ]), ""]
    else:
        L += ["d1_results.jsonl 없음"]

    # 4 RQ3
    L += ["", "## 4. 판정 설정 — 불통과 확률 짝 차이(반복 1~3회차로 맞춤)", ""]
    common = list(range(1, min(n for n in sched.values()) + 1)) if sched else []
    groups = {"결함(D2 · D4, C 가 1·2단계 통과)": [], "대조군(C 원본)": []}
    d3_group: list[str] = []
    for oid, m in by_orig.items():
        if "C" not in m or not s12_pass(rows[m["C"]], thr):
            continue
        groups["대조군(C 원본)"].append(m["C"])
        groups["결함(D2 · D4, C 가 1·2단계 통과)"] += [m[d] for d in HEADLINE_DEFECTS if d in m]
        d3_group += [m[d] for d in SECONDARY_DEFECTS if d in m]

    def rows_4(group_items: dict[str, list[str]]) -> list[list[Any]]:
        out = []
        for a, b in ((OPERATING, "minimal"), (OPERATING, "medium")):
            if a not in sched or b not in sched:
                continue
            for gname, cids in group_items.items():
                vals = []
                for cid in cids:
                    pa, pb = s3_fail_prob(rows[cid], a, common), s3_fail_prob(rows[cid], b, common)
                    if pa is not None and pb is not None:
                        vals.append((persona[cid], pa - pb))
                out.append([f"{a} − {b}", gname, len(vals), fmt_boot(cluster_boot(vals), signed=True)])
        return out

    h4 = ["설정 쌍", "집단", "케이스 n", "불통과 확률 차이 (주)"]
    L += [md_table(h4, rows_4(groups))]
    lat_rows = []
    for e in sched:
        lat = [x for cid in judged for j in rows[cid].get("stage3", []) if j["effort"] == e for x in j["latency_s"]]
        flips = []
        for cid in judged:
            js = [s3(rows[cid], e, r) for r in common]
            ok = [j["passed"] for j in js if j and not j["missing"]]
            flips += [ok[i] != ok[k] for i in range(len(ok)) for k in range(i + 1, len(ok))]
        lat_rows.append([e, f"{statistics.median(lat):.1f}s" if lat else "–",
                         f"{np.percentile(lat, 90):.1f}s" if lat else "–", rate(sum(flips), len(flips))])
    L += ["", md_table(["설정", "지연 중앙값", "지연 p90", "같은 설정 회차 쌍 판정 뒤집힘(기저선)"], lat_rows)]

    # 칸별 n · CI 폭
    L += ["", "## 사전 등록 칸별 n · 최대 CI 반폭(근사, p=0.5)", ""]
    cells = [["1-a D1 문구", len(d1_primary)]]
    cells += [[f"1-b {r[0]}", r[1]] for r in t1b]
    cells += [["1-c C 원본", len(c_cids)]]
    L += [md_table(["칸", "n", "최대 CI 반폭"],
                   [[c, n, f"±{1.96 * math.sqrt(0.25 / n):.0%}" if n else "–"] for c, n in cells])]
    L += ["", "- CI 폭이 해석 불가 수준인 칸은 본 실행 전에 보조로 내린다(플랜 사전 등록 절)."]

    # ═══ 보조 결과 ═══════════════════════════════════════════════════════════════
    def sec(header: list[str]) -> list[str]:
        """보조 표에서는 "(주)" 표시를 뗀다 — 헤드라인 값으로 읽히지 않게."""
        return [h.replace(" (주)", "") for h in header]

    L += ["", "# 보조 결과", ""]
    L += ["## D3 개인화 실패 (보조 — 사전 강등, 헤드라인에 쓰지 않는다)", "",
          "- 강등 근거: 시범 2회차 사용 가능 비율 1/5 → 원본 70건 기준 약 14건, 최대 CI 반폭 약 ±26%. "
          "D3 판정 결과를 보기 전에 예상 표본 크기로 정했다(2026-09-29).",
          "- 측정 방식은 D2 · D4 와 같다. 인용할 때는 탐색적 결과로 n 과 CI 를 함께 적는다.", "",
          "탐지(1-b 와 같은 계산):", "", md_table(sec(h1b), [row_1b(d) for d in SECONDARY_DEFECTS]), "",
          "점수 신호(2 와 같은 계산):", "", md_table(sec(h2), [row_2(d) for d in SECONDARY_DEFECTS]), ""]
    d3_rows4 = rows_4({"D3(C 가 1·2단계 통과)": d3_group})
    L += ["판정 설정(4 와 같은 계산):", "", md_table(sec(h4), d3_rows4) if d3_rows4 else "설정 비교 없음(반복 설정 1종)", ""]
    L += ["## 케이스 구성", ""]
    comp = []
    all_cases = list(cases.values())
    for key in sorted({(c["defect"], c["level"]) for c in all_cases},
                      key=lambda k: (DEFECT_ORDER.index(k[0]) if k[0] in DEFECT_ORDER else 99, k[1])):
        cs = [c for c in all_cases if (c["defect"], c["level"]) == key]
        comp.append([key[0], key[1], len(cs), sum(c["valid"] for c in cs), sum(bool(c["length_flags"]) for c in cs),
                     sum(c["case_id"] in rows for c in cs)])
    L += [md_table(["결함", "층", "생성", "유효", "길이 규칙 걸림", "판정함"], comp)]
    review_path = out_dir / "review_originals_summary.csv"
    if review_path.exists():
        rv = _read_csv(review_path)
        unfit = [r["original_id"] for r in rv if r.get("persona_product_fit(O/X)", "").upper() == "X"]
        failed = [r["original_id"] for r in rv if r.get("persona_product_fit(O/X)", "").upper() == "O"
                  and r.get("review_ok(O/X)", "").upper() == "X"]
        L += ["", f"- 원본 {len(rv)}건 중 페르소나-상품 부적합으로 전부 제외 {len(unfit)}건 {unfit or ''}",
              f"- 검수 탈락(자연 결함 후보) {len(failed)}건 {failed or ''}"]

    L += ["", "## 멈춤 규칙 확인 — 문구 단독 판정 대 원본 속 판정(바꾼 문장 단위)", ""]
    d1_by_id = {r["item_id"]: r for r in d1}
    stop = []
    for cid in judged:
        c = cases[cid]
        if c["defect"] != "D1":
            continue
        alone = d1_by_id.get(c.get("d1_item_id"), {}).get("templated")
        if not alone:
            stop.append([cid, "d1_results 에 항목 없음", "", ""])
            continue
        row = rows[cid]
        inj = [x for x in row["stage2"]["sentences"] if x["is_injected"]]
        in_s1 = sorted(row["stage1"]["injected_hits"])
        in_s2 = any(x["exact_top1"] > thr and not x["hedge_override"] for x in inj)
        same_score = inj and abs(inj[0]["exact_top1"] - alone["exact_top1"]) < 1e-6
        ok = in_s1 == sorted(alone["stage1_hits"]) and in_s2 == alone["s2_exact_on"] and same_score
        if not ok:
            stop.append([cid, f"1단계 {in_s1} vs {sorted(alone['stage1_hits'])}",
                         f"2단계 {in_s2} vs {alone['s2_exact_on']}", f"점수 일치 {bool(same_score)}"])
    n_d1 = sum(cases[c]["defect"] == "D1" for c in judged)
    L += [f"- 원본 속 D1 {n_d1}건 중 불일치 {len(stop)}건" + (" → **멈춤: 원인을 고치고 시범을 다시 돌린다**" if stop else "")]
    if stop:
        L += ["", md_table(["케이스", "1단계", "2단계", "점수"], stop)]
    xb = [(cid, rows[cid]["stage1"].get("cross_boundary_hits")) for cid in judged if rows[cid]["stage1"].get("cross_boundary_hits")]
    L += [f"- 경계 넘는 매칭(멈춤 사유 아님): {len(xb)}건 {xb[:5] if xb else ''}"]
    eq_bad = [cid for cid in judged if not rows[cid]["equivalence"]["match"]]
    L += [f"- check_quality(llm=None) 와 ANN 기준 1·2단계 도출값 불일치: {len(eq_bad)}건 {eq_bad or ''}"]
    s2_split = [cid for cid in judged if s2_pass(rows[cid], "exact", True, thr) != s2_pass(rows[cid], "ann", True, thr)]
    L += [f"- 2단계 전수 대 ANN 판정이 갈린 케이스(정합성 실패 아님): {len(s2_split)}건 {s2_split[:8] or ''}"]

    L += ["", f"## 치환 대조군(C_repl) 대 C 원본 — 치환 행위 효과 ({OPERATING})", ""]
    rep = []
    for oid, m in by_orig.items():
        if "C_repl" in m and "C" in m:
            a = pipeline_fail_prob(rows[m["C_repl"]], OPERATING, low_runs, thr)
            b = pipeline_fail_prob(rows[m["C"]], OPERATING, low_runs, thr)
            if a is not None and b is not None:
                rep.append((persona[m["C"]], a - b))
    L += [f"- 원본 {len(rep)}건, 불통과 확률 차이(C_repl − C): {fmt_boot(cluster_boot(rep), signed=True)}"]

    L += ["", "## 원본 속 D1 파이프라인 사유 (보조, 3단계 accuracy 경로 포함)", ""]
    d1rows = []
    for cid in [c for c in judged if cases[c]["defect"] == "D1"]:
        row = rows[cid]
        j = s3(row, OPERATING, 1)
        d1rows.append([cid, cases[cid]["level"], "X" if not row["stage1"]["passed"] else "O",
                       "O" if s2_pass(row, "exact", True, thr) else "X", "O" if s2_pass(row, "ann", True, thr) else "X",
                       "–" if not j or j["missing"] else j["scores"]["accuracy"], ", ".join(cases[cid]["length_flags"])])
    L += [md_table(["케이스", "층", "1단계", "2단계(전수)", "2단계(ANN)", f"accuracy({OPERATING} 1회)", "길이"], d1rows)
          if d1rows else "원본 속 D1 없음"]

    L += ["", "## 자연 결함(N)", ""]
    nrows = []
    for cid in [c for c in judged if cases[c]["defect"] == "N"]:
        p = pipeline_fail_prob(rows[cid], OPERATING, low_runs, thr)
        nrows.append([cid, cases[cid]["label_source"], "–" if p is None else f"{p:.0%}"])
    L += [md_table(["케이스", "라벨", "불통과 확률"], nrows) if nrows else "자연 결함 없음"]

    L += ["", f"## RQ4 일관성 — {OPERATING} 1회차로 경계선 선택, 2회차 이후로만 측정", ""]
    if len(low_runs) >= 3:
        grp = {"경계선": [0, 0], "비경계": [0, 0]}
        for cid in judged:
            if cases[cid]["defect"] == "D1":
                continue
            j1 = s3(rows[cid], OPERATING, 1)
            if not j1 or j1["missing"]:
                continue
            later = {j["passed"] for j in (s3(rows[cid], OPERATING, r) for r in low_runs[1:]) if j and not j["missing"]}
            g = grp["경계선" if is_boundary(j1) else "비경계"]
            g[1] += 1
            g[0] += len(later) > 1
        L += [md_table(["집단", "측정 중 판정이 뒤집힌 케이스"], [[k, rate(*v)] for k, v in grp.items()])]
    else:
        L += [f"{OPERATING} 반복이 3회 미만 — 측정 불가(시범 결과는 consistency.py 참고)"]

    L += ["", f"## 케이스별 상세 ({OPERATING} 1회차)", ""]
    det = []
    for cid in sorted(judged, key=lambda c: (cases[c]["original_id"], c)):
        row = rows[cid]
        j = s3(row, OPERATING, 1)
        top = max((x["exact_top1"] for x in row["stage2"]["sentences"]), default=0.0)
        det.append([cid, "O" if row["stage1"]["passed"] else "X", f"{top:.3f}",
                    "O" if s2_pass(row, "exact", True, thr) else "X",
                    "–" if not j or j["missing"] else " ".join(str(j["scores"][k]) for k in SCORE_KEYS)
                    + f" ({j['scores']['overall']})"])
    L += [md_table(["케이스", "1단계", "2단계 전수 최고", "2단계(전수·켬)", "3단계 acc·tone·pers·nat·cta (평균)"], det)]
    return "\n".join(L) + "\n"


def main() -> None:
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", default="main")
    args = parser.parse_args()
    report = build_report(args.run)
    path = run_dir(args.run) / "report.md"
    path.write_text(report, encoding="utf-8")
    print(f"→ {path}")


if __name__ == "__main__":
    main()
