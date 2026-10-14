"""
원본(O) 표본 추출 → 실제 생성 서비스로 메시지 생성 → 검수용 CSV.

표본: 상품 × 페르소나 × 발송 목적. 카테고리 가중 추출(시드 고정).
    - 페르소나는 평가용 60명. 페르소나의 product_tag 와 같은 소분류(sub_tag)의 상품과 짝짓는다.
    - 페르소나는 다른 상품으로 최대 2회까지 쓴다. 1회 제한이면 짝지을 수 있는 페르소나가 59명이라
      70건을 뽑을 수 없다(플랜 3차 검토). 분석의 부트스트랩은 페르소나 단위로 묶는다.
    - 카테고리를 돌아가며 똑같이 뽑으면 비화장품(뷰티툴 · 이너뷰티 · 생활도구)이 25/70 들어간다.
      화장품 후보가 많은 카테고리에 가중치를 준다. 화장품 여부 자체는 검수 CSV 에서 상품 단위로 정한다.
    - 상품은 brand_tone.yaml 에 키가 정확히 있는 브랜드에서만 고른다
      (오타 키 글램팜·아모레퍼시픽, 프로필 없는 3개 브랜드는 기본 톤으로 대체되므로 제외).
생성: CrmMessageGenerator 를 generate_message_node 와 같은 순서·설정으로 호출한다.
검수 CSV 두 개 (게이트 판정 결과는 넣지 않는다 — 검수는 게이트와 무관하게):
    - review_originals.csv: 문장마다 명사가 겹치는 DB 필드를 자동으로 붙이고 판정기 가시성
      (_JUDGE_PRODUCT_FIELDS)을 표시한다.
    - review_originals_summary.csv: 원본마다 한 줄. 자동 힌트(기능성 서술 · 내부 정보 노출 ·
      판정기에 안 보이는 필드 인용)와 사용자가 채울 열(review_ok · is_cosmetic ·
      functional_certified · meta_leak · natural_defect).

사용법:
    python build_originals.py --run pilot --n 5
    python build_originals.py --run main --n 70 --sample-only   # 생성 없이 표본 구성만 확인
"""

import argparse
import asyncio
import csv
import hashlib
import json
import random
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from _common import bootstrap, load_jsonl, load_personas, persona_info, run_dir, write_jsonl

bootstrap()

import psycopg2  # noqa: E402
from kiwipiepy import Kiwi  # noqa: E402

from app.config.settings import settings  # noqa: E402
from app.core.data_loader import get_brand_tones  # noqa: E402
from app.core.llm_factory import get_llm  # noqa: E402
from app.agents.generate_message_agent.nodes import _parse_message  # noqa: E402
from app.agents.generate_message_agent.prompts.quality_check_prompt import _JUDGE_PRODUCT_FIELDS  # noqa: E402
from app.agents.generate_message_agent.services.generate_crm_message import CrmMessageGenerator  # noqa: E402

DEFAULT_SEED = 20260929
PURPOSES = [
    "브랜드/제품 첫소개",
    "신제품 홍보",
    "베스트셀러 제품 소개",
    "프로모션/이벤트 소개",
    "성분/효능 강조 소개",
    "피부타입/고민 강조 소개",
    "라이프스타일/연령대 강조 소개",
]
# 검수 자동 대응에서 뺄 필드 — 식별자·URL·검색용 파생 필드
_SKIP_FIELDS = {"product_id", "vectordb_id", "product_created_at", "combined", "search_tags", "search_phrases"}
_NUMERIC_FIELDS = ("sale_price", "original_price", "discount_rate", "rating", "review_count")
_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
MAX_PERSONA_USES = 2
# 화장품 후보가 많은 카테고리에 가중치(플랜 "원본 표본"). 로컬 DB 기준 짝지을 수 있는 페르소나 수는
# 스킨케어 15 · 헤어 12 · 색조 8 · 향수/바디 7 · 뷰티툴 10 · 이너뷰티 5 · 생활도구 2.
CATEGORY_WEIGHTS = {"스킨케어": 3, "색조": 3, "헤어": 3, "향수/바디": 3, "뷰티툴": 1, "이너뷰티": 1, "생활도구": 1}
# 기능성 인증 서술 힌트 — 구조화된 인증 필드가 없어 자유 서술에서 찾는다(24개 상품 해당, 사용자 확인 필요)
_FUNCTIONAL_RE = re.compile(r"식약처[^\"]{0,30}기능성|기능성[^\"]{0,15}(?:보고|심사|인증)|기능성\s?화장품")
# 내부 메타 정보 노출 힌트 — 시범 O001 "외근형(땀·답답함 걱정) 페르소나도"
_META_LEAK_RE = re.compile(r"페르소나|[가-힣]+형\s?\(|타[겟깃]\s?고객|고객군")

