"""
잠금 전 검증기 시험 (1단계) — 오탐과 재현율.

    python pilot_prelock.py select    # 비대상 원본 10건 고르기 → result/pilot/messages.jsonl, inject_template.csv
    python pilot_prelock.py build     # 사용자가 채운 inject_template.csv → result/pilot_inject/messages.jsonl
    python pilot_prelock.py summary   # 두 측정 결과를 사람이 보기 쉬운 표로 → result/pilot/summary.md

- 대상은 게이트 실험 원본 중 사람 확인 대상이 아닌 원본(review_audit.json 의 originals 에 없는 것)이다.
  진행 중인 원본 확인의 눈가림을 지키기 위해서다. 신제품 · 베스트셀러 목적을 3건 이상 넣는다.
- 재현율: 그중 5건의 사본에 사용자가 정답을 아는 날조 문장 8개 이상(8개 유형 모두)을 넣는다.
- 음성 대조: 근거가 실제로 그 상품 DB에 있는 문장 2~3개도 넣는다.
"""

import csv
import json
import random
import sys

import gg_common as gg
import grounding_def as gd
from gg_common import load_jsonl, write_jsonl

SEED = 20261005
PILOT = gg.RESULT / "pilot"
INJECT = gg.RESULT / "pilot_inject"
FOCUS = ("신제품 홍보", "베스트셀러 제품 소개")


def originals() -> dict[str, dict]:
    return {o["original_id"]: o for o in load_jsonl(gg.INSAMPLE_SOURCE)}


def as_message(o: dict) -> dict:
    return {"item_id": o["original_id"], "title": o["title"], "message": o["message"], "json_ok": bool(o["title"]),
            "product_snapshot": o["product_snapshot"], "persona_info": o["persona_info"],
            "purpose": o["purpose"], "brand": o["brand"]}


def select() -> None:
    audit = json.loads((gg.QG / "result" / "main" / "review_audit.json").read_text(encoding="utf-8"))
    audited = set(audit["originals"])
    pool = [o for oid, o in sorted(originals().items()) if oid not in audited]
    rng = random.Random(SEED)
    focus = [o for o in pool if o["purpose"] in FOCUS]
    rest = [o for o in pool if o["purpose"] not in FOCUS]
    pick = rng.sample(focus, min(4, len(focus)))
    pick += rng.sample(rest, 10 - len(pick))
    pick.sort(key=lambda o: o["original_id"])
    PILOT.mkdir(parents=True, exist_ok=True)
    write_jsonl(PILOT / "messages.jsonl", [as_message(o) for o in pick])
    # 사본 5건 — 신제품 · 베스트셀러를 우선
    copies = sorted(pick, key=lambda o: (o["purpose"] not in FOCUS, o["original_id"]))[:5]
    with open(PILOT / "inject_template.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["copy_id", "base_item", "purpose", "product_name", "db_proof_points_or_value(음성 대조 재료)",
                    "message(원문)", "inject_sentence", "inject_type(" + "·".join(gd.CLAIM_TYPES) + "·음성대조)",
                    "expected(근거 없음/근거 있음)"])
        for i, o in enumerate(copies, 1):
            p = o["product_snapshot"]
            proof = " | ".join(str(x) for x in (p.get("proof_points") or []) + (p.get("value") or []))[:400]
            for slot in range(3):  # 사본마다 세 줄(8개 유형 + 음성 대조 2~3개를 5개 사본에 나눠 넣는다)
                w.writerow([f"C{i}", o["original_id"], o["purpose"], p.get("product_name", ""), proof if slot == 0 else "",
                            o["message"] if slot == 0 else "", "", "", ""])
    print(f"시험 원본 10건: {[o['original_id'] for o in pick]} (목적: {[o['purpose'] for o in pick]})")
    print(f"→ {PILOT / 'messages.jsonl'}, {PILOT / 'inject_template.csv'}")


