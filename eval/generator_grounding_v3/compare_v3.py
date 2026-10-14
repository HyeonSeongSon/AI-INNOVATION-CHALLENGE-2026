"""
v3 개발 라운드 판정 · 보고 (탐색적) — v1 · v2(2라운드 저장분) · v3 짝 비교.

    python compare_v3.py stageA --tag v3     # A단계: 재판정 판정기 비열등 · 형식 · 정리 정규식(v2+1) · 보고용 지표 → result/dev/v3/stageA.{md,json}
    python compare_v3.py stageB --tag v3     # B단계: 주 지표 · 9개 유형 · 8개 유형 한도 · 목적 전달 · 지연 · P5 부작용 · P1 분류 CSV → stageB.{md,json}
    python compare_v3.py v3r --tag v3r       # v3R: v2 대비 근거 · 품질 동시 판정 → result/dev/v3r/compare.{md,json}

판정 규칙은 AMENDMENTS 'v3 개발 기록(태그)'과 플랜을 따른다.
- v3 · v3b · v3c(stageA): 판정기는 result/dev/judge/ 값. v1 · v2 는 v3 때 한 번 판정한 값을 v3b · v3c 에서 다시 썼으므로
  v3b · v3c 와는 판정 시점이 다르다(rejudge 가 이미 있는 판정을 건너뜀).
- v3R: 시도마다 result/dev/judge_<tag>/ 에 v1 · v2 · 태그를 같은 시점에 판정한 값을 쓴다.
"""

import argparse
import csv
import json
import re
import subprocess
import sys
from typing import Any

import v3_common as v3
from v3_common import gg, vc
from gg_common import load_jsonl

import report as r1  # noqa: E402
import measure as m1  # noqa: E402
import measure_v3 as m3  # noqa: E402
import grounding_def_v2 as gd  # noqa: E402

from app.core.data_loader import get_brand_tones  # noqa: E402

DEV = v3.RESULT / "dev"
MAIN2 = vc.RESULT / "main"
NI = {"pass_rate": -0.15, "personalization": -0.3, "cta_clarity": -0.3, "tone": -0.3}
NI_PURPOSE = -0.15
FORMAT_MAX_INCREASE, CTA_MIN, CLEANUP_TOL, PRIMARY_TOL, REGRESSION_LIMIT = 2, 0.95, 1, 2, 1
LATENCY_CAP_S, THROUGHPUT_CAP = 5.0, 1.5


def msgs(tag: str) -> dict[str, dict]:
    p = (MAIN2 / tag / "messages.jsonl") if tag in ("v1", "v2") else (DEV / tag / "messages.jsonl")
    return {r["item_id"]: r for r in load_jsonl(p)}


def judged(tag: str, jdir=None) -> dict[str, dict]:
    rows = load_jsonl((jdir or DEV / "judge") / f"{tag}.jsonl")
    by: dict[str, dict] = {}
    for r in rows:
        if not r.get("missing"):
            by.setdefault(r["item_id"], {"judge": {}})["judge"][r["run"]] = r
    return {i: {"judge": [v["judge"][k] for k in sorted(v["judge"])]} for i, v in by.items()}


def verifier(tag: str) -> dict[str, dict]:
    p = (MAIN2 / tag / "measure.jsonl") if tag in ("v1", "v2") else (DEV / tag / "measure.jsonl")
    return {r["item_id"]: r["verifier"] for r in load_jsonl(p) if r.get("verifier")}


def prompt_src(tag: str) -> str:
    if tag == "v1":
        return subprocess.run(["git", "show", f"{v3.V1_COMMIT}:{v3.PURPOSE_REL}"], cwd=gg.REPO, capture_output=True,
                              check=True).stdout.decode("utf-8")
    if tag == "v2":
        return (v3.HERE / "snapshots" / "purpose_prompt_v2.py").read_text(encoding="utf-8")
    return gg.PURPOSE_PROMPT.read_text(encoding="utf-8")


