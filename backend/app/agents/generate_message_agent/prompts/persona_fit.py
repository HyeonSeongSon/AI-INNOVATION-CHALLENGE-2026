"""
페르소나-상품 연결 계산(persona_fit) — 생성 전에 '무엇을 이어도 되는지'를 정해 프롬프트에 넣는다.

v1 이후 남은 결함 대부분은 생성 LLM 이 페르소나와 상품을 즉석에서 잇다가 생겼다. 그래서 연결 판단을 생성과 분리한다.
V4 구조:
- LLM(gpt-5-mini)은 페르소나 니즈마다 상태를 하나만 낸다(needs 한 목록 — 같은 니즈가 두 상태에 들어갈 수 없다).
  need_type: concern(고민 · 효과 기대) · preference(제형 · 향 · 사용감 선호) · criterion(구매 기준) · usage(사용 방식 · 시점)
- 코드 검증: 근거 문구가 스냅숏에 실제로 있어야 하고(공백 무시), 근거 필드의 분류가 종류와 맞아야 한다.
  concern 은 고민과 근거 문구가 두 글자 이상 겹쳐야 한다(v3). usage 는 항상 연결 불가다(사용 시점은 상품 필드로만 쓴다).
  LLM 이 다른 종류로 냈어도 페르소나 원문의 사용 방식 · 사용 상황 줄과 세 글자 이상 연속으로 겹치면 내린다.
- 연결 확인(LINK_CHECK_ENABLED): 승인된 연결 묶음을 별도 호출로 "근거 문구가 니즈와 같은 결과 · 속성을 말하는가" 되묻고
  아니면 내린다. 호출이 실패하면 확인되지 않은 연결은 모두 내린다(통과시키지 않는다).
- 결과는 기존 FitResult(connectable · not_connectable · conflicts)로 돌려준다(저장된 캐시 · CachedFitter 와 호환).
생성 프롬프트에는 승인된 연결만 넣는다(build_fit_section). 연결 불가 · 충돌은 생성 뒤 점검과 평가 저장용이다.
생성 프롬프트의 페르소나는 build_persona_view 로 거른다(이름 · 나이 · 성별 · 직업, 목적 7 만 라이프스타일까지).
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

# 연결 확인을 켤지(V4 단계 1(b) 결과로 정한다 — 이 파일의 해시로 잠긴다)
LINK_CHECK_ENABLED = True
# 연결 확인의 추론 강도. 비우면 fit 과 같은 LLM(settings.persona_fit_reasoning_effort). 단계 1(b) 미달 시 미리 정한 보정 = "low"
LINK_REASONING_EFFORT = ""

LIFESTYLE_PURPOSE = "라이프스타일/연령대 강조 소개"


class FitNeed(BaseModel):
    persona_need: str = Field(description="페르소나의 고민 · 니즈 · 선호 · 구매 기준 · 사용 방식을 짧게(15자 이내 명사구)")
    need_type: Literal["concern", "preference", "criterion", "usage"] = Field(
        description="concern: 피부 · 모발 · 몸 고민이나 효과 기대 / preference: 제형 · 향 · 마무리감 · 사용감 선호 / "
                    "criterion: 구매 기준 / usage: 사용 방식 · 사용 시점 · 사용 상황")
    status: Literal["connectable", "not_connectable", "conflict"] = Field(
        description="connectable: 상품정보에 같은 결과 · 같은 속성의 근거가 있음 / not_connectable: 근거 없음 / "
                    "conflict: 같은 축에서 상품 특성과 정반대")
    product_evidence: str = Field(default="", description="connectable · conflict 일 때 근거 상품정보 문구를 한 글자도 바꾸지 않고 그대로(40자 이내)")
    field: str = Field(default="", description="그 문구가 있는 상품정보 필드 이름")


class FitOutput(BaseModel):
    needs: List[FitNeed]


class LinkVerdict(BaseModel):
    idx: int
    same: bool = Field(description="근거 문구가 니즈와 같은 결과 · 같은 속성을 말하면 true")


class LinkVerdicts(BaseModel):
    verdicts: List[LinkVerdict]


@dataclass
class FitResult:
    status: str
    connectable: List[Dict[str, str]] = field(default_factory=list)
    not_connectable: List[str] = field(default_factory=list)
    conflicts: List[Dict[str, str]] = field(default_factory=list)
    demoted: List[Dict[str, str]] = field(default_factory=list)  # 코드 검증 · 연결 확인에서 내린 항목과 이유
    unknown_fields: List[str] = field(default_factory=list)
    lexical_demoted: List[str] = field(default_factory=list)  # 어휘 겹침으로 내린 고민(동의어일 수 있어 따로 남긴다)
    link_check: str = ""  # V4: ""(끔) · "ok" · "error"
    link_blocked: List[Dict[str, str]] = field(default_factory=list)  # V4: 연결 확인이 내린 연결

    @property
    def risky(self) -> bool:
        """연결 불가 고민이나 충돌 선호가 있는 쌍(평가의 위험군 정의)."""
        return bool(self.not_connectable or self.conflicts)

    @property
    def concern_links(self) -> int:
        return sum(1 for c in self.connectable if c.get("need_type") == "concern")

    def to_dict(self) -> Dict[str, Any]:
        return {"status": self.status, "connectable": self.connectable, "not_connectable": self.not_connectable,
                "conflicts": self.conflicts, "demoted": self.demoted, "unknown_fields": self.unknown_fields,
                "lexical_demoted": self.lexical_demoted, "link_check": self.link_check, "link_blocked": self.link_blocked}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FitResult":
        defaults = {"status": FIT_OK, "link_check": ""}
        return cls(**{k: d.get(k, defaults.get(k, [])) for k in
                      ("status", "connectable", "not_connectable", "conflicts", "demoted", "unknown_fields",
                       "lexical_demoted", "link_check", "link_blocked")})


SYSTEM = """당신은 뷰티 CRM 메시지를 쓰기 전에 고객(페르소나)과 상품을 어디까지 이어도 되는지 정리하는 분석가입니다.
메시지를 쓰지 않습니다. 페르소나의 니즈를 하나씩 needs 목록에 적고, 니즈마다 상태를 하나만 고릅니다.

