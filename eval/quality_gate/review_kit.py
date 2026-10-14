"""
검수 도구 — 원본(result/<run>/review_originals_summary.csv)과 D1 문구 모집단(data/d1_phrases.csv)을
브라우저에서 근거와 나란히 보며 채운다. 누를 때마다 CSV 에 바로 저장한다. LLM · 게이트 · DB 호출 없음.

화면에는 판정이 아니라 근거만 보여 준다(검수자가 초안에 끌려가지 않게):
    원본: 페르소나 원문 · 상품 요약 · 기능성 관련 DB 서술 · 문장별로 명사가 겹치는 DB 값(판정기에 보이는지 표시) ·
          문장 속 수치가 DB · 브랜드 프로필 어디에 있는지 · 브랜드 프로필과 겹치는 말 · 자동 힌트(build_originals) ·
          상품 원천 레코드(DB 시드 파일): 상세페이지 원본 이미지 · 상품 페이지 링크 · `문서`(gpt-5.1 이 상세 이미지를
          옮겨 적은 글 — 원본 아님, get_data_history/create_product_document) 중 기능성 관련 줄과 전문
    문구: 게이트에 넣을 문장 · 원문 표기 · 보도자료 원문 맥락 · 지침 별표 1 해당 줄 · 제외 사유

근거 텍스트: data/enforcement_text/ — vault raw/ 의 보도자료 13건 · 지침 · 별표 5 PDF 에서 뽑은 텍스트(2026-09-29).

사용법:
    python review_kit.py serve --run main      # 브라우저에 http://127.0.0.1:8765 가 열린다. 끝낼 때 Ctrl+C
    python review_kit.py status --run main     # 남은 칸 수
    python review_kit.py compare --run main    # 사람 대 LLM 1차 검수(result/<run>/review_llm/) 일치율 · 불일치 목록
"""

import argparse
import ast
import csv
import json
import os
import re
import shutil
import sys
import webbrowser
from collections import Counter
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import build_originals as bo  # bootstrap · kiwi · 판정기 가시 필드
from _common import load_jsonl, run_dir

from app.core.data_loader import get_brand_tones  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent / "data"))
from build_d1_phrases import HEDGE, PREDICATES  # noqa: E402

HERE = Path(__file__).resolve().parent
PHRASES_CSV = HERE / "data" / "d1_phrases.csv"
TEXT_DIR = HERE / "data" / "enforcement_text"
GUIDELINE_TXT = TEXT_DIR / "화장품_표시광고_관리지침_민원인안내서_안내서-0086-07_20250814.txt"
UI_HTML = HERE / "review_kit_ui.html"
REPO = HERE.parents[1]
SEED_SCRIPT = REPO / "database" / "seed_products.py"
PRODUCT_DATA_DIR = REPO / "data"
# 기능성화장품 유형(화장품법 시행규칙 제2조)과 표시 문구를 찾는 말 — 판정이 아니라 줄을 골라 보여 주는 용도
FUNC_RE = re.compile(r"기능성|식약처|식품의약품안전처|심사|보고|SPF|PA\s?\+|자외선|미백|주름\s?개선|탈모|여드름|튼살|염모|제모")

# 근거 없는 구체 사실(A안, 2026-09-30 사용자 결정) — 사람 검수 화면과 LLM 검수가 같은 정의를 쓴다
UNSUPPORTED_DEF = (
    "이 상품의 DB에도 브랜드 프로필에도 근거가 없는, 참 · 거짓을 확인할 수 있는 구체 주장이 있으면 있음: "
    "수치(% · 배 · 시간 · 용량 · 개수), 날짜(출시일 등), 시험 · 임상 · 인증 · 수상 · 특허, 판매 실적 수치 · 순위. "
    "DB의 product_created_at(DB 등록 시각)은 출시일 근거가 아니다. "
    "해당 없음: 사용 상황 · 루틴 시간('출근 전 5분'), 사용감 · 효능의 일반 표현('끈적임 없이', '피부결을 매끈하게'), "
    "막연한 인기 표현('꾸준히 사랑받는'). 결함으로 세지 않는다 — 대조군 오탐률을 이 표시가 있는 원본을 넣은 값 · 뺀 값으로 나눠 보고한다."
)

