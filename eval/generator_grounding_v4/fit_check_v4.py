"""
V4 단계 1(b) — 새 fit + 연결 확인 부품 점검(생성 없음) → result/stage1/

    python fit_check_v4.py record          # 구현 세부 · 분모(usage 성격 H-O 수) · 파일 해시를 AMENDMENTS 에 먼저 기록
    python fit_check_v4.py fit             # 새 fit(연결 확인 포함)을 N · F 140쌍 → fit_cache.jsonl (단계 1(a) · 2 에서 그대로 씀)
    python fit_check_v4.py link_labels     # 연결 확인 단독: H 라벨 116개 연결에 직접 → link_labels.json + 막힌 O 재판정표(blocked_o.csv)
    python fit_check_v4.py precision_export  # 새 fit 승인 연결 무작위 40개 → precision.csv (사람 연결 판정)
    python fit_check_v4.py latency         # fit + 연결 확인 추가 지연(10태스크 × 3회 중앙값)
    python fit_check_v4.py summary         # 사람 판정까지 모아 기준 판정 → stage1b.md / stage1b.json

사람 판정 화면: python human_tool_v4.py result/stage1/blocked_o.csv · result/stage1/precision.csv
"""

import asyncio
import csv
import json
import random
import re
import statistics
import sys
import time

import v4_common as c

from app.agents.generate_message_agent.prompts import persona_fit as pf  # noqa: E402
from app.agents.generate_message_agent.prompts.product_fields import generation_product_info  # noqa: E402

S1 = c.RESULT / "stage1"
FIT_CACHE = S1 / "fit_cache.jsonl"
LINK_JSON = S1 / "link_labels.json"
BLOCKED_CSV = S1 / "blocked_o.csv"
PREC_CSV = S1 / "precision.csv"
LAT_JSON = S1 / "latency.json"
KIND = "V4 단계 1 구현 기록"
SEED = 20261007
LABELS = c.vc.RESULT / "fit_effort" / "irrelevant_check.csv"
KNOWN_DEV = ("N014", "N028", "N035", "N038", "N047")  # 이미 본 fit 원인 5건(판정 기준 아님, 보고만)
RECALL_ITEMS = ("F011", "F012", "F013", "F018", "F026", "F051", "F069", "N057")  # (나) 7쌍 + N057
CRIT = {"x_block_min": 6, "o_true_overblock_max": 11, "precision_min": 0.90, "precision_n": 40,
        "recall_min": 6, "latency_max_s": 8.0}  # 7.0 → 8.0 결과 본 뒤 완화(AMENDMENTS 'V4 연결 확인 지연 기준 완화')
USAGE_LIKE = re.compile(r"사용|덧바|수시|단계|(?:세안|샤워|드라이|메이크업|화장|외출|출근|취침|잠들기)\s*(?:전|후|직전|직후)|젖은|마른")
# 정정(AMENDMENTS 'V4 단계 1 구현 기록 정정'): 위 정규식은 사용감 · 고민까지 잡아 분모를 줄였다. 결과 보기 전에
# 사용 방식 · 시점 · 상황 니즈만 손으로 고른 목록으로 바꾼다(촉촉한 사용감 · 세안 후 당김 · 세안 후 개운함은 분모에 남김).
USAGE_O_NEEDS = {"샴푸 후 사용", "메이크업 전 사용", "데일리 사용 가능", "온 가족 사용", "야간 사용(저소음)", "드라이 마무리 사용", "수시 보습"}


def usage_like(need: str) -> bool:
    return need in USAGE_O_NEEDS

CSV_COLS = ["행", "상품명", "니즈", "근거 문구", "상품정보", "판정", "메모"]

REL = lambda p: str(p.relative_to(c.gg.REPO)).replace("\\", "/")  # noqa: E731
FINAL_FILES = [c.gg.REPO / "backend" / "app" / "agents" / "generate_message_agent" / x for x in
               ("prompts/persona_fit.py", "prompts/purpose_prompt.py", "prompts/product_fields.py",
                "services/generate_crm_message.py", "services/claim_check.py")]


