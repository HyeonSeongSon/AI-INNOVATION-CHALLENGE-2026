"""
V4 단계 1(a) — 생성 뒤 점검(claim_check) 오프라인 측정(비용 0) → result/stage1/offline_check.{json,md}

    python offline_check_v4.py

- 대상: 저장된 v3R N 70 · v3R F 70 · v0 F 70(210 메시지), 정답은 검증기 지적 문구.
- 범주 A · D 분모: 단계 0 확정 목록(denominators.csv, AMENDMENTS 24). B: 근거없는고민연결 지적. C: 근거없는고민연결 · 특성어긋남 지적.
- 잡음: 적중 위치가 지적 문구 위치와 겹칠 때만(C 는 위치가 없어 니즈와 지적 문구가 세 글자 이상 겹칠 때).
- fit: N 은 저장된 v3R fit, F(v3R · v0)는 단계 1(b)의 V4 fit 으로 근사(v3R F fit 은 저장되지 않음, v0 는 fit 없이 생성됨).
- D 는 면제 범위 두 설정(usage · all)을 함께 낸다(미리 정한 보정 1회).
- 한계: 사전을 다듬은 데이터와 잰 데이터가 같은 210건이다.
"""

import csv
import json
import sys

import v4_common as c

from app.agents.generate_message_agent.prompts import persona_fit as pf  # noqa: E402
from app.agents.generate_message_agent.services import claim_check as cc  # noqa: E402

S1 = c.RESULT / "stage1"
CRIT = {"min_pos": 10, "recall_min": 0.5, "fp_max": 0.10, "union_max": 0.10}
SUBSET = {"A": ["v3r_N:N031", "v3r_N:N042", "v3r_F:F028", "v3r_F:F038", "v3r_F:F047", "v3r_F:F058", "v3r_N:N035"],
          "B": ["v3r_N:N029", "v3r_N:N048", "v3r_N:N057", "v3r_F:F062"],
          "C": ["v3r_N:N029", "v3r_N:N048", "v3r_N:N057", "v3r_F:F062"],
          "D": ["v3r_N:N014", "v3r_N:N035", "v3r_F:F026"]}


def fits() -> dict[str, pf.FitResult]:
    out = {f"v3r_N:{r['item_id']}": pf.FitResult.from_dict(r) for r in c.load_jsonl(c.V3_RESULT / "dev" / "v3r" / "fit_cache.jsonl")}
    v4 = {r["item_id"]: pf.FitResult.from_dict(r) for r in c.load_jsonl(S1 / "fit_cache.jsonl")}
    for iid, f in v4.items():
        if iid.startswith("F"):
            out[f"v3r_F:{iid}"] = f
            out[f"v0_F:{iid}"] = f
    return out


def span_pos(m: dict, span: str):
    for where in ("title", "message"):
        i = (m[where] or "").find(span)
        if i >= 0:
            return where, i, i + len(span)
    return None