# 사람이 채우는 열 — 화면 구성과 저장 검증이 이 한 곳을 따른다
ORIG_FIELDS: list[dict[str, Any]] = [
    {"col": "persona_product_fit(O/X)", "section": "fit", "label": "페르소나-상품 적합",
     "options": [["O", "적합"], ["X", "부적합"]], "required": True,
     "help": "상품이 페르소나의 니즈 · 고민과 정면으로 어긋날 때만 X(예: 가습을 원하는데 제습기). "
             "X면 이 원본은 대조군 · 모든 변형 · 자연 결함에서 빠진다(표본을 소분류로 짝지은 부산물)."},
    {"col": "is_cosmetic(O/X)", "section": "product", "label": "화장품인가",
     "options": [["O", "화장품"], ["X", "아님"]], "required": True,
     "help": "화장품법 제2조: 피부 · 모발에 바르거나 뿌리는 등으로 쓰는 물품. 기기(고데기 · 드라이어 · 마사지기), "
             "도구(브러시 · 양말), 식품(이너뷰티), 생활용품은 X. category 필드로 정하지 않는다(예: 젤 양말이 바디케어로 분류됨)."},
    {"col": "functional_certified(O/X)", "section": "product", "label": "기능성 표시 상품",
     "options": [["O", "표시 있음"], ["X", "없음"]], "required": False,
     "help": "상품이 기능성화장품으로 표시돼 있으면 O. 근거: 상세페이지 이미지 · 문서의 '기능성화장품' 표기나 식약처 심사 · 보고 문구, "
             "상품명의 SPF · PA 표기(자외선 차단은 기능성 유형). 기능성 유형: 미백 · 주름 개선 · 자외선 차단 · 염모 · 탈색 · 제모 · "
             "탈모 증상 완화 · 여드름성 피부 완화 · 피부장벽 기능 회복(가려움 개선) · 튼살 붉은선 완화. "
             "이 상품의 기능성 서술은 결함으로 세지 않고, 오탐 분석에서 따로 나눈다."},
    {"col": "review_ok(O/X)", "section": "message", "label": "메시지에 결함이 없는가",
     "options": [["O", "결함 없음"], ["X", "결함 있음"]], "required": True,
     "help": "X = DB와 어긋나는 사실(가격 · 성분 · 수치), 지침 금지 표현, 명백한 오류. "
             "결함이 아닌 것: DB에는 없고 브랜드 프로필에만 있는 서술(아래 '브랜드 프로필'에 표시), "
             "판정기에 안 보이는 필드를 인용한 것(자동 표시만), 기능성 표시 상품의 기능성 서술, "
             "DB에 근거가 없는 구체 사실(수치 · 날짜 · 시험 · 인증 등 — 아래 '근거 없는 구체 사실' 칸에 표시)."},
    {"col": "natural_defect(라벨)", "section": "message", "label": "결함 라벨 (결함 있음일 때)", "type": "text",
     "suggest": ["사실 오류: ", "규제 위반: ", "개인화 오류: ", "미검증"], "required": False,
     "help": "라벨이 있고 '미검증'이 아니면 자연 결함 케이스(N)가 된다. 비우거나 '미검증'이면 원본에서 빠지기만 한다."},
    {"col": "meta_leak(O/X)", "section": "message", "label": "내부 정보 노출",
     "options": [["O", "있음"], ["X", "없음"]], "required": False,
     "help": "'페르소나', '외근형(…)', '타겟 고객'처럼 생성에 쓴 내부 라벨이 고객에게 보이는 문장에 나오면 있음."},
    {"col": "brand_profile_unverified(O/X)", "section": "message", "label": "브랜드 프로필 유래 미검증 서술",
     "options": [["O", "있음"], ["X", "없음"]], "required": False,
     "help": "확인 가능한 사실(수치 · 순위 · 점유율 · 수상 · 특허 · 인증 등)이 이 상품의 DB에는 없고 브랜드 프로필(LLM 생성)에만 있으면 있음. "
             "예: DB에는 '미용실 점유율 1위'만 있는데 메시지가 프로필의 '미용실 10명 중 9명이 선택'을 씀. "
             "DB는 이 상품 것만 본다(같은 브랜드 다른 상품 DB는 근거 아님). 어조 · 분위기 표현은 해당 없음. "
             "DB에도 프로필에도 없는 사실은 이 칸이 아니라 메모에 '근거 없는 사실'로 적는다. 결함으로 세지 않는다."},
    {"col": "unsupported_fact(O/X)", "section": "message", "label": "근거 없는 구체 사실",
     "options": [["O", "있음"], ["X", "없음"]], "required": False, "help": UNSUPPORTED_DEF},
    {"col": "review_note", "section": "note", "label": "메모", "type": "textarea", "required": False, "help": ""},
]
PHRASE_FIELDS: list[dict[str, Any]] = [
    {"col": "review_ok(O/X)", "label": "검수", "required": True,
     "options_include": [["O", "문장 · 분류 맞음"], ["X", "틀림"]],
     "options_exclude": [["O", "제외 동의"], ["X", "제외 반대"]],
     "help_include": "원문 문구의 주장이 문장에 그대로 담겼는지, 서술어 때문에 뜻이 바뀌지 않았는지 본다. "
                     "층 · category는 결과를 나눠 보는 용도라, 틀렸으면 메모만 남기고 O로 둬도 된다.",
     "help_exclude": "제외 사유가 규칙(결정 5 · 6 · 7)에 맞는지 본다. 제외 반대(X)면 메모에 이유를 적는다 — 모집단을 다시 만든다."},
    {"col": "review_note", "label": "메모", "type": "textarea", "required": False},
]
GENERIC = {"피부", "제품", "사용", "케어", "관리", "고민", "효과", "하루", "브랜드", "고객", "일상", "선택", "추천"}