kiwi = Kiwi()


def _norm_tag(tag: str | None) -> str:
    return (tag or "").replace(" ", "")


def _nouns(text: str) -> set[str]:
    return {t.form for t in kiwi.tokenize(text) if t.tag in ("NNG", "NNP", "SL") and len(t.form) >= 2}


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in _NUM_RE.findall(text)}


def _tone_brands() -> set[str]:
    return set(get_brand_tones().get("brand_ton_prompt", {}).keys())


def _load_products() -> list[dict[str, Any]]:
    conn = psycopg2.connect(
        host=settings.postgres_host, port=settings.postgres_port, dbname=settings.postgres_db,
        user=settings.postgres_user, password=settings.postgres_password,
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT product_id, brand, category, tag, sub_tag FROM products")
            return [dict(zip(("product_id", "brand", "category", "tag", "sub_tag"), r)) for r in cur.fetchall()]
    finally:
        conn.close()


def sample(n: int, seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    personas = load_personas()
    tone_brands = _tone_brands()
    products = [p for p in _load_products() if p["brand"] in tone_brands]

    # 페르소나 product_tag(크림·샴푸 …)는 v3 상품의 소분류(sub_tag)에 해당한다
    by_tag: dict[str, list[dict]] = defaultdict(list)
    for p in products:
        by_tag[_norm_tag(p["sub_tag"])].append(p)

    # (category → [(persona_id, [products])]) — 페르소나 태그와 같은 태그의 상품만
    pairs_by_cat: dict[str, list[tuple[str, list[dict]]]] = defaultdict(list)
    for pid, persona in sorted(personas.items()):
        for cat in sorted({p["category"] for p in by_tag.get(_norm_tag(persona["product_tag"]), [])}):
            cands = sorted(
                (p for p in by_tag[_norm_tag(persona["product_tag"])] if p["category"] == cat),
                key=lambda p: p["product_id"],
            )
            pairs_by_cat[cat].append((pid, cands))

    categories = sorted(pairs_by_cat)
    persona_uses: Counter = Counter()
    used_products: set[str] = set()
    samples = []
    while len(samples) < n:
        avail = {
            cat: [(pid, cs) for pid, cs in (
                (pid, [p for p in cands if p["product_id"] not in used_products])
                for pid, cands in pairs_by_cat[cat] if persona_uses[pid] < MAX_PERSONA_USES
            ) if cs]
            for cat in categories
        }
        cats = [c for c in categories if avail[c]]
        if not cats:
            raise RuntimeError(f"표본 {n}건을 채우지 못했습니다 (확보 {len(samples)}건)")
        cat = rng.choices(cats, weights=[CATEGORY_WEIGHTS.get(c, 1) for c in cats])[0]
        # 덜 쓴 페르소나를 먼저 쓴다 — 재사용은 1회 사용 페르소나가 바닥난 뒤에만 생긴다
        fewest = min(persona_uses[pid] for pid, _ in avail[cat])
        pid, cands = rng.choice([(pid, cs) for pid, cs in avail[cat] if persona_uses[pid] == fewest])
        product = rng.choice(cands)
        persona_uses[pid] += 1
        used_products.add(product["product_id"])
        samples.append({
            "original_id": f"O{len(samples) + 1:03d}",
            "persona_id": pid,
            "product_id": product["product_id"],
            "brand": product["brand"],
            "category": product["category"],
            "tag": product["tag"],
            "sub_tag": product["sub_tag"],
            "purpose": rng.choice(PURPOSES),
            "persona_use": persona_uses[pid],
        })
    return samples


async def generate(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """generate_message_node 와 같은 순서: 상품 조회 → 브랜드 톤 → 목적별 프롬프트 → 생성."""
    generator = CrmMessageGenerator()
    llm = get_llm(settings.chatgpt_model_name, temperature=settings.llm_temperature_generator)
    personas = load_personas()

    async def one(s: dict[str, Any]) -> dict[str, Any]:
        pinfo = persona_info(personas[s["persona_id"]])
        tasks = [{"product_id": s["product_id"], "purpose": s["purpose"]}]
        tasks = await generator.get_product_info(tasks)
        tasks = await generator.get_brand_tone(tasks)
        tasks = await generator.get_crm_prompt(tasks, persona_info=pinfo)
        prompt_text = "\n".join(m.content for m in tasks[0]["prompt"])
        t0 = time.perf_counter()
        generated = await generator.generate_crm_message(tasks, llm)
        latency = round(time.perf_counter() - t0, 2)
        if not generated:
            return {**s, "error": "generation_failed", "latency_s": latency}
        msg = _parse_message(generated[0]["message"])
        return {
            **s,
            "persona_info": pinfo,
            "title": msg.get("title", ""),
            "message": msg.get("message", ""),
            "product_snapshot": tasks[0]["product_info"],
            "generation": {
                "model": settings.chatgpt_model_name,
                "temperature_setting": settings.llm_temperature_generator,
                "prompt_sha256": hashlib.sha256(prompt_text.encode("utf-8")).hexdigest(),
                "latency_s": latency,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
            "review_status": "unreviewed",
        }

    return await asyncio.gather(*(one(s) for s in samples))


def review_rows(original: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    """문장별 DB 필드 자동 대응. 반환: (CSV 행, 판정기에 안 보이는 필드만 인용한 문장 존재 여부)."""
    product = original["product_snapshot"]
    field_nouns = {
        k: _nouns(json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v)
        for k, v in product.items() if k not in _SKIP_FIELDS and v not in (None, "", [], {})
    }
    field_numbers = {
        k: _numbers(json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v)
        for k, v in product.items() if k not in _SKIP_FIELDS and v not in (None, "", [], {})
    }
    rows = []
    invisible_citation = False
    text = f"{original['title']}\n{original['message']}"
    # 검수용 분리는 소수점("평점 4.5")을 자르지 않는다 — 게이트 2단계 분리와는 다르다
    for idx, sentence in enumerate(s for s in re.split(r"[!?。！？\n]+|\.(?!\d)|(?<!\d)\.", text) if s.strip()):
        sentence = sentence.strip()
        s_nouns = _nouns(sentence)
        visible, invisible = [], []
        for field, nouns in field_nouns.items():
            hit = s_nouns & nouns
            if hit:
                (visible if field in _JUDGE_PRODUCT_FIELDS else invisible).append(f"{field}:{'/'.join(sorted(hit))}")
        nums = _numbers(sentence)
        num_visible = sorted(n for n in nums if any(n in field_numbers[f] for f in field_numbers if f in _JUDGE_PRODUCT_FIELDS))
        num_invisible_only = sorted(
            n for n in nums
            if n not in num_visible and any(n in field_numbers[f] for f in field_numbers if f not in _JUDGE_PRODUCT_FIELDS)
        )
        flags = []
        if not visible and not invisible and not num_visible and not num_invisible_only:
            flags.append("근거 필드 없음(브랜드 프로필 유래·일반 서술 여부 확인)")
        if invisible and not visible:
            flags.append("판정기에 안 보이는 필드만 대응")
        if num_invisible_only:
            flags.append("판정기에 안 보이는 수치")
        if (invisible and not visible) or num_invisible_only:
            invisible_citation = True
        if nums - set(num_visible) - set(num_invisible_only):
            flags.append("DB에 없는 수치")
        rows.append({
            "original_id": original["original_id"],
            "sent_idx": idx,
            "sentence": sentence,
            "visible_fields": "; ".join(visible),
            "invisible_fields": "; ".join(invisible),
            "numbers": ", ".join(sorted(nums)),
            "auto_flags": " | ".join(flags),
            "review_ok(O/X)": "",
            "review_note": "",
        })
    return rows, invisible_citation


def persona_needs(original: dict[str, Any]) -> str:
    """페르소나 원문에서 상품 적합 판단에 쓰는 줄(고민 · 니즈 · 구매 기준)만 뽑는다."""
    text = original.get("persona_info", {}).get("페르소나 정보", "")
    keep = [ln.strip() for ln in text.split("\n") if ln.strip().startswith(("고민", "니즈", "구매 기준"))]
    return " / ".join(keep)


def summary_row(original: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """원본 단위 검수 행 — 자동 힌트 + 사용자가 채울 열.

    persona_product_fit(O/X) 가 X 인 원본은 C · 모든 변형 · 자연 결함에서 뺀다(make_variants · make_d1_set).
    표본을 추천기 대신 소분류로 짝지어 생긴 부산물이라(시범 2회차 O005: 가습을 원하는 페르소나에 제습기),
    운영 입력이 아니고 생성기 결함도 아니다. 뺀 수만 보고한다.
    """
    product = original["product_snapshot"]
    functional = _FUNCTIONAL_RE.search(json.dumps(product, ensure_ascii=False))
    leak = sorted(set(_META_LEAK_RE.findall(f"{original['title']} {original['message']}")))
    return {
        "original_id": original["original_id"],
        "category": original["category"], "tag": original["tag"], "sub_tag": original["sub_tag"],
        "product_name": product.get("product_name", ""), "brand": original["brand"],
        "persona_id": original["persona_id"], "persona_needs": persona_needs(original),
        "purpose": original["purpose"],
        "title": original["title"], "message_len": len(original["message"]),
        "hint_functional": functional.group(0) if functional else "",
        "hint_meta_leak": ", ".join(leak),
        "hint_invisible_field_citation": "O" if original.get("invisible_field_citation") else "",
        "hint_unsupported_sentences": sum("근거 필드 없음" in r["auto_flags"] for r in rows),
        "persona_product_fit(O/X)": "",
        "review_ok(O/X)": "",
        "is_cosmetic(O/X)": "",
        "functional_certified(O/X)": "",
        "meta_leak(O/X)": "",
        "brand_profile_unverified(O/X)": "",
        "unsupported_fact(O/X)": "",
        "natural_defect(라벨)": "",
        "review_note": "",
    }


def write_review(out_dir, originals: list[dict[str, Any]]) -> None:
    """검수 CSV 두 개 작성 + 원본마다 invisible_field_citation 표시."""
    all_rows, summaries = [], []
    for o in originals:
        rows, invisible = review_rows(o)
        o["invisible_field_citation"] = invisible
        all_rows.extend(rows)
        summaries.append(summary_row(o, rows))
    for name, table in (("review_originals.csv", all_rows), ("review_originals_summary.csv", summaries)):
        with open(out_dir / name, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(table[0].keys()))
            writer.writeheader()
            writer.writerows(table)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", default="pilot")
    parser.add_argument("--n", type=int, default=5)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--review-only", action="store_true", help="생성 없이 originals.jsonl 로 검수 CSV 만 다시 만든다")
    parser.add_argument("--sample-only", action="store_true", help="생성 없이 표본 구성만 출력한다(LLM 호출 없음)")
    args = parser.parse_args()

    out_dir = run_dir(args.run)
    if args.review_only:
        originals = load_jsonl(out_dir / "originals.jsonl")
        write_review(out_dir, originals)
        write_jsonl(out_dir / "originals.jsonl", originals)
        print(f"→ {out_dir / 'review_originals.csv'}")
        return

    samples = sample(args.n, args.seed)
    print(f"표본 {len(samples)}건:")
    for s in samples:
        print(f"  {s['original_id']} {s['category']}/{s['tag']}/{s['sub_tag']} {s['brand']} {s['product_id']} × {s['persona_id']}(#{s['persona_use']}) × {s['purpose']}")
    uses = Counter(s["persona_id"] for s in samples)
    print(f"카테고리: {dict(Counter(s['category'] for s in samples).most_common())}")
    print(f"페르소나 {len(uses)}명, 2회 사용 {sum(v == 2 for v in uses.values())}명")
    if args.sample_only:
        return

    originals = asyncio.run(generate(samples))
    failed = [o for o in originals if o.get("error")]
    originals = [o for o in originals if not o.get("error")]
    print(f"생성 성공 {len(originals)} / 실패 {len(failed)}")

    write_review(out_dir, originals)
    write_jsonl(out_dir / "originals.jsonl", originals)
    (out_dir / "originals_meta.json").write_text(json.dumps({
        "seed": args.seed, "n_requested": args.n, "n_generated": len(originals),
        "generation_failed": [f["original_id"] for f in failed],
        "latency_s": [o["generation"]["latency_s"] for o in originals],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    for o in originals:
        print(f"\n[{o['original_id']}] ({len(o['message'])}자) {o['title']}\n{o['message']}")
    print(f"\n→ {out_dir / 'originals.jsonl'}\n→ {out_dir / 'review_originals.csv'}")


if __name__ == "__main__":
    main()
