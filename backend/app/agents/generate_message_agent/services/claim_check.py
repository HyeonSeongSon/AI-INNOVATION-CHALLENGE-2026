"""
생성 뒤 점검(V4) — 생성된 제목 · 본문에서 상품정보에 근거 없는 표현을 범주 사전으로 찾는다(정규식 수준, LLM 없음).

범주(사전은 범주 단어로만 만든다 — 특정 사례 문장을 넣지 않는다)
- A 근거 없는 한정 표현: 지속 시간 · 횟수 · 양 · 비교 표현이 상품정보에 같은 표현으로 없으면 걸린다.
- B 근거 없는 공감 호출: fit 이 승인한 고민 연결이 0개인데 고민을 불러내는 표현(걱정 · 고민 · 신경 쓰 · 불편 · 답답 + ~때 / ~라면 /
  ~시죠 꼴)이 나오면 걸린다. 그 고민어가 상품정보의 고민 · 대상 필드와 세 글자 이상 연속으로 겹치면 통과.
- C 연결 불가 니즈 재등장: fit 의 연결 불가 니즈가 메시지와 세 글자 이상 연속으로 겹치면 걸린다.
- D 근거 없는 사용 시점 · 단계: 루틴 단계어(세안 · 샤워 · 드라이 · 메이크업 등) + 시점어(전 · 후 · 직전 · 직후 · 마무리) 또는
  "젖은 · 마른 ~" 표현이, 상품 사용 필드의 한 항목 안에 같은 단계어 · 같은 시점어로 함께 있지 않으면 걸린다.
켜는 범주는 ENABLED_CATEGORIES 로 정한다(V4 단계 1(a) 오프라인 점검 결과 — 이 파일의 해시로 잠긴다).
걸리면 생성기가 1회 다시 쓴다(generate_crm_message). 점검 결과는 태스크 안에서만 쓰고 state 에는 남기지 않는다.
"""

import json
import re
from typing import Any, Dict, Iterable, List, Optional

from ..prompts.persona_fit import overlap3
from ..prompts.product_fields import generation_product_info

# 운영에서 켜는 범주(단계 1(a) 결과로 정한다). 비어 있으면 점검 · 재생성을 하지 않는다.
# V4 단계 1 결과: A 만 켠다(재현율 24/25, 사람 확인 진짜 오탐 6/139). B · C · D 는 기준 미달로 끈다.
ENABLED_CATEGORIES: frozenset = frozenset({"A"})

# D 면제 범위: "usage"(사용 필드) — 단계 1(a)의 미리 정한 보정 1회로 "all"(상품정보 전체 필드)로 넓힐 수 있다
D_EXEMPT_SCOPE = "usage"

_A_PATTERNS = {
    "지속 시간": r"\d+\s*(?:시간|분|일간|주간|개월)|하루\s*종일|종일|하루\s*동안|밤새|오후까지|저녁까지|아침까지",
    "횟수": r"한\s*번|두\s*번|\d+\s*회|매일|하루\s*\d+\s*번|주\s*\d+\s*(?:~\s*\d+\s*)?회|수시로",
    "양": r"스푼|방울|펌프|소량|듬뿍|한\s*겹|두\s*겹|\d+\s*(?:알|정|캡슐|포)\b",
    "비교 · 변화": r"다른|다르게|다르기|달라|달랐|달리|변화|차이|차별|기존\s*대비|더\s*오래|전보다",
}
# A 보정(V4 단계 1(a) 1회): 상품정보에 같은 뜻의 다른 말이 있으면 통과
_A_SAME_MEANING = {"매일": ("데일리", "daily", "매일", "1일1회", "하루1회", "하루한번")}

_B_PATTERN = r"(걱정|고민|신경\s*쓰|불편|답답)[가-힣\s]{0,8}?(?:때|라면|시죠|시나요|나요|세요|던)"
# D: 루틴 단계를 나타내는 일반 명사(범주 사전) + 시점어. 질감 · 마무리감의 "마무리"는 단계어가 앞에 올 때만 본다.
_D_STEPS = (r"세안|클렌징|샤워|목욕|드라이|메이크업|화장|스타일링|기초|스킨케어|면도|운동|외출|출근|퇴근|취침|잠들기|자기|"
            r"식사|식후|샴푸|린스|헹굼|각질\s*제거|팩")