# ── CSV ──────────────────────────────────────────────────────────────────────

def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), [dict(r) for r in reader]


def write_csv_atomic(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp, path)


# ── 원본 근거 ────────────────────────────────────────────────────────────────

def _items(value: Any) -> list[str]:
    if value in (None, "", [], {}):
        return []
    if isinstance(value, list):
        return [json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v) for v in value if v]
    if isinstance(value, dict):
        return [json.dumps(value, ensure_ascii=False)]
    return [str(value)]


def split_sentences(text: str) -> list[str]:
    """build_originals.review_rows 와 같은 분리(소수점은 자르지 않는다)."""
    return [s.strip() for s in re.split(r"[!?。！？\n]+|\.(?!\d)|(?<!\d)\.", text) if s.strip()]


def original_evidence(o: dict[str, Any], flags: dict[int, str], brand_profile: str) -> dict[str, Any]:
    p = o["product_snapshot"]
    visible = set(bo._JUDGE_PRODUCT_FIELDS)
    cells = []  # (field, text, nouns, numbers)
    for field, value in p.items():
        if field in bo._SKIP_FIELDS:
            continue
        for text in _items(value):
            cells.append((field, text, bo._nouns(text), bo._numbers(text)))
    brand_nouns = bo._nouns(brand_profile) - GENERIC if brand_profile else set()
    brand_numbers = bo._numbers(brand_profile) if brand_profile else set()

    sentences = []
    for idx, s in enumerate(split_sentences(f"{o['title']}\n{o['message']}")):
        s_nouns = bo._nouns(s)
        matches = []
        for field, text, nouns, _ in cells:
            hit = (s_nouns & nouns) - GENERIC
            if hit:
                matches.append({"field": field, "visible": field in visible, "text": text[:240],
                                "hit": sorted(hit), "score": len(hit)})
        matches.sort(key=lambda m: (-m["score"], not m["visible"], m["field"]))
        numbers = []
        for n in sorted(bo._numbers(s)):
            where = sorted({f for f, _, _, nums in cells if n in nums})
            numbers.append({"n": n, "fields": where, "visible": any(f in visible for f in where),
                            "brand": n in brand_numbers})
        sentences.append({
            "idx": idx, "text": s, "matches": matches[:8], "n_matches": len(matches), "numbers": numbers,
            "brand_overlap": sorted((s_nouns & brand_nouns) - {w for m in matches for w in m["hit"]}),
            "flags": flags.get(idx, ""),
        })

    functional = []
    for field, text, _, _ in cells:
        if FUNC_RE.search(text):
            functional.append({"field": field, "visible": field in visible, "text": text[:300]})

    brief_keys = ("product_name", "brand", "category", "tag", "sub_tag", "sale_price", "discount_rate", "skin_type",
                  "concerns", "suitable_for", "body_area", "function", "ingredient", "target_user")
    return {
        "persona": o.get("persona_info", {}).get("페르소나 정보", ""),
        "product": [{"field": k, "text": ", ".join(_items(p.get(k))), "visible": k in visible}
                    for k in brief_keys if _items(p.get(k))],
        "functional": functional, "sentences": sentences, "brand_profile": brand_profile,
    }


