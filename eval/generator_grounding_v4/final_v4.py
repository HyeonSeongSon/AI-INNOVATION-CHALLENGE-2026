"""
V4 최종 시험 — 초기(v0) 대 V4, 한 번만(PREREG_final_v4.md). 순서는 v3 최종 절차와 같다.

    python final_v4.py capacity          # 1. 표본 용량(건수만, 잠그기 전) → PREREG 4절에 적는다
    python final_v4.py dummy             # 3. 도구 더미 시험(API 호출 없음): v0 페르소나 원문 · 점검 미적용 · V4 해시
    python final_v4.py lock              # 2 · 4. PREREG · 측정 도구 · 모델 설정 해시 잠금 → baseline_final_v4.json + AMENDMENTS
    python final_v4.py sample            # 5. 예약 상품에서 표본(시드 20261021, 부위 맞춤) → result/final/inputs.jsonl
    python final_v4.py gen --cond v0     # 6. v0 생성(내용 출력 없음)
    python final_v4.py gen --cond v4     # 7. V4 생성(AMENDMENTS 'V4 최종 버전 확정' 해시와 같을 때만, fit · 점검 저장)
    python final_v4.py measure           # 8. v0 · V4 같은 시점 검증기 medium + 판정기 2회
    python final_v4.py human_export      # 9. 사람 확인표(층별 배분, 버전 가림) → result/final/human/human_check.csv
    python final_v4.py report            # 보고서 → result/final/report_final_v4.md
"""

import argparse
import asyncio
import csv
import json
import random
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone

import v4_common as c

FINAL = c.RESULT / "final"
BASELINE = c.HERE / "baseline_final_v4.json"
PREREG = c.HERE / "PREREG_final_v4.md"
SEED, N, MIN_N, JUDGE_RUNS, EFFORT, NEG_PER_COND = 20261021, 85, 70, 2, "medium", 12
KIND_LOCK, KIND_FIX, KIND_SAMPLE, KIND_VERSION = "V4 최종 측정 잠금", "V4 최종 측정 도구 수정", "V4 최종 측정 표본", "V4 최종 버전 확정"
STRATA = ("양성", "재검토", "음성")
NI = {"pass_rate": -0.15, "personalization": -0.3, "cta_clarity": -0.3, "tone": -0.3, "accuracy": -0.3, "purpose_conveyed": -0.15}
REL = lambda p: p.resolve().relative_to(c.gg.REPO).as_posix()  # noqa: E731


def tool_files():
    return [c.vc.HERE / "grounding_def_v2.py", c.vc.HERE / "measure_v2.py", c.V3 / "v3_common.py", c.HERE / "v4_common.py",
            c.HERE / "final_v4.py", c.HERE / "v0_generator.py", c.HERE / "metrics_v4.py", c.HERE / "human_tool_v4.py",
            c.HERE / "HUMAN_RUBRIC.md", PREREG, c.V3 / "snapshots" / "generate_crm_message_v3r.py", c.V3 / "snapshots" / "hashes_v3r.json"]


# ── 표본 ─────────────────────────────────────────────────────────────────────

def _exclude() -> set[str]:
    """예약 규칙과 같은 제외(원본 · holdout · insample · 개발 N · 최종 F)."""
    import sample_holdout as sh
    ex = sh._original_products()  # insample 은 원본과 같은 상품이다
    ex |= {r.get("product_id") or r["product_snapshot"].get("product_id") for r in c.gg.load_inputs("holdout")}
    ex |= {r["product_id"] for r in c.load_jsonl(c.vc.RESULT / "main" / "inputs.jsonl")}
    ex |= {r["product_id"] for r in c.load_jsonl(c.V3_RESULT / "final" / "inputs.jsonl")}
    return ex


def _part(text: str) -> set[str]:
    t = text or ""
    out = set()
    if re.search(r"발|풋", t):
        out.add("foot")
    if re.search(r"손|핸드", t):
        out.add("hand")
    return out


