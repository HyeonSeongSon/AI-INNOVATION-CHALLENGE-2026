"""
보류 표본 (2단계) — 수정에 쓰지 않은 상품으로 채택 판단용 입력을 만든다.

    python sample_holdout.py validate              # 운영 경로 스냅숏이 원본 70건과 같은지 확인(필수, 먼저)
    python sample_holdout.py capacity              # 첫 보류 70건이 채워지는지 · 확장 가능 건수 확인(LLM 호출 없음)
    python sample_holdout.py build                 # 보류 표본 70건 → result/holdout/inputs.jsonl
    python sample_holdout.py build --ext --n N     # 9단계 확장(시드 20261002, 기준 1이 "확장"일 때만)

- 표본 추출은 build_originals.sample 의 반복문을 복사하고 두 가지만 바꾼다.
  1. used_products 를 원본 70건(확장이면 + 첫 보류 표본)의 상품으로 시작한다.
  2. 목적은 무작위 대신 7개를 순환시켜 각 10건으로 맞춘다.
- 스냅숏은 생성기와 같은 운영 경로(CrmMessageGenerator.get_product_info → DB API)로 받는다.
  validate 가 원본 70건의 저장 스냅숏과 키 · 값 · 타입이 모두 같다고 확인한 뒤에만 build 한다.
"""

import argparse
import asyncio
import json
import random
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

import gg_common as gg
from gg_common import load_jsonl, write_jsonl

import build_originals as bo  # noqa: E402 — gg_common 이 경로를 잡은 뒤
from _common import load_personas, persona_info  # noqa: E402

from app.agents.generate_message_agent.services.generate_crm_message import CrmMessageGenerator  # noqa: E402

SEED = 20261001
EXT_SEED = 20261002
N = 70
VALIDATION = gg.RESULT / "snapshot_validation.json"


def _originals() -> list[dict]:
    return load_jsonl(gg.INSAMPLE_SOURCE)


async def _fetch(product_ids: list[str]) -> dict[str, dict]:
    gen = CrmMessageGenerator()
    tasks = await gen.get_product_info([{"product_id": pid} for pid in product_ids])
    return {t["product_id"]: t["product_info"] for t in tasks}


def _diff(a, b, path="") -> list[str]:
    """키 · 값 · 타입까지 같은지 (JSON 직렬화 결과가 같아도 int/float 차이는 잡는다)."""
    if type(a) is not type(b):
        return [f"{path}: 타입 {type(a).__name__} ≠ {type(b).__name__}"]
    if isinstance(a, dict):
        out = [f"{path}.{k}: 키 없음(저장본에만)" for k in a.keys() - b.keys()]
        out += [f"{path}.{k}: 키 추가(새 조회에만)" for k in b.keys() - a.keys()]
        for k in a.keys() & b.keys():
            out += _diff(a[k], b[k], f"{path}.{k}")
        return out
    if isinstance(a, list):
        if len(a) != len(b):
            return [f"{path}: 길이 {len(a)} ≠ {len(b)}"]
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in _diff(x, y, f"{path}[{i}]")]
    return [] if a == b else [f"{path}: 값 {str(a)[:60]!r} ≠ {str(b)[:60]!r}"]


def validate() -> None:
    origs = _originals()
    fetched = asyncio.run(_fetch([o["product_id"] for o in origs]))
    report, bad = {}, 0
    for o in origs:
        new = fetched.get(o["product_id"])
        diffs = ["조회 실패"] if new is None else _diff(o["product_snapshot"], json.loads(json.dumps(new, ensure_ascii=False)))
        if diffs:
            bad += 1
            report[o["original_id"]] = diffs[:20]
    result = {"checked_at": datetime.now(timezone.utc).isoformat(), "n": len(origs), "mismatch": bad,
              "passed": bad == 0, "details": report}
    VALIDATION.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"스냅숏 대조: {len(origs)}건 중 불일치 {bad}건 → {VALIDATION}")
    for oid, d in list(report.items())[:10]:
        print(f"  {oid}: {d[:3]}")
    if bad:
        raise SystemExit("불일치가 있어 보류 표본을 만들 수 없습니다")


