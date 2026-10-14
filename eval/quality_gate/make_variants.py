"""
원본에서 결함 변형과 대조군을 만들고 자동 유효성 검사를 한다. LLM 호출 없음.
플랜: wiki/dev-tasks/message-quality-gate-defect-injection-plan-20260929.md (8차 검토 반영판)

| 변형 | 만드는 법 |
|---|---|
| C      | 원본 그대로 (오탐 분모) |
| C_repl | D1 과 같은 slot 문장을 DB 필드(texture)로 만든 중립 사실 문장으로 치환 — 치환 행위 효과 분리용 |
| D1     | (보조) d1_set.jsonl 의 in_message 문자열을 **그대로** slot 문장과 치환. 주 지표는 run_d1.py |
| D2     | 성분 고유명 제자리 치환(판정기 가시 필드 23개 어디에도 없는 성분, 부분 문자열 겹침 제외) 또는
|        | sale_price · discount_rate 숫자를 제목 + 본문 전부에서 같은 값으로 치환. 기능 대체 없음 |
| D3     | 메시지는 그대로, 페르소나 원문에서 메시지가 언급한 속성(여러 줄)만 모순되는 값으로 바꿔 판정.
|        | 사용자가 검수한 d3_table.csv 의 reviewed_usable=O 행만 쓴다(draft_d3.py 가 초안) |
| D4     | 본문 · 제목의 CTA 문장 전부 삭제(제목은 CTA 구절만). 남은 CTA 가 있으면 무효 |
| N      | 자연 결함 — 검수에서 실제 결함으로 확인된 원본(review_ok=X, natural_defect 라벨) |

페르소나-상품 부적합(검수 persona_product_fit=X) 원본은 C · 모든 변형 · N 에서 뺀다. 표본을 추천기 대신
소분류로 짝지어 생긴 부산물이라 운영 입력도, 생성기 결함도 아니다(시범 2회차 O005). 뺀 수만 보고한다.

시범에서 확인된 라벨 오류(wiki/errors/quality-gate-pilot-variant-label-errors-20260929.md)를 막는 규칙:
마지막 CTA 한 문장만 지우지 않는다 · 다른 상품군 페르소나로 바꾸지 않는다 · 기능을 성분 대신 넣지 않는다 ·
"DB에 없음"을 필드 하나로 판단하지 않는다 · 제목의 숫자를 빼먹지 않는다.

입력 (result/<run>/): originals.jsonl, review_originals_summary.csv, d1_set.jsonl(선택), d3_table.csv(선택)
출력: cases.jsonl

사용법:
    python make_variants.py --run main
    python make_variants.py --run pilot --no-review     # 검수 전 스모크 전용
"""

import argparse
import csv
import difflib
import random
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from _common import (
    bootstrap, fix_josa, gate_sentences, is_cta, is_decimal_fragment, judge_visible_text, load_jsonl, load_personas, nospace,
    run_dir, sentence_spans, short_name, topic_josa, write_jsonl,
)

bootstrap()

import psycopg2  # noqa: E402

from app.config.settings import settings  # noqa: E402
from make_d1_set import pick_slot  # noqa: E402

DEFAULT_SEED = 20260929


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value if v]
    return [str(value)] if value else []