def sample_pairs(n: int, seed: int, exclude: set[str], prefix: str, names: dict[str, str]) -> list[dict]:
    """sample_holdout.sample 복사본 + 부위 맞춤(핸드&풋케어: 페르소나 부위와 상품명 부위가 같은 짝만)."""
    import build_originals as bo
    from _common import load_personas, persona_info
    rng = random.Random(seed)
    personas = load_personas()
    tone_brands = bo._tone_brands()
    products = [p for p in bo._load_products() if p["brand"] in tone_brands]
    by_tag: dict[str, list[dict]] = defaultdict(list)
    for p in products:
        by_tag[bo._norm_tag(p["sub_tag"])].append(p)

    def body_ok(pid: str, p: dict) -> bool:
        tag = bo._norm_tag(p["sub_tag"])
        if "핸드" not in tag and "풋" not in tag:
            return True
        labels = re.findall(r"(?:^|\n)\s*([^:\n]*(?:손|발)[^:\n]*):", persona_info(personas[pid])["페르소나 정보"])
        pp = _part(" ".join(labels))  # 라벨(예: '발 상태', '손·발 상태')에서만 부위를 읽는다
        pr = _part(names.get(p["product_id"], ""))
        return not pp or not pr or bool(pp & pr)

    pairs_by_cat: dict[str, list[tuple[str, list[dict]]]] = defaultdict(list)
    for pid, persona in sorted(personas.items()):
        for cat in sorted({p["category"] for p in by_tag.get(bo._norm_tag(persona["product_tag"]), [])}):
            cands = sorted((p for p in by_tag[bo._norm_tag(persona["product_tag"])] if p["category"] == cat and body_ok(pid, p)),
                           key=lambda p: p["product_id"])
            if cands:
                pairs_by_cat[cat].append((pid, cands))
    categories = sorted(pairs_by_cat)
    persona_uses: Counter = Counter()
    used: set[str] = set(exclude)
    samples = []
    while len(samples) < n:
        avail = {cat: [(pid, cs) for pid, cs in ((pid, [p for p in cands if p["product_id"] not in used])
                                                  for pid, cands in pairs_by_cat[cat] if persona_uses[pid] < bo.MAX_PERSONA_USES) if cs]
                 for cat in categories}
        cats = [k for k in categories if avail[k]]
        if not cats:
            break
        cat = rng.choices(cats, weights=[bo.CATEGORY_WEIGHTS.get(k, 1) for k in cats])[0]
        fewest = min(persona_uses[pid] for pid, _ in avail[cat])
        pid, cands = rng.choice([(pid, cs) for pid, cs in avail[cat] if persona_uses[pid] == fewest])
        product = rng.choice(cands)
        persona_uses[pid] += 1
        used.add(product["product_id"])
        samples.append({"item_id": f"{prefix}{len(samples) + 1:03d}", "persona_id": pid, "product_id": product["product_id"],
                        "brand": product["brand"], "category": product["category"], "tag": product["tag"],
                        "sub_tag": product["sub_tag"], "purpose": bo.PURPOSES[len(samples) % len(bo.PURPOSES)],
                        "persona_use": persona_uses[pid]})
    return samples


def fetch_snapshots(ids: list[str], chunk: int = 4, tries: int = 3) -> dict[str, dict]:
    """DB API 에 한꺼번에 몰리지 않게 작은 묶음으로 조회하고, 빠진 상품은 다시 묻는다(병렬 수백 건이면 API 가 밀린다)."""
    import sample_holdout as sh
    got: dict[str, dict] = {}
    for k in range(0, len(ids), chunk):
        part = ids[k:k + chunk]
        for _ in range(tries):
            todo = [i for i in part if i not in got]
            if not todo:
                break
            got.update(asyncio.run(sh._fetch(todo)))
    return got


def _hand_foot_names() -> dict[str, str]:
    """부위 맞춤에 필요한 핸드&풋케어 예약 상품의 상품명만 조회한다."""
    import build_originals as bo
    import sample_holdout as sh
    ids = [p["product_id"] for p in bo._load_products()
           if p["product_id"] in c.reserved_ids() and ("핸드" in bo._norm_tag(p["sub_tag"]) or "풋" in bo._norm_tag(p["sub_tag"]))]
    snaps = fetch_snapshots(ids) if ids else {}
    return {pid: s.get("product_name", "") for pid, s in snaps.items()}


