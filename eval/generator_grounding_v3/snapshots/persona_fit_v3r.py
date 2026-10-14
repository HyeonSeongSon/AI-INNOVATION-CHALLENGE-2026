"""
페르소나-상품 연결 계산(persona_fit) — 생성 전에 '무엇을 이어도 되는지'를 정해 프롬프트에 넣는다.

v1 이후 남은 결함 대부분은 생성 LLM 이 페르소나와 상품을 즉석에서 잇다가 생겼다.
- 상품 특성을 페르소나 선호에 맞춰 바꿈(예: 가벼운 제형을 '묵직하게 코팅'으로)
- 상품정보에 없는 고민을 상품 적합성처럼 연결(예: '번들거림이 신경 쓰이는 분께')
그래서 연결 판단을 생성과 분리한다. gpt-5-mini 가 세 목록을 내고, 코드가 근거를 검증한다.
- connectable    : 상품정보에 근거가 있는 고민(concern) · 선호(preference)와 그 근거 문구
- not_connectable: 상품정보에 없는 고민 · 니즈 — 메시지에서 꺼내지 않음(v3R)
- conflicts      : 선호와 상품 특성이 반대인 것 — 선호를 약속하지 않고 상품 특성을 그대로 씀
코드 검증: 근거 문구가 스냅숏에 실제로 있어야 하고(공백 무시), 근거 필드의 분류가 종류와 맞아야 한다
(concern → evidence, preference → evidence · style, meta 는 거부). concern 은 고민과 근거 문구가 두 글자 이상
겹쳐야 한다(v3). 어기면 not_connectable 로 내린다. 같은 니즈가 conflicts 나 not_connectable 에도 있으면
connectable 에서 뺀다(v3 · v3R).
의미 연결까지 보증하지는 않는다(평가에서 '무관 근거' 비율을 따로 잰다).
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from ....config.settings import settings
from ....core.llm_factory import get_llm
from ....core.llm_utils import ainvoke_with_retry
from ....core.logging import get_logger
from .product_fields import field_class, generation_product_info

logger = get_logger("persona_fit")

FIT_OK, FIT_FALLBACK, FIT_DISABLED = "ok", "fallback", "disabled"


class FitConnectable(BaseModel):
    persona_need: str = Field(description="페르소나의 고민 · 니즈 · 선호를 짧게")
    need_type: Literal["concern", "preference"] = Field(
        description="concern: 피부 · 모발 고민이나 효능 기대 / preference: 제형 · 향 · 마무리감 · 사용감 선호")
    product_evidence: str = Field(description="근거가 된 상품정보 문구를 한 글자도 바꾸지 않고 그대로")
    field: str = Field(description="그 문구가 있는 상품정보 필드 이름")


class FitConflict(BaseModel):
    persona_preference: str = Field(description="페르소나의 선호")
    product_fact: str = Field(description="그 선호와 반대인 상품정보 문구를 그대로")
    field: str = Field(description="그 문구가 있는 상품정보 필드 이름")


class FitOutput(BaseModel):
    connectable: List[FitConnectable]
    not_connectable: List[str] = Field(description="상품정보에 근거가 없는 페르소나 고민 · 니즈")
    conflicts: List[FitConflict]


@dataclass
class FitResult:
    status: str
    connectable: List[Dict[str, str]] = field(default_factory=list)
    not_connectable: List[str] = field(default_factory=list)
    conflicts: List[Dict[str, str]] = field(default_factory=list)
    demoted: List[Dict[str, str]] = field(default_factory=list)  # 코드 검증에서 내린 항목과 이유
    unknown_fields: List[str] = field(default_factory=list)
    lexical_demoted: List[str] = field(default_factory=list)  # 어휘 겹침으로 내린 고민(동의어일 수 있어 따로 남긴다)

    @property
    def risky(self) -> bool:
        """연결 불가 고민이나 충돌 선호가 있는 쌍(평가의 위험군 정의)."""
        return bool(self.not_connectable or self.conflicts)

    def to_dict(self) -> Dict[str, Any]:
        return {"status": self.status, "connectable": self.connectable, "not_connectable": self.not_connectable,
                "conflicts": self.conflicts, "demoted": self.demoted, "unknown_fields": self.unknown_fields,
                "lexical_demoted": self.lexical_demoted}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FitResult":
        return cls(**{k: d.get(k, [] if k != "status" else FIT_OK) for k in
                      ("status", "connectable", "not_connectable", "conflicts", "demoted", "unknown_fields",
                       "lexical_demoted")})


SYSTEM = """당신은 뷰티 CRM 메시지를 쓰기 전에 고객(페르소나)과 상품을 어디까지 이어도 되는지 정리하는 분석가입니다.
메시지를 쓰지 않습니다. 아래 세 목록만 짧게 만듭니다.