_D_PATTERN = (rf"({_D_STEPS})\s*(직전|직후|전|후|마무리)(?:\s*단계)?"
              r"|(젖은|마른)\s*(?:머리|모발|피부|상태)")
USAGE_FIELDS = ("usage_context", "application_timing", "how_to_use", "usage", "daily_intake")
CONCERN_FIELDS = ("concern", "concerns", "suitable_for", "skin_type", "target_user", "target_tags", "function_desc")


def _squash(t: str) -> str:
    return re.sub(r"\s+", "", t or "")


def _flat(v: Any) -> List[str]:
    if v in (None, "", [], {}):
        return []
    if isinstance(v, (list, tuple)):
        return [s for x in v for s in _flat(x)]
    if isinstance(v, dict):
        return [s for x in v.values() for s in _flat(x)]
    return [str(v)]


def parse_message(raw: Any) -> Dict[str, str]:
    """생성 결과(AIMessage 또는 문자열)에서 title · message 를 꺼낸다. 실패하면 본문 전체를 message 로 본다."""
    content = raw.content if hasattr(raw, "content") else str(raw)
    m = re.search(r"\{.*\}", content, re.S)
    if m:
        try:
            d = json.loads(m.group(0))
            if isinstance(d, dict):
                return {"title": str(d.get("title", "")), "message": str(d.get("message", ""))}
        except Exception:  # noqa: BLE001
            pass
    return {"title": "", "message": content}


def detect(title: str, message: str, product_info: Dict[str, Any], fit: Optional[Any] = None,
           categories: Iterable[str] = ("A", "B", "C", "D"), d_scope: Optional[str] = None) -> List[Dict[str, Any]]:
    """걸린 표현 목록. 각 항목: {cat, sub, text, where(title|message), start, end}. fit 은 FitResult(없으면 B · C 생략)."""
    info = generation_product_info(product_info)
    all_text = _squash(json.dumps(info, ensure_ascii=False))
    cats = set(categories)
    hits: List[Dict[str, Any]] = []
    for where, text in (("title", title or ""), ("message", message or "")):
        if "A" in cats:
            for sub, pat in _A_PATTERNS.items():
                for m in re.finditer(pat, text):
                    hit = _squash(m.group(0))
                    alts = _A_SAME_MEANING.get(hit, (hit,))
                    if not any(a in all_text or a.lower() in all_text.lower() for a in alts):
                        hits.append({"cat": "A", "sub": sub, "text": m.group(0), "where": where, "start": m.start(), "end": m.end()})
        if "B" in cats and fit is not None and getattr(fit, "status", "") == "ok" and not fit.concern_links:
            concern_text = " ".join(s for k in CONCERN_FIELDS for s in _flat(info.get(k)))
            for m in re.finditer(_B_PATTERN, text):
                start = max(text.rfind(p, 0, m.start()) for p in (".", ",", "?", "!", "\n")) + 1
                phrase = text[start:m.end()]
                if not overlap3(phrase, concern_text):
                    hits.append({"cat": "B", "sub": "공감 호출", "text": phrase.strip(), "where": where,
                                 "start": start, "end": m.end()})
        if "C" in cats and fit is not None:
            for need in getattr(fit, "not_connectable", []) or []:
                if overlap3(need, text):
                    hits.append({"cat": "C", "sub": "연결 불가 니즈", "text": need, "where": where, "start": -1, "end": -1})
        if "D" in cats:
            scope = d_scope or D_EXEMPT_SCOPE
            entries = (_flat([info.get(k) for k in USAGE_FIELDS]) if scope == "usage"
                       else _flat(list(info.values())))
            for m in re.finditer(_D_PATTERN, text):
                if m.group(1):
                    noun, mark = _squash(m.group(1)), m.group(2)
                else:
                    noun, mark = m.group(3), ""
                ok = any(noun in _squash(e) and (not mark or mark in e) for e in entries)
                if not ok:
                    hits.append({"cat": "D", "sub": "사용 시점", "text": m.group(0), "where": where, "start": m.start(), "end": m.end()})
    return hits


def regenerate_note(hits: List[Dict[str, Any]]) -> str:
    items = list(dict.fromkeys(h["text"] for h in hits))
    return ("방금 쓴 메시지의 다음 표현은 상품정보에 근거가 없습니다: " + ", ".join(f"'{t}'" for t in items)
            + ". 이 표현을 빼거나 상품정보 문구로 바꾸고, 나머지는 유지해 같은 JSON 형식으로 다시 쓰세요.")
