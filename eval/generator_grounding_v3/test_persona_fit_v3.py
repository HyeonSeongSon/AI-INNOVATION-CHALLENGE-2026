"""
persona_fit · 생성 서비스 단위 시험 v3R (API 호출 없음).

    python test_persona_fit_v3.py

v2 시험(eval/generator_grounding_v2/test_persona_fit.py)의 코드 검증 규칙에 더해
- 모순 제거: 연결 가능 ↔ 충돌(v3), 연결 가능 ↔ 연결 불가(v3R ①), 근거만 바꾼 중복 니즈(v3R ②, N032 유형)
- 고민 연결 어휘 겹침 규칙(v3, 유지)과 사람 판정 116건 대조 재현
- 안내 형식(v3R): 근거 문구가 앞, 고민 · 선호 둘 다, 연결 불가는 '꺼내지 않는다'
- SYSTEM: 같은 축 규칙, 니즈는 하나씩
- 저장된 v2 · v3 fit 캐시가 그대로 로드됨
- 생성 서비스: 생성 후 검사 제거(호출 1회, fit_recheck · fit_banned 없음)
"""

import asyncio
import json
import sys

import v3_common as v3  # noqa: F401 — 경로 · bootstrap
from gg_common import load_jsonl

from langchain_core.messages import AIMessage  # noqa: E402
from app.agents.generate_message_agent.prompts import persona_fit as pf  # noqa: E402
from app.agents.generate_message_agent.services.generate_crm_message import CrmMessageGenerator  # noqa: E402

SNAP = {
    "product_id": "X1", "product_name": "테스트 크림", "brand": "테스트", "rating": 4.8, "review_count": 10,
    "texture": ["로션처럼 가벼운 제형"], "concern": ["피부 건조"], "key_benefits": ["피부 건조함 완화"],
    "fragrance": "무향", "summary": "가벼운 제형의 보습 크림",
}


def C(need, typ, ev, fld):  # noqa: N802
    return pf.FitConnectable(persona_need=need, need_type=typ, product_evidence=ev, field=fld)


def verify_rules() -> None:
    raw = pf.FitOutput(
        connectable=[
            C("건조함", "concern", "피부 건조함 완화", "key_benefits"),          # 유지
            C("번들거림", "concern", "피지 조절 효과", "key_benefits"),          # 지어낸 근거 → 내림
            C("번들거림", "concern", "로션처럼 가벼운 제형", "texture"),          # concern 에 style 근거 → 내림
            C("가벼운 제형", "preference", "로션처럼 가벼운 제형", "texture"),    # preference 에 style → 유지
            C("가벼운 제형", "preference", "테스트 크림", "product_name"),        # meta → 내림(같은 니즈가 유지돼 연결 불가에는 안 남김)
            C("건조함", "concern", "피부 건조", "summary"),                      # 필드 이름 틀림 → 실제 필드로 고침
            C("상쾌한 향", "preference", "무향", "fragrance"),                   # 충돌에도 있음 → 모순으로 내림(v3)
            C("메이크업 밀림", "concern", "가벼운 제형의 보습 크림", "summary"),  # 고민-근거 어휘 겹침 없음 → 내림(v3)
        ],
        not_connectable=["번들거림"],
        conflicts=[pf.FitConflict(persona_preference="묵직한 코팅감", product_fact="로션처럼 가벼운 제형", field="texture"),
                   pf.FitConflict(persona_preference="상쾌한 향 선호", product_fact="무향", field="fragrance"),
                   pf.FitConflict(persona_preference="진한 향", product_fact="강한 플로럴 향", field="fragrance")],  # 없는 문구
    )
    res = pf.verify(raw, SNAP)
    kept = [(c["persona_need"], c["need_type"], c["field"]) for c in res.connectable]
    assert kept == [("건조함", "concern", "key_benefits"), ("가벼운 제형", "preference", "texture"),
                    ("건조함", "concern", "concern")], kept
    reasons = [d["reason"] for d in res.demoted]
    assert len(reasons) == 6 and reasons[-1] == "같은 니즈가 충돌에도 있음(모순)", reasons
    assert "고민과 근거 문구가 겹치지 않음(어휘)" in reasons
    assert res.lexical_demoted == ["메이크업 밀림"] and "메이크업 밀림" in res.not_connectable
    assert "가벼운 제형" not in res.not_connectable  # v3R ②: 유지된 니즈의 중복은 연결 불가에 남기지 않는다
    assert pf.FitResult.from_dict(res.to_dict()).lexical_demoted == ["메이크업 밀림"]
    assert [c["persona_preference"] for c in res.conflicts] == ["묵직한 코팅감", "상쾌한 향 선호"]
    assert "상쾌한 향" not in res.not_connectable  # 충돌 모순은 충돌로만 남긴다
    print("verify(어휘 · 충돌 모순 · 중복 니즈): 통과")


