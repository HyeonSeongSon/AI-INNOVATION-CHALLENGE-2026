"""
V4 단계 2 판정 — <tag> 대 v3R(N + F 140건). 모든 게이트를 한 번에 판정한다 → result/dev/<tag>/compare.{md,json}

    python compare_v4.py --tag v4

- 검증기: V4 는 새 실행, v3R 은 저장분(사용자 결정 — 실행 간 흔들림이 섞인 참고 비교).
- 판정기: v3R 과 V4 를 같은 시점에 2회씩 재판정한 값(judge_<tag>/).
- 기준(AMENDMENTS 'V4 사전 기록(단계 0)'): 주 지표 ≤ 6 · 짝 비교 악화 ≤ 개선, 9개 유형 ≤ 10, 개인화 하한 > −0.15(비열등),
  CTA · tone · 통과율 · 목적 전달 하한 > −0.15, 재생성 비율 ≤ 10%, 형식 위반 0.
"""

import argparse
import json
import sys

import v4_common as c
import main_v4 as mv4
import metrics_v4 as mt

import report as r1  # noqa: E402 — v1 보고 도구(item_judge · paired_test)
import grounding_def_v2 as gd  # noqa: E402
import compare_v3 as cv3  # noqa: E402 — boot_lower90 · judged

PRIMARY_MAX, ALL9_MAX, NI, REGEN_MAX = 6, 10, -0.15, 0.10
QUALITY = ("personalization", "cta_clarity", "tone", "pass_rate")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    tag = ap.parse_args().tag
    out_dir = mv4.DEV / tag
    M = {"v3r": {m["item_id"]: m for m in mv4.v3r_messages()}, tag: {m["item_id"]: m for m in mv4.tag_messages(tag)}}
    V = {"v3r": {}, tag: {r["item_id"]: r["verifier"] for r in c.load_jsonl(out_dir / "measure.jsonl") if r.get("verifier")}}
    for key in ("v3r_N", "v3r_F"):
        _, meas = c.stored(key)
        V["v3r"].update({i: r["verifier"] for i, r in meas.items()})
    jdir = mv4.judge_dir(tag)
    J = {t: cv3.judged(t, jdir) for t in ("v3r", tag)}
    ids = sorted(set(M["v3r"]) & set(M[tag]) & set(V["v3r"]) & set(V[tag]))
    JI = {t: {i: r1.item_judge(J[t].get(i, {"judge": []})) for i in ids} for t in ("v3r", tag)}
    fits = mt.v4_fits()
    gates, L = {}, [f"# V4 판정 — {tag} 대 v3R (개발 시험, N + F {len(ids)}건)", "",
                    "- 검증기: V4 새 실행 · v3R 저장분(실행 간 흔들림이 섞인 참고 비교, 사용자 결정). 판정기: 같은 시점 재판정.",
                    "- 모든 행을 한 번에 판정한다(AMENDMENTS 'V4 사전 기록(단계 0)').", ""]

    # 근거
    pp = {t: sum(V[t][i]["primary_positive"] for i in ids) for t in ("v3r", tag)}
    a9 = {t: sum(V[t][i]["llm_positive"] for i in ids) for t in ("v3r", tag)}
    imp = {k: sum(1 for i in ids if V["v3r"][i][k] and not V[tag][i][k]) for k in ("primary_positive", "llm_positive")}
    wor = {k: sum(1 for i in ids if not V["v3r"][i][k] and V[tag][i][k]) for k in ("primary_positive", "llm_positive")}
    gates["primary"] = pp[tag] <= PRIMARY_MAX and wor["primary_positive"] <= imp["primary_positive"]
    gates["all9"] = a9[tag] <= ALL9_MAX
    L += ["## 근거 (검증기, LLM 양성 · 재검토 포함 메시지 수)", "", f"| 지표 | v3R | {tag} | 기준 | 판정 |", "|---|---|---|---|---|",
          f"| 주 지표(특성어긋남 + 근거없는고민연결) | {pp['v3r']} | {pp[tag]} | ≤ {PRIMARY_MAX} · 악화 ≤ 개선 | {'통과' if gates['primary'] else '미달'} |",
          f"| 9개 유형 합계 | {a9['v3r']} | {a9[tag]} | ≤ {ALL9_MAX} | {'통과' if gates['all9'] else '미달'} |", ""]
    for k, name in (("primary_positive", "주 지표"), ("llm_positive", "9개 유형")):
        t = r1.paired_test(imp[k], wor[k])
        L.append(f"- {name} v3R → {tag}: 개선 {imp[k]} · 악화 {wor[k]}, {t['method']} p = {t['p']:.3f} (보고용, 검증기 실행이 달라 참고)")
    L += ["", f"| 유형 | v3R | {tag} |", "|---|---|---|"]
    for ty in gd.CLAIM_TYPES:
        L.append(f"| {ty} | {sum(1 for i in ids if V['v3r'][i]['type_counts'].get(ty))} | {sum(1 for i in ids if V[tag][i]['type_counts'].get(ty))} |")
    L.append("")

    # 품질
    both = [i for i in ids if JI["v3r"][i] and JI[tag][i]]
    q = {}
    L += [f"## 품질 (판정기 2회 평균, 같은 시점, 짝 {len(both)}건)", "",
          f"| 지표 | v3R | {tag} | 차이 | 단측 90% 하한 | 기준 | 판정 |", "|---|---|---|---|---|---|---|"]
    for k in QUALITY:
        mean, lower = cv3.boot_lower90([JI[tag][i][k] - JI["v3r"][i][k] for i in both])
        gates[k] = lower > NI
        q[k] = {"mean": mean, "lower": lower}
        L.append(f"| {k} | {sum(JI['v3r'][i][k] for i in both) / len(both):.3f} | {sum(JI[tag][i][k] for i in both) / len(both):.3f} | "
                 f"{mean:+.3f} | {lower:+.3f} | 하한 > −0.15 | {'통과' if gates[k] else '미달'} |")
    d = [(V[tag][i]["purpose_conveyed"] == "O") - (V["v3r"][i]["purpose_conveyed"] == "O") for i in ids]
    mean, lower = cv3.boot_lower90(d)
    gates["purpose"] = lower > NI
    q["purpose"] = {"mean": mean, "lower": lower}
    L.append(f"| 목적 전달(검증기) | {sum(V['v3r'][i]['purpose_conveyed'] == 'O' for i in ids)}/{len(ids)} | "
             f"{sum(V[tag][i]['purpose_conveyed'] == 'O' for i in ids)}/{len(ids)} | {mean:+.3f} | {lower:+.3f} | 하한 > −0.15 | "
             f"{'통과' if gates['purpose'] else '미달'} |")

    # 재생성 · 형식
    st = [M[tag][i].get("claim_check") for i in ids]
    regen = sum(s in ("regenerated", "still_hit") for s in st) / len(ids)
    gates["regen"] = regen <= REGEN_MAX
    import measure as m1
    import run_d1
    det = run_d1.make_detector()
    fmt = sum(1 for i in ids if (lambda f: (not f["json_ok"]) or f["title_over"] or f["body_over"] or not f["cta_last"])(
        m1.format_metrics(M[tag][i], det)))
    gates["format"] = fmt == 0
    L += [f"| 재생성 비율 | - | {regen:.1%} | - | - | ≤ 10% | {'통과' if gates['regen'] else '미달'} |",
          f"| 형식 위반(JSON · 길이 · CTA 마지막) | - | {fmt} | - | - | 0 | {'통과' if gates['format'] else '미달'} |", ""]

    # 보고(게이트 아님)
    gp = {t: sum(mt.grounded_personalization(M[t][i], V[t][i], fits[i]) for i in ids) for t in ("v3r", tag)}
    mat = [i for i in both if mt.matched(fits[i])]
    unm = [i for i in both if not mt.matched(fits[i])]

    def avg(S, t, k="personalization"):
        return sum(JI[t][i][k] for i in S) / len(S) if S else float("nan")
    a_hits = [i for i in ids if M[tag][i].get("claim_hits")]
    still = [i for i in ids if M[tag][i].get("claim_check") == "still_hit"]
    a_vs_ver = sum(1 for i in a_hits if V[tag][i]["type_counts"].get("수치") or V[tag][i]["type_counts"].get("변화차별"))
    lat = json.loads((out_dir / "latency.json").read_text(encoding="utf-8")) if (out_dir / "latency.json").exists() else {}
    L += ["## 보고 (게이트 아님)", "",
          f"- 개인화 점추정 변화: {q['personalization']['mean']:+.3f}",
          f"- 근거 있는 개인화 비율: v3R {gp['v3r']}/{len(ids)} → {tag} {gp[tag]}/{len(ids)}",
          f"- 짝 층 개인화(V4 fit 기준): 맞는 짝 {len(mat)}건 v3R {avg(mat, 'v3r'):.2f} → {tag} {avg(mat, tag):.2f} · "
          f"안 맞는 짝 {len(unm)}건 v3R {avg(unm, 'v3r'):.2f} → {tag} {avg(unm, tag):.2f}",
          f"- 점검 A: 첫 생성에서 걸린 메시지 {len(a_hits)}건(그중 재생성 뒤에도 걸림 {len(still)}건), "
          f"걸린 메시지 중 최종 메시지에 검증기 수치 · 변화차별 지적 {a_vs_ver}건",
          f"- 점검 상태: { {s: st.count(s) for s in set(st)} }",
          f"- 지연(5태스크 배치, 재생성 포함): {lat.get('batch5_median_s', '-')}초 중앙값 · p90 {lat.get('batch5_p90_s', '-')}초",
          f"- 판정기 불통과(2회 중 1회 이상): v3R {sum(1 for i in ids if JI['v3r'][i] and JI['v3r'][i]['pass_rate'] < 1)} · "
          f"{tag} {sum(1 for i in ids if JI[tag][i] and JI[tag][i]['pass_rate'] < 1)}", ""]
    by_p: dict[str, list[str]] = {}
    for i in ids:
        by_p.setdefault(M[tag][i]["purpose"], []).append(i)
    L += [f"| 목적 | 건수 | 개인화 v3R | {tag} |", "|---|---|---|---|"]
    for pu, its in sorted(by_p.items()):
        jj = [i for i in its if i in both]
        L.append(f"| {pu} | {len(its)} | {avg(jj, 'v3r'):.2f} | {avg(jj, tag):.2f} |")
    ok_all = all(gates.values())
    L += ["", f"## 판정: {'통과' if ok_all else '미달'} — " + ", ".join(f"{k} {'O' if v else 'X'}" for k, v in gates.items())]
    (out_dir / "compare.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (out_dir / "compare.json").write_text(json.dumps(
        {"tag": tag, "passed": ok_all, "gates": gates, "primary": pp, "all9": a9, "improved": imp, "worsened": wor,
         "quality": q, "regen_rate": regen, "format_violations": fmt, "grounded_personalization": gp},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