def caught(hit: dict, m: dict, span: str) -> bool:
    if hit["start"] < 0:  # C
        return pf.overlap3(hit["text"], span)
    pos = span_pos(m, span)
    return bool(pos) and pos[0] == hit["where"] and hit["start"] < pos[2] and pos[1] < hit["end"]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    F = fits()
    msgs, meas = {}, {}
    for key in c.STORED:
        ms, me = c.stored(key)
        msgs.update({f"{key}:{i}": v for i, v in ms.items()})
        meas.update({f"{key}:{i}": v for i, v in me.items()})
    with open(c.STAGE0 / "denominators.csv", encoding="utf-8-sig") as f:
        dl = {r["cid"]: (r["사용자 수정(A/D/제외, 비우면 동의)"] or r["Claude 분류"]) for r in csv.DictReader(f)}
    denom: dict[str, list[tuple[str, str]]] = {"A": [], "B": [], "C": [], "D": []}
    for cid, lab in dl.items():
        if lab in ("A", "D"):
            k, iid, j = cid.split(":")
            denom[lab].append((f"{k}:{iid}", meas[f"{k}:{iid}"]["verifier"]["claims"][int(j)]["span"]))
    for mid, me in meas.items():
        for cl in me["verifier"]["claims"]:
            if cl["type"] == "근거없는고민연결":
                denom["B"].append((mid, cl["span"]))
            if cl["type"] in ("근거없는고민연결", "특성어긋남"):
                denom["C"].append((mid, cl["span"]))
    clean = [mid for mid, me in meas.items() if not me["verifier"]["claims"]]

    def run(cat: str, d_scope: str = "usage") -> dict:
        hits = {mid: cc.detect(m["title"], m["message"], m["product_snapshot"], F.get(mid), categories=(cat,), d_scope=d_scope)
                for mid, m in msgs.items()}
        got = [(mid, span) for mid, span in denom[cat] if any(caught(h, msgs[mid], span) for h in hits[mid])]
        sub = [x for x in denom[cat] if x[0] in SUBSET[cat]]
        sub_got = [x for x in got if x[0] in SUBSET[cat]]
        fp = sum(1 for mid in clean if hits[mid])
        n = len(denom[cat])
        r = {"pos": n, "caught": len(got), "recall": round(len(got) / n, 3) if n else None,
             "v3r_subset": f"{len(sub_got)}/{len(sub)}", "v3r_subset_missed": sorted({x[0] for x in sub} - {x[0] for x in sub_got}),
             "fp_msgs": fp, "clean_msgs": len(clean), "fp_rate": round(fp / len(clean), 3),
             "flagged_msgs": sum(1 for v in hits.values() if v)}
        r["pass"] = (n >= CRIT["min_pos"] and r["recall"] >= CRIT["recall_min"] and r["fp_rate"] <= CRIT["fp_max"])
        r["min_pos_short"] = n < CRIT["min_pos"]
        r["_flagged"] = {mid for mid, v in hits.items() if v}
        r["fp_examples"] = [f"{mid}: {[h['text'] for h in hits[mid]][:3]}" for mid in clean if hits[mid]][:15]
        r["missed_examples"] = [f"{mid}: {span}" for mid, span in denom[cat] if (mid, span) not in got][:15]
        return r

    res = {"A": run("A"), "B": run("B"), "C": run("C"), "D": run("D", "usage"), "D_all": run("D", "all")}
    passing = [k for k in ("A", "B", "C", "D") if res[k]["pass"] or (k == "D" and res["D_all"]["pass"])]
    union = set().union(*(res["D_all" if k == "D" and not res["D"]["pass"] else k]["_flagged"] for k in passing)) if passing else set()
    res["union"] = {"categories": passing, "flagged": len(union), "of": len(msgs), "rate": round(len(union) / len(msgs), 3),
                    "pass": len(union) / len(msgs) <= CRIT["union_max"]}
    for v in res.values():
        v.pop("_flagged", None)
    S1.mkdir(parents=True, exist_ok=True)
    (S1 / "offline_check.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    L = ["# V4 단계 1(a) — 생성 뒤 점검 오프라인 측정", "", f"- 기준: `{json.dumps(CRIT, ensure_ascii=False)}`",
         "- 한계: 사전을 다듬은 데이터와 잰 데이터가 같은 210건. F 의 fit 은 V4 fit 근사.", "",
         "| 범주 | 분모 | 잡음 | 재현율 | v3R 부분집합 | 지적 없는 메시지 걸림 | 판정 |", "|---|---|---|---|---|---|---|"]
    for k in ("A", "B", "C", "D", "D_all"):
        r = res[k]
        verdict = "통과" if r["pass"] else ("분모 부족(결정권자)" if r["min_pos_short"] else "미달")
        L.append(f"| {k} | {r['pos']} | {r['caught']} | {r['recall']} | {r['v3r_subset']} | {r['fp_msgs']}/{r['clean_msgs']} = {r['fp_rate']} | {verdict} |")
    u = res["union"]
    L += ["", f"- 켜는 후보 범주 합집합 걸림: {u['flagged']}/{u['of']} = {u['rate']} ({u['categories']}) → {'통과' if u['pass'] else '미달'}", ""]
    for k in ("A", "B", "C", "D", "D_all"):
        L += [f"## {k}", "", f"- 놓친 v3R 부분집합: {res[k]['v3r_subset_missed']}", "- 오탐 예:"]
        L += [f"  - {x}" for x in res[k]["fp_examples"]]
        L += ["- 놓친 예:"] + [f"  - {x}" for x in res[k]["missed_examples"]] + [""]
    (S1 / "offline_check.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[5:13]))


if __name__ == "__main__":
    main()