def capacity() -> None:
    names = _hand_foot_names()
    s = sample_pairs(N, SEED, _exclude(), "X", names)
    sub = {x["product_id"] for x in s} <= c.reserved_ids()
    print(f"확보 가능 {len(s)}건(목표 {N}, 최소 {MIN_N}) · 예약 목록 부분집합 {sub} · 핸드&풋 상품명 조회 {len(names)}개")


# ── 잠금 ─────────────────────────────────────────────────────────────────────

def final_version() -> dict:
    e = next((x for x in reversed(c.gg.amendments_entries()) if x["kind"] == KIND_VERSION), None)
    if e is None:
        raise SystemExit("AMENDMENTS 에 'V4 최종 버전 확정' 이 없습니다")
    return {"version": json.loads(e["content"])["version"], "hashes": e["new_hashes"], "entry": e["id"]}


def lock() -> None:
    if BASELINE.exists():
        raise SystemExit("이미 잠겼습니다. 수정은 AMENDMENTS('V4 최종 측정 도구 수정')로 한다")
    if "확보 가능 건수:" not in PREREG.read_text(encoding="utf-8"):
        raise SystemExit("PREREG 4절에 표본 용량(확보 가능 건수:)을 먼저 적는다")
    import measure_v2 as mv
    from app.config.settings import settings
    fv = final_version()
    hashes = {REL(p): c.gg.sha256(p) for p in tool_files()}
    base = {"locked_at": datetime.now(timezone.utc).isoformat(), "tools": hashes, "final_version": fv,
            "verifier": {"model": mv.VERIFIER_MODEL, "effort": EFFORT},
            "judge": {"model": settings.chatgpt_model_name, "runs": JUDGE_RUNS},
            "persona_fit": {"model": settings.persona_fit_model_name or settings.chatgpt_model_name,
                            "effort": settings.persona_fit_reasoning_effort},
            "v0": {"commit": c.v3.V0_COMMIT, "purpose_prompt_sha": c.v3.v0_sha()},
            "sample": {"seed": SEED, "n": N, "min_n": MIN_N, "neg_per_cond": NEG_PER_COND}}
    BASELINE.write_text(json.dumps(base, ensure_ascii=False, indent=2), encoding="utf-8")
    c.gg.append_amendment(KIND_LOCK, "V4 최종 시험(v0 대 V4) 사전 등록 · 측정 도구 잠금. PREREG_final_v4.md 참고",
                          {**hashes, REL(BASELINE): c.gg.sha256(BASELINE)})
    print(json.dumps({k: v for k, v in base.items() if k != "tools"}, ensure_ascii=False, indent=1))


def check_lock(strict: bool = True) -> list[str]:
    if not BASELINE.exists():
        raise SystemExit("baseline_final_v4.json 없음 — lock 을 먼저 한다")
    exp = dict(json.loads(BASELINE.read_text(encoding="utf-8"))["tools"])
    for e in c.gg.amendments_entries():
        if e["kind"] == KIND_FIX:
            exp.update({k: v for k, v in e.get("new_hashes", {}).items() if k in exp})
    now = {REL(p): c.gg.sha256(p) for p in tool_files()}
    bad = [k for k in exp if now.get(k) != exp[k]]
    if bad and strict:
        raise SystemExit(f"잠금과 다른 측정 도구 파일(기록 없는 변경): {bad}")
    return bad


def check_version() -> dict:
    from fit_check_v4 import FINAL_FILES
    fv = final_version()
    now = {REL(p): c.gg.sha256(p) for p in FINAL_FILES}
    bad = [k for k, v in fv["hashes"].items() if now.get(k) != v]
    if bad:
        raise SystemExit(f"'V4 최종 버전 확정'(AMENDMENTS {fv['entry']})과 다른 파일: {bad}")
    return fv