def _load_catalog() -> list[dict[str, Any]]:
    conn = psycopg2.connect(
        host=settings.postgres_host, port=settings.postgres_port, dbname=settings.postgres_db,
        user=settings.postgres_user, password=settings.postgres_password,
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT product_id, category, tag, sub_tag, product_details FROM products")
            return [dict(zip(("product_id", "category", "tag", "sub_tag", "details"), r)) for r in cur.fetchall()]
    finally:
        conn.close()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [{k.strip(): (v or "").strip() for k, v in row.items()} for row in csv.DictReader(f)]


# ── 치환 도구 ──────────────────────────────────────────────────────────────────

def replace_sentence(message: str, old: str, new: str) -> str | None:
    """본문에서 문장 old(게이트 분리 기준, 끝 구두점 없음)를 new 로 바꾼다. old 뒤 끝 구두점까지 교체."""
    pos = message.find(old)
    if pos < 0 or message.find(old, pos + 1) >= 0:
        return None
    end = pos + len(old)
    while end < len(message) and message[end] in ".!?。！？":
        end += 1
    new = new.strip()
    if not new.endswith((".", "!", "?")):
        new += "."
    return message[:pos] + new + message[end:]


def neutral_sentence(original: dict[str, Any]) -> str | None:
    """C_repl 용 중립 사실 문장 — 판정기에 보이는 texture 필드로만 만든다."""
    product = original["product_snapshot"]
    textures = _as_list(product.get("texture"))
    if not textures:
        return None
    texture = textures[0].strip().rstrip(".")
    short = short_name(product.get("product_name", ""), f"{original['title']} {original['message']}")
    subject = f"{short}{topic_josa(short)} " if short else "이 제품은 "
    tail = f"{texture}입니다." if texture.endswith(("제형", "타입", "텍스처")) else f"{texture} 제형입니다."
    return subject + tail


def _sub_all(text: str, old: str, new: str, numeric: bool = False) -> str:
    pattern = re.escape(old)
    if numeric:
        pattern = rf"(?<![\d,.]){pattern}"
    return re.sub(pattern, new, text)


def ingredient_name(item: str) -> str:
    """성분 필드 값 "이름 (설명)"에서 이름만 — 예: "베타-글루칸 (보습)" → "베타-글루칸". 상표 기호는 뺀다."""
    return re.sub(r"\s*\([^)]*\)|[™®]", "", item).strip()


# 앞 단어를 떼고 남은 꼬리가 이 낱말뿐이면 성분 언급으로 보지 않는다 — 시범 O004 "탈모 기능성 성분"이
# "성분"까지 줄어 문장 속 일반어 "성분"에 걸렸다
_GENERIC_INGREDIENT_WORDS = {"성분", "기능성성분", "추출물", "오일", "젤", "크림", "엑스", "워터", "파우더", "복합체"}
# 성분 필드에 섞여 있는 성분 아닌 값 — 시범 O001 후보 "전통한지 제조공법 응용"
_NON_INGREDIENT_RE = re.compile(r"공법|기술|방식|특허|처방|공정|설계|구조|시스템|소재|함유|배합|성분")


def find_ingredient_mention(name: str, text: str) -> re.Match | None:
    """메시지 속 성분 언급 — 띄어쓰기 차이("함유젤" ↔ "함유 젤")와 앞 단어 생략
    ("이니스프리 그린티 세라마이드" ↔ "그린티 세라마이드")을 허용한다. 긴 형태부터 찾는다."""
    words = name.split()
    for i in range(len(words)):
        variant = nospace(" ".join(words[i:]))
        if len(variant) < 3 or variant in _GENERIC_INGREDIENT_WORDS:
            break
        pattern = r"\s?".join(re.escape(ch) for ch in variant)
        m = re.search(pattern, text)
        if m:
            return m
    return None


def swap_word(text: str, old: str, new: str) -> str:
    """old 를 전부 new 로 바꾸고, 바뀐 자리마다 뒤 조사(은/는 · 이/가 · 을/를 · 과/와)를 받침에 맞춘다."""
    for m in reversed(list(re.finditer(re.escape(old), text))):
        text = text[:m.start()] + new + text[m.end():]
        text = fix_josa(text, m.start(), m.start() + len(new))
    return text


def d2_variant(original: dict[str, Any], catalog: list[dict[str, Any]], rng: random.Random) -> dict[str, Any] | None:
    """D2 절차: 성분 고유명 치환 우선, 없으면 숫자 치환. 둘 다 없으면 None(기기류 등)."""
    product = original["product_snapshot"]
    title, message = original["title"], original["message"]
    text = f"{title} {message}"
    visible = judge_visible_text(product) + nospace(text)
    own = [ingredient_name(i) for i in _as_list(product.get("ingredient"))]
    own = [i for i in own if len(nospace(i)) >= 2]
    mentions = [(m.start(), m.group(0)) for m in (find_ingredient_mention(i, text) for i in own) if m]
    if mentions:
        target = min(mentions)[1]
        own_ns = [nospace(i) for i in own]
        for level in ("sub_tag", "tag", "category"):
            pool = sorted({
                name
                for p in catalog
                if p["product_id"] != original["product_id"] and p[level] == original.get(level)
                for name in (ingredient_name(x) for x in _as_list((p["details"] or {}).get("ingredient")))
                if 2 <= len(nospace(name)) <= 15
                and not _NON_INGREDIENT_RE.search(name)
                and nospace(name) not in visible
                and not any(nospace(name) in o or o in nospace(name) for o in own_ns)
            })
            # 치환 뒤에도 길이 규칙(본문 20~350자 · 제목 5~40자)을 지키는 후보만 — 시범 O002 가 354자로 넘었다
            fits = [n for n in pool
                    if len(swap_word(message, target, n)) <= settings.message_body_max_length
                    and len(swap_word(title, target, n)) <= settings.message_title_max_length]
            if fits:
                new = rng.choice(fits)
                return {"level": "ingredient", "field": "ingredient", "before": target, "after": new,
                        "title": swap_word(title, target, new), "message": swap_word(message, target, new),
                        "pool_level": level,
                        "label": f"{target} → {new} (판정기 가시 필드 23개에 없는 성분)"}
    price, rate = product.get("sale_price"), product.get("discount_rate")
    text = f"{title} {message}"
    if price:
        for form, fmt in ((f"{int(price):,}원", "{:,}원"), (f"{int(price)}원", "{}원")):
            if re.search(rf"(?<![\d,.]){re.escape(form)}", text):
                new = fmt.format(int(round(int(price) * 1.3, -2)))
                return {"level": "price", "field": "sale_price", "before": form, "after": new,
                        "title": _sub_all(title, form, new, True), "message": _sub_all(message, form, new, True),
                        "label": f"{form} → {new} (DB sale_price 와 모순, 제목·본문 전부 치환)"}
    if rate:
        form = f"{int(rate)}%"
        if re.search(rf"(?<![\d,.]){re.escape(form)}", text):
            new = f"{int(rate) + 20 if int(rate) <= 70 else int(rate) - 20}%"
            return {"level": "price", "field": "discount_rate", "before": form, "after": new,
                    "title": _sub_all(title, form, new, True), "message": _sub_all(message, form, new, True),
                    "label": f"{form} → {new} (DB discount_rate 와 모순, 제목·본문 전부 치환)"}
    return None


def d4_variant(original: dict[str, Any]) -> dict[str, Any] | None:
    """D4 절차: 본문 CTA 문장 전부 + 제목 CTA 구절 삭제. CTA 가 없으면 None."""
    body = original["message"]
    # 게이트 문장 단위로 판별하되, 원문에서 CTA 구간만 잘라 낸다. 남은 조각을 다시 이어 붙이면
    # 소수점이 깨진다(시범 2회차 O001 "평점 4.5" → "평점 4. 5").
    spans = [(s, e) for s, e in sentence_spans(body) if not is_decimal_fragment(body[s:e].strip().rstrip(".!?"), body)]
    cut = [(s, e) for s, e in spans if is_cta(body[s:e])]
    removed = [body[s:e].strip() for s, e in cut]
    new_body = body
    for s, e in reversed(cut):
        new_body = new_body[:s] + new_body[e:]
    new_body = re.sub(r"[ \t]{2,}", " ", new_body).strip()
    title = original["title"]
    parts = re.split(r"\s*[—|·]\s*", title)
    title_removed = [p for p in parts if is_cta(p)]
    new_title = " — ".join(p for p in parts if not is_cta(p)).strip() if title_removed else title
    if not removed and not title_removed:
        return None
    return {"title": new_title, "message": new_body, "deleted": removed + title_removed,
            "remaining_cta": [s for s in gate_sentences(new_title, new_body) if is_cta(s)]}


def sentence_diff(original: dict[str, Any], title: str, message: str) -> list[dict[str, Any]]:
    a = gate_sentences(original["title"], original["message"])
    b = gate_sentences(title, message)
    return [
        {"op": tag, "before": a[i1:i2], "after": b[j1:j2]}
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
        if tag != "equal"
    ]


def length_flags(title: str, message: str) -> list[str]:
    flags = []
    if len(message) > settings.message_body_max_length:
        flags.append(f"body_over_{settings.message_body_max_length}({len(message)})")
    if len(message) < settings.message_body_min_length:
        flags.append(f"body_under_{settings.message_body_min_length}({len(message)})")
    if not 5 <= len(title) <= settings.message_title_max_length:
        flags.append(f"title_len({len(title)})")
    return flags


def make_case(original: dict[str, Any], suffix: str, defect: str, level: str, *, title: str | None = None,
              message: str | None = None, judge_persona: dict[str, Any] | None = None,
              changed_sentences: list[str] | None = None, **extra: Any) -> dict[str, Any]:
    title = original["title"] if title is None else title
    message = original["message"] if message is None else message
    return {
        "case_id": f"{original['original_id']}-{suffix}",
        "original_id": original["original_id"], "persona_id": original["persona_id"],
        "defect": defect, "level": level,
        "product_id": original["product_id"], "purpose": original["purpose"],
        "title": title, "message": message,
        "original_title": original["title"], "original_message": original["message"],
        "persona_info": judge_persona or original["persona_info"],
        "changed_sentences": changed_sentences or [],
        "diff": sentence_diff(original, title, message),
        "length_flags": length_flags(title, message),
        **extra,
    }


def validate(case: dict[str, Any]) -> list[str]:
    ops = [d["op"] for d in case["diff"]]
    d = case["defect"]
    problems = []
    if d in ("C", "N", "D3") and ops:
        problems.append(f"메시지가 바뀜 {ops}")
    if d in ("C_repl", "D1"):
        if ops != ["replace"] or len(case["diff"][0]["before"]) != 1 or len(case["diff"][0]["after"]) != 1:
            problems.append(f"한 문장 치환이 아님 {[(x['op'], len(x['before']), len(x['after'])) for x in case['diff']]}")
    if d == "D2":
        if not ops or set(ops) != {"replace"}:
            problems.append(f"제자리 치환이 아님 {ops}")
        for x in case["diff"]:
            expect = [swap_word(b, case["d2_before"], case["d2_after"]) if case["level"] == "ingredient"
                      else _sub_all(b, case["d2_before"], case["d2_after"], True) for b in x["before"]]
            if expect != x["after"]:
                problems.append("치환 외의 변경이 섞임")
                break
    if d == "D4":
        if case.get("remaining_cta"):
            problems.append(f"CTA 가 남음 {case['remaining_cta']}")
        if set(ops) - {"delete", "replace"}:
            problems.append(f"삭제 외 변경 {ops}")
    if d == "D3" and not case.get("persona_changed_lines"):
        problems.append("페르소나가 바뀌지 않음")
    return problems


def d3_case(original: dict[str, Any], row: dict[str, str], persona: dict[str, Any]) -> dict[str, Any] | None:
    """검수한 D3 표 한 행 → 페르소나 원문의 해당 줄만 바꾼 판정 입력."""
    lines = persona["information"].split("\n")
    nums = [int(x) for x in re.findall(r"\d+", row["persona_line_numbers"])]
    new_lines = [x for x in row["new_lines"].split(" || ")]
    if not nums or len(nums) != len(new_lines) or any(n < 1 or n > len(lines) for n in nums):
        return None
    changed = []
    for n, new in zip(nums, new_lines):
        if lines[n - 1].strip() != new.strip():
            changed.append({"line": n, "before": lines[n - 1], "after": new})
            lines[n - 1] = new
    judge = {"persona_id": f"{persona['persona_id']}-D3", "페르소나 정보": "\n".join(lines)}
    return make_case(
        original, "D3", "D3", "attribute_swap", judge_persona=judge,
        label_source=f"persona:{persona['persona_id']} 속성 '{row['attribute']}' 치환 (검수 O)",
        attribute=row["attribute"], message_evidence=row["message_evidence"],
        conflict_basis=row["conflict_basis"], persona_changed_lines=changed,
        evidence_in_message=row["message_evidence"] in f"{original['title']} {original['message']}",
    )


def build(out_dir: Path, seed: int, no_review: bool) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rng = random.Random(seed)
    originals = load_jsonl(out_dir / "originals.jsonl")
    personas = load_personas()
    catalog = _load_catalog()

    review = {}
    if not no_review:
        review = {r["original_id"]: r for r in _read_csv(out_dir / "review_originals_summary.csv")}
        for col in ("persona_product_fit(O/X)", "review_ok(O/X)"):
            # 페르소나-상품 부적합(X) 원본은 전부 빠지므로 review_ok 가 비어도 된다
            blank = [oid for oid, r in review.items() if r.get(col, "").upper() not in ("O", "X")
                     and (col == "persona_product_fit(O/X)" or r.get("persona_product_fit(O/X)", "").upper() != "X")]
            if blank:
                raise SystemExit(f"{col}가 비어 있습니다: {blank[:10]} … (검수 후 다시 실행)")
    d1_items = defaultdict(list)
    if (out_dir / "d1_set.jsonl").exists():
        for it in load_jsonl(out_dir / "d1_set.jsonl"):
            if it["role"] == "in_message":
                d1_items[it["original_id"]].append(it)
    d3_rows = {}
    if (out_dir / "d3_table.csv").exists():
        d3_rows = {r["original_id"]: r for r in _read_csv(out_dir / "d3_table.csv")
                   if r.get("reviewed_usable(O/X)", "").upper() == "O"}

    cases, skipped = [], defaultdict(list)
    for o in originals:
        oid = o["original_id"]
        r = review.get(oid, {})
        if not no_review and r["persona_product_fit(O/X)"].upper() == "X":
            skipped["페르소나-상품 부적합(표본 부산물, 전부 제외)"].append(oid)
            continue
        if not no_review and r["review_ok(O/X)"].upper() == "X":
            label = r.get("natural_defect(라벨)", "")
            if label and label != "미검증":
                cases.append(make_case(o, "N", "N", "natural", label_source=f"검수 자연 결함: {label}"))
            else:
                skipped["원본 검수 탈락(자연 결함 라벨 없음 · 미검증만)"].append(oid)
            continue

        extra_o = {"functional_certified": r.get("functional_certified(O/X)", "").upper() == "O",
                   "unsupported_fact": r.get("unsupported_fact(O/X)", "").upper() == "O",
                   "invisible_field_citation": bool(o.get("invisible_field_citation"))}
        cases.append(make_case(o, "C", "C", "original", label_source="원본(검수 O)" if r else "원본(검수 전)", **extra_o))

        # slot: 원본 속 D1 이 있으면 같은 자리, 없으면 같은 규칙으로 고른다
        items = d1_items.get(oid, [])
        slot_sentence = items[0]["slot_sentence"] if items else None
        if slot_sentence is None:
            idx = pick_slot(o, personas[o["persona_id"]]["information"])
            slot_sentence = gate_sentences("", o["message"])[idx] if idx is not None else None

        neutral = neutral_sentence(o)
        if slot_sentence and neutral:
            new_msg = replace_sentence(o["message"], slot_sentence, neutral)
            if new_msg:
                cases.append(make_case(o, "Crepl", "C_repl", "neutral_replace", message=new_msg,
                                       changed_sentences=[neutral], replaced_sentence=slot_sentence,
                                       label_source="중립 사실 문장(texture 필드)", **extra_o))
        else:
            skipped["C_repl 없음(slot 또는 texture 없음)"].append(oid)

        for it in items:
            new_msg = replace_sentence(o["message"], it["slot_sentence"], it["sentence"])
            if not new_msg:
                skipped["D1 slot 문장을 찾지 못함"].append(oid)
                continue
            cases.append(make_case(
                o, f"D1-{it['phrase_id']}", "D1", it["stratum"], message=new_msg,
                changed_sentences=[it["sentence"]], injected_sentence=it["sentence"],
                d1_item_id=it["item_id"], d1_category=it["category"], template_type=it["template_type"],
                replaced_sentence=it["slot_sentence"], label_source=f"d1_set:{it['item_id']} ({it['source_ref']})",
            ))

        v2 = d2_variant(o, catalog, rng)
        if v2:
            changed = [s for s in gate_sentences(v2["title"], v2["message"])
                       if s not in gate_sentences(o["title"], o["message"])]
            cases.append(make_case(
                o, "D2", "D2", v2["level"], title=v2["title"], message=v2["message"], changed_sentences=changed,
                d2_before=v2["before"], d2_after=v2["after"],
                label_source=f"product_db:{o['product_id']}:{v2['field']} {v2['label']}",
            ))
        else:
            skipped["D2 없음(성분 언급 · 가격 언급 둘 다 없음)"].append(oid)

        if oid in d3_rows:
            c3 = d3_case(o, d3_rows[oid], personas[o["persona_id"]])
            if c3:
                cases.append(c3)
            else:
                skipped["D3 표 행 형식 오류"].append(oid)

        v4 = d4_variant(o)
        if v4:
            cases.append(make_case(
                o, "D4", "D4", "cta_delete_all", title=v4["title"], message=v4["message"],
                deleted_sentences=v4["deleted"], remaining_cta=v4["remaining_cta"], label_source="CTA 전부 삭제",
            ))
        else:
            skipped["D4 없음(CTA 없음)"].append(oid)

    for case in cases:
        case["invalid_reasons"] = validate(case)
        if case["defect"] == "D3" and not case.get("evidence_in_message"):
            case["invalid_reasons"].append("message_evidence 가 메시지에 없음")
        case["valid"] = not case["invalid_reasons"]
    return cases, dict(skipped)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", default="main")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--no-review", action="store_true", help="검수 전 스모크 전용: 모든 원본을 검수 O 로 본다")
    args = parser.parse_args()

    out_dir = run_dir(args.run)
    cases, skipped = build(out_dir, args.seed, args.no_review)
    write_jsonl(out_dir / "cases.jsonl", cases)

    by = defaultdict(lambda: [0, 0])
    for c in cases:
        by[(c["defect"], c["level"])][0 if c["valid"] else 1] += 1
    print("변형 (유효 / 무효):")
    for (defect, level), (ok, bad) in sorted(by.items()):
        print(f"  {defect:6} {level:16} {ok} / {bad}")
    for reason, oids in skipped.items():
        print(f"  건너뜀 — {reason}: {len(oids)}건 {oids[:8]}")
    for c in cases:
        if c["invalid_reasons"] or c["length_flags"]:
            print(f"  ! {c['case_id']}: invalid={c['invalid_reasons']} length={c['length_flags']}")
    print(f"\n→ {out_dir / 'cases.jsonl'} ({len(cases)}건)")


if __name__ == "__main__":
    main()
