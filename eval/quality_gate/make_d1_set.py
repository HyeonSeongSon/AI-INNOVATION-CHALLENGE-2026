"""
D1 문구 집합을 만든다 — 사전 등록한 문장 만들기 규칙 + 생성 원본에서 뽑은 틀 모음. LLM 호출 없음.

플랜 "사전 등록 1 · 문장 틀 · 문장 만들기 규칙 · 문구 모집단":
    - D1 주 지표의 단위는 서로 다른 문구다(1·2단계는 결정적이고 문장 단위로 판정).
    - 문구 모집단은 d1_phrases.csv 한 파일이다. 출처 · 기간 · 포함 규칙을 실행 전에 고정하고,
      조건에 맞는 문구를 전부 넣는다(include=O). 뺀 문구는 exclude_reason 을 남긴다.
    - 문장 만들기 규칙 (서술어는 data/build_d1_phrases.py 의 PREDICATES · HEDGE 한 곳에서 정한다):
        원래 문장(kind=sentence)  → 그대로 (끝에 마침표만 붙임)
        비헷지 층                 → 문구 형태별 고정 서술어 하나 (override 조건이 성립하면 무효)
            noun_phrase "{표현} 효과가 있습니다." · condition "{표현}에 효과가 있습니다." ·
            clause "{표현}합니다." · attribute "{표현} 제품입니다." · copula "{표현}입니다."
        헷지 층(stratum=hedge)    → "{표현}에 도움을 줍니다."  (hedge_basis 가 있는 유형만)
    - 틀 모음: 생성 원본의 주장 문장(CTA · 질문 제외)에서 앞부분을 떼어 만든다.
        상품명 주어 "{짧은 이름}은/는 " · "이 제품은 " · 성분 주어 "{성분} 성분이 " · 앞 절 "{절}, " · 주어 없음 ""
      문구마다 틀 하나를 시드로 뽑아 채운다(실제 분포를 따르는 혼합). 맨 문구는 상한값으로 함께 잰다.
    - 기능성 효능 유형(functional_cosmetic_unauthorized)은 D1 에서 뺀다(DB 에 인증 필드 없음).
    - 헷지 층과 RQ2 표적 시험에는 "헷지를 붙여도 위반"이라는 외부 근거(hedge_basis)가 있어야 한다.

원본 속 D1(보조): 검수에서 화장품으로 확인된 원본마다 문구 하나를, 그 원본 자신의 틀 모음에서 뽑은
틀로 채워 in_message 항목으로 만든다. make_variants.py 는 이 문자열을 그대로 원본의 slot 문장과 바꾼다
(단독 판정과 원본 속 판정이 같은 문자열이어야 멈춤 규칙이 의미를 가진다).

입력 (result/<run>/):
    originals.jsonl, review_originals_summary.csv(is_cosmetic · persona_product_fit · review_ok), d1_phrases.csv
    d1_phrases.csv(기본 data/d1_phrases.csv — 모집단은 실행과 무관하게 하나) 열:
        phrase_id, text, kind(sentence|noun_phrase|condition|clause|attribute|copula), stratum(explicit|subtle|hedge),
        category(금지어 사전 6종 | none), source(보도자료 분류), source_ref, hedge_basis, include(O/X), exclude_reason,
        review_ok(O/X)(사용자 전수 검수 — 비어 있으면 멈춤, X 는 제외) · 그 밖의 참고 열
출력: template_pool.json, d1_set.jsonl, d1_set_meta.json

사용법:
    python make_d1_set.py --run main
    python make_d1_set.py --run pilot --phrases result/smoke/d1_phrases_smoke.csv --cosmetic-by-category  # 스모크 전용
"""

import argparse
import csv
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from _common import (
    bootstrap, gate_sentences, is_cta, is_decimal_fragment, load_jsonl, load_personas, run_dir, short_name,
    topic_josa, write_jsonl,
)

bootstrap()

sys.path.insert(0, str(Path(__file__).resolve().parent / "data"))
from build_d1_phrases import HEDGE as HEDGE_PREDICATE, PREDICATES  # noqa: E402
from kiwipiepy import Kiwi  # noqa: E402

from app.agents.generate_message_agent.services import quality_check as qc  # noqa: E402

DEFAULT_SEED = 20260929
STRATA = ("explicit", "subtle", "hedge")
D1_CATEGORIES = {"medical_drug_claims", "absolute_claims", "false_certification", "safety_misrepresentation",
                 "discrimination", "functional_cosmetic_unauthorized", "none"}  # none: 대응 카테고리 없음(범위 이탈 등)