# ── 표본 · 생성 · 측정 ─────────────────────────────────────────────────────────

def sample() -> None:
    check_lock()
    import sample_holdout as sh
    from _common import load_personas, persona_info
    out = FINAL / "inputs.jsonl"
    if out.exists():
        raise SystemExit(f"{out} 이 이미 있습니다")
    names, failed = _hand_foot_names(), set()
    for _ in range(6):  # v3 최종과 같은 처리: 스냅숏 조회가 안 되는 상품은 빼고 같은 시드로 다시 뽑는다
        s = sample_pairs(N, SEED, _exclude() | failed, "R", names)
        snaps = fetch_snapshots([x["product_id"] for x in s])
        miss = {x["product_id"] for x in s if x["product_id"] not in snaps}
        if not miss:
            break
        failed |= miss
    else:
        raise SystemExit(f"스냅숏 조회 실패가 계속됩니다: {sorted(failed)[:10]}")
    if not {x["product_id"] for x in s} <= c.reserved_ids():
        raise SystemExit("예약 목록 밖 상품이 뽑혔습니다")
    if len(s) < MIN_N:
        raise SystemExit(f"{len(s)}건 < 최소 {MIN_N}건")
    personas = load_personas()
    rows = [{**x, "persona_info": persona_info(personas[x["persona_id"]]), "product_snapshot": snaps[x["product_id"]]} for x in s]
    c.write_jsonl(out, rows)
    c.gg.append_amendment(KIND_SAMPLE, f"n={len(rows)}(시드 {SEED}, 예약 상품 부분집합 확인, 부위 맞춤 적용, 스냅숏 조회 실패로 뺀 상품 "
                          f"{len(failed)}개)", {REL(out): c.gg.sha256(out)})
    print(f"표본 {len(rows)}건 → {out}")


class RecordingFitter:
    """실제 PersonaFitter 를 그대로 부르고 결과만 상품 ID 로 저장한다(평가 쪽 감싸개)."""

    def __init__(self, inner):
        self.inner, self.by = inner, {}

    async def fit(self, persona_info, product_info):
        r = await self.inner.fit(persona_info, product_info)
        self.by[product_info.get("product_id")] = r.to_dict()
        return r


