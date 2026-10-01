"""
v2 잠금 전 검증기 시험 (1단계) — 정의 v2 · 추론 강도(high · medium) 결정.

    python prelock_v2.py build                 # 시험 세트 3종 → result/prelock/{pilot,inject,human}/messages.jsonl
    python prelock_v2.py run --effort high     # 세 세트를 measure_v2 로 측정(이미 한 항목은 건너뜀)
    python prelock_v2.py run --effort medium
    python prelock_v2.py summary               # result/prelock/summary.md (effort 별 비교)

세트
- pilot : v1 잠금 전 시험의 비대상 원본 10건(오탐 확인, 정답 없음 — 사람이 눈으로 확인)
- inject: v1 사본 5건(넣은 문장 15개) + v2 새 유형 문장 4개(고민연결 날조 1 · 숫자 단위 변형 1 · 리뷰 기반 검증 1 ·
          고민연결 음성 대조 1). 정답: 날조 15 · 음성 대조 4
- human : 1라운드 사람 확인 메시지 15건(사람 O 5 · 사람 X 10). 사람 판정은 v1 정의(8개 유형) 기준이라
          v2 의 class_v1types(8개 유형만)와 비교한다. 새 유형(고민연결) 지적은 따로 보고한다.

effort 결정 규칙(PREREG_v2): 날조 놓침 0 · 음성 대조 오탐 0 · 사람 판정 일치율이 high 와 같거나 나으면 medium.
"""

import argparse
import asyncio
import json
import sys

import v2_common as vc
from gg_common import load_jsonl, write_jsonl

PRE = vc.RESULT / "prelock"
V1R = vc.gg.RESULT

# v2 새 유형 문장 — copy_id 는 v1 사본(C1~C5)에 덧붙인다. 정답은 상품 스냅숏 문자열 검색으로 확인했다(build 가 다시 확인).
NEW_SENTENCES = [
    {"copy_id": "C3", "sentence": "입술 착색이 고민인 분께 딱 맞는 립밤이에요.", "type": "근거없는고민연결",
     "expected": "근거 없음", "absent": ["착색"]},
    {"copy_id": "C3", "sentence": "입술 건조함이 고민인 분께 잘 맞는 립밤이에요.", "type": "음성대조",
     "expected": "근거 있음", "present": ["입술 건조"]},
    {"copy_id": "C4", "sentence": "사용 2일 만에 모발강화율 132%를 확인했어요.", "type": "수치",
     "expected": "근거 없음", "absent": ["2일"]},
    {"copy_id": "C2", "sentence": "리뷰 1,783건이 검증한 팔레트예요.", "type": "검증주장",
     "expected": "근거 없음", "absent_fields": ["proof_points", "value"]},
]
# 1라운드 사람 확인 코드 → (조건, 항목, 사람 판정). O: 사람이 근거 없음으로 본 것, X: LLM 지적이 있었으나 사람은 아니라고 본 것
HUMAN_CASES = {
    "K007": ("after", "H062", "O"), "K035": ("after", "H051", "O"), "K030": ("before", "H030", "O"),
    "K032": ("before", "H023", "O"), "K036": ("before", "H065", "O"),
    "K002": ("before", "H045", "X"), "K011": ("after", "H016", "X"), "K012": ("after", "H059", "X"),
    "K015": ("before", "H043", "X"), "K021": ("before", "H006", "X"), "K025": ("after", "H067", "X"),
    "K027": ("after", "H063", "X"), "K039": ("before", "H020", "X"), "K041": ("after", "H054", "X"),
    "K038": ("before", "H012", "X"),
}


def _insert(body: str, sent: str) -> str:
    cut = body.rfind(".", 0, max(0, len(body) - 5))
    return (body[:cut + 1] + " " + sent + body[cut + 1:]) if cut > 0 else sent + " " + body


