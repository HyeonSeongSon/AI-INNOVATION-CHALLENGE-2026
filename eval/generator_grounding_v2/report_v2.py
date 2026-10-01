"""
v2 보고서 (방향성 확인 라운드) — result/main/report_v2.md

    python report_v2.py

입력: result/main/{v1,v2,nofit}/measure.jsonl, result/main/human/{sample_map.json,human_check.csv},
      result/main/latency.json(있으면). 통계 함수는 v1 report.py 것을 import 한다(파일은 고치지 않음).
판정 규칙은 PREREG_v2.md 를 따른다. 채택 기준 1(확정 · 시사 · 미달)은 격하로 계산하지 않는다.
"""

import csv
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from typing import Any

import v2_common as vc
from gg_common import load_jsonl

import report as r1  # noqa: E402 — paired_test · paired_boot_lower · item_judge · weighted_rate
import grounding_def_v2 as gd  # noqa: E402

MAIN = vc.RESULT / "main"
CONDS = ("v1", "v2", "nofit")
STRATA = ("양성", "재검토", "음성")
CLEANUP = ("number_mutation", "review_verified", "change_hook_title", "test_kind_missing")
NI = {"pass_rate": -0.15, "personalization": -0.3, "cta_clarity": -0.3, "tone": -0.3, "purpose_conveyed": -0.15}
FORMAT_MAX_INCREASE, CTA_MIN, REGRESSION_LIMIT = 2, 0.95, 1
LATENCY_CAP_S, THROUGHPUT_CAP = 5.0, 1.5


def load(cond: str) -> dict[str, dict]:
    p = MAIN / cond / "measure.jsonl"
    return {r["item_id"]: r for r in load_jsonl(p)} if p.exists() else {}


def messages(cond: str) -> dict[str, dict]:
    p = MAIN / cond / "messages.jsonl"
    return {r["item_id"]: r for r in load_jsonl(p)} if p.exists() else {}