def stage_a(tag: str) -> None:
    tags = ("v1", "v2", tag)
    M = {t: msgs(t) for t in tags}
    J = {t: judged(t) for t in tags}
    ids = sorted(set.intersection(*(set(M[t]) for t in tags)))
    tones = get_brand_tones().get("brand_ton_prompt", {})
    import run_d1
    det = run_d1.make_detector()
    R = {t: {i: m3.regex_metrics_v3(M[t][i], str(tones.get(M[t][i]["brand"], "") or "")) for i in ids} for t in tags}
    F = {t: {i: m1.format_metrics(M[t][i], det) for i in ids} for t in tags}
    L = [f"# v3 개발 라운드 A단계 — {tag} (탐색적, 2라운드 새 표본 {len(ids)}건)", "",
         "- 판정기는 v1 · v2 · v3를 같은 시점에 다시 판정한 값이다(result/dev/judge/).", ""]
    ok_all = True

    # 판정기 비열등(v1 대비)
    def ni_rows(b: str) -> tuple[bool, list[str]]:
        jb = {i: r1.item_judge(J["v1"].get(i, {"judge": []})) for i in ids}
        ja = {i: r1.item_judge(J[b].get(i, {"judge": []})) for i in ids}
        both = [i for i in ids if jb[i] and ja[i]]
        rows, ok = [], True
        for k, margin in NI.items():
            mean, lower = r1.paired_boot_lower([ja[i][k] - jb[i][k] for i in both])
            good = lower > margin
            ok &= good
            rows.append(f"| {k} | {sum(jb[i][k] for i in both) / len(both):.3f} | {sum(ja[i][k] for i in both) / len(both):.3f} | "
                        f"{mean:+.3f} | {lower:+.3f} | {margin} | {'통과' if good else '미달'} |")
        fv = lambda f: (not f["json_ok"]) or f["title_over"] or f["body_over"]  # noqa: E731
        fb, fa = sum(fv(F["v1"][i]) for i in ids), sum(fv(F[b][i]) for i in ids)
        cta = sum(F[b][i]["cta_last"] for i in ids) / len(ids)
        g1, g2 = fa - fb <= FORMAT_MAX_INCREASE, cta >= CTA_MIN
        ok &= g1 and g2
        rows.append(f"| 형식 위반 수 | {fb} | {fa} | {fa - fb:+d} | - | +{FORMAT_MAX_INCREASE} | {'통과' if g1 else '미달'} |")
        rows.append(f"| CTA 마지막 | - | {cta:.0%} | - | - | ≥{CTA_MIN:.0%} | {'통과' if g2 else '미달'} |")
        return ok, rows, len(both)

    for b in ("v2", tag):
        ok, rows, nb = ni_rows(b)
        if b == tag:
            ok_all &= ok
        L += [f"## 판정기 비열등 — v1 → {b} (짝 {nb}건){' — 판정 대상' if b == tag else ' — 참고(재판정으로 v2 미달 재확인)'}", "",
              f"| 지표 | v1 | {b} | 차이 | 단측 95% 하한 | 여유 | 판정 |", "|---|---|---|---|---|---|---|", *rows, ""]

    # 정리 정규식(v2 + 1 이내)
    L += ["## 정리 항목 (메시지 수, v3 정규식 — 변화 암시에 '달라질' 포함)", "", f"| 항목 | v1 | v2 | {tag} | 판정(v2+{CLEANUP_TOL}) |", "|---|---|---|---|---|"]
    over = []
    for k in m3.CLEANUP:
        n = {t: sum(1 for i in ids if R[t][i][k]) for t in tags}
        good = n[tag] <= n["v2"] + CLEANUP_TOL
        ok_all &= good
        L.append(f"| {k} | {n['v1']} | {n['v2']} | {n[tag]} | {'통과' if good else '미달'} |")
        if n[tag] > n["v2"]:
            over += [(k, i, R[tag][i][k]) for i in ids if R[tag][i][k]]
    if over:
        L += ["", "v2보다 늘어난 항목의 메시지(원인 행 확인용):"]
        L += [f"- {k} {i}: {v} — 제목 「{M[tag][i]['title']}」" for k, i, v in over]
    L.append("")

    # 보고만: 예시 복제 · 구조 다양성 · 지금 · fit_recheck
    L += ["## 보고 지표 (판정 아님)", "", f"| 지표 | v1 | v2 | {tag} |", "|---|---|---|---|"]
    q = {t: m3.prompt_quotes(prompt_src(t)) for t in tags}
    cp = {t: [i for i in ids if m3.example_copy(M[t][i], q[t])] for t in tags}
    S = {t: m3.structure([M[t][i] for i in ids]) for t in tags}
    L.append("| 프롬프트 예시 복제(제목 · CTA, 자기 버전 프롬프트 기준) | " + " | ".join(f"{len(cp[t])}" for t in tags) + " |")
    L.append("| CTA 앞 두 어절 상위 1개 | " + " | ".join(f"{S[t]['cta_head_top1'][0]} {S[t]['cta_head_top1_share']:.0%}" for t in tags) + " |")
    L.append("| CTA 끝 어절 종류 수 (상위 1개) | " + " | ".join(f"{S[t]['cta_tail_kinds']} ({S[t]['cta_tail_top1'][0]} {S[t]['cta_tail_top1'][1]})" for t in tags) + " |")
    L.append("| 제목 앞 두 어절 상위 1개 | " + " | ".join(f"{S[t]['title_head_top1'][0]} {S[t]['title_head_top1_share']:.0%}" for t in tags) + " |")
    L.append("| CTA에 '지금' (진단용, 판정기 가점 아님) | " + " | ".join(f"{S[t]['cta_now']}" for t in tags) + " |")
    rc = [M[tag][i].get("fit_recheck") for i in ids]
    L.append(f"| fit_recheck(none · regenerated · still_hit) | - | - | {rc.count('none')} · {rc.count('regenerated')} · {rc.count('still_hit')} |")
    if cp[tag]:
        L += ["", f"{tag} 예시 복제: " + "; ".join(f"{i} {m3.example_copy(M[tag][i], q[tag])}" for i in cp[tag])]
    L += ["", f"## A단계 판정: {'통과 → B단계' if ok_all else '미달 → 원인 행 수정 후 A 재시도'}"]
    (DEV / tag / "stageA.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (DEV / tag / "stageA.json").write_text(json.dumps({"tag": tag, "passed": ok_all}, ensure_ascii=False), encoding="utf-8")
    print("\n".join(L))


def stage_b(tag: str) -> None:
    tags = ("v1", "v2", tag)
    V = {t: verifier(t) for t in tags}
    M = {t: msgs(t) for t in tags}
    ids = sorted(set.intersection(*(set(V[t]) for t in tags)))
    L = [f"# v3 개발 라운드 B단계 — {tag} (탐색적, 검증기 medium, 짝 {len(ids)}건)", "",
         "- 같은 70건으로 설계한 개발 확인이다. 효과 주장은 최종 측정(PREREG_final.md)으로만 한다.", ""]
    ok_all = True
    pp = {t: sum(V[t][i]["primary_positive"] for i in ids) for t in tags}
    a9 = {t: sum(V[t][i]["llm_positive"] for i in ids) for t in tags}
    good = pp[tag] <= pp["v2"] + PRIMARY_TOL
    ok_all &= good
    L += ["## 주 지표 · 9개 유형 (LLM 양성 · 재검토 포함 메시지 수)", "", f"| | v1 | v2 | {tag} |", "|---|---|---|---|",
          f"| 주 지표(특성어긋남 · 근거없는고민연결) | {pp['v1']} | {pp['v2']} | {pp[tag]} |",
          f"| 9개 유형 | {a9['v1']} | {a9['v2']} | {a9[tag]} |", ""]
    for a, b in (("v1", tag), ("v2", tag)):
        for key, name in (("primary_positive", "주 지표"), ("llm_positive", "9개 유형")):
            bb = sum(1 for i in ids if V[a][i][key] and not V[b][i][key])
            cc = sum(1 for i in ids if not V[a][i][key] and V[b][i][key])
            t = r1.paired_test(bb, cc)
            L.append(f"- {name} {a} → {b}: 개선 {bb} · 악화 {cc}, {t['method']} p = {t['p']:.3f} (보고용)")
    L += [f"- 안전 기준 주 지표 {tag} ≤ v2 + {PRIMARY_TOL}({pp['v2'] + PRIMARY_TOL}): {'통과' if good else '미달'}", ""]

    L += ["## 8개 유형 한도 (v1 대비 +1 이내)", "", f"| 유형 | v1 | v2 | {tag} | 판정 |", "|---|---|---|---|---|"]
    for ty in gd.CLAIM_TYPES:
        n = {t: sum(1 for i in ids if V[t][i]["type_counts"].get(ty)) for t in tags}
        if ty in gd.V1_TYPES:
            g = n[tag] - n["v1"] <= REGRESSION_LIMIT
            ok_all &= g
            L.append(f"| {ty} | {n['v1']} | {n['v2']} | {n[tag]} | {'통과' if g else '초과'} |")
        else:
            L.append(f"| {ty} | {n['v1']} | {n['v2']} | {n[tag]} | (주 지표) |")
    L.append("")

    d = [(V[tag][i]["purpose_conveyed"] == "O") - (V["v1"][i]["purpose_conveyed"] == "O") for i in ids]
    mean, lower = r1.paired_boot_lower(d)
    g = lower > NI_PURPOSE
    ok_all &= g
    L += [f"## 목적 전달(LLM): v1 {sum(V['v1'][i]['purpose_conveyed'] == 'O' for i in ids)} · v2 "
          f"{sum(V['v2'][i]['purpose_conveyed'] == 'O' for i in ids)} · {tag} {sum(V[tag][i]['purpose_conveyed'] == 'O' for i in ids)}"
          f" — v1 대비 {mean:+.3f}, 하한 {lower:+.3f} (여유 {NI_PURPOSE}) {'통과' if g else '미달'}", ""]

    lp = DEV / tag / "latency.json"
    if lp.exists():
        lat = json.loads(lp.read_text(encoding="utf-8"))
        g = lat["added_median_10_s"] <= LATENCY_CAP_S and lat["throughput_ratio_40"] <= THROUGHPUT_CAP
        ok_all &= g
        L += [f"## 지연: 태스크 10개 +{lat['added_median_10_s']:.2f}초(상한 {LATENCY_CAP_S}) · 40개 {lat['throughput_ratio_40']:.2f}배"
              f"(상한 {THROUGHPUT_CAP}) → {'통과' if g else '미달'} · 재생성 {lat['recheck']['n_regen']}건(항목 생성 시간 중앙값 "
              f"재생성 {lat['recheck']['median_regen_item_s']} / 일반 {lat['recheck']['median_plain_item_s']}초)", ""]
    else:
        ok_all = False
        L += ["## 지연: 측정 전(main_v3.py latency) — 판정 보류", ""]

    # P5 부작용 점검: 연결 가능 항목을 문장에 쓴 메시지 중 주 지표 양성 비율
    def used(fitc: dict, m: dict) -> bool:
        t = m3.squash(m["title"] + m["message"])
        return any(m3.squash(c["product_evidence"]) in t or m3.squash(c["persona_need"]) in t for c in fitc.get("connectable", []))
    fit2 = {r["item_id"]: r for r in load_jsonl(MAIN2 / "fit_cache.jsonl")}
    fit3 = {r["item_id"]: r for r in load_jsonl(DEV / tag / "fit_cache.jsonl")}
    u2 = [i for i in ids if used(fit2[i], M["v2"][i])]
    u3 = [i for i in ids if used(fit3[i], M[tag][i])]
    r2 = sum(V["v2"][i]["primary_positive"] for i in u2) / len(u2) if u2 else float("nan")
    r3 = sum(V[tag][i]["primary_positive"] for i in u3) / len(u3) if u3 else float("nan")
    L += ["## P5 부작용 점검 (보고)", "",
          f"- 연결 가능 항목을 문장에 쓴 메시지: v2 {len(u2)}건 중 주 지표 양성 {r2:.1%} · {tag} {len(u3)}건 중 {r3:.1%}",
          f"- {tag}에서 올라가면 '연결 가능 1개 이상 사용' 의무가 무관 근거를 끌어온 신호 → 다음 반복에서 '권장'으로 낮춘다.", ""]

    # P1 분류 CSV(사용자가 분류)
    rows = []
    for i in ids:
        if not V[tag][i]["primary_positive"]:
            continue
        sents = m1.review_kit.split_sentences(M[tag][i]["message"])
        for c in V[tag][i]["claims"]:
            if c.get("type") not in gd.PRIMARY_TYPES:
                continue
            sp = c.get("span", "")
            hit = next((s for s in [M[tag][i]["title"], *sents] if m3.squash(sp)[:12] and m3.squash(sp)[:12] in m3.squash(s)), "")
            rows.append({"item_id": i, "type": c["type"], "span": sp, "sentence": hit,
                         "next_sentence": sents[sents.index(hit) + 1] if hit in sents and sents.index(hit) + 1 < len(sents) else "",
                         "not_connectable": " / ".join(fit3[i].get("not_connectable", [])),
                         "P1형(O/X)": "", "메모": ""})
    p1 = DEV / tag / "p1_classification.csv"
    with open(p1, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["item_id", "type", "span", "sentence", "next_sentence", "not_connectable", "P1형(O/X)", "메모"])
        w.writeheader()
        w.writerows(rows)
    L += ["## P1형 분류 (사용자)", "", f"- {p1} 의 'P1형(O/X)' 칸을 채운다. P1형 = (a) 근거없는고민연결 클레임, (b) 그 고민이 질문 · 공감 문장에 나옴,",
          "  (c) 같은 문장 뒤쪽이나 바로 다음 문장에 제품명 · 효과가 이어짐 — 셋 다일 때만. 2건 이상이면 다음 반복에서 공감 금지 문구를 추가한다.", ""]
    L += [f"## B단계 판정(안전 기준): {'통과' if ok_all else '미달'}"]
    (DEV / tag / "stageB.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (DEV / tag / "stageB.json").write_text(json.dumps({"tag": tag, "passed": ok_all, "primary": pp, "all9": a9},
                                                     ensure_ascii=False), encoding="utf-8")
    print("\n".join(L))