def build() -> None:
    for name in ("pilot", "inject", "human"):
        (PRE / name).mkdir(parents=True, exist_ok=True)
    # pilot
    write_jsonl(PRE / "pilot" / "messages.jsonl", load_jsonl(V1R / "pilot" / "messages.jsonl"))
    # inject — v1 사본 + 새 문장
    msgs = {m["item_id"]: m for m in load_jsonl(V1R / "pilot_inject" / "messages.jsonl")}
    truth = load_jsonl(V1R / "pilot_inject" / "truth.jsonl")
    by_copy = {k.split(":")[0]: k for k in msgs}
    for s in NEW_SENTENCES:
        iid = by_copy[s["copy_id"]]
        snap = json.dumps(msgs[iid]["product_snapshot"], ensure_ascii=False)
        for w in s.get("absent", []):
            assert w not in snap, f"{s['sentence']}: '{w}'가 스냅숏에 있음"
        for w in s.get("present", []):
            assert w in snap, f"{s['sentence']}: '{w}'가 스냅숏에 없음"
        for f in s.get("absent_fields", []):
            assert not msgs[iid]["product_snapshot"].get(f), f"{s['sentence']}: {f} 가 비어 있지 않음"
        msgs[iid]["message"] = _insert(msgs[iid]["message"], s["sentence"])
        truth.append({"item_id": iid, "sentence": s["sentence"], "type": s["type"], "expected": s["expected"]})
    write_jsonl(PRE / "inject" / "messages.jsonl", list(msgs.values()))
    write_jsonl(PRE / "inject" / "truth.jsonl", truth)
    # human
    src = {t: {m["item_id"]: m for m in load_jsonl(V1R / "holdout" / t / "messages.jsonl")} for t in ("before", "after")}
    rows, labels = [], {}
    for code, (tag, iid, lab) in HUMAN_CASES.items():
        rows.append({**src[tag][iid], "item_id": code})
        labels[code] = {"tag": tag, "item_id": iid, "human": lab}
    write_jsonl(PRE / "human" / "messages.jsonl", rows)
    (PRE / "human" / "labels.json").write_text(json.dumps(labels, ensure_ascii=False, indent=2), encoding="utf-8")
    n_fab = sum(1 for t in truth if t["expected"] == "근거 없음")
    print(f"pilot 10 · inject {len(msgs)}건(날조 {n_fab} · 음성 대조 {len(truth) - n_fab}) · human {len(rows)}건 → {PRE}")


async def run(effort: str) -> None:
    import measure_v2 as mv
    for name in ("pilot", "inject", "human"):
        d = PRE / name
        await mv.run(mv.m1.load_messages(d / "messages.jsonl"), d / effort, effort, 0, False)


def _sq(s: str) -> str:
    return "".join((s or "").split())