async def _gen(cond: str) -> None:
    check_lock()
    from app.config.settings import settings
    from app.core.llm_factory import get_llm
    from app.agents.generate_message_agent.services import claim_check as cc
    items = c.load_jsonl(FINAL / "inputs.jsonl")
    rec = None
    if cond == "v0":
        from v0_generator import make_v0_generator
        gen, label = make_v0_generator()
    else:
        fv = check_version()
        from app.agents.generate_message_agent.prompts import persona_fit as pf
        from app.agents.generate_message_agent.services.generate_crm_message import CrmMessageGenerator
        rec = RecordingFitter(pf.PersonaFitter())
        gen, label = CrmMessageGenerator(persona_fitter=rec), f"V4(AMENDMENTS {fv['entry']})"
    llm = get_llm(settings.chatgpt_model_name, temperature=settings.llm_temperature_generator)
    out = FINAL / cond / "messages.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    done = {r["item_id"] for r in c.load_jsonl(out)} if out.exists() else set()
    lock_, sem = asyncio.Lock(), asyncio.Semaphore(8)

    async def one(it):
        async with sem:
            t0 = time.perf_counter()
            tasks = [{"product_id": it["product_id"], "purpose": it["purpose"], "product_info": it["product_snapshot"]}]
            tasks = await gen.get_brand_tone(tasks)
            tasks = await gen.get_crm_prompt(tasks, persona_info=it["persona_info"])
            g = await gen.generate_crm_message(tasks, llm)
            dt = round(time.perf_counter() - t0, 2)
        if not g:
            return
        raw = g[0]["message"]
        content = raw.content if hasattr(raw, "content") else str(raw)
        msg = cc.parse_message(raw)
        try:
            ok = isinstance(json.loads(content), dict)
        except Exception:  # noqa: BLE001
            ok = False
        row = {**it, "tag": cond, "title": msg["title"], "message": msg["message"], "json_ok": ok,
               "fit_status": tasks[0].get("fit_status"), "claim_check": g[0].get("claim_check"),
               "claim_hits": [{k: x[k] for k in ("cat", "sub", "text", "where")} for x in g[0].get("claim_hits", [])],
               "fit": rec.by.get(it["product_id"]) if rec else None,
               "generation": {"version": label, "model": settings.chatgpt_model_name, "latency_s": dt,
                              "generated_at": datetime.now(timezone.utc).isoformat()}}
        async with lock_:
            with open(out, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    todo = [it for it in items if it["item_id"] not in done]
    print(f"{cond} [{label}]: 생성 {len(todo)}건(이미 {len(done)}건)", flush=True)
    await asyncio.gather(*(one(it) for it in todo))
    rows = {r["item_id"]: r for r in c.load_jsonl(out)}
    c.write_jsonl(out, [rows[it["item_id"]] for it in items if it["item_id"] in rows])
    import measure as m1
    import run_d1
    det = run_d1.make_detector()
    fm = [m1.format_metrics(r, det) for r in rows.values()]
    st = [r.get("claim_check") for r in rows.values()]
    print(f"→ {out} {len(rows)}/{len(items)} · JSON {sum(r['json_ok'] for r in rows.values())} · CTA 마지막 "
          f"{sum(f['cta_last'] for f in fm)} · 점검 {dict(Counter(st))} · fit {dict(Counter(r.get('fit_status') for r in rows.values()))}")


async def _measure() -> None:
    check_lock()
    import measure as m1
    import measure_v2 as mv
    items = {r["item_id"] for r in c.load_jsonl(FINAL / "inputs.jsonl")}
    for cond in ("v0", "v4"):
        if {r["item_id"] for r in c.load_jsonl(FINAL / cond / "messages.jsonl")} != items:
            raise SystemExit(f"{cond} 메시지가 입력과 다릅니다 — 생성을 끝낸 뒤 측정한다")
    for cond in ("v0", "v4"):
        await mv.run(m1.load_messages(FINAL / cond / "messages.jsonl"), FINAL / cond, EFFORT, JUDGE_RUNS, False)


# ── 더미 시험(API 호출 없음) ─────────────────────────────────────────────────────

def dummy() -> None:
    import inspect
    from v0_generator import make_v0_generator, _load_snapshot_module
    from app.agents.generate_message_agent.prompts import persona_fit as pf
    fails = []
    gen, _ = make_v0_generator()
    msgs, _ = c.stored("v3r_F")
    for iid in ("F001", "F026", "F049"):
        m = msgs[iid]
        tasks = asyncio.run(gen.get_brand_tone([{"product_id": m["product_id"], "purpose": m["purpose"], "product_info": m["product_snapshot"]}]))
        tasks = asyncio.run(gen.get_crm_prompt(tasks, persona_info=m["persona_info"]))
        text = "\n".join(x.content for x in tasks[0]["prompt"])
        raw = str(m["persona_info"])
        if raw not in text:
            fails.append(f"{iid}: v0 프롬프트에 원본 persona_info 가 그대로 없음")
        view = pf.build_persona_view(m["persona_info"], m["purpose"]) or ""
        if "피부 고민" in raw and "피부 고민" not in text:
            fails.append(f"{iid}: v0 프롬프트가 거른 페르소나로 보임")
        if tasks[0].get("fit_status") != "disabled":
            fails.append(f"{iid}: v0 fit_status 가 disabled 가 아님")
        _ = view
    src = inspect.getsource(_load_snapshot_module().CrmMessageGenerator)
    if "claim_check" in src or "_generate_one" in src:
        fails.append("v0 생성기에 생성 뒤 점검이 들어 있음")
    try:
        check_version()
    except SystemExit as e:
        fails.append(str(e))
    print("더미 시험: " + ("전부 통과" if not fails else f"실패 {fails}"))
    if fails:
        sys.exit(1)


# ── 사람 확인 · 보고 ───────────────────────────────────────────────────────────

HUMAN = FINAL / "human"


def human_export() -> None:
    check_lock()
    from app.agents.generate_message_agent.prompts.product_fields import generation_product_info
    out = HUMAN / "human_check.csv"
    if out.exists():
        raise SystemExit(f"{out} 이 이미 있습니다")
    rng = random.Random(SEED)
    rows = []
    for cond in ("v0", "v4"):
        meas = {r["item_id"]: r for r in c.load_jsonl(FINAL / cond / "measure.jsonl")}
        msgs = {r["item_id"]: r for r in c.load_jsonl(FINAL / cond / "messages.jsonl")}
        by = defaultdict(list)
        for i, r in meas.items():
            by[r["verifier"]["class"]].append(i)
        pick = [(h, i) for h in ("양성", "재검토") for i in sorted(by[h])]
        pick += [("음성", i) for i in rng.sample(sorted(by["음성"]), min(NEG_PER_COND, len(by["음성"])))]
        rows += [(cond, h, i, msgs[i]) for h, i in pick]
    rng.shuffle(rows)
    key = {}
    HUMAN.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["행", "상품명", "제목", "본문", "상품정보", "판정", "메모"])
        for k, (cond, h, i, m) in enumerate(rows, 1):
            key[str(k)] = {"cond": cond, "stratum": h, "item_id": i}
            w.writerow([k, m["product_snapshot"].get("product_name", ""), m["title"], m["message"],
                        json.dumps(generation_product_info(m["product_snapshot"]), ensure_ascii=False, indent=1), "", ""])
    (HUMAN / "sample_map.json").write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"→ {out} {len(rows)}행 {dict(Counter((v['cond'], v['stratum']) for v in key.values()))}")