def seed_source_files() -> list[str]:
    """DB 시드 스크립트의 SOURCE_FILES 를 그대로 읽는다(DB 와 같은 원천을 보도록)."""
    tree = ast.parse(SEED_SCRIPT.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "SOURCE_FILES" for t in node.targets):
            return list(ast.literal_eval(node.value))
    raise SystemExit(f"{SEED_SCRIPT} 에서 SOURCE_FILES 를 찾지 못함")


def load_source_records(products: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """product_id → 원천 레코드. product_id 가 없는 추가분(_add)은 시드가 id 를 새로 만들었으므로 (브랜드, 상품명)으로 찾는다."""
    want_ids = {p["product_id"] for p in products}
    want_names = {(p.get("brand"), p.get("product_name")): p["product_id"] for p in products}
    out: dict[str, dict[str, Any]] = {}
    for fname in seed_source_files():
        path = PRODUCT_DATA_DIR / fname
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                r = json.loads(line)
                pid = r.get("product_id")
                if pid in want_ids:
                    out.setdefault(pid, {**r, "_file": fname, "_match": "product_id"})
                else:
                    by_name = want_names.get((r.get("브랜드"), r.get("상품명")))
                    if by_name and not pid:
                        out.setdefault(by_name, {**r, "_file": fname, "_match": "브랜드+상품명"})
    return out


def source_evidence(rec: dict[str, Any] | None) -> dict[str, Any]:
    if not rec:
        return {"found": False}
    doc = rec.get("문서") or ""
    sections, title, buf = [], "", []
    for line in doc.splitlines():
        m = re.match(r"^\s*(\d+\))\s*(.+)$", line)
        if m and len(m.group(2)) < 60:
            if title or buf:
                sections.append({"title": title, "text": "\n".join(buf).strip()})
            title, buf = f"{m.group(1)} {m.group(2).strip()}", []
        else:
            buf.append(line)
    if title or buf:
        sections.append({"title": title, "text": "\n".join(buf).strip()})
    func_lines = []
    for line in doc.splitlines():
        t = line.strip(" -\t")
        if t and FUNC_RE.search(t) and t not in func_lines:
            func_lines.append(t[:300])
    images = [u for u in (rec.get("상품상세_이미지") or []) if isinstance(u, str)]
    return {
        "found": True, "file": rec["_file"], "match": rec["_match"],
        "url": rec.get("product_url") or rec.get("url") or "",
        "one_liner": rec.get("한줄소개") or "",
        "images": images, "has_doc": bool(doc), "doc_sections": sections, "func_lines": func_lines[:30],
    }


def load_originals(out_dir: Path) -> list[dict[str, Any]]:
    originals = load_jsonl(out_dir / "originals.jsonl")
    _, summary = read_csv(out_dir / "review_originals_summary.csv")
    hints = {r["original_id"]: r for r in summary}
    _, sent_rows = read_csv(out_dir / "review_originals.csv")
    flags: dict[str, dict[int, str]] = {}
    for r in sent_rows:
        flags.setdefault(r["original_id"], {})[int(r["sent_idx"])] = r.get("auto_flags", "")
    tones = get_brand_tones().get("brand_ton_prompt", {})
    sources = load_source_records([o["product_snapshot"] for o in originals])
    out = []
    for o in sorted(originals, key=lambda x: x["original_id"]):
        h = hints.get(o["original_id"], {})
        out.append({
            "id": o["original_id"], "category": o["category"], "tag": o["tag"], "sub_tag": o["sub_tag"],
            "brand": o["brand"], "purpose": o["purpose"], "persona_id": o["persona_id"],
            "title": o["title"], "message": o["message"], "message_len": len(o["message"]),
            "hints": {k: h.get(k, "") for k in ("hint_functional", "hint_meta_leak",
                                                "hint_invisible_field_citation", "hint_unsupported_sentences")},
            **original_evidence(o, flags.get(o["original_id"], {}), str(tones.get(o["brand"], "") or "")),
            "source": source_evidence(sources.get(o["product_snapshot"]["product_id"])),
        })
    return out


# ── 문구 근거 ────────────────────────────────────────────────────────────────

def _squash(text: str) -> tuple[str, list[int]]:
    """공백 · 각주 표시(*)를 뺀 문자열과 원래 위치 대응표."""
    chars, pos = [], []
    for i, ch in enumerate(text):
        if not ch.isspace() and ch != "*":
            chars.append(ch)
            pos.append(i)
    return "".join(chars), pos


def find_context(text: str, phrase: str, width: int = 90) -> dict[str, str] | None:
    squashed, pos = _squash(text)
    for cand in (phrase, re.sub(r"^\([^)]*\)\s*", "", phrase)):
        key = re.sub(r"[\s*]", "", cand)
        i = squashed.find(key) if key else -1
        if i >= 0:
            start, end = pos[i], pos[i + len(key) - 1] + 1
            flat = lambda s: re.sub(r"\s+", " ", s)  # noqa: E731
            return {"pre": flat(text[max(0, start - width):start]), "hit": flat(text[start:end]),
                    "post": flat(text[end:end + width])}
    return None


def annex1_lines() -> list[str]:
    lines = GUIDELINE_TXT.read_text(encoding="utf-8").splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.strip() == "[별표 1]")
    end = next(i for i, ln in enumerate(lines) if i > start and ln.strip() == "[별표 2]")
    return [ln.strip() for ln in lines[start:end] if ln.strip() and not ln.startswith("===")]