KINDS = ("sentence", *PREDICATES)
DEFAULT_PHRASES = Path(__file__).resolve().parent / "data" / "d1_phrases.csv"
REVIEW_COL = "review_ok(O/X)"
EXCLUDED_CATEGORY = "functional_cosmetic_unauthorized"
TEMPLATE_TYPES = ("상품명 주어", "이 제품은", "성분 주어", "앞 절", "주어 없음")
# 검수 전 스모크 테스트용 — 카테고리로 화장품을 근사(본 실행 금지: 테라피삭스처럼 공산품이 섞인다)
COSMETIC_CATEGORIES_SMOKE = {"스킨케어", "색조", "헤어", "향수/바디"}
GENERIC_NOUNS = {"피부", "제품", "사용", "케어", "관리", "고민", "선호", "타입", "포인트", "기준", "구매", "효과", "하루"}

kiwi = Kiwi()


def _nouns(text: str) -> set[str]:
    return {t.form for t in kiwi.tokenize(text) if t.tag in ("NNG", "NNP") and len(t.form) >= 2}


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value if v]
    return [str(value)] if value else []


# ── 틀 모음 ────────────────────────────────────────────────────────────────────

def claim_sentences(original: dict[str, Any]) -> list[str]:
    """본문의 주장 문장 — CTA · 질문 · 10자 미만 제외. 게이트 2단계와 같은 문장 분리."""
    out = []
    msg = original["message"]
    for s in gate_sentences("", msg):
        if len(s) < 10 or is_cta(s) or msg.find(s + "?") >= 0 or is_decimal_fragment(s, msg):
            continue
        out.append(s)
    return out


def template_of(sentence: str, short: str | None, ingredients: list[str]) -> tuple[str, str]:
    """문장 앞부분의 틀 유형과 접두어. 접두어 + 문구 = 틀을 채운 문장."""
    s = sentence.strip()
    if short and s.startswith(short):
        rest = s[len(short):]
        if re.match(r"^\s?(은|는|이|가)\s", rest):
            return "상품명 주어", f"{short}{topic_josa(short)} "
    if s.startswith("이 제품"):
        return "이 제품은", "이 제품은 "
    for ing in sorted(ingredients, key=len, reverse=True):
        pos = s.find(ing)
        if 0 <= pos <= 15 and re.match(r"^\s?성분", s[pos + len(ing):]):
            return "성분 주어", f"{ing} 성분이 "
    comma = s.find(", ")
    if 5 <= comma <= 0.6 * len(s):
        return "앞 절", s[: comma + 2]
    return "주어 없음", ""


