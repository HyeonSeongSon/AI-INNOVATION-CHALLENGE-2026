"""
V4 단위 시험(API 호출 없음).

    python test_v4.py
"""

import asyncio
import re
import sys

import v4_common as c
from langchain_core.messages import AIMessage

from app.agents.generate_message_agent.prompts import persona_fit as pf
from app.agents.generate_message_agent.prompts.purpose_prompt import PurPosePrompts
from app.agents.generate_message_agent.services import claim_check as cc
from app.agents.generate_message_agent.services import generate_crm_message as gcm

FAILS: list[str] = []


def check(cond: bool, name: str) -> None:
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


class FakeStructured:
    def __init__(self, out=None, exc=None):
        self.out, self.exc = out, exc

    async def ainvoke(self, *_a, **_k):
        if self.exc:
            raise self.exc
        return self.out


class FakeLLM:
    def __init__(self, fit_out=None, link_out=None, link_exc=None, gen=None):
        self.fit_out, self.link_out, self.link_exc, self.gen = fit_out, link_out, link_exc, gen or []

    def with_structured_output(self, schema):
        if schema is pf.FitOutput:
            return FakeStructured(self.fit_out)
        return FakeStructured(self.link_out, self.link_exc)

    async def ainvoke(self, *_a, **_k):
        return AIMessage(content=self.gen.pop(0))


def sample():
    msgs, _ = c.stored("v3r_N")
    return msgs


def test_single_list() -> None:
    msgs = sample()
    m = msgs["N029"]
    ev = "미세한 거품이 피부 노폐물과 피지를 부드럽게 제거합니다."
    N = pf.FitNeed
    raw = pf.FitOutput(needs=[
        N(persona_need="세정력 확실", need_type="preference", status="connectable", product_evidence=ev, field="key_benefits"),
        N(persona_need="세정력 확실", need_type="preference", status="not_connectable"),
        N(persona_need="풍성한 거품", need_type="preference", status="conflict", product_evidence="미세한 거품", field="texture"),
        N(persona_need="풍성한 거품", need_type="preference", status="connectable", product_evidence="미세한 거품", field="texture"),
        N(persona_need="블랙헤드", need_type="concern", status="not_connectable"),
    ])
    r = pf.verify(raw, m["product_snapshot"], m["persona_info"])
    needs = [x["persona_need"] for x in r.connectable]
    check(needs == ["세정력 확실"], "같은 니즈: 연결 가능이 남으면 연결 불가에서 뺀다 · 충돌이면 연결 가능에서 뺀다")
    check("세정력 확실" not in r.not_connectable and "블랙헤드" in r.not_connectable, "연결 불가 목록 정리")
    check([x["persona_preference"] for x in r.conflicts] == ["풍성한 거품"], "충돌 유지")
    d = pf.FitResult.from_dict(r.to_dict())
    check(d.to_dict() == r.to_dict(), "to_dict / from_dict 왕복")
    old = c.load_jsonl(c.V3_RESULT / "dev" / "v3r" / "fit_cache.jsonl")[0]
    check(pf.FitResult.from_dict(old).link_check == "", "저장된 v3R 캐시(세 목록 형식) 호환")


def test_usage_block() -> None:
    msgs = sample()
    m = msgs["N014"]  # 사용 방식: 드라이 전 젖은 모발에 사용
    N = pf.FitNeed
    raw = pf.FitOutput(needs=[
        N(persona_need="젖은 모발 사용", need_type="usage", status="connectable", product_evidence="리브인 세럼 제형", field="attribute"),
        N(persona_need="젖은 모발 케어", need_type="preference", status="connectable", product_evidence="리브인 세럼 제형", field="attribute"),
        N(persona_need="가벼운 세럼 타입", need_type="preference", status="connectable", product_evidence="리브인 세럼 제형", field="attribute"),
    ])
    r = pf.verify(raw, m["product_snapshot"], m["persona_info"])
    check([x["persona_need"] for x in r.connectable] == ["가벼운 세럼 타입"], "usage 차단 + 사용 방식 줄 겹침 차단(LLM 분류와 무관)")


