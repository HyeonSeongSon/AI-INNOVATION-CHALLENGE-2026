"""
persona_fit 단위 시험 (API 호출 없음) — 코드 검증 규칙과 프롬프트 연결 경로.

    python test_persona_fit.py
"""

import asyncio
import hashlib
import sys

import v2_common  # noqa: F401 — 경로 · bootstrap

from app.agents.generate_message_agent.prompts import persona_fit as pf  # noqa: E402
from app.agents.generate_message_agent.services.generate_crm_message import CrmMessageGenerator  # noqa: E402

SNAP = {
    "product_id": "X1", "product_name": "테스트 크림", "brand": "테스트", "rating": 4.8, "review_count": 10,
    "texture": ["로션처럼 가벼운 제형"], "concern": ["피부 건조"], "key_benefits": ["피부 건조함 완화"],
    "fragrance": "무향", "summary": "가벼운 제형의 보습 크림",
}
PERSONA = {"페르소나 정보": "고민: 건조함, 번들거림\n선호 포인트: 가벼운 제형, 묵직한 코팅감"}


def C(need, typ, ev, fld):  # noqa: N802
    return pf.FitConnectable(persona_need=need, need_type=typ, product_evidence=ev, field=fld)


def run() -> None:
    raw = pf.FitOutput(
        connectable=[
            C("건조함", "concern", "피부 건조함 완화", "key_benefits"),          # 유지
            C("번들거림", "concern", "피지 조절 효과", "key_benefits"),          # 지어낸 근거 → 내림
            C("번들거림", "concern", "로션처럼 가벼운 제형", "texture"),          # concern 에 style 근거 → 내림
            C("가벼운 제형", "preference", "로션처럼 가벼운 제형", "texture"),    # preference 에 style → 유지
            C("가벼운 제형", "preference", "테스트 크림", "product_name"),        # meta → 내림
            C("건조함", "concern", "피부 건조", "summary"),                      # 필드 이름 틀림 → 실제 필드(concern)로 고침
        ],
        not_connectable=["번들거림"],
        conflicts=[pf.FitConflict(persona_preference="묵직한 코팅감", product_fact="로션처럼 가벼운 제형", field="texture"),
                   pf.FitConflict(persona_preference="진한 향", product_fact="강한 플로럴 향", field="fragrance")],  # 없는 문구
    )
    res = pf.verify(raw, SNAP)
    kept = [(c["persona_need"], c["need_type"], c["field"]) for c in res.connectable]
    assert kept == [("건조함", "concern", "key_benefits"), ("가벼운 제형", "preference", "texture"),
                    ("건조함", "concern", "concern")], kept
    assert len(res.demoted) == 4, res.demoted  # 지어낸 근거 · style→concern · meta · 없는 충돌 문구
    assert [c["persona_preference"] for c in res.conflicts] == ["묵직한 코팅감"]
    assert res.risky and res.status == pf.FIT_OK
    sec = pf.build_fit_section(res)
    assert "고민 연결" in sec and "선호 일치" in sec and "연결 불가" in sec and "충돌" in sec, sec
    assert "효능 약속으로 키우지 않는다" in sec
    # 연결 가능 0개 문구
    empty = pf.verify(pf.FitOutput(connectable=[], not_connectable=["번들거림"], conflicts=[]), SNAP)
    assert "공감하는 1문장까지만" in pf.build_fit_section(empty)
    print("verify · build_fit_section: 통과")

    # LLM 오류 → fallback
    class Boom:
        def with_structured_output(self, _):
            return self

        async def ainvoke(self, *_a, **_k):
            raise RuntimeError("boom")

    fitter = pf.PersonaFitter(llm=Boom())
    r = asyncio.run(fitter.fit(PERSONA, SNAP))
    assert r.status == pf.FIT_FALLBACK, r
    assert asyncio.run(fitter.fit(None, SNAP)).status == pf.FIT_DISABLED
    print("오류 시 fallback · 페르소나 없음 disabled: 통과")

    # 구조화(운영) 페르소나도 텍스트로 바뀌는지
    structured = {"persona_id": "P1", "고민 키워드": ["건조"], "선호 제형(텍스처)": ["가벼운"], "피부타입": []}
    t = pf._persona_text(structured)
    assert "건조" in t and "persona_id" not in t and "피부타입" not in t, t
    print("구조화 페르소나 텍스트: 통과")


def v1_prompt_hash() -> str:
    """fitter 를 주입하지 않으면 get_crm_prompt 가 1라운드 v1 과 같은 프롬프트를 그리는지(2단계 시점에만 의미 있음)."""
    gen = CrmMessageGenerator()
    tasks = [{"product_id": "X1", "purpose": p, "product_info": SNAP, "brand_tone": "톤"} for p in gen._purpose_prompt_map]
    out = asyncio.run(gen.get_crm_prompt(tasks, persona_info=PERSONA))
    assert all(t["fit_status"] == pf.FIT_DISABLED for t in out)
    text = "\n".join(m.content for t in out for m in t["prompt"])
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    run()
    print("fitter 없음 프롬프트 해시:", v1_prompt_hash())