def human() -> dict[str, dict[str, list[int]]]:
    mp, hp = MAIN / "human" / "sample_map.json", MAIN / "human" / "human_check.csv"
    out: dict[str, dict[str, list[int]]] = {c: {h: [] for h in STRATA} for c in CONDS}
    if not (mp.exists() and hp.exists()):
        return out
    mapping = json.loads(mp.read_text(encoding="utf-8"))
    rows = {r["code"]: r for r in csv.DictReader(open(hp, encoding="utf-8-sig"))}
    for code, m in mapping.items():
        v = (rows.get(code, {}).get("unsupported_claim(O/X)") or "").strip().upper()
        if v in ("O", "X"):
            out[m["tag"]][m["stratum"]].append(1 if v == "O" else 0)
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    MAIN.mkdir(parents=True, exist_ok=True)
    M = {c: load(c) for c in CONDS}
    common = sorted(set.intersection(*(set(M[c]) for c in CONDS if M[c]))) if all(M.values()) else []
    L = ["# 생성기 근거 개선 v2 — 방향성 확인 라운드 보고서", "",
         f"- 작성: {datetime.now(timezone.utc).isoformat()} · 조건: v1 / v2(연결 모듈 포함) / v2-nofit(정리만) · 짝 {len(common)}건",
         "- 채택 기준 1(확정 · 시사 · 미달)은 판정력 부족으로 계산하지 않는다(PREREG_v2.md).", ""]
    if not common:
        L.append("측정 결과 없음")
        (MAIN / "report_v2.md").write_text("\n".join(L), encoding="utf-8")
        return
    ver = [i for i in common if all(M[c][i]["verifier"] for c in CONDS)]

    # ── 무결성
    base = json.loads(vc.BASELINE_V2.read_text(encoding="utf-8")) if vc.BASELINE_V2.exists() else {}
    now = vc.gg.file_hashes(vc.PREREG_V2_FILES)
    status = {k: ("기준과 같음" if base.get("prereg_v2", {}).get(k) == v else "기준과 다름") for k, v in now.items()}
    gate_ok = base.get("gate") == vc.gg.file_hashes(vc.gg.GATE_FILES)
    L += ["## 무결성", "", f"- 사전 등록 v2 파일: {status}", f"- 게이트 파일 4개: {'기준과 같음' if gate_ok else '기준과 다름'}", ""]

    # ── 주 지표 (방향)
    H = human()
    sizes = {c: {h: sum(1 for i in ver if M[c][i]["verifier"]["class_primary"] == h) for h in STRATA} for c in CONDS}
    samples = {c: dict(H[c]) for c in CONDS}
    for h in ("재검토", "음성"):  # nofit 의 확인하지 않은 층은 v2 비율을 빌려 쓴다(사전 등록)
        if not samples["nofit"][h]:
            samples["nofit"][h] = samples["v2"][h]
    fallback = {"양성": 1.0, "재검토": 1.0, "음성": 0.0}
    llm = {c: sum(M[c][i]["verifier"]["primary_positive"] for i in ver) for c in CONDS}
    hw = {c: r1.weighted_rate(sizes[c], {h: v for h, v in samples[c].items() if v}, fallback) for c in CONDS}
    L += ["## 주 지표 — 페르소나 유래 근거 없는 주장(특성어긋남 · 근거없는고민연결), 방향만", "",
          "| | v1 | v2 | v2-nofit |", "|---|---|---|---|",
          "| LLM 양성(재검토 포함) | " + " | ".join(f"{llm[c]}/{len(ver)} ({llm[c] / len(ver):.1%})" for c in CONDS) + " |",
          "| LLM 층(양성 · 재검토 · 음성) | " + " | ".join(" · ".join(str(sizes[c][h]) for h in STRATA) for c in CONDS) + " |",
          "| 사람 가중 비율(점추정) | " + " | ".join(f"{hw[c]:.1%}" for c in CONDS) + " |",
          "| 사람 확인 O/확인 (층별) | " + " | ".join(", ".join(f"{h} {sum(H[c][h])}/{len(H[c][h])}" for h in STRATA if H[c][h]) or "-" for c in CONDS) + " |", ""]
    for a, b in (("v1", "v2"), ("v1", "nofit"), ("nofit", "v2")):
        bb = sum(1 for i in ver if M[a][i]["verifier"]["primary_positive"] and not M[b][i]["verifier"]["primary_positive"])
        cc = sum(1 for i in ver if not M[a][i]["verifier"]["primary_positive"] and M[b][i]["verifier"]["primary_positive"])
        t = r1.paired_test(bb, cc)
        L.append(f"- 참고 짝 비교 {a} → {b}: 개선 {bb} · 악화 {cc}, {t['method']} p = {t['p']:.3f}")
    L += ["- nofit 의 재검토 · 음성 층 사람 비율은 v2 의 같은 층 비율을 빌려 쓴 값이다.", ""]

    # ── 정리 항목
    def cnt(c, key):
        return sum(1 for i in common if M[c][i]["regex"][key])
    L += ["## 정리 항목 (전체 70건, 메시지 수)", "", "| 항목 | v1 | v2 | v2-nofit |", "|---|---|---|---|"]
    names = {"number_mutation": "C 숫자 · 단위 변형", "review_verified": "D 리뷰 기반 검증", "change_hook_title": "E 변화 암시 제목",
             "test_kind_missing": "H 종류어 없는 시험 CTA", "cleanup_any": "**합산(하나라도)**", "cta_template_usage": "CTA 틀 '사용법과 ○○'"}
    for k, n in names.items():
        L.append(f"| {n} | " + " | ".join(str(cnt(c, k)) for c in CONDS) + " |")
    tests = {}
    for key in ("cleanup_any", "cta_template_usage"):
        for b in ("nofit", "v2"):
            bb = sum(1 for i in common if M["v1"][i]["regex"][key] and not M[b][i]["regex"][key])
            cc = sum(1 for i in common if not M["v1"][i]["regex"][key] and M[b][i]["regex"][key])
            tests[(key, b)] = r1.paired_test(bb, cc)
            L.append(f"- {names[key]} v1 → {b}: 개선 {bb} · 악화 {cc}, p = {tests[(key, b)]['p']:.4f}")
    msgs = {c: messages(c) for c in CONDS}
    best = [i for i in common if M["v1"][i]["purpose"] == "베스트셀러 제품 소개"]
    if best:
        lab = {c: sum(1 for i in best if "베스트셀러" in (msgs[c][i]["title"] + msgs[c][i]["message"])) for c in CONDS}
        L.append(f"- 베스트셀러 목적의 '베스트셀러' 라벨 포함: " + " · ".join(f"{c} {lab[c]}/{len(best)}" for c in CONDS))
    L.append("")
    item_ok = {b: all(cnt(b, k) <= cnt("v1", k) for k in CLEANUP) for b in ("nofit", "v2")}

    # ── 8개 유형 회귀 한도
    L += ["## 8개 유형 회귀 한도 (LLM 클레임이 있는 메시지 수, v1 대비 +1 이내)", "", "| 유형 | v1 | v2 | v2-nofit | 판정 |", "|---|---|---|---|---|"]
    over = {"v2": [], "nofit": []}
    for t in gd.V1_TYPES:
        n = {c: sum(1 for i in ver if M[c][i]["verifier"]["type_counts"].get(t)) for c in CONDS}
        bad = [c for c in ("v2", "nofit") if n[c] - n["v1"] > REGRESSION_LIMIT]
        for c in bad:
            over[c].append(t)
        L.append(f"| {t} | {n['v1']} | {n['v2']} | {n['nofit']} | {'초과: ' + ', '.join(bad) + ' (사람 확인 필요)' if bad else '통과'} |")
    L.append("")

    # ── 비열등
    def ni(b: str) -> tuple[bool, list[str]]:
        rows, ok_all = [], True
        jb = {i: r1.item_judge(M["v1"][i]) for i in common}
        ja = {i: r1.item_judge(M[b][i]) for i in common}
        both = [i for i in common if jb[i] and ja[i]]
        for k in ("pass_rate", "personalization", "cta_clarity", "tone"):
            d = [ja[i][k] - jb[i][k] for i in both]
            mean, lower = r1.paired_boot_lower(d)
            ok = lower > NI[k]
            ok_all &= ok
            rows.append(f"| {k} | {sum(jb[i][k] for i in both) / len(both):.3f} | {sum(ja[i][k] for i in both) / len(both):.3f} | "
                        f"{mean:+.3f} | {lower:+.3f} | {NI[k]} | {'통과' if ok else '미달'} |")
        d = [(M[b][i]["verifier"]["purpose_conveyed"] == "O") - (M["v1"][i]["verifier"]["purpose_conveyed"] == "O") for i in ver]
        mean, lower = r1.paired_boot_lower(d)
        ok = lower > NI["purpose_conveyed"]
        ok_all &= ok
        rows.append(f"| purpose_conveyed(LLM) | {sum(M['v1'][i]['verifier']['purpose_conveyed'] == 'O' for i in ver)}/{len(ver)} | "
                    f"{sum(M[b][i]['verifier']['purpose_conveyed'] == 'O' for i in ver)}/{len(ver)} | {mean:+.3f} | {lower:+.3f} | "
                    f"{NI['purpose_conveyed']} | {'통과' if ok else '미달'} |")
        fv = lambda r: (not r["format"]["json_ok"]) or r["format"]["title_over"] or r["format"]["body_over"]  # noqa: E731
        fb, fa = sum(fv(M["v1"][i]) for i in common), sum(fv(M[b][i]) for i in common)
        cta = sum(M[b][i]["format"]["cta_last"] for i in common) / len(common)
        ok_all &= (fa - fb <= FORMAT_MAX_INCREASE) and cta >= CTA_MIN
        rows.append(f"| 형식 위반 수 | {fb} | {fa} | {fa - fb:+d} | - | +{FORMAT_MAX_INCREASE} | {'통과' if fa - fb <= FORMAT_MAX_INCREASE else '미달'} |")
        rows.append(f"| CTA 존재율 | - | {cta:.0%} | - | - | ≥{CTA_MIN:.0%} | {'통과' if cta >= CTA_MIN else '미달'} |")
        return ok_all, rows
    ni_res = {}
    for b in ("v2", "nofit"):
        ok, rows = ni(b)
        ni_res[b] = ok
        L += [f"## 비열등 — v1 → {b}", "", "| 지표 | v1 | " + b + " | 차이 | 단측 95% 하한 | 여유 | 판정 |",
              "|---|---|---|---|---|---|---|", *rows, ""]

    # ── 지연
    lat = json.loads((MAIN / "latency.json").read_text(encoding="utf-8")) if (MAIN / "latency.json").exists() else None
    lat_ok = None
    if lat:
        lat_ok = lat["added_median_10_s"] <= LATENCY_CAP_S and lat["throughput_ratio_40"] <= THROUGHPUT_CAP
        L += ["## 지연 (연결 모듈)", "", f"- 태스크 10개 추가 지연 중앙값 {lat['added_median_10_s']:.2f}초(상한 {LATENCY_CAP_S}) · "
              f"40개 처리 시간 비율 {lat['throughput_ratio_40']:.2f}배(상한 {THROUGHPUT_CAP}) → {'통과' if lat_ok else '미달'}", ""]

    # ── 반영 판정
    reg_ok = {b: not over[b] for b in ("nofit", "v2")}
    clean_adopt = item_ok["nofit"] and reg_ok["nofit"] and ni_res["nofit"]
    fit_dir = llm["v2"] < llm["nofit"] and hw["v2"] < hw["nofit"]
    fit_adopt = fit_dir and ni_res["v2"] and bool(lat_ok)
    fallback_conservative = ni_res["nofit"] and reg_ok["nofit"] and llm["nofit"] <= llm["v1"] and hw["nofit"] <= hw["v1"]
    L += ["## 운영 반영 판정 (사전 등록 규칙)", "",
          f"- 프롬프트 정리: {'반영' if clean_adopt else '보류'} — 개별 항목 ≤ v1 {item_ok['nofit']}, 회귀 한도 {reg_ok['nofit']}"
          f"{' (초과 유형: ' + ', '.join(over['nofit']) + ' → 사람 확인 후 재판정)' if over['nofit'] else ''}, 비열등 {ni_res['nofit']}",
          f"- 연결 모듈(fit): {'반영' if fit_adopt else '반영 안 함'} — 추가 효과 방향(LLM · 사람 모두 v2 < nofit) {fit_dir}, "
          f"비열등 {ni_res['v2']}, 지연 {lat_ok}. 새 해악은 사람 확인 메모로 따로 본다.",
          f"- fit 없는 경로 페르소나 문구: {'보수적 문구' if fallback_conservative else 'v1 문구'}",
          "- 보고 문구: A · B 감소 효과는 검증되지 않았다(방향성 확인 라운드). 포트폴리오에도 '채택 판정 아님'을 적는다.", "",
          "## 한계", "",
          "- 묶음 개입(정리 규칙 여러 줄을 함께 바꿈) · 효과는 초안 생성 단계 한정(피드백 재작성 경로는 연결 모듈을 거치지 않음)",
          "- 연결 모듈은 실행마다 결과가 달라진다(재실행 Jaccard 0.33). 평가는 캐시를 썼고 운영은 실시간 호출이다.",
          "- 평가 페르소나(자유 서술) ≠ 운영 페르소나(구조화). 연결 모듈 무관 근거 6.9%(95% 3.5~13.0%).",
          "- 검증기 정밀도는 새 유형에서 불확실하다(사전 계산 8~64%). 판정기는 personalization 을 보상한다."]
    (MAIN / "report_v2.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"→ {MAIN / 'report_v2.md'}")


if __name__ == "__main__":
    main()