def test_persona_view() -> None:
    seen, bad = set(), []
    for key in c.STORED:
        msgs, _ = c.stored(key)
        for m in msgs.values():
            pid = m["persona_id"]
            if pid in seen:
                continue
            seen.add(pid)
            for purpose in ("베스트셀러 제품 소개", pf.LIFESTYLE_PURPOSE):
                v = pf.build_persona_view(m["persona_info"], purpose) or ""
                labels = {ln.split(":", 1)[0] for ln in v.splitlines()}
                allowed = {"이름", "나이", "성별", "직업"} | ({"라이프스타일"} if purpose == pf.LIFESTYLE_PURPOSE else set())
                if not labels <= allowed or "이름" not in labels:
                    bad.append((pid, purpose, labels))
                if re.search(r"고민|피부 타입|사용 방식|구매 기준|니즈", v):
                    bad.append((pid, purpose, "금지 라벨 문자열"))
    check(len(seen) >= 50 and not bad, f"평가 페르소나 {len(seen)}명 전원 이름 · 나이 · 성별 · 직업만(목적 7 은 라이프스타일까지) {bad[:2]}")
    d = {"persona_id": "P", "이름": "가", "나이": 30, "성별": "여", "직업": "직장인", "피부타입": ["건성"], "고민 키워드": ["건조"],
         "스킨케어 루틴": ["세안 후 토너"], "주 활동 환경": ["사무실"], "구매 결정 요인": ["리뷰"]}
    v = pf.build_persona_view(d, "브랜드/제품 첫소개")
    v7 = pf.build_persona_view(d, pf.LIFESTYLE_PURPOSE)
    check(v == "이름: 가\n나이: 30\n성별: 여\n직업: 직장인" and "주 활동 환경" in v7 and "건조" not in v7, "운영 dict 거르기")
    check(pf.persona_usage_text(d) == "['세안 후 토너']" or "세안 후 토너" in pf.persona_usage_text(d), "운영 dict 사용 방식 줄")


def test_fit_section() -> None:
    f = pf.FitResult(status="ok", connectable=[{"persona_need": "입술 건조", "need_type": "concern", "product_evidence": "보습", "field": "function"}],
                     not_connectable=["블랙헤드"], conflicts=[{"persona_preference": "묵직한 제형", "product_fact": "가벼운 제형", "field": "texture"}])
    s = pf.build_fit_section(f)
    check("블랙헤드" not in s and "묵직한" not in s and "입술 건조" in s, "연결 안내에 연결 불가 · 충돌 문구 없음")
    msgs = sample()
    m = msgs["N029"]
    pp = PurPosePrompts()
    for builder in ("build_purpose_bestseller_prompt", "build_purpose_skintype_and_concern_point_prompt"):
        pr = getattr(pp, builder)(m["product_snapshot"], "톤", persona_info=pf.build_persona_view(m["persona_info"]), fit_section=s)
        text = "\n".join(x.content for x in pr)
        check("블랙헤드" not in text and "메이크업 잔여물" not in text, f"{builder} 프롬프트에 원문 고민 없음")


def test_claim_check() -> None:
    msgs = sample()
    m = msgs["N029"]
    prod = m["product_snapshot"]
    hits = cc.detect("하루 종일 촉촉", "세안 후 당김 없이 촉촉하게", prod, None, categories=("A",))
    check([h["text"] for h in hits] == ["하루 종일"], "A: 상품정보에 없는 표현만 걸림")
    f_none = pf.FitResult(status="ok", connectable=[], not_connectable=["블랙헤드 고민"])
    f_one = pf.FitResult(status="ok", connectable=[{"persona_need": "x", "need_type": "concern", "product_evidence": "y", "field": "z"}])
    msg = "촬영이 잦아 모공이 걱정될 때 써 보세요."
    check(any(h["cat"] == "B" for h in cc.detect("", msg, prod, f_none, categories=("B",))), "B: 승인 고민 0 + 공감 호출 → 걸림")
    check(not cc.detect("", msg, prod, f_one, categories=("B",)), "B: 승인 고민이 있으면 걸지 않음")
    check(not cc.detect("", "세안 후 당김이 걱정될 때", prod, f_none, categories=("B",)), "B: 고민어가 상품 고민 필드와 겹치면 면제")
    check(any(h["cat"] == "C" for h in cc.detect("", "블랙헤드 고민 끝", prod, f_none, categories=("C",))), "C: 연결 불가 니즈 재등장")
    check(any(h["cat"] == "D" for h in cc.detect("", "샤워 전에 바르세요", prod, None, categories=("D",))), "D: 상품 사용 필드에 없는 시점")
    check(not cc.detect("", "외출 후 세안에 쓰세요", prod, None, categories=("D",)), "D: 상품 사용 필드에 같은 단계 · 시점이 있으면 통과")
    check(cc.ENABLED_CATEGORIES == frozenset({"A"}), "켜진 점검 범주는 단계 1 결과대로 A 만")