1. connectable (최대 6개): 페르소나의 고민 · 선호 중 상품정보에 같은 뜻의 근거가 있는 것.
   - 한 고민 · 선호는 한 번만, 가장 직접적인 근거 하나만 적습니다.
   - 서로 다른 니즈 두 개를 '·' 나 '/' 로 묶지 말고 하나씩 따로 적습니다.
   - persona_need 는 15자 이내 명사구입니다(예: "입술 건조", "가벼운 제형").
   - need_type: 피부 · 모발 · 두피 · 몸의 고민이나 효능 기대는 "concern", 제형 · 향 · 마무리감 · 사용감 선호는 "preference".
   - product_evidence 는 상품정보 문구를 한 글자도 바꾸지 말고 짧게(40자 이내) 그대로 옮깁니다. field 는 그 필드 이름입니다.
   - 근거가 그 고민 · 선호와 직접 같은 뜻일 때만 넣습니다. 비슷해 보이는 다른 효과를 끌어다 붙이지 않습니다.
   - preference 는 상품 특성과 같은 축(제형 · 마무리감 · 흡수 · 향 · 사용감 · 용량 · 용기)에서 같은 쪽일 때만 넣습니다.
     축이 다르면 넣지 않습니다(예: 상쾌한 느낌 ↔ 포근한 향, 가벼운 사용감 ↔ 촉촉한 사용감, 휴대성 ↔ 리필 구성).
     같은 축에서 반대면 connectable 이 아니라 conflicts 에 넣습니다.
2. not_connectable (최대 4개): 페르소나의 '고민'(피부 · 모발 · 몸 상태의 불편) 중 상품정보에 근거가 없는 것만.
   선호 · 구매 기준 · 생활 습관은 넣지 않습니다. 15자 이내 명사구로, 설명을 붙이지 않습니다. 니즈는 하나씩 적습니다.
3. conflicts (최대 3개): 페르소나 선호와 상품 특성이 같은 축에서 정반대인 것만.
   예: 묵직한 제형 ↔ 가벼운 제형, 광택 ↔ 매트, 빠른 흡수 ↔ 흡수 보통, 무향 ↔ 향 있음, 간단한 단계 ↔ 여러 단계.
   축이 다르면(예: 뭉치지 않음 ↔ 고발색) 충돌이 아닙니다. product_fact 는 상품정보 문구를 40자 이내로 그대로 옮깁니다.