def contradiction_not_connectable() -> None:
    # v3R ①: LLM 이 연결 불가로도 낸 니즈는 연결 가능에서 내린다(부분 문자열)
    raw = pf.FitOutput(connectable=[C("윤기 표현", "preference", "로션처럼 가벼운 제형", "texture"),
                                    C("가벼운 제형", "preference", "로션처럼 가벼운 제형", "texture")],
                       not_connectable=["윤기 표현 지속"], conflicts=[])
    res = pf.verify(raw, SNAP)
    assert [c["persona_need"] for c in res.connectable] == ["가벼운 제형"], res.connectable
    assert res.demoted[-1]["reason"] == "같은 니즈가 연결 불가에도 있음(모순)"
    # v3R ②: N032 유형(같은 니즈를 근거만 바꿔 두 번, 하나만 검증 통과) — 연결 안내에 양쪽으로 적히지 않는다
    raw = pf.FitOutput(connectable=[C("윤기 있는 피부 표현", "preference", "테스트 크림", "product_name"),
                                    C("윤기 있는 피부 표현", "preference", "로션처럼 가벼운 제형", "texture")],
                       not_connectable=[], conflicts=[])
    res = pf.verify(raw, SNAP)
    assert [c["persona_need"] for c in res.connectable] == ["윤기 있는 피부 표현"]
    assert "윤기 있는 피부 표현" not in res.not_connectable
    # 저장된 v2 캐시의 실제 N032 는 연결 가능 · 불가 양쪽에 같은 니즈가 있었다(새 규칙의 대상)
    v2c = {r["item_id"]: r for r in load_jsonl(v3.vc.RESULT / "main" / "fit_cache.jsonl")}["N032"]
    assert "윤기 있는 피부 표현" in v2c["not_connectable"] and any(
        c["persona_need"] == "윤기 있는 피부 표현" for c in v2c["connectable"])
    print("연결 가능 ↔ 연결 불가 모순(①) · 중복 니즈(② N032 유형): 통과")


def fit_section() -> None:
    res = pf.verify(pf.FitOutput(connectable=[C("건조함", "concern", "피부 건조함 완화", "key_benefits"),
                                              C("가벼운 제형", "preference", "로션처럼 가벼운 제형", "texture")],
                                 not_connectable=["번들거림"],
                                 conflicts=[pf.FitConflict(persona_preference="묵직한 코팅감",
                                                           product_fact="로션처럼 가벼운 제형", field="texture")]), SNAP)
    sec = pf.build_fit_section(res)
    for k in ("말할 수 있는 효과: '피부 건조함 완화' (관련 고민: 건조함)",
              "말할 수 있는 특성: '로션처럼 가벼운 제형' (관련 선호: 가벼운 제형)",
              "연결 불가 (메시지에서 꺼내지 않는다)", "충돌", "효능 약속으로 키우지 않는다"):
        assert k in sec, (k, sec)
    assert "공감은 해도" not in sec and "→ 근거:" not in sec
    empty = pf.verify(pf.FitOutput(connectable=[], not_connectable=["번들거림"], conflicts=[]), SNAP)
    e = pf.build_fit_section(empty)
    assert "페르소나의 고민은 꺼내지 않고" in e and "장면 묘사로만" in e, e
    assert "같은 축" in pf.SYSTEM and "하나씩 따로 적습니다" in pf.SYSTEM and "니즈는 하나씩 적습니다" in pf.SYSTEM
    print("안내 형식(고민 · 선호 · 연결 불가 · 빈 경우) · SYSTEM(같은 축 · 하나씩): 통과")


def lexical_vs_human() -> None:
    """고민 연결 어휘 겹침 규칙을 사람 판정 116건(2라운드 무관 근거 확인)에 대 본다 — 결정 당시 수치 재현."""
    import csv
    rows = list(csv.DictReader(open(v3.vc.RESULT / "fit_effort" / "irrelevant_check.csv", encoding="utf-8-sig")))
    con = [r for r in rows if r["종류"] == "고민"]
    miss = lambda r: not pf._lexical_overlap(r["페르소나_고민선호"], r["상품정보_근거"])  # noqa: E731
    x_caught = sum(1 for r in con if r["관련(O/X)"] == "X" and miss(r))
    o_dem = sum(1 for r in con if r["관련(O/X)"] == "O" and miss(r))
    n_x, n_o = sum(r["관련(O/X)"] == "X" for r in con), sum(r["관련(O/X)"] == "O" for r in con)
    assert (x_caught, n_x, o_dem, n_o) == (1, 1, 3, 43), (x_caught, n_x, o_dem, n_o)
    print(f"어휘 겹침(고민 연결만, 유지) 대 사람 판정: 무관 {x_caught}/{n_x} 잡음 · 관련 {o_dem}/{n_o} 잘못 내림")


def cache_load() -> None:
    n = 0
    for p in (v3.vc.RESULT / "main" / "fit_cache.jsonl", v3.RESULT / "dev" / "v3" / "fit_cache.jsonl"):
        for r in load_jsonl(p):
            f = pf.FitResult.from_dict(r)
            pf.build_fit_section(f)
            n += 1
    print(f"저장 캐시 로드 · 안내 생성 {n}건: 통과")


class FakeLLM:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    async def ainvoke(self, prompt, *a, **k):
        self.calls.append(prompt)
        return AIMessage(content=self.replies.pop(0))


def no_recheck() -> None:
    gen = CrmMessageGenerator()
    base = {"product_id": "X1", "purpose": "브랜드/제품 첫소개", "prompt": [AIMessage(content="p")]}
    msg = json.dumps({"title": "t", "message": "번들거림이 신경 쓰이나요? 이 크림은 …"}, ensure_ascii=False)
    llm = FakeLLM([msg])
    [out] = asyncio.run(gen.generate_crm_message([base], llm))
    assert len(llm.calls) == 1 and "fit_recheck" not in out and "fit_banned" not in out
    assert not hasattr(pf, "banned_terms") and not hasattr(pf, "banned_hits")
    print("생성 서비스: 생성 후 검사 없음(호출 1회): 통과")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    verify_rules()
    contradiction_not_connectable()
    fit_section()
    lexical_vs_human()
    cache_load()
    no_recheck()