def test_failure_paths() -> None:
    msgs = sample()
    m = msgs["N029"]
    ev = "미세한 거품이 피부 노폐물과 피지를 부드럽게 제거합니다."
    raw = pf.FitOutput(needs=[pf.FitNeed(persona_need="세정력 확실", need_type="preference", status="connectable",
                                         product_evidence=ev, field="key_benefits")])
    fitter = pf.PersonaFitter(llm=FakeLLM(fit_out=raw, link_exc=RuntimeError("down")), link_check=True)
    r = asyncio.run(fitter.fit(m["persona_info"], m["product_snapshot"]))
    check(r.status == "ok" and not r.connectable and r.link_check == "error" and "세정력 확실" in r.not_connectable,
          "연결 확인 실패 → 확인 안 된 연결은 내림")
    fitter2 = pf.PersonaFitter(llm=FakeLLM(fit_out=raw, link_out=pf.LinkVerdicts(verdicts=[pf.LinkVerdict(idx=0, same=True)])), link_check=True)
    r2 = asyncio.run(fitter2.fit(m["persona_info"], m["product_snapshot"]))
    check([x["persona_need"] for x in r2.connectable] == ["세정력 확실"] and r2.link_check == "ok", "연결 확인 통과 → 유지")

    gen = gcm.CrmMessageGenerator.__new__(gcm.CrmMessageGenerator)
    task = {"product_id": "x", "purpose": "베스트셀러 제품 소개", "product_info": m["product_snapshot"], "prompt": ["p"], "fit": None}
    old_en, old_detect = cc.ENABLED_CATEGORIES, cc.detect
    try:
        cc.ENABLED_CATEGORIES = frozenset({"A"})
        cc.detect = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        out = asyncio.run(gen.generate_crm_message([task], FakeLLM(gen=['{"title":"t","message":"m"}'])))
        check(len(out) == 1 and out[0]["claim_check"] == "error" and out[0]["message"].content.startswith("{"),
              "점검 예외 → 첫 결과 사용 + error 기록")
        cc.detect = old_detect
        out2 = asyncio.run(gen.generate_crm_message(
            [task], FakeLLM(gen=['{"title":"하루 종일 촉촉","message":"m"}', '{"title":"촉촉","message":"m"}'])))
        check(out2[0]["claim_check"] == "regenerated" and "하루 종일" not in out2[0]["message"].content, "걸리면 1회 재생성")
    finally:
        cc.ENABLED_CATEGORIES, cc.detect = old_en, old_detect


def test_state_whitelist() -> None:
    src = (c.gg.REPO / "backend" / "app" / "agents" / "generate_message_agent" / "nodes.py").read_text(encoding="utf-8")
    block = src[src.index("generated_tasks = ["):src.index("]", src.index("for t in tasks", src.index("generated_tasks = [")))]
    keys = set(re.findall(r'"(\w+)":', block))
    check(keys == {"product_id", "product_name", "brand", "sub_tag", "purpose", "message"},
          f"state 로 가는 generated_tasks 필드에 fit · 점검 상세 없음 {sorted(keys)}")


def test_reserved() -> None:
    rid = next(iter(c.reserved_ids()))
    try:
        c.assert_not_reserved([rid])
        check(False, "예약 상품이 섞이면 중단")
    except SystemExit:
        check(True, "예약 상품이 섞이면 중단")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    for t in (test_single_list, test_usage_block, test_persona_view, test_fit_section, test_claim_check, test_failure_paths,
              test_state_whitelist, test_reserved):
        t()
    print(f"\n실패 {len(FAILS)}건" if FAILS else "\n전부 통과")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