def sample(n: int, seed: int, exclude: set[str], id_prefix: str, strict: bool = True) -> list[dict]:
    """build_originals.sample 복사본 — used_products 시작값과 목적 순환만 다르다."""
    rng = random.Random(seed)
    personas = load_personas()
    tone_brands = bo._tone_brands()
    products = [p for p in bo._load_products() if p["brand"] in tone_brands]

    by_tag: dict[str, list[dict]] = defaultdict(list)
    for p in products:
        by_tag[bo._norm_tag(p["sub_tag"])].append(p)

    pairs_by_cat: dict[str, list[tuple[str, list[dict]]]] = defaultdict(list)
    for pid, persona in sorted(personas.items()):
        for cat in sorted({p["category"] for p in by_tag.get(bo._norm_tag(persona["product_tag"]), [])}):
            cands = sorted(
                (p for p in by_tag[bo._norm_tag(persona["product_tag"])] if p["category"] == cat),
                key=lambda p: p["product_id"],
            )
            pairs_by_cat[cat].append((pid, cands))

    categories = sorted(pairs_by_cat)
    persona_uses: Counter = Counter()
    used_products: set[str] = set(exclude)  # 변경 1
    samples = []
    while len(samples) < n:
        avail = {
            cat: [(pid, cs) for pid, cs in (
                (pid, [p for p in cands if p["product_id"] not in used_products])
                for pid, cands in pairs_by_cat[cat] if persona_uses[pid] < bo.MAX_PERSONA_USES
            ) if cs]
            for cat in categories
        }
        cats = [c for c in categories if avail[c]]
        if not cats:
            if strict:
                raise RuntimeError(f"표본 {n}건을 채우지 못했습니다 (확보 {len(samples)}건)")
            break
        cat = rng.choices(cats, weights=[bo.CATEGORY_WEIGHTS.get(c, 1) for c in cats])[0]
        fewest = min(persona_uses[pid] for pid, _ in avail[cat])
        pid, cands = rng.choice([(pid, cs) for pid, cs in avail[cat] if persona_uses[pid] == fewest])
        product = rng.choice(cands)
        persona_uses[pid] += 1
        used_products.add(product["product_id"])
        samples.append({
            "item_id": f"{id_prefix}{len(samples) + 1:03d}",
            "persona_id": pid,
            "product_id": product["product_id"],
            "brand": product["brand"],
            "category": product["category"],
            "tag": product["tag"],
            "sub_tag": product["sub_tag"],
            "purpose": bo.PURPOSES[len(samples) % len(bo.PURPOSES)],  # 변경 2: 7개 순환
            "persona_use": persona_uses[pid],
        })
    return samples


def _original_products() -> set[str]:
    return {o["product_id"] for o in _originals()}


def capacity() -> None:
    orig = _original_products()
    full = sample(10_000, SEED, orig, "H", strict=False)
    print(f"원본 상품 제외 후 시드 {SEED}로 채울 수 있는 최대 건수: {len(full)}")
    first = sample(N, SEED, orig, "H")
    ext_cap = len(sample(10_000, EXT_SEED, orig | {s['product_id'] for s in first}, "E", strict=False))
    print(f"첫 보류 {N}건: 채움 가능. 원본 · 첫 보류 상품을 뺀 확장 가능 건수(시드 {EXT_SEED}): {ext_cap}")
    print(f"  → 9단계 확장 크기: {min(ext_cap, N)}건" + (" (40건 미만이라 첫 보류 상품 재사용 규칙 적용)" if ext_cap < 40 else ""))


def build(ext: bool, n: int) -> None:
    if not (VALIDATION.exists() and json.loads(VALIDATION.read_text(encoding="utf-8"))["passed"]):
        raise SystemExit("snapshot_validation.json 이 통과 상태가 아닙니다 — validate 를 먼저 돌린다")
    set_name = "holdout_ext" if ext else "holdout"
    out = gg.set_dir(set_name) / "inputs.jsonl"
    if out.exists():
        raise SystemExit(f"{out} 이 이미 있습니다(덮어쓰지 않음)")
    exclude = _original_products()
    if ext:
        exclude |= {r["product_id"] for r in gg.load_inputs("holdout")}
    seed = EXT_SEED if ext else SEED
    samples = sample(n, seed, exclude, "E" if ext else "H")
    fetched = asyncio.run(_fetch([s["product_id"] for s in samples]))
    missing = [s["item_id"] for s in samples if s["product_id"] not in fetched]
    if missing:
        raise SystemExit(f"스냅숏 조회 실패: {missing}")
    personas = load_personas()
    rows = [{**s, "persona_info": persona_info(personas[s["persona_id"]]),
             "product_snapshot": json.loads(json.dumps(fetched[s["product_id"]], ensure_ascii=False))}
            for s in samples]
    write_jsonl(out, rows)
    uses = Counter(r["persona_id"] for r in rows)
    meta = {"built_at": datetime.now(timezone.utc).isoformat(), "seed": seed, "n": len(rows),
            "excluded_products": len(exclude), "purposes": dict(Counter(r["purpose"] for r in rows)),
            "categories": dict(Counter(r["category"] for r in rows).most_common()),
            "personas": len(uses), "personas_used_twice": sum(v == 2 for v in uses.values()),
            "personas_overlap_with_originals": len(set(uses) & {o["persona_id"] for o in _originals()})}
    (out.parent / "inputs_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    print(f"→ {out}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("validate", "capacity", "build"))
    ap.add_argument("--ext", action="store_true")
    ap.add_argument("--n", type=int, default=N)
    a = ap.parse_args()
    {"validate": validate, "capacity": capacity}.get(a.cmd, lambda: build(a.ext, a.n))()