def load_phrases(phrases_csv: Path) -> list[dict[str, Any]]:
    _, rows = read_csv(phrases_csv)
    texts = {p.stem: p.read_text(encoding="utf-8") for p in TEXT_DIR.glob("20*.txt")}
    annex = annex1_lines()
    rules = {**{k: v.format("{표현}") for k, v in PREDICATES.items()}, "hedge": HEDGE.format("{표현}"),
             "sentence": "원래 문장 그대로"}
    out = []
    for r in rows:
        variants = [v for v in r["original"].split(" / ") if v]
        contexts = []
        for ref in [x.strip() for x in r["source_ref"].split(";") if x.strip()]:
            rel = ref.split("(")[0]
            label = ref[len(rel):].strip("()")
            ctx = next((c for v in variants if (c := find_context(texts.get(rel, ""), v))), None)
            contexts.append({"release": rel, "type": label, "context": ctx})
        roots = [x for x in r.get("guideline_roots", "").split(",") if x]
        guideline = []
        for root in roots:
            hits = [ln for ln in annex if root in re.sub(r"\s", "", ln)][:2]
            guideline.append({"root": root, "lines": hits})
        rule_key = "hedge" if r.get("stratum") == "hedge" else r.get("kind", "")
        out.append({
            "id": r["phrase_id"], **{k: r.get(k, "") for k in (
                "text", "kind", "stratum", "category", "source", "source_ref", "hedge_basis", "include",
                "exclude_reason", "sentence_preview", "original", "text_edit", "n_sources", "note")},
            "rule": rules.get(rule_key, ""), "contexts": contexts, "guideline": guideline,
        })
    return out