def build() -> None:
    by_id = originals()
    with open(PILOT / "inject_template.csv", encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("inject_sentence") or "").strip()]
    if not rows:
        raise SystemExit("inject_template.csv 에 inject_sentence 가 비어 있습니다")
    type_col = [c for c in rows[0] if c.startswith("inject_type")][0]
    exp_col = [c for c in rows[0] if c.startswith("expected")][0]
    copies: dict[str, dict] = {}
    truth = []
    for r in rows:
        o = by_id[r["base_item"]]
        m = copies.setdefault(r["copy_id"], {**as_message(o), "item_id": f"{r['copy_id']}:{o['original_id']}"})
        sent = r["inject_sentence"].strip()
        sent = sent if sent.endswith((".", "!", "?")) else sent + "."
        body = m["message"]
        cut = body.rfind(".", 0, max(0, len(body) - 5))
        m["message"] = (body[:cut + 1] + " " + sent + body[cut + 1:]) if cut > 0 else sent + " " + body
        truth.append({"item_id": m["item_id"], "sentence": sent, "type": r[type_col].strip(), "expected": r[exp_col].strip()})
    INJECT.mkdir(parents=True, exist_ok=True)
    write_jsonl(INJECT / "messages.jsonl", list(copies.values()))
    write_jsonl(INJECT / "truth.jsonl", truth)
    print(f"사본 {len(copies)}건 · 넣은 문장 {len(truth)}개 → {INJECT}")


def summary() -> None:
    L = ["# 잠금 전 검증기 시험", ""]
    for name, d in (("비대상 원본 10건 (오탐 확인)", PILOT), ("사본 (재현율 · 음성 대조)", INJECT)):
        path = d / "measure.jsonl"
        if not path.exists():
            continue
        msgs = {m["item_id"]: m for m in load_jsonl(d / "messages.jsonl")}
        L += [f"## {name}", ""]
        for r in load_jsonl(path):
            v = r["verifier"]
            m = msgs[r["item_id"]]
            L += [f"### {r['item_id']} · {r['purpose']} · 판정 {v['class'] if v else '-'}", "",
                  f"> {m['title']} / {m['message']}", ""]
            if v:
                for c in v["claims"]:
                    flag = "자동 재검토" if c["auto_review"] else ("구간 불일치" if not c["span_in_message"] else "근거 없음")
                    L.append(f"- **{flag}** [{c['type']} · {c['db_judgment']} · {c['source']}] \"{c['span']}\" — {c['reason']}"
                             + (f" (가까운 DB: {c['closest_db_text'][:80]})" if c["closest_db_text"] else ""))
                L.append(f"- 근거 있음 {v['n_supported']}개: " + "; ".join(f"\"{s['span']}\"({s['db_field']})" for s in v["supported_claims"][:8]))
                L.append(f"- 목적 전달: {v['purpose_conveyed']} — {v['purpose_reason']}")
            L.append("")
        if (d / "truth.jsonl").exists():
            res = {r["item_id"]: r for r in load_jsonl(path)}
            L += ["## 넣은 문장별 결과", "", "| 사본 | 유형 | 기대 | 문장 | 검증기 |", "|---|---|---|---|---|"]
            for t in load_jsonl(d / "truth.jsonl"):
                v = res.get(t["item_id"], {}).get("verifier") or {}
                hit = [c for c in v.get("claims", []) if gg_common_squash(c["span"]) in gg_common_squash(t["sentence"])
                       or gg_common_squash(t["sentence"]) in gg_common_squash(c["span"])]
                got = ("근거 없음(자동 재검토)" if hit and all(c["auto_review"] for c in hit) else "근거 없음") if hit else "근거 있음 또는 못 찾음"
                L.append(f"| {t['item_id']} | {t['type']} | {t['expected']} | {t['sentence']} | {got} |")
            L.append("")
    out = PILOT / "summary.md"
    out.write_text("\n".join(L), encoding="utf-8")
    print(f"→ {out}")


def gg_common_squash(s: str) -> str:
    import re
    return re.sub(r"\s+", "", s or "")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    {"select": select, "build": build, "summary": summary}[sys.argv[1]]()
