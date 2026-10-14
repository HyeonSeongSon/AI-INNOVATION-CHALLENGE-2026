"""
최종 측정 사람 확인 — 표본(눈가림) · 확인 도구 실행 · 결과 읽기 · 도구 시험.

    python human_final.py sample     # v0 · 최종 측정 뒤: 양성 · 재검토 전부 + 음성 조건별 12건 → result/final/human/
    python human_final.py serve      # 확인 화면(127.0.0.1:8770, check_tool_final)
    python human_final.py status     # 남은 빈칸
    python human_final.py test       # 단계 0 도구 시험: v1 저장 메시지 3건(2라운드 표본)으로 화면 자료 · 저장 · 완료 규칙 · 집계를 확인하고 지운다

층은 검증기 9개 유형 기준 class(양성 · 재검토 · 음성). 배분 · 계산은 PREREG_final.md 6절.
"""

import json
import random
import shutil
import sys
import tempfile
from pathlib import Path

import v3_common as v3
from gg_common import load_jsonl, write_jsonl

import check_tool_final as ct  # noqa: E402
import grounding_def_v2 as gd  # noqa: E402

FINAL = v3.FINAL
HUMAN = FINAL / "human"
SEED = 20261012
NEG_PER_COND = 12
CONDS = ("v0", "final")
STRATA = ("양성", "재검토", "음성")


def build(chosen: list[dict], out_dir: Path, seed: int) -> None:
    """chosen: [{tag, item_id, stratum, msg}] → 섞어서 코드를 붙이고 check_items.jsonl · sample_map.json 을 쓴다."""
    rng = random.Random(seed)
    rng.shuffle(chosen)
    out_dir.mkdir(parents=True, exist_ok=True)
    mapping, rows = {}, []
    for n, c in enumerate(chosen, 1):
        code = f"P{n:03d}"
        mapping[code] = {"tag": c["tag"], "item_id": c["item_id"], "stratum": c["stratum"]}
        m = c["msg"]
        rows.append({"code": code, "purpose": m["purpose"], "brand": m["brand"], "persona_info": m["persona_info"],
                     "product_snapshot": m["product_snapshot"], "title": m["title"], "message": m["message"]})
    (out_dir / "sample_map.json").write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    write_jsonl(out_dir / "check_items.jsonl", rows)


def sample() -> None:
    if (HUMAN / "sample_map.json").exists():
        raise SystemExit("이미 표본이 있습니다")
    rng = random.Random(SEED)
    chosen, counts = [], {}
    for cond in CONDS:
        meas = {r["item_id"]: r for r in load_jsonl(FINAL / cond / "measure.jsonl")}
        msgs = {r["item_id"]: r for r in load_jsonl(FINAL / cond / "messages.jsonl")}
        if any(r["verifier"] is None for r in meas.values()):
            raise SystemExit(f"{cond}: 검증기 결과가 빠진 항목이 있습니다 — 측정을 끝낸 뒤 뽑는다")
        for stratum in STRATA:
            pool = sorted(i for i, r in meas.items() if r["verifier"]["class"] == stratum)
            pick = pool if stratum != "음성" or len(pool) <= NEG_PER_COND else rng.sample(pool, NEG_PER_COND)
            counts[(cond, stratum)] = (len(pick), len(pool))
            chosen += [{"tag": cond, "item_id": i, "stratum": stratum, "msg": msgs[i]} for i in pick]
    build(chosen, HUMAN, SEED)
    print(f"사람 확인 {len(chosen)}건 → {HUMAN}")
    for (c, h), (k, n) in counts.items():
        print(f"  {c} {h}: {k}/{n}")