- 니즈는 페르소나 정보의 고민 · 효과 기대 · 선호 · 구매 기준 · 사용 방식에서 뽑습니다(최대 12개).
  이름 · 나이 · 직업 · 생활 방식 자체는 니즈가 아닙니다.
- 한 니즈는 한 번만 적습니다. 서로 다른 니즈 두 개를 '·' 나 '/' 로 묶지 말고 따로 적습니다. persona_need 는 15자 이내 명사구입니다.
- need_type
  - concern: 피부 · 모발 · 두피 · 몸의 고민, 또는 지속 · 내구 · 차단 · 방지 · 개선처럼 효과를 기대하는 니즈
  - preference: 제형 · 향 · 마무리감 · 흡수 · 사용감 · 용량 · 용기 선호
  - criterion: 구매 기준(무엇을 보고 고르는지)
  - usage: 사용 방식 · 사용 시점 · 사용 단계 · 사용 상황
- status
  - connectable: 상품정보에 그 니즈와 같은 결과 · 같은 속성을 말하는 문구가 있을 때만. 관련 있어 보이는 다른 효과 · 다른 축 ·
    다른 사용 시점의 문구는 근거가 아닙니다.
  - conflict: 선호와 상품 특성이 같은 축에서 정반대일 때(축이 다르면 충돌이 아님)
  - not_connectable: 그 외 전부
- connectable · conflict 이면 product_evidence 에 상품정보 문구를 한 글자도 바꾸지 말고 짧게(40자 이내) 옮기고,
  field 에 그 필드 이름을 적습니다. not_connectable 이면 둘 다 비웁니다.
- usage 는 상품정보에 같은 시점이 있어도 not_connectable 로 둡니다(사용 시점은 메시지에서 상품정보로만 씁니다)."""

LINK_SYSTEM = """당신은 뷰티 상품정보 검수자입니다. 각 '연결'에서 근거 문구가 페르소나 니즈와 같은 결과 · 같은 속성을 말하는지 판정합니다.
- same=true: 표현이 달라도 근거 문구가 니즈와 같은 결과 · 같은 속성을 말한다.
- same=false: 관련은 있지만 다른 효과 · 다른 축(제형 · 마무리감 · 흡수 · 향 · 지속 · 대상) · 다른 사용 시점을 말한다.
  근거 문구가 니즈보다 좁거나, 사용 시점 · 방법만 말하고 니즈의 결과를 말하지 않아도 false 다.