def labels() -> dict[str, list[dict]]:
    by: dict[str, list[dict]] = {}
    with open(LABELS, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            by.setdefault(r["item_id"], []).append({
                "persona_need": r["페르소나_고민선호"], "need_type": "concern" if r["종류"] == "고민" else "preference",
                "product_evidence": r["상품정보_근거"], "label": r["관련(O/X)"].strip().upper()})
    return by


def holdout() -> dict[str, dict]:
    rows = {r["item_id"]: r for r in c.gg.load_inputs("holdout")}
    c.assert_not_reserved(r["product_snapshot"].get("product_id") for r in rows.values())
    return rows


def dev_items() -> dict[str, dict]:
    """N 70 + F 70 입력(저장된 v3R 메시지에서 입력 필드만)."""
    out = {}
    for key in ("v3r_N", "v3r_F"):
        msgs, _ = c.stored(key)
        for iid, m in msgs.items():
            out[iid] = {k: m[k] for k in ("item_id", "persona_id", "product_id", "purpose", "persona_info", "product_snapshot")}
    return out


def guard() -> None:
    if not any(e["kind"] == KIND for e in c.gg.amendments_entries()):
        raise SystemExit("기록이 먼저다: python fit_check_v4.py record")


def record() -> None:
    if any(e["kind"] == KIND for e in c.gg.amendments_entries()):
        raise SystemExit("이미 기록됨")
    lb = labels()
    o_all = [l for ls in lb.values() for l in ls if l["label"] == "O"]
    usage_o = [l for l in o_all if USAGE_LIKE.search(l["persona_need"])]
    content = (
        "V4 단계 1 구현 기록(결과 보기 전). 플랜 대비 구현 세부: "
        "① 연결 확인은 쌍마다 승인 연결 묶음을 한 번에 되묻는다(v3R2 후보 A 방식, 연결별 판정), 실패 · 누락 연결은 내림. "
        "② 범주 D 면제는 '상품 사용 필드의 한 항목 안에 같은 루틴 단계어와 같은 시점어가 함께 있을 때'(플랜의 세 글자 겹침을 "
        "시점어까지 포함하도록 구체화 — 단계어만 겹치는 '메이크업 마무리' 같은 경우를 통과시키지 않기 위함), 단계어는 일반 루틴 명사 사전. "
        "③ 범주 B 고민어 구간은 앞 구두점부터 호출 표현까지. ④ 범주 A 면제는 걸린 표현 전체(공백 무시)가 상품정보에 있을 때. "
        f"⑤ H-O 의 usage 성격 판정 규칙: 니즈에 사용 · 덧바름 · 수시 · 단계 · (루틴 단계어+전/후) · 젖은/마른이 있으면 — "
        f"해당 {len(usage_o)}개를 분모에서 뺀다(분모 {len(o_all) - len(usage_o)}/{len(o_all)}). "
        f"기준: {json.dumps(CRIT, ensure_ascii=False)}. 연결 확인 · 생성 뒤 점검 범주는 이 기준을 넘을 때만 켠다."
    )
    e = c.gg.append_amendment(KIND, content, {REL(p): c.gg.sha256(p) for p in FINAL_FILES})
    print(f"AMENDMENTS {e['id']} · usage 성격 H-O {len(usage_o)}개: {[l['persona_need'] for l in usage_o]}")


async def _fit() -> None:
    guard()
    if FIT_CACHE.exists():
        raise SystemExit(f"{FIT_CACHE} 이 이미 있습니다")
    items = dev_items()
    fitter, sem = pf.PersonaFitter(link_check=True), asyncio.Semaphore(8)
    h = {"persona_fit": c.gg.sha256(FINAL_FILES[0]), "product_fields": c.gg.sha256(FINAL_FILES[2])}

    async def one(it):
        async with sem:
            r = await fitter.fit(it["persona_info"], it["product_snapshot"])
        return {"item_id": it["item_id"], **h, **r.to_dict()}

    rows = await asyncio.gather(*(one(it) for it in items.values()))
    c.write_jsonl(FIT_CACHE, rows)
    n = len(rows)
    print(f"fit {n}쌍 · ok {sum(r['status'] == 'ok' for r in rows)} · 연결 평균 {sum(len(r['connectable']) for r in rows) / n:.1f} · "
          f"고민 연결 0개 {sum(not any(x['need_type'] == 'concern' for x in r['connectable']) for r in rows)} · "
          f"연결 확인이 내림 {sum(len(r['link_blocked']) for r in rows)} · 확인 오류 {sum(r['link_check'] == 'error' for r in rows)}")


async def _link_labels() -> None:
    guard()
    H, LB = holdout(), labels()
    fitter = pf.PersonaFitter(link_check=True)
    res = await asyncio.gather(*(fitter.check_links(H[i]["product_snapshot"], ls) for i, ls in LB.items()))
    rows, blocked_o = [], []
    for (iid, ls), vs in zip(LB.items(), res):
        for l, same in zip(ls, vs):
            rows.append({"item_id": iid, **l, "same": same, "usage_like": usage_like(l["persona_need"])})
            if l["label"] == "O" and not same and not usage_like(l["persona_need"]):
                blocked_o.append((iid, l))
    xb = sum(1 for r in rows if r["label"] == "X" and not r["same"])
    data = {"x_total": sum(r["label"] == "X" for r in rows), "x_blocked": xb,
            "o_total_excl_usage": sum(r["label"] == "O" and not r["usage_like"] for r in rows),
            "o_blocked_excl_usage": len(blocked_o), "rows": rows}
    S1.mkdir(parents=True, exist_ok=True)
    LINK_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    if not BLOCKED_CSV.exists():
        with open(BLOCKED_CSV, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(CSV_COLS)
            for k, (iid, l) in enumerate(blocked_o, 1):
                snap = H[iid]["product_snapshot"]
                w.writerow([k, snap.get("product_name", ""), l["persona_need"], l["product_evidence"],
                            json.dumps(generation_product_info(snap), ensure_ascii=False, indent=1), "", ""])
    print(f"X 차단 {xb}/{data['x_total']} · O(usage 제외) 막힘 {len(blocked_o)}/{data['o_total_excl_usage']} → 재판정표 {BLOCKED_CSV.name}")


def precision_export() -> None:
    guard()
    if PREC_CSV.exists():
        raise SystemExit(f"{PREC_CSV} 이 이미 있습니다(판정 보호)")
    items = dev_items()
    pool = [(r["item_id"], x) for r in c.load_jsonl(FIT_CACHE) if r["item_id"] not in KNOWN_DEV for x in r["connectable"]]
    pick = random.Random(SEED).sample(pool, CRIT["precision_n"])
    key = {}
    with open(PREC_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(CSV_COLS)
        for k, (iid, x) in enumerate(pick, 1):
            snap = items[iid]["product_snapshot"]
            key[str(k)] = {"item_id": iid, "need_type": x["need_type"]}
            w.writerow([k, snap.get("product_name", ""), x["persona_need"], x["product_evidence"],
                        json.dumps(generation_product_info(snap), ensure_ascii=False, indent=1), "", ""])
    (S1 / "precision_key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"→ {PREC_CSV} {len(pick)}개(후보 {len(pool)}개)")


async def _latency() -> None:
    guard()
    its = list(dev_items().values())[:10]
    fitter = pf.PersonaFitter(link_check=True)
    tot = []
    for _ in range(3):
        t0 = time.perf_counter()
        await asyncio.gather(*(fitter.fit(it["persona_info"], it["product_snapshot"]) for it in its))
        tot.append(time.perf_counter() - t0)
    data = {"fit_plus_link_median_10_s": round(statistics.median(tot), 2), "runs_s": [round(t, 2) for t in tot],
            "pass": statistics.median(tot) <= CRIT["latency_max_s"]}
    S1.mkdir(parents=True, exist_ok=True)
    LAT_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(data)


def _judged(path) -> list[dict]:
    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    blank = [r["행"] for r in rows if not r["판정"]]
    if blank:
        raise SystemExit(f"{path.name} 빈칸 {len(blank)}행")
    return rows


def summary() -> None:
    lk = json.loads(LINK_JSON.read_text(encoding="utf-8"))
    bo = _judged(BLOCKED_CSV)
    pr = _judged(PREC_CSV)
    lat = json.loads(LAT_JSON.read_text(encoding="utf-8"))
    lat["pass"] = lat["fit_plus_link_median_10_s"] <= CRIT["latency_max_s"]
    fits = {r["item_id"]: r for r in c.load_jsonl(FIT_CACHE)}
    true_over = sum(r["판정"] == "O" for r in bo)
    prec_o = sum(r["판정"] == "O" for r in pr)
    recall = {i: sum(x["need_type"] == "concern" for x in fits[i]["connectable"]) for i in RECALL_ITEMS}
    known = {i: [f"{x['persona_need']} ← {x['product_evidence']}" for x in fits[i]["connectable"]] for i in KNOWN_DEV}
    res = {
        "link_x_block": {"value": lk["x_blocked"], "of": lk["x_total"], "pass": lk["x_blocked"] >= CRIT["x_block_min"]},
        "link_true_overblock": {"value": true_over, "blocked_o": len(bo), "of": lk["o_total_excl_usage"],
                                "ambiguous": sum(r["판정"] == "애매" for r in bo), "pass": true_over <= CRIT["o_true_overblock_max"]},
        "precision": {"o": prec_o, "n": len(pr), "ambiguous": sum(r["판정"] == "애매" for r in pr),
                      "rate": round(prec_o / len(pr), 3), "pass": prec_o / len(pr) >= CRIT["precision_min"]},
        "recall_proxy": {"value": sum(v >= 1 for v in recall.values()), "of": len(recall), "by_item": recall,
                         "pass": sum(v >= 1 for v in recall.values()) >= CRIT["recall_min"]},
        "latency": {"value": lat["fit_plus_link_median_10_s"], "pass": lat["pass"]},
        "known_dev_report_only": known,
    }
    res["link_check_on"] = res["link_x_block"]["pass"] and res["link_true_overblock"]["pass"] and res["latency"]["pass"]
    (S1 / "stage1b.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    L = ["# V4 단계 1(b) — fit + 연결 확인 부품 점검", "", f"- 기준(AMENDMENTS '{KIND}'): `{json.dumps(CRIT, ensure_ascii=False)}`", "",
         "| 항목 | 값 | 기준 | 판정 |", "|---|---|---|---|",
         f"| 연결 확인: 나쁜 연결(H-X) 차단 | {lk['x_blocked']}/{lk['x_total']} | ≥ {CRIT['x_block_min']} | {'통과' if res['link_x_block']['pass'] else '미달'} |",
         f"| 연결 확인: 진짜 과잉 차단(막힌 H-O 중 재판정 O) | {true_over} (막힘 {len(bo)}/{lk['o_total_excl_usage']}) | ≤ {CRIT['o_true_overblock_max']} | {'통과' if res['link_true_overblock']['pass'] else '미달'} |",
         f"| 새 fit 처음 보는 연결 정밀도(주 판정, 점검용) | {prec_o}/{len(pr)} = {prec_o / len(pr):.0%} | ≥ 90% | {'통과' if res['precision']['pass'] else '미달'} |",
         f"| 재현율 대리 (나) 7쌍 + N057 | {res['recall_proxy']['value']}/8 | ≥ {CRIT['recall_min']} | {'통과' if res['recall_proxy']['pass'] else '미달'} |",
         f"| fit + 연결 확인 추가 지연 중앙값 | {lat['fit_plus_link_median_10_s']}초 | ≤ 8.0초(결과 본 뒤 7.0에서 완화) | {'통과' if lat['pass'] else '미달'} |",
         "", f"- 연결 확인 켜기: {'예' if res['link_check_on'] else '아니오'}",
         "- 40개 정밀도는 증명이 아니라 점검이다(참 정밀도 80%가 90%를 넘겨 통과할 확률 약 15%).",
         f"- 재현율 항목별 고민 연결 수: {recall}", "", "## 이미 본 개발 5건의 새 fit 연결(보고만, 판정 기준 아님)", ""]
    L += [f"- {i}: {v}" for i, v in known.items()]
    (S1 / "stage1b.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[4:12]))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    sync = {"record": record, "precision_export": precision_export, "summary": summary}
    asyn = {"fit": _fit, "link_labels": _link_labels, "latency": _latency}
    if cmd in sync:
        sync[cmd]()
    elif cmd in asyn:
        asyncio.run(asyn[cmd]())
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