def summary() -> None:
    L = ["# v2 잠금 전 검증기 시험", ""]
    res: dict[str, dict] = {}
    for effort in ("high", "medium"):
        if not (PRE / "inject" / effort / "measure.jsonl").exists():
            continue
        r: dict = {}
        inj = {x["item_id"]: x for x in load_jsonl(PRE / "inject" / effort / "measure.jsonl")}
        rows = []
        for t in load_jsonl(PRE / "inject" / "truth.jsonl"):
            v = inj[t["item_id"]]["verifier"] or {}
            hit = [c for c in v.get("claims", []) if c["span_in_message"] and
                   (_sq(c["span"]) in _sq(t["sentence"]) or _sq(t["sentence"]) in _sq(c["span"]))]
            got = "근거 없음" if hit else "근거 있음 또는 못 찾음"
            rows.append((t, got, [c["type"] for c in hit]))
        r["missed"] = [t["sentence"] for t, got, _ in rows if t["expected"] == "근거 없음" and got != "근거 없음"]
        r["neg_fp"] = [t["sentence"] for t, got, _ in rows if t["expected"] == "근거 있음" and got == "근거 없음"]
        r["inject_rows"] = rows
        hum = {x["item_id"]: x for x in load_jsonl(PRE / "human" / effort / "measure.jsonl")}
        labels = json.loads((PRE / "human" / "labels.json").read_text(encoding="utf-8"))
        agree, n, detail = 0, 0, []
        for code, lab in labels.items():
            v = hum[code]["verifier"]
            if v is None:  # 결측(오류)은 일치율에서 뺀다
                detail.append((code, lab, "결측", "-", {}))
                continue
            pred = "O" if v.get("v1types_positive") else "X"
            agree += pred == lab["human"]
            n += 1
            detail.append((code, lab, pred, v.get("class_primary"), v.get("type_counts", {})))
        r["human_agree"], r["human_n"], r["human_detail"] = agree, n, detail
        r["missing"] = sum(1 for name in ("pilot", "inject", "human")
                           for x in load_jsonl(PRE / name / effort / "measure.jsonl") if x["verifier"] is None)
        pil = load_jsonl(PRE / "pilot" / effort / "measure.jsonl")
        r["pilot"] = [(x["item_id"], (x["verifier"] or {}).get("class"), (x["verifier"] or {}).get("class_primary"),
                       [(c["type"], c["span"][:40]) for c in (x["verifier"] or {}).get("claims", [])]) for x in pil]
        usage = {"prompt": 0, "completion": 0}
        for name in ("pilot", "inject", "human"):
            u = json.loads((PRE / name / effort / "measure_meta.json").read_text(encoding="utf-8"))["usage"]
            usage["prompt"] += u["prompt"]
            usage["completion"] += u["completion"]
        r["usage"] = usage
        res[effort] = r

    L += ["| | high | medium |", "|---|---|---|"]
    metrics = [
        ("날조 놓침", lambda r: str(len(r["missed"]))),
        ("음성 대조 오탐", lambda r: str(len(r["neg_fp"]))),
        ("사람 판정 일치(8개 유형)", lambda r: "{}/{}".format(r["human_agree"], r["human_n"])),
        ("출력 토큰", lambda r: "{:,}".format(r["usage"]["completion"])),
        ("검증 결측(오류)", lambda r: str(r["missing"])),
    ]
    for label, f in metrics:
        L.append("| {} | {} | {} |".format(label, *(f(res[e]) if e in res else "-" for e in ("high", "medium"))))
    if "high" in res and "medium" in res:
        h, md = res["high"], res["medium"]
        if h["missing"] or md["missing"]:
            L += ["", "**결정 보류:** 검증 결측이 있어 다시 돌린 뒤 판정한다."]
        else:
            ok = (not md["missed"] and not md["neg_fp"] and md["human_agree"] >= h["human_agree"])
            L += ["", f"**결정 규칙 적용:** {'medium 으로 잠금' if ok else 'high 유지'}"]
    for e, r in res.items():
        L += ["", f"## {e}", "", "### 넣은 문장", "", "| 유형 | 기대 | 문장 | 검증기 | 붙은 유형 |", "|---|---|---|---|---|"]
        L += [f"| {t['type']} | {t['expected']} | {t['sentence']} | {got} | {', '.join(ty)} |" for t, got, ty in r["inject_rows"]]
        L += ["", "### 사람 판정 사례 (8개 유형 기준 비교, 주 지표 층은 참고)", "",
              "| 코드 | 항목 | 사람 | v2(8개 유형) | v2 주 지표 층 | 유형별 지적 |", "|---|---|---|---|---|---|"]
        L += [f"| {c} | {lab['tag']} {lab['item_id']} | {lab['human']} | {p} | {kp} | "
              f"{', '.join(f'{k} {n}' for k, n in tc.items() if n)} |" for c, lab, p, kp, tc in r["human_detail"]]
        L += ["", "### 비대상 원본 10건 (눈으로 확인)", ""]
        L += [f"- {i} · 9유형 {k} · 주 지표 {kp} · {cl}" for i, k, kp, cl in r["pilot"]]
    out = PRE / "summary.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"→ {out}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("build", "run", "summary"))
    ap.add_argument("--effort", choices=("high", "medium"))
    a = ap.parse_args()
    if a.cmd == "build":
        build()
    elif a.cmd == "run":
        asyncio.run(run(a.effort))
    else:
        summary()