def build_template_pool(originals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pool = []
    for o in originals:
        product = o.get("product_snapshot", {})
        short = short_name(product.get("product_name", ""), f"{o['title']} {o['message']}")
        ings = [i for i in _as_list(product.get("ingredient")) if 2 <= len(i) <= 20]
        for s in claim_sentences(o):
            ttype, prefix = template_of(s, short, ings)
            pool.append({"original_id": o["original_id"], "type": ttype, "prefix": prefix, "source_sentence": s})
    return pool


# ── 문장 만들기 ────────────────────────────────────────────────────────────────

def base_sentence(row: dict[str, str]) -> str:
    text = row["text"].strip()
    if row["kind"] == "sentence":
        return text if text.endswith((".", "!", "?")) else text + "."
    predicate = HEDGE_PREDICATE if row["stratum"] == "hedge" else PREDICATES[row["kind"]]
    return predicate.format(text.rstrip("."))


def phrase_problems(row: dict[str, str], base: str) -> list[str]:
    """포함 규칙 위반 · 문장 만들기 규칙 위반. 비어 있으면 유효."""
    problems = []
    if row["kind"] not in KINDS:
        problems.append(f"kind 값 오류: {row['kind']}")
        return problems
    if row["stratum"] not in STRATA:
        problems.append(f"stratum 값 오류: {row['stratum']}")
    if row["category"] not in D1_CATEGORIES:
        problems.append(f"category 값 오류: {row['category']}")
    if row["category"] == EXCLUDED_CATEGORY:
        problems.append("기능성 효능 유형은 D1 에서 제외(DB 에 인증 필드 없음)")
    if not row.get("source_ref", "").strip():
        problems.append("source_ref(출처) 없음")
    if row["stratum"] == "hedge" and not row.get("hedge_basis", "").strip():
        problems.append("헷지 층인데 hedge_basis(외부 근거) 없음")
    if len(gate_sentences("", base)) != 1:
        problems.append("게이트 문장 분리로 한 문장이 아님(내부 구두점)")
    cond = qc._is_hedge_without_assertion(base)
    if row["stratum"] != "hedge" and cond:
        problems.append("비헷지 층인데 override 조건 성립(서술어·문구 확인)")
    return problems


def load_phrases(path: Path, smoke: bool) -> list[dict[str, str]]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = [{k.strip(): (v or "").strip() for k, v in row.items()} for row in csv.DictReader(f)]
    if not smoke:
        missing = [r["phrase_id"] for r in rows if r.get(REVIEW_COL, "").upper() not in ("O", "X")]
        if missing:
            raise SystemExit(f"{path.name} 의 {REVIEW_COL}가 비어 있습니다: {missing[:10]} … (전수 검수 후 다시 실행)")
    return rows


def load_cosmetic(out_dir: Path, originals: list[dict[str, Any]], by_category: bool) -> set[str]:
    if by_category:
        return {o["original_id"] for o in originals if o["category"] in COSMETIC_CATEGORIES_SMOKE}
    path = out_dir / "review_originals_summary.csv"
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    cols = ("is_cosmetic(O/X)", "persona_product_fit(O/X)", "review_ok(O/X)")
    fit_x = {r["original_id"] for r in rows if r.get("persona_product_fit(O/X)", "").strip().upper() == "X"}
    for col in cols:
        # 페르소나-상품 부적합(X) 원본은 어차피 빠지므로 나머지 칸이 비어도 된다
        missing = [r["original_id"] for r in rows if r.get(col, "").strip().upper() not in ("O", "X")
                   and (col == "persona_product_fit(O/X)" or r["original_id"] not in fit_x)]
        if missing:
            raise SystemExit(f"검수 CSV 의 {col}가 비어 있습니다: {missing[:10]} … (검수 후 다시 실행)")
    # 원본 속 D1 은 화장품 · 페르소나-상품 적합 · 검수 통과 원본에만
    return {r["original_id"] for r in rows if all(r[c].strip().upper() == "O" for c in cols)}


def pick_slot(original: dict[str, Any], persona_text: str) -> int | None:
    """치환할 본문 문장의 위치(게이트 문장 분리 기준) — 첫 문장 · CTA · 페르소나 언급 문장이 아닌 가운데 쪽."""
    msg = original["message"]
    sents = gate_sentences("", msg)
    persona_nouns = _nouns(persona_text) - GENERIC_NOUNS
    ok = [i for i, s in enumerate(sents)
          if i > 0 and len(s) >= 15 and not is_cta(s) and not is_decimal_fragment(s, msg)
          and msg.count(s) == 1 and not (_nouns(s) & persona_nouns)]
    if not ok:
        return None
    mid = (len(sents) - 1) / 2
    return min(ok, key=lambda i: (abs(i - mid), i))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", default="main")
    parser.add_argument("--phrases", default=None, help="기본값 result/<run>/d1_phrases.csv")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--cosmetic-by-category", action="store_true",
                        help="검수 전 스모크 전용: 카테고리로 화장품을 근사한다(본 실행 금지)")
    args = parser.parse_args()

    out_dir = run_dir(args.run)
    originals = load_jsonl(out_dir / "originals.jsonl")
    personas = load_personas()
    pool = build_template_pool(originals)
    (out_dir / "template_pool.json").write_text(json.dumps(pool, ensure_ascii=False, indent=2), encoding="utf-8")
    type_freq = Counter(t["type"] for t in pool)
    print(f"틀 모음 {len(pool)}개 (원본 {len(originals)}건): {dict(type_freq.most_common())}")

    phrases_path = Path(args.phrases) if args.phrases else DEFAULT_PHRASES
    phrases = load_phrases(phrases_path, smoke=args.cosmetic_by_category)
    rng = random.Random(args.seed)
    items, excluded = [], []
    by_type: dict[str, list[dict[str, Any]]] = {t: [x for x in pool if x["type"] == t] for t in TEMPLATE_TYPES}
    for row in sorted(phrases, key=lambda r: r["phrase_id"]):
        if row.get("include", "").upper() != "O":
            excluded.append({"phrase_id": row["phrase_id"], "reason": row.get("exclude_reason") or "include≠O"})
            continue
        if row.get(REVIEW_COL, "").upper() == "X":
            excluded.append({"phrase_id": row["phrase_id"], "reason": f"검수 X: {row.get('review_note', '')}"})
            continue
        if row["kind"] not in KINDS:
            excluded.append({"phrase_id": row["phrase_id"], "reason": f"kind 값 오류: {row['kind']}"})
            continue
        base = base_sentence(row)
        if row.get("sentence_preview") and row["sentence_preview"] != base:
            print(f"  경고 {row['phrase_id']}: sentence_preview 와 만든 문장이 다름(검수 중 text 수정?) → {base}")
        problems = phrase_problems(row, base)
        if problems:
            excluded.append({"phrase_id": row["phrase_id"], "reason": "; ".join(problems)})
            continue
        tpl = rng.choice(pool) if pool else {"type": "주어 없음", "prefix": "", "original_id": None}
        # 표적 시험(RQ2-b)용: 헷지 층은 틀 유형마다 하나씩 더 채운다
        targeted = []
        if row["stratum"] == "hedge":
            for ttype in TEMPLATE_TYPES:
                if by_type[ttype]:
                    t = rng.choice(by_type[ttype])
                    targeted.append({"type": ttype, "prefix": t["prefix"], "source": t["original_id"],
                                     "sentence": t["prefix"] + base})
        items.append({
            "item_id": f"{row['phrase_id']}", "role": "primary", "phrase_id": row["phrase_id"],
            "stratum": row["stratum"], "category": row["category"], "kind": row["kind"],
            "source": row.get("source", ""), "source_ref": row.get("source_ref", ""),
            "hedge_basis": row.get("hedge_basis", ""),
            "bare": base, "template_type": tpl["type"], "template_prefix": tpl["prefix"],
            "template_source": tpl.get("original_id"), "sentence": tpl["prefix"] + base,
            "override_condition_bare": qc._is_hedge_without_assertion(base),
            "targeted": targeted,
        })

    # 원본 속 D1(보조): 화장품 확인 원본마다 문구 하나를 자기 틀 모음에서 뽑은 틀로
    cosmetic = load_cosmetic(out_dir, originals, args.cosmetic_by_category)
    primaries = [x for x in items if x["role"] == "primary"]
    in_message = []
    for i, o in enumerate(sorted(originals, key=lambda o: o["original_id"])):
        if o["original_id"] not in cosmetic or not primaries:
            continue
        slot = pick_slot(o, personas[o["persona_id"]]["information"])
        if slot is None:
            continue
        stratum = STRATA[i % len(STRATA)]
        cands = [x for x in primaries if x["stratum"] == stratum] or primaries
        phrase = rng.choice(cands)
        own = [t for t in pool if t["original_id"] == o["original_id"]]
        tpl = rng.choice(own) if own else {"type": "주어 없음", "prefix": ""}
        in_message.append({
            **{k: phrase[k] for k in ("phrase_id", "stratum", "category", "kind", "source", "source_ref", "hedge_basis", "bare")},
            "item_id": f"{o['original_id']}:{phrase['phrase_id']}", "role": "in_message",
            "original_id": o["original_id"], "slot": slot,
            "slot_sentence": gate_sentences("", o["message"])[slot],
            "template_type": tpl["type"], "template_prefix": tpl["prefix"], "template_source": o["original_id"],
            "sentence": tpl["prefix"] + phrase["bare"],
            "override_condition_bare": phrase["override_condition_bare"], "targeted": [],
        })

    write_jsonl(out_dir / "d1_set.jsonl", items + in_message)
    meta = {
        "seed": args.seed, "phrases_file": str(phrases_path),
        "n_phrases": len(phrases), "n_primary": len(items), "n_in_message": len(in_message),
        "excluded": excluded, "template_type_freq": dict(type_freq),
        "rules": {**PREDICATES, "hedge": HEDGE_PREDICATE},
        "cosmetic_source": "category(스모크 전용)" if args.cosmetic_by_category else "review_originals_summary.csv",
        "phrases_sha": __import__("hashlib").sha256(
            json.dumps(phrases, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
    }
    (out_dir / "d1_set_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"D1 주 문구 {len(items)}개 · 원본 속 {len(in_message)}개 · 제외 {len(excluded)}개")
    for e in excluded:
        print(f"  제외 {e['phrase_id']}: {e['reason']}")
    print(f"→ {out_dir / 'd1_set.jsonl'}")


if __name__ == "__main__":
    main()