def results(human_dir: Path = HUMAN) -> dict[str, dict[str, dict[str, list[int]]]]:
    """{'headline'|'primary': {cond: {stratum: [0/1 …]}}}. 완료되지 않은 행(빈칸 · 근거 빠진 O)은 넣지 않는다."""
    mapping = json.loads((human_dir / "sample_map.json").read_text(encoding="utf-8"))
    _, rows = ct.rk.read_csv(human_dir / "human_check.csv")
    by = {r["code"]: {f: r.get(f, "") for f in ct.FIELDS[1:]} for r in rows}
    out = {k: {c: {h: [] for h in STRATA} for c in {m["tag"] for m in mapping.values()}} for k in ("headline", "primary")}
    for code, m in mapping.items():
        v = by.get(code)
        if not v or not ct.row_done(v):
            continue
        o = v["unsupported_claim(O/X)"] == "O"
        types = set(v["types"].split(",")) if o else set()
        out["headline"][m["tag"]][m["stratum"]].append(1 if o else 0)
        out["primary"][m["tag"]][m["stratum"]].append(1 if types & set(gd.PRIMARY_TYPES) else 0)
    return out


def test() -> None:
    """도구 시험 — v1 저장 메시지 3건. 결과 파일은 임시 폴더에 쓰고 끝나면 지운다."""
    src = load_jsonl(v3.vc.RESULT / "main" / "v1" / "messages.jsonl")[:3]
    tmp = Path(tempfile.mkdtemp(prefix="human_final_test_"))
    try:
        build([{"tag": t, "item_id": m["item_id"], "stratum": s, "msg": m}
               for m, t, s in zip(src, ("v0", "final", "v0"), ("양성", "음성", "재검토"))], tmp, SEED)
        ct.set_paths(tmp)
        items = load_jsonl(ct.ITEMS)
        ct.ensure_csv([it["code"] for it in items])
        data = ct.payload()
        assert len(data["items"]) == 3 and data["types"] == list(gd.CLAIM_TYPES), "화면 자료 이상"
        assert data["definition"] == gd.GROUNDING_DEF and len(data["boundary"]) == len(gd.BOUNDARY_CASES), "정의가 9개 유형 전체가 아님"
        store = ct.Store()
        c1, c2, c3 = (it["code"] for it in items)
        assert store.save(c1, "types", "없는유형") is not None, "없는 유형을 거르지 않음"
        for col, val in (("unsupported_claim(O/X)", "O"), ("purpose_conveyed(O/X)", "O")):
            assert store.save(c1, col, val) is None
        assert not ct.row_done(store.values()[c1]), "근거 없는 O 가 완료로 셈"
        assert store.save(c1, "sentences", "2") is None and store.save(c1, "types", "근거없는고민연결,수치") is None
        assert ct.row_done(store.values()[c1]) and store.values()[c1]["types"] == "수치,근거없는고민연결", "유형 정렬 · 완료 규칙"
        for code in (c2, c3):
            assert store.save(code, "unsupported_claim(O/X)", "X") is None and store.save(code, "purpose_conveyed(O/X)", "O") is None
        res = results(tmp)
        tags = json.loads((tmp / "sample_map.json").read_text(encoding="utf-8"))
        want_h = sum(1 for c, m in tags.items() if c == c1)
        got_h = sum(sum(v) for cond in res["headline"].values() for v in cond.values())
        got_p = sum(sum(v) for cond in res["primary"].values() for v in cond.values())
        assert got_h == want_h == 1 and got_p == 1, (got_h, got_p)
        assert sum(len(v) for cond in res["headline"].values() for v in cond.values()) == 3
        print("도구 시험 통과: 화면 자료(9개 유형 정의 · 경계 사례 전체) · 유형 검사 · O 완료 규칙 · 집계(헤드라인 · 주 지표)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        ct.set_paths(HUMAN)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "serve":
        ct.serve("--no-open" not in sys.argv)
    elif cmd == "status":
        ct.ensure_csv([it["code"] for it in load_jsonl(ct.ITEMS)])
        ct.status()
    else:
        {"sample": sample, "test": test}[cmd]()