페르소나의 이름 · 나이 · 직업 · 생활 방식 자체는 목록에 넣지 않습니다."""


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


_OVERLAP_STOP = {"케어", "개선", "피부", "제품", "효과", "느낌", "타입", "사용", "없음", "있는"}


def _bigrams(text: str) -> set:
    words = re.sub(r"[^가-힣A-Za-z0-9]", " ", text or "").split()
    return {w[i:i + 2] for w in words for i in range(len(w) - 1)} - _OVERLAP_STOP


def _lexical_overlap(need: str, evidence: str) -> bool:
    """고민과 근거 문구가 두 글자 이상 겹치는지. 사람 판정 116건 중 고민 연결 44건에 대 보면
    무관 근거 1/1 을 잡고 관련 연결 3/43(7%, 동의어)을 내린다. 선호에는 걸지 않는다(관련 18/65 를 내려서)."""
    return bool(_bigrams(need) & _bigrams(evidence))


def _persona_text(persona_info: Dict[str, Any]) -> str:
    if "페르소나 정보" in persona_info:  # 평가용 자유 서술
        return str(persona_info["페르소나 정보"])
    return json.dumps({k: v for k, v in persona_info.items() if k != "persona_id" and v not in (None, "", [], {})},
                      ensure_ascii=False)  # 운영 구조화 dict


def verify(raw: FitOutput, product_info: Dict[str, Any]) -> FitResult:
    """LLM 출력을 스냅숏과 대조한다. 지어낸 근거 · 분류가 맞지 않는 근거는 not_connectable 로 내린다."""
    info = generation_product_info(product_info)
    field_text = {k: _squash(json.dumps(v, ensure_ascii=False)) for k, v in info.items()}
    all_text = _squash(json.dumps(info, ensure_ascii=False))
    res = FitResult(status=FIT_OK, not_connectable=list(raw.not_connectable))
    for c in raw.connectable:
        ev = _squash(c.product_evidence)
        if not ev or ev not in all_text:
            res.demoted.append({**c.model_dump(), "reason": "근거 문구가 상품정보에 없음"})
            res.not_connectable.append(c.persona_need)
            continue
        # 필드 이름이 틀렸으면 문구가 실제로 있는 필드로 고친다
        fld = c.field if ev in field_text.get(c.field, "") else next((k for k, t in field_text.items() if ev in t), c.field)
        cls = field_class(fld)
        if cls is None:
            res.unknown_fields.append(fld)
            cls = "evidence"
        allowed = ("evidence",) if c.need_type == "concern" else ("evidence", "style")
        if cls not in allowed:
            res.demoted.append({**c.model_dump(), "field": fld, "reason": f"{c.need_type} 근거로 {cls} 필드는 쓸 수 없음"})
            res.not_connectable.append(c.persona_need)
            continue
        if c.need_type == "concern" and not _lexical_overlap(c.persona_need, c.product_evidence):
            res.demoted.append({**c.model_dump(), "field": fld, "reason": "고민과 근거 문구가 겹치지 않음(어휘)"})
            res.not_connectable.append(c.persona_need)
            res.lexical_demoted.append(c.persona_need)
            continue
        res.connectable.append({**c.model_dump(), "field": fld})
    for f in raw.conflicts:
        fact = _squash(f.product_fact)
        if fact and fact in all_text:
            res.conflicts.append(f.model_dump())
        else:
            res.demoted.append({**f.model_dump(), "reason": "충돌 근거 문구가 상품정보에 없음"})
    # 모순 제거: 같은 니즈가 연결 가능과 충돌에 함께 있으면 충돌만 남긴다(연결 안내가 서로 반대 지시를 내리지 않게)
    prefs = [_squash(f["persona_preference"]) for f in res.conflicts]
    keep = []
    for c in res.connectable:
        need = _squash(c["persona_need"])
        if need and any(p and (need in p or p in need) for p in prefs):
            res.demoted.append({**c, "reason": "같은 니즈가 충돌에도 있음(모순)"})
        else:
            keep.append(c)
    res.connectable = keep
    # 모순 제거(v3R) ① LLM 이 연결 불가로 낸 니즈와 겹치는 연결 가능은 내린다(부분 문자열 비교)
    blocked = [_squash(n) for n in raw.not_connectable]
    keep = []
    for c in res.connectable:
        need = _squash(c["persona_need"])
        if need and any(b and (need in b or b in need) for b in blocked):
            res.demoted.append({**c, "reason": "같은 니즈가 연결 불가에도 있음(모순)"})
            res.not_connectable.append(c["persona_need"])
        else:
            keep.append(c)
    res.connectable = keep
    # ② 같은 니즈를 근거만 바꿔 두 번 낸 경우, 검증을 통과한 쪽이 있으면 내린 쪽을 연결 불가에 남기지 않는다
    #    (연결 안내가 같은 니즈를 '말할 수 있는 효과'와 '연결 불가'에 함께 적는 것을 막는다. 예: N032)
    kept = {_squash(c["persona_need"]) for c in res.connectable}
    res.not_connectable = [n for n in res.not_connectable if _squash(n) not in kept]
    if res.unknown_fields:
        logger.warning("persona_fit.unknown_fields", fields=sorted(set(res.unknown_fields)))
    return res


def build_fit_section(fit: FitResult) -> str:
    """생성 프롬프트에 넣는 '페르소나-상품 연결 안내'. 근거 문구를 앞에 두고 페르소나 쪽 말은 괄호로만 둔다(v3R)."""
    concerns = [c for c in fit.connectable if c["need_type"] == "concern"]
    prefs = [c for c in fit.connectable if c["need_type"] == "preference"]
    lines = ["## 페르소나-상품 연결 안내 (생성 전에 상품정보와 대조한 결과)"]
    lines.append("- 말할 수 있는 효과 (따옴표 안 근거 문구 범위의 효과만 말하고, 괄호 안 고민은 공감용으로만 쓴다):")
    lines += [f"  - 말할 수 있는 효과: '{c['product_evidence']}' (관련 고민: {c['persona_need']})" for c in concerns] or ["  - (없음)"]
    lines.append("- 말할 수 있는 특성 (사용감 묘사로만 쓰고, 효능 약속으로 키우지 않는다):")
    lines += [f"  - 말할 수 있는 특성: '{c['product_evidence']}' (관련 선호: {c['persona_need']})" for c in prefs] or ["  - (없음)"]
    lines.append("- 연결 불가 (메시지에서 꺼내지 않는다):")
    lines += [f"  - {n}" for n in dict.fromkeys(fit.not_connectable)] or ["  - (없음)"]
    lines.append("- 충돌 (이 선호는 약속하지 않고 상품정보 특성을 그대로 쓴다):")
    lines += [f"  - {c['persona_preference']} ↔ 상품정보: '{c['product_fact']}'" for c in fit.conflicts] or ["  - (없음)"]
    if not fit.connectable:
        lines.append("- 말할 수 있는 효과 · 특성이 없다. 페르소나의 고민은 꺼내지 않고, 사용 상황은 장면 묘사로만 쓴다. "
                     "본문은 상품정보의 효능 중심으로 쓴다.")
    return "\n".join(lines)


class PersonaFitter:
    """페르소나 × 상품 연결 계산기. LLM 은 생성자에서 주입한다(레포 CLAUDE.md P9)."""

    def __init__(self, llm: Optional[Any] = None):
        self._llm = llm or get_llm(settings.persona_fit_model_name or settings.chatgpt_model_name,
                                   reasoning_effort=settings.persona_fit_reasoning_effort)
        self._structured = self._llm.with_structured_output(FitOutput)

    async def fit(self, persona_info: Optional[Dict[str, Any]], product_info: Dict[str, Any]) -> FitResult:
        if not persona_info:
            return FitResult(status=FIT_DISABLED)
        user = ("[페르소나]\n" + _persona_text(persona_info) + "\n\n[상품정보]\n"
                + json.dumps(generation_product_info(product_info), ensure_ascii=False, indent=1))
        try:
            raw = await ainvoke_with_retry(
                self._structured, [("system", SYSTEM), ("human", user)],
                semaphore_key="persona_fit", max_concurrency=settings.persona_fit_max_concurrency,
                max_retries=settings.persona_fit_max_retries, backoff_base=settings.persona_fit_backoff_base,
                logger=logger, retry_event="persona_fit_retry",
            )
            return verify(raw, product_info)
        except Exception as e:  # noqa: BLE001 — 실패하면 연결 안내 없이(보수적 문구로) 생성한다
            logger.warning("persona_fit.failed", error_type=type(e).__name__)
            return FitResult(status=FIT_FALLBACK)