# ── v3R: v2 대비 동시 판정 ─────────────────────────────────────────────────────

V3R_PRIMARY_MAX, V3R_ALL9_MAX = 11, 16       # v2 7 + 4 · v2 11 + 5 (두 독립 실행 차이의 이항 표준편차 올림)
V3R_NI = -0.15                               # 짝 부트스트랩 단측 90% 하한 기준
V3R_UP = ("cta_clarity", "personalization")  # v2가 떨어뜨린 지표: 점추정 상승 + 하한 > −0.15
V3R_KEEP = ("pass_rate", "tone")             # 하한 > −0.15


def boot_lower90(diffs: list[float]) -> tuple[float, float]:
    """짝 차이 평균과 부트스트랩 단측 90% 하한(report.paired_boot_lower 와 같은 시드 · 반복, 분위만 10%)."""
    import random
    if not diffs:
        return float("nan"), float("nan")
    rng = random.Random(r1.BOOT_SEED)
    n = len(diffs)
    means = [sum(diffs[rng.randrange(n)] for _ in range(n)) / n for _ in range(r1.BOOT_REPS)]
    return sum(diffs) / n, r1.percentile(means, 0.10)


def compare_v3r(tag: str) -> None:
    import main_v3 as mv3
    jdir = mv3.judge_dir(tag)
    tags = ("v1", "v2", tag)
    M = {t: msgs(t) for t in tags}
    J = {t: judged(t, jdir) for t in tags}
    V = {t: verifier(t) for t in tags}
    ids = sorted(set.intersection(*(set(M[t]) for t in tags), *(set(V[t]) for t in tags)))
    JI = {t: {i: r1.item_judge(J[t].get(i, {"judge": []})) for i in ids} for t in tags}
    fit = {r["item_id"]: r for r in load_jsonl(DEV / tag / "fit_cache.jsonl")}
    L = [f"# v3R 판정 — {tag} 대 v2 (탐색적, 2라운드 새 표본 {len(ids)}건)", "",
         f"- 판정기는 v1 · v2 · {tag}를 같은 시점에 다시 판정한 값({jdir.name}/). 검증기 v1 · v2 는 저장분.",
         "- 판정 규칙은 AMENDMENTS 'v3 개발 기록(태그)' 그대로. 모든 행을 동시에 판정한다.", ""]
    gates = {}

    # 근거
    pp = {t: sum(V[t][i]["primary_positive"] for i in ids) for t in tags}
    a9 = {t: sum(V[t][i]["llm_positive"] for i in ids) for t in tags}
    gates["primary"], gates["all9"] = pp[tag] <= V3R_PRIMARY_MAX, a9[tag] <= V3R_ALL9_MAX

    def rate(a, b):
        return f"{(b - a) / a:+.0%}" if a else "-"
    L += ["## 근거 (검증기, LLM 양성 · 재검토 포함 메시지 수)", "",
          f"| 지표 | v1(보고) | v2 | {tag} | v2 대비 | 기준 | 판정 |", "|---|---|---|---|---|---|---|",
          f"| 주 지표(특성어긋남 + 근거없는고민연결) | {pp['v1']} | {pp['v2']} | {pp[tag]} | {rate(pp['v2'], pp[tag])} | "
          f"≤ {V3R_PRIMARY_MAX} | {'통과' if gates['primary'] else '미달'} |",
          f"| 9개 유형 합계 | {a9['v1']} | {a9['v2']} | {a9[tag]} | {rate(a9['v2'], a9[tag])} | ≤ {V3R_ALL9_MAX} | "
          f"{'통과' if gates['all9'] else '미달'} |", ""]
    for key, name in (("primary_positive", "주 지표"), ("llm_positive", "9개 유형")):
        bb = sum(1 for i in ids if V["v2"][i][key] and not V[tag][i][key])
        cc = sum(1 for i in ids if not V["v2"][i][key] and V[tag][i][key])
        t = r1.paired_test(bb, cc)
        L.append(f"- {name} v2 → {tag}: 개선 {bb} · 악화 {cc}, {t['method']} p = {t['p']:.3f} (보고용)")
    L += ["", f"| 유형 | v1 | v2 | {tag} |", "|---|---|---|---|"]
    for ty in gd.CLAIM_TYPES:
        n = {t: sum(1 for i in ids if V[t][i]["type_counts"].get(ty)) for t in tags}
        L.append(f"| {ty} | {n['v1']} | {n['v2']} | {n[tag]} |")
    L.append("")

    # 품질(판정기, 같은 시점)
    both = [i for i in ids if JI["v2"][i] and JI[tag][i]]
    v1ok = [i for i in both if JI["v1"][i]]
    L += [f"## 품질 (판정기 2회 평균, 같은 시점, 짝 {len(both)}건)", "",
          f"| 지표 | v1(보고) | v2 | {tag} | v2 대비 차이 | 단측 90% 하한 | 기준 | 판정 |", "|---|---|---|---|---|---|---|---|"]
    q = {}
    for k in (*V3R_UP, *V3R_KEEP):
        mean, lower = boot_lower90([JI[tag][i][k] - JI["v2"][i][k] for i in both])
        good = lower > V3R_NI and (mean > 0 if k in V3R_UP else True)
        gates[k] = good
        q[k] = {"mean": mean, "lower": lower}
        v1m = sum(JI["v1"][i][k] for i in v1ok) / len(v1ok) if v1ok else float("nan")
        crit = "상승 · 하한 > −0.15" if k in V3R_UP else "하한 > −0.15"
        word = ("개선" if lower > 0 else "점추정 상승") if (k in V3R_UP and good) else ("통과" if good else "미달")
        L.append(f"| {k} | {v1m:.3f} | {sum(JI['v2'][i][k] for i in both) / len(both):.3f} | "
                 f"{sum(JI[tag][i][k] for i in both) / len(both):.3f} | {mean:+.3f} | {lower:+.3f} | {crit} | {word} |")
    d = [(V[tag][i]["purpose_conveyed"] == "O") - (V["v2"][i]["purpose_conveyed"] == "O") for i in ids]
    mean, lower = boot_lower90(d)
    gates["purpose"] = lower > V3R_NI
    q["purpose"] = {"mean": mean, "lower": lower}
    po = {t: sum(V[t][i]["purpose_conveyed"] == "O" for i in ids) for t in tags}
    L.append(f"| 목적 전달(검증기) | {po['v1']}/{len(ids)} | {po['v2']}/{len(ids)} | {po[tag]}/{len(ids)} | {mean:+.3f} | "
             f"{lower:+.3f} | 하한 > −0.15 | {'통과' if gates['purpose'] else '미달'} |")
    L += ["", "- 보고 문구 규칙: 품질은 하한 > 0일 때만 '개선', 그 외 통과는 '점추정 상승'."]
    by_p: dict[str, list[str]] = {}
    for i in ids:
        by_p.setdefault(M[tag][i]["purpose"], []).append(i)
    L += ["", f"| 목적 | 건수 | 목적 전달 v2 | {tag} | personalization v2 | {tag} |", "|---|---|---|---|---|---|"]
    for pu, its in sorted(by_p.items()):
        jj = [i for i in its if i in both]

        def pv(t):
            return sum(JI[t][i]["personalization"] for i in jj) / len(jj) if jj else float("nan")
        L.append(f"| {pu} | {len(its)} | {sum(V['v2'][i]['purpose_conveyed'] == 'O' for i in its)} | "
                 f"{sum(V[tag][i]['purpose_conveyed'] == 'O' for i in its)} | {pv('v2'):.2f} | {pv(tag):.2f} |")
    L.append("")

    # 보고: 고민 연결 0건 하위 집단 · 피드백 루프 진입 · 날짜 · 형식
    zero = [i for i in both if not any(c["need_type"] == "concern" for c in fit.get(i, {}).get("connectable", []))]
    rest = [i for i in both if i not in zero]

    def sub(S, t):
        return sum(JI[t][i]["personalization"] for i in S) / len(S) if S else float("nan")
    fail = {t: sum(1 for i in ids if JI[t][i] and JI[t][i]["pass_rate"] < 1) for t in tags}
    tones = get_brand_tones().get("brand_ton_prompt", {})
    dates = sum(1 for i in ids
                if m3.regex_metrics_v3(M[tag][i], str(tones.get(M[tag][i]["brand"], "") or ""))["date_from_created_at"])
    import run_d1
    det = run_d1.make_detector()

    def fv(f):
        return (not f["json_ok"]) or f["title_over"] or f["body_over"]
    fmt = {t: sum(fv(m1.format_metrics(M[t][i], det)) for i in ids) for t in ("v2", tag)}
    L += ["## 보고 (판정 아님)", "",
          f"- 고민 연결 0건 항목({tag} fit): {len(zero)}건 — personalization v2 {sub(zero, 'v2'):.2f} → {tag} "
          f"{sub(zero, tag):.2f}; 나머지 {len(rest)}건 v2 {sub(rest, 'v2'):.2f} → {tag} {sub(rest, tag):.2f}. "
          "판정은 70건 전체로 하고, 미달 원인이 이 집단에 몰리면 보고서에 '루브릭 방향 충돌'로 적는다.",
          f"- 판정기 불통과(2회 중 1회 이상, 배포 시 피드백 재작성 루프 진입): v1 {fail['v1']} · v2 {fail['v2']} · {tag} {fail[tag]}",
          f"- DB 등록 시각 날짜(date_from_created_at): {tag} {dates}건",
          f"- 형식 위반(JSON · 길이): v2 {fmt['v2']} · {tag} {fmt[tag]}", ""]
    ok_all = all(gates.values())
    L += [f"## 판정: {'통과' if ok_all else '미달'} — " + ", ".join(f"{k} {'O' if v else 'X'}" for k, v in gates.items())]
    (DEV / tag / "compare.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (DEV / tag / "compare.json").write_text(json.dumps(
        {"tag": tag, "passed": ok_all, "gates": gates, "primary": pp, "all9": a9, "quality": q, "judge_fail": fail,
         "zero_concern": len(zero), "date_from_created_at": dates}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n".join(L))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("stageA", "stageB", "v3r"))
    ap.add_argument("--tag", required=True)
    a = ap.parse_args()
    {"stageA": stage_a, "stageB": stage_b, "v3r": compare_v3r}[a.cmd](a.tag)


if __name__ == "__main__":
    main()