# ── 저장소 ───────────────────────────────────────────────────────────────────

class Store:
    def __init__(self, out_dir: Path, phrases_csv: Path):
        self.paths = {"originals": out_dir / "review_originals_summary.csv", "phrases": phrases_csv}
        self.keys = {"originals": "original_id", "phrases": "phrase_id"}
        self.fields = {"originals": ORIG_FIELDS, "phrases": PHRASE_FIELDS}
        self.backup_dir = out_dir / "review_backup"
        self.tables: dict[str, tuple[list[str], list[dict[str, str]], float]] = {}
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.backup_dir.mkdir(exist_ok=True)
        for name, path in self.paths.items():
            shutil.copy2(path, self.backup_dir / f"{stamp}_{path.name}")
            self._load(name)

    def _load(self, name: str) -> None:
        fields, rows = read_csv(self.paths[name])
        self.tables[name] = (fields, rows, self.paths[name].stat().st_mtime)

    def values(self, name: str) -> dict[str, dict[str, str]]:
        cols = [f["col"] for f in self.fields[name]]
        _, rows, _ = self.tables[name]
        return {r[self.keys[name]]: {c: r.get(c, "") for c in cols} for r in rows}

    def save(self, name: str, item_id: str, col: str, value: str) -> str | None:
        """저장 후 None, 실패하면 사람이 읽을 이유."""
        spec = next((f for f in self.fields.get(name, []) if f["col"] == col), None)
        if spec is None:
            return f"편집할 수 없는 열: {col}"
        value = re.sub(r"[\r\n]+", " / ", value or "").strip()[:500]
        if spec.get("type") not in ("text", "textarea") and value not in ("", "O", "X"):
            return f"O/X 가 아닌 값: {value}"
        path = self.paths[name]
        if path.stat().st_mtime != self.tables[name][2]:
            self._load(name)  # 다른 곳(엑셀 등)에서 바뀌었으면 다시 읽고 그 위에 쓴다
        fields, rows, _ = self.tables[name]
        row = next((r for r in rows if r[self.keys[name]] == item_id), None)
        if row is None:
            return f"없는 항목: {item_id}"
        if col not in fields:
            return f"CSV 에 열이 없음: {col}"
        old = row.get(col, "")
        row[col] = value
        try:
            write_csv_atomic(path, fields, rows)
        except PermissionError:
            row[col] = old
            return f"{path.name} 이(가) 다른 프로그램(엑셀 등)에서 열려 있어 저장하지 못했습니다. 닫고 다시 누르세요."
        self.tables[name] = (fields, rows, path.stat().st_mtime)
        return None