연결 번호(idx)마다 same 을 낸다."""


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


_OVERLAP_STOP = {"케어", "개선", "피부", "제품", "효과", "느낌", "타입", "사용", "없음", "있는"}


def _bigrams(text: str) -> set:
    words = re.sub(r"[^가-힣A-Za-z0-9]", " ", text or "").split()
    return {w[i:i + 2] for w in words for i in range(len(w) - 1)} - _OVERLAP_STOP


def _lexical_overlap(need: str, evidence: str) -> bool:
    """고민과 근거 문구가 두 글자 이상 겹치는지(v3). 선호에는 걸지 않는다."""
    return bool(_bigrams(need) & _bigrams(evidence))


def _trigrams(text: str) -> set:
    s = re.sub(r"[^가-힣A-Za-z0-9]", "", text or "")
    return {s[i:i + 3] for i in range(len(s) - 2)}


def overlap3(a: str, b: str) -> bool:
    """두 문자열이 (공백 · 기호를 빼고) 세 글자 이상 연속으로 겹치는지."""
    return bool(_trigrams(a) & _trigrams(b))


# ── 페르소나 원문 다루기 ─────────────────────────────────────────────────────────

_FREE_KEY = "페르소나 정보"  # 평가용 자유 서술
_VIEW_LABELS = ("이름", "나이", "성별", "직업")
_LIFESTYLE_LABELS = ("라이프스타일",)
_USAGE_LABELS = ("사용 방식", "사용 상황", "사용 시점", "사용방식", "사용상황")
# 운영 구조화 dict(persona_client.py) 키
_DICT_VIEW_KEYS = ("이름", "나이", "성별", "직업")
_DICT_LIFESTYLE_KEYS = ("주 활동 환경", "수면 시간", "스트레스", "스크린 사용")
_DICT_USAGE_KEYS = ("스킨케어 루틴",)


def _free_lines(text: str) -> List[tuple]:
    """"라벨: 값" 줄(줄바꿈 · '|' 구분)을 (라벨, 값) 목록으로."""
    out = []
    for seg in re.split(r"[\n|]", text or ""):
        if ":" in seg:
            k, v = seg.split(":", 1)
            if k.strip():
                out.append((k.strip(), v.strip()))
    return out


def _persona_text(persona_info: Dict[str, Any]) -> str:
    if _FREE_KEY in persona_info:
        return str(persona_info[_FREE_KEY])
    return json.dumps({k: v for k, v in persona_info.items() if k != "persona_id" and v not in (None, "", [], {})},
                      ensure_ascii=False)


def persona_usage_text(persona_info: Optional[Dict[str, Any]]) -> str:
    """페르소나 원문의 사용 방식 · 사용 상황 줄(코드 차단용)."""
    if not persona_info:
        return ""
    if _FREE_KEY in persona_info:
        return " ".join(v for k, v in _free_lines(str(persona_info[_FREE_KEY])) if any(u in k for u in _USAGE_LABELS))
    return " ".join(str(persona_info.get(k) or "") for k in _DICT_USAGE_KEYS)


def build_persona_view(persona_info: Optional[Dict[str, Any]], purpose: str = "") -> Optional[str]:
    """생성 프롬프트에 넣을 페르소나 정보. 이름 · 나이 · 성별 · 직업만(목적 7 은 라이프스타일까지). 처음 보는 라벨은 뺀다."""
    if not persona_info:
        return None
    lifestyle = purpose == LIFESTYLE_PURPOSE
    if _FREE_KEY in persona_info:
        keep = _VIEW_LABELS + (_LIFESTYLE_LABELS if lifestyle else ())
        lines = [f"{k}: {v}" for k, v in _free_lines(str(persona_info[_FREE_KEY])) if k in keep]
        return "\n".join(lines) or None
    keys = _DICT_VIEW_KEYS + (_DICT_LIFESTYLE_KEYS if lifestyle else ())
    lines = [f"{k}: {persona_info[k]}" for k in keys if persona_info.get(k) not in (None, "", [], {})]
    return "\n".join(lines) or None


# ── 검증 ─────────────────────────────────────────────────────────────────────

def verify(raw: FitOutput, product_info: Dict[str, Any], persona_info: Optional[Dict[str, Any]] = None) -> FitResult:
    """LLM 출력을 스냅숏과 대조한다. 지어낸 근거 · 분류가 맞지 않는 근거 · 사용 방식 연결은 not_connectable 로 내린다."""
    info = generation_product_info(product_info)
    field_text = {k: _squash(json.dumps(v, ensure_ascii=False)) for k, v in info.items()}
    all_text = _squash(json.dumps(info, ensure_ascii=False))
    usage_text = persona_usage_text(persona_info)
    res = FitResult(status=FIT_OK)

    def demote(n: FitNeed, reason: str, fld: str = "") -> None:
        res.demoted.append({**n.model_dump(), **({"field": fld} if fld else {}), "reason": reason})
        res.not_connectable.append(n.persona_need)

    for n in raw.needs:
        if n.status == "not_connectable":
            res.not_connectable.append(n.persona_need)
            continue
        ev = _squash(n.product_evidence)
        if n.status == "conflict":
            if ev and ev in all_text:
                res.conflicts.append({"persona_preference": n.persona_need, "product_fact": n.product_evidence,
                                      "field": n.field})
            else:
                res.demoted.append({**n.model_dump(), "reason": "충돌 근거 문구가 상품정보에 없음"})
            continue
        # connectable
        if n.need_type == "usage":
            demote(n, "사용 방식 · 시점 니즈는 연결하지 않음(상품 필드로만 씀)")
            continue
        if usage_text and (overlap3(n.persona_need, usage_text) or overlap3(n.product_evidence, usage_text)):
            demote(n, "페르소나 사용 방식 · 상황 줄과 겹침(코드 차단)")
            continue
        if not ev or ev not in all_text:
            demote(n, "근거 문구가 상품정보에 없음")
            continue
        fld = n.field if ev in field_text.get(n.field, "") else next((k for k, t in field_text.items() if ev in t), n.field)
        cls = field_class(fld)
        if cls is None:
            res.unknown_fields.append(fld)
            cls = "evidence"
        allowed = ("evidence",) if n.need_type == "concern" else ("evidence", "style")
        if cls not in allowed:
            demote(n, f"{n.need_type} 근거로 {cls} 필드는 쓸 수 없음", fld)
            continue
        if n.need_type == "concern" and not _lexical_overlap(n.persona_need, n.product_evidence):
            demote(n, "고민과 근거 문구가 겹치지 않음(어휘)", fld)
            res.lexical_demoted.append(n.persona_need)
            continue
        res.connectable.append({"persona_need": n.persona_need, "need_type": n.need_type,
                                "product_evidence": n.product_evidence, "field": fld})
    # 같은 니즈 정리: 충돌이 있으면 연결 가능에서 빼고(반대 지시 방지), 연결 가능이 남은 니즈는 연결 불가에서 뺀다
    prefs = [_squash(f["persona_preference"]) for f in res.conflicts]
    keep = []
    for c in res.connectable:
        need = _squash(c["persona_need"])
        if need and any(p and (need in p or p in need) for p in prefs):
            res.demoted.append({**c, "reason": "같은 니즈가 충돌에도 있음(모순)"})
        else:
            keep.append(c)
    res.connectable = keep
    kept = {_squash(c["persona_need"]) for c in res.connectable}
    res.not_connectable = list(dict.fromkeys(n for n in res.not_connectable if _squash(n) not in kept))
    if res.unknown_fields:
        logger.warning("persona_fit.unknown_fields", fields=sorted(set(res.unknown_fields)))
    return res


def build_fit_section(fit: FitResult) -> str:
    """생성 프롬프트에 넣는 '페르소나-상품 연결 안내'. 승인된 연결만 넣는다(연결 불가 · 충돌은 넣지 않음, V4)."""
    concerns = [c for c in fit.connectable if c["need_type"] == "concern"]
    others = [c for c in fit.connectable if c["need_type"] != "concern"]
    lines = ["## 페르소나-상품 연결 안내 (생성 전에 상품정보와 대조한 결과)"]
    if not fit.connectable:
        lines.append("- 이 고객과 상품 사이에 확인된 연결이 없다. 고객의 고민 · 피부 타입은 꺼내지 않고 상품정보 중심으로 쓴다.")
        return "\n".join(lines)
    lines.append("- 고민 공감 (공감 표현은 고객의 말로 쓰고, 효과는 따옴표 안 근거 문구 범위로만 말한다):")
    lines += [f"  - 공감 표현: {c['persona_need']} → 말할 수 있는 효과: '{c['product_evidence']}'" for c in concerns] or ["  - (없음)"]
    lines.append("- 선호 · 구매 기준 (사용감 · 특성 묘사로만 쓰고 효능 약속으로 키우지 않는다):")
    lines += [f"  - {'구매 기준' if c['need_type'] == 'criterion' else '선호'}: {c['persona_need']} → 말할 수 있는 특성: "
              f"'{c['product_evidence']}'" for c in others] or ["  - (없음)"]
    return "\n".join(lines)


class PersonaFitter:
    """페르소나 × 상품 연결 계산기. LLM 은 생성자에서 주입한다(레포 CLAUDE.md P9)."""

    def __init__(self, llm: Optional[Any] = None, link_llm: Optional[Any] = None, link_check: Optional[bool] = None):
        self._llm = llm or get_llm(settings.persona_fit_model_name or settings.chatgpt_model_name,
                                   reasoning_effort=settings.persona_fit_reasoning_effort)
        self._structured = self._llm.with_structured_output(FitOutput)
        self._link_check = LINK_CHECK_ENABLED if link_check is None else link_check
        if link_llm is None and LINK_REASONING_EFFORT:
            link_llm = get_llm(settings.persona_fit_model_name or settings.chatgpt_model_name,
                               reasoning_effort=LINK_REASONING_EFFORT)
        self._link = (link_llm or self._llm).with_structured_output(LinkVerdicts) if self._link_check else None

    async def check_links(self, product_info: Dict[str, Any], links: List[Dict[str, str]]) -> List[bool]:
        """연결 묶음을 한 번에 되묻는다. 예외는 호출한 쪽에서 처리한다."""
        if not links:
            return []
        body = "\n".join(f"{i}. 니즈: {c['persona_need']} ← 근거 문구: '{c['product_evidence']}'" for i, c in enumerate(links))
        user = ("[상품정보]\n" + json.dumps(generation_product_info(product_info), ensure_ascii=False, indent=1)
                + "\n\n[연결]\n" + body)
        out = await ainvoke_with_retry(
            self._link, [("system", LINK_SYSTEM), ("human", user)],
            semaphore_key="persona_fit_link", max_concurrency=settings.persona_fit_max_concurrency,
            max_retries=settings.persona_fit_max_retries, backoff_base=settings.persona_fit_backoff_base,
            logger=logger, retry_event="persona_fit_link_retry",
        )
        got = {v.idx: v.same for v in out.verdicts}
        return [bool(got.get(i, False)) for i in range(len(links))]  # 답이 빠진 연결은 내린다

    async def _apply_link_check(self, res: FitResult, product_info: Dict[str, Any]) -> FitResult:
        try:
            same = await self.check_links(product_info, res.connectable)
            res.link_check = "ok"
        except Exception as e:  # noqa: BLE001 — 확인되지 않은 연결은 통과시키지 않는다
            logger.warning("persona_fit.link_check_failed", error_type=type(e).__name__)
            same = [False] * len(res.connectable)
            res.link_check = "error"
        keep = []
        for c, ok in zip(res.connectable, same):
            if ok:
                keep.append(c)
            else:
                blocked = {**c, "reason": "연결 확인: 같은 결과 · 속성 아님" if res.link_check == "ok" else "연결 확인 실패"}
                res.link_blocked.append(blocked)
                res.demoted.append(blocked)
                res.not_connectable.append(c["persona_need"])
        res.connectable = keep
        kept = {_squash(c["persona_need"]) for c in keep}
        res.not_connectable = list(dict.fromkeys(n for n in res.not_connectable if _squash(n) not in kept))
        return res

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
            res = verify(raw, product_info, persona_info)
        except Exception as e:  # noqa: BLE001 — 실패하면 연결 안내 없이(보수적 문구로) 생성한다
            logger.warning("persona_fit.failed", error_type=type(e).__name__)
            return FitResult(status=FIT_FALLBACK)
        if self._link_check and res.connectable:
            res = await self._apply_link_check(res, product_info)
        return res