def _human_results():
    p = HUMAN / "human_check.csv"
    if not p.exists():
        return None
    key = json.loads((HUMAN / "sample_map.json").read_text(encoding="utf-8"))
    with open(p, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if any(not r["판정"] for r in rows):
        return None
    res = {"v0": defaultdict(list), "final": defaultdict(list)}
    amb = Counter()
    for r in rows:
        k = key[r["행"]]
        cond = "final" if k["cond"] == "v4" else "v0"
        res[cond][k["stratum"]].append(1 if r["판정"] == "O" else 0)
        amb[k["cond"]] += r["판정"] == "애매"
    return res, amb


def report() -> None:
    import report as r1
    import grounding_def_v2 as gd
    import metrics_v4 as mt
    sys.path.insert(0, str(c.V3))
    import final_main as fm
    bad = check_lock(strict=False)
    M = {cnd: {r["item_id"]: r for r in c.load_jsonl(FINAL / cnd / "measure.jsonl")} for cnd in ("v0", "v4")}
    msgs = {cnd: {r["item_id"]: r for r in c.load_jsonl(FINAL / cnd / "messages.jsonl")} for cnd in ("v0", "v4")}
    ids = sorted(i for i in M["v0"] if M["v0"][i].get("verifier") and M["v4"].get(i, {}).get("verifier"))
    n = len(ids)
    fv = final_version()
    hr = _human_results()
    L = ["# V4 최종 시험 보고서 — 초기(v0) 대 V4", "",
         f"- 작성: {datetime.now(timezone.utc).isoformat()} · 짝 {n}건 · 최종 버전: V4 (AMENDMENTS {fv['entry']}, 채택 확정 뒤 한 번 측정)",
         f"- 측정 도구 잠금 대조: {'마지막 기록과 같음' if not bad else '기록 없는 변경 ' + str(bad) + ' → 이 보고서는 탐색적'}",
         "- 표본: 처음 보는 예약 상품(AMENDMENTS 21), 같은 입력으로 v0 · V4 를 같은 시점에 측정", ""]
    summary = {}
    for key, cls, title in (("headline", "class", "헤드라인 — 근거 없는 상품 주장(9개 유형)이 1개 이상인 메시지"),
                            ("primary", "class_primary", "주 지표 — 특성어긋남 · 근거없는고민연결")):
        pos = {cnd: [i for i in ids if M[cnd][i]["verifier"][cls] in ("양성", "재검토")] for cnd in M}
        b = sum(1 for i in ids if i in pos["v0"] and i not in pos["v4"])
        cc_ = sum(1 for i in ids if i not in pos["v0"] and i in pos["v4"])
        t = r1.paired_test(b, cc_)
        ci = {cnd: fm.wilson(len(pos[cnd]), n) for cnd in M}
        L += [f"## {title}", "", "| | v0 | V4 |", "|---|---|---|",
              "| LLM 양성(재검토 포함) | " + " | ".join(f"{len(pos[x])}/{n} = {len(pos[x]) / n:.1%} (95% CI {ci[x][0]:.1%}~{ci[x][1]:.1%})" for x in M) + " |",
              "| LLM 층(양성 · 재검토 · 음성) | " + " | ".join(" · ".join(str(sum(1 for i in ids if M[x][i]['verifier'][cls] == h)) for h in STRATA) for x in M) + " |"]
        if hr and key == "headline":
            res, amb = hr
            sizes = {"v0": {h: sum(1 for i in ids if M["v0"][i]["verifier"]["class"] == h) for h in STRATA},
                     "final": {h: sum(1 for i in ids if M["v4"][i]["verifier"]["class"] == h) for h in STRATA}}
            w = fm.weighted_ci(sizes, res)
            L += [f"| 사람 확인 반영(기준표) | {w['point']['v0']:.1%} (95% CI {w['ci']['v0'][0]:.1%}~{w['ci']['v0'][1]:.1%}) | "
                  f"{w['point']['final']:.1%} (95% CI {w['ci']['final'][0]:.1%}~{w['ci']['final'][1]:.1%}) |",
                  "| 사람 확인 O/확인 (층별) | " + " | ".join(", ".join(f"{h} {sum(res[x][h])}/{len(res[x][h])}" for h in STRATA if res[x].get(h)) for x in ("v0", "final")) + " |",
                  f"\n- 사람 확인 반영 차이(V4 − v0): {w['diff']:+.1%} (95% CI {w['diff_ci'][0]:+.1%}~{w['diff_ci'][1]:+.1%}) · 애매 v0 {amb['v0']} · V4 {amb['v4']}"]
            summary["human"] = w
        L += [f"- 짝 비교 v0 → V4: 개선 {b} · 악화 {cc_}, {t['method']} p = {t['p']:.4f}", ""]
        summary[key] = {x: len(pos[x]) / n for x in M}
        summary[key + "_ci"] = ci
    L += ["## 유형별 (LLM 클레임이 있는 메시지 수)", "", "| 유형 | v0 | V4 |", "|---|---|---|"]
    for ty in gd.CLAIM_TYPES:
        L.append(f"| {ty} | " + " | ".join(str(sum(1 for i in ids if M[x][i]["verifier"]["type_counts"].get(ty))) for x in M) + " |")
    L += ["", "## 품질 비열등 (v0 대비 짝 부트스트랩 단측 95% 하한, 보고용)", "", "| 지표 | v0 | V4 | 차이 | 하한 | 여유 | 판정 |", "|---|---|---|---|---|---|---|"]
    jb = {i: r1.item_judge(M["v0"][i]) for i in ids}
    ja = {i: r1.item_judge(M["v4"][i]) for i in ids}
    jid = [i for i in ids if jb[i] and ja[i]]
    for k, margin in NI.items():
        if k == "purpose_conveyed":
            vb = {i: float(M["v0"][i]["verifier"]["purpose_conveyed"] == "O") for i in ids}
            va = {i: float(M["v4"][i]["verifier"]["purpose_conveyed"] == "O") for i in ids}
            use = ids
        else:
            vb, va, use = {i: jb[i][k] for i in jid}, {i: ja[i][k] for i in jid}, jid
        d, lo = r1.paired_boot_lower([va[i] - vb[i] for i in use])
        L.append(f"| {k} | {sum(vb[i] for i in use) / len(use):.3f} | {sum(va[i] for i in use) / len(use):.3f} | {d:+.3f} | {lo:+.3f} | {margin} | {'통과' if lo >= margin else '미달'} |")
    fits = {i: msgs["v4"][i].get("fit") or {} for i in ids}
    mat = [i for i in jid if mt.matched(fits[i])]
    unm = [i for i in jid if not mt.matched(fits[i])]
    if mat:
        d, lo = r1.paired_boot_lower([ja[i]["personalization"] - jb[i]["personalization"] for i in mat])
        L += ["", f"- 2차 사전 등록: 맞는 짝 {len(mat)}건 개인화 v0 {sum(jb[i]['personalization'] for i in mat) / len(mat):.2f} → V4 "
              f"{sum(ja[i]['personalization'] for i in mat) / len(mat):.2f} (차이 {d:+.3f}, 하한 {lo:+.3f}, 여유 −0.3 → {'통과' if lo >= -0.3 else '미달'})"]
    if unm:
        L.append(f"- 보고용: 안 맞는 짝 {len(unm)}건 개인화 v0 {sum(jb[i]['personalization'] for i in unm) / len(unm):.2f} → V4 "
                 f"{sum(ja[i]['personalization'] for i in unm) / len(unm):.2f}")
    gp = {x: sum(mt.grounded_personalization(msgs[x][i], M[x][i]["verifier"], fits[i]) for i in ids) for x in M}
    st = Counter(msgs["v4"][i].get("claim_check") for i in ids)
    L += [f"- 2차 사전 등록: 근거 있는 개인화 v0 {gp['v0']}/{n} → V4 {gp['v4']}/{n}",
          f"- V4 생성 정보: 점검 {dict(st)} · fit {dict(Counter(msgs['v4'][i].get('fit_status') for i in ids))} · "
          f"연결 확인 {dict(Counter((fits[i] or {}).get('link_check', '') for i in ids))}", "",
          "## 측정 범위와 한계", "",
          "- 생성 단계 한정. 운영의 품질 게이트 뒤 재작성은 측정하지 않았다.",
          "- 결과 본 뒤 바꾼 결정 3건: 연결 확인 지연 기준 7.0 → 8.0초(AMENDMENTS 29), 점검 A 사람 확인 추가(30), 채택 규칙 근거 우선(33).",
          "- 단계 2 근소 미달(재생성 10.7%, 형식 위반 1건)은 버전 파일을 고치지 않고 공개했다.",
          "- 평가 짝은 추천 결과가 아니라 같은 상품 종류 안 무작위라 운영보다 덜 맞을 수 있다.", ""]
    h = summary["headline"]
    L += ["## 보고 문구", "",
          f"- LLM 기준 초기 {h['v0']:.1%} → V4 {h['v4']:.1%} (각 {n}건, 처음 보는 상품, 같은 시점, 95% CI "
          f"{summary['headline_ci']['v0'][0]:.1%}~{summary['headline_ci']['v0'][1]:.1%} / {summary['headline_ci']['v4'][0]:.1%}~{summary['headline_ci']['v4'][1]:.1%})"]
    if "human" in summary:
        w = summary["human"]
        L.append(f"- 사람 확인 반영(기준표) 초기 {w['point']['v0']:.1%} → V4 {w['point']['final']:.1%}")
    out = FINAL / "report_final_v4.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("capacity", "dummy", "lock", "sample", "gen", "measure", "human_export", "report"))
    ap.add_argument("--cond", choices=("v0", "v4"))
    a = ap.parse_args()
    if a.cmd == "gen":
        if not a.cond:
            raise SystemExit("--cond v0 | v4")
        asyncio.run(_gen(a.cond))
    elif a.cmd == "measure":
        asyncio.run(_measure())
    else:
        {"capacity": capacity, "dummy": dummy, "lock": lock, "sample": sample, "human_export": human_export, "report": report}[a.cmd]()


if __name__ == "__main__":
    main()