def make_handler(store: Store, payload: dict[str, Any]):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:  # 요청 로그는 끈다
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path in ("/", "/index.html"):
                self._send(200, UI_HTML.read_bytes(), "text/html; charset=utf-8")
            elif self.path == "/api/data":
                data = {**payload, "values": {n: store.values(n) for n in ("originals", "phrases")}}
                self._send(200, json.dumps(data, ensure_ascii=False).encode(), "application/json; charset=utf-8")
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self) -> None:
            if self.path != "/api/save":
                self._send(404, b"not found", "text/plain")
                return
            try:
                req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8"))
                err = store.save(req["file"], req["id"], req["col"], req.get("value", ""))
            except Exception as e:  # noqa: BLE001 — 화면에 이유를 보여 준다
                err = f"저장 오류: {e}"
            body = {"ok": err is None, "error": err, "saved_at": datetime.now().strftime("%H:%M:%S")}
            self._send(200, json.dumps(body, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    return Handler


# ── 명령 ─────────────────────────────────────────────────────────────────────

def blanks(name: str, rows: list[dict[str, str]]) -> dict[str, int]:
    specs = ORIG_FIELDS if name == "originals" else PHRASE_FIELDS
    return {f["col"]: sum(1 for r in rows if not r.get(f["col"], "").strip())
            for f in specs if f.get("options") or f.get("options_include")}


def cmd_status(out_dir: Path, phrases_csv: Path) -> None:
    for name, path in (("originals", out_dir / "review_originals_summary.csv"), ("phrases", phrases_csv)):
        _, rows = read_csv(path)
        print(f"{path.name} ({len(rows)}행) — 빈 칸:")
        specs = {f["col"]: f for f in (ORIG_FIELDS if name == "originals" else PHRASE_FIELDS)}
        for col, n in blanks(name, rows).items():
            mark = "필수" if specs[col].get("required") else "선택"
            print(f"  {col:34s} {n:3d}  ({mark})")


def cmd_serve(out_dir: Path, phrases_csv: Path, port: int, open_browser: bool) -> None:
    print("근거 계산 중(형태소 분석)…")
    payload = {
        "run": out_dir.name,
        "schema": {"originals": ORIG_FIELDS, "phrases": PHRASE_FIELDS},
        "originals": load_originals(out_dir),
        "phrases": load_phrases(phrases_csv),
        # 사람 확인(감사) 대상 — 눈가림: 어떤 항목인지만 넘기고, 고른 이유(LLM 값)는 넘기지 않는다
        "audit": ({k: sorted(v) for k, v in json.loads((out_dir / "review_audit.json").read_text(encoding="utf-8")).items()
                   if k in ("originals", "phrases")} if (out_dir / "review_audit.json").exists() else None),
    }
    store = Store(out_dir, phrases_csv)
    server = HTTPServer(("127.0.0.1", port), make_handler(store, payload))
    url = f"http://127.0.0.1:{port}"
    print(f"검수 화면: {url}  (끝낼 때 Ctrl+C)")
    print(f"저장 위치: {store.paths['originals']}")
    print(f"           {store.paths['phrases']}")
    print(f"시작 시점 백업: {store.backup_dir}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n종료")
        cmd_status(out_dir, phrases_csv)


def kappa(pairs: list[tuple[str, str]]) -> float | None:
    n = len(pairs)
    if n == 0:
        return None
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return None if pe == 1 else (po - pe) / (1 - pe)


def audit_group(reasons: list[str]) -> str:
    """사람 확인 대상을 고른 이유로 묶는다. LLM 정확도의 치우치지 않은 추정은 '무작위' 묶음뿐이다."""
    text = " ".join(reasons)
    if "이미 사람이 채움" in text:
        return "사전 사람 검수(LLM 결과 보기 전)"
    if "무작위" in text:
        return "무작위(LLM O · 확신 높음)"
    return "LLM X · 확신 낮음"


def cmd_compare(out_dir: Path, phrases_csv: Path, other_dir: Path) -> None:
    """사람(1차) 대 다른 검수(2차, 기본 LLM) 일치율. 사람 쪽은 merge 로 LLM 값이 들어간 행(label_source=llm)을 빼고,
    눈가림 스냅숏(review_backup/human_blind_snapshot_*)이 있으면 그 값을 우선한다(LLM 결과를 본 뒤 고친 값 제외)."""
    audit_path = out_dir / "review_audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8")) if audit_path.exists() else {}
    lines = ["# 검수 일치율", "", f"- 1차: 사람 검수 · 2차: `{other_dir}`",
             "- 두 검수 모두 값이 있는 항목만 센다. κ는 Cohen's kappa.",
             "- 묶음: 사람 확인 대상을 고른 이유. LLM 판단 정확도의 치우치지 않은 추정은 '무작위' 묶음이다"
             "(LLM X · 확신 낮음 묶음은 불일치가 많을 쪽을 골라 담은 것).", ""]
    for name, file_key, mine, theirs, key in (
        ("원본", "originals", out_dir / "review_originals_summary.csv", other_dir / "review_originals_summary.csv", "original_id"),
        ("문구", "phrases", phrases_csv, other_dir / "d1_phrases.csv", "phrase_id"),
    ):
        if not theirs.exists():
            lines += [f"## {name}", "", f"2차 파일 없음: {theirs}", ""]
            continue
        a = {r[key]: r for r in read_csv(mine)[1] if r.get("label_source", "") != "llm"}
        snaps = sorted((out_dir / "review_backup").glob(f"human_blind_snapshot_*_{mine.name}"))
        if snaps:
            for r in read_csv(snaps[-1])[1]:
                if r[key] in a and any(r.get(c, "").strip() for c in (f["col"] for f in ORIG_FIELDS + PHRASE_FIELDS)):
                    a[r[key]] = r
            lines.append(f"- {name}: 눈가림 스냅숏 `{snaps[-1].name}` 값 우선")
        b = {r[key]: r for r in read_csv(theirs)[1]}
        reasons = audit.get(file_key, {})
        group = {i: audit_group(reasons[i]) if i in reasons else "확인 대상 아님" for i in a}
        specs = ORIG_FIELDS if name == "원본" else PHRASE_FIELDS
        cols = [f["col"] for f in specs if f.get("options") or f.get("options_include")]
        both = lambda i, c: i in b and a[i].get(c, "").strip() and b[i].get(c, "").strip()  # noqa: E731
        lines += ["", f"## {name}", "", "| 열 | 묶음 | n | 일치 | κ |", "|---|---|---|---|---|"]
        for col in cols:
            for g in ["전체", *sorted({group[i] for i in a if both(i, col)})]:
                pairs = [(a[i][col].strip().upper(), b[i][col].strip().upper()) for i in a
                         if both(i, col) and (g == "전체" or group[i] == g)]
                if not pairs:
                    continue
                k = kappa(pairs)
                lines.append(f"| {col} | {g} | {len(pairs)} | {sum(x == y for x, y in pairs)}/{len(pairs)} | "
                             f"{'-' if k is None else f'{k:.2f}'} |")
        diffs = [(i, group[i], c, a[i][c], b[i][c], a[i].get("review_note", ""), b[i].get("review_note", ""))
                 for i in a for c in cols if both(i, c) and a[i][c].strip().upper() != b[i][c].strip().upper()]
        lines += ["", "| 항목 | 묶음 | 열 | 1차 | 2차 | 1차 메모 | 2차 메모 |", "|---|---|---|---|---|---|---|"]
        lines += [f"| {i} | {g} | {c} | {x} | {y} | {nx} | {ny} |" for i, g, c, x, y, nx, ny in sorted(diffs)] \
            or ["| (불일치 없음) ||||||"]
        lines.append("")
    out = out_dir / "review_agreement.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"→ {out}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="원본 · D1 문구 검수 도구")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("serve", "status", "compare"):
        p = sub.add_parser(name)
        p.add_argument("--run", default="main")
        p.add_argument("--phrases", default=str(PHRASES_CSV), help="기본값 data/d1_phrases.csv")
        if name == "serve":
            p.add_argument("--port", type=int, default=8765)
            p.add_argument("--no-open", action="store_true", help="브라우저를 자동으로 열지 않는다")
        if name == "compare":
            p.add_argument("--other-dir", default=None, help="기본값 result/<run>/review_llm (LLM 1차 검수)")
    args = parser.parse_args()
    out_dir = run_dir(args.run)
    if not (out_dir / "originals.jsonl").exists():
        raise SystemExit(f"{out_dir / 'originals.jsonl'} 없음 — build_originals.py 를 먼저 돌린다")
    phrases_csv = Path(args.phrases)
    if args.cmd == "serve":
        cmd_serve(out_dir, phrases_csv, args.port, not args.no_open)
    elif args.cmd == "status":
        cmd_status(out_dir, phrases_csv)
    else:
        cmd_compare(out_dir, phrases_csv, Path(args.other_dir) if args.other_dir else out_dir / "review_llm")


if __name__ == "__main__":
    main()
