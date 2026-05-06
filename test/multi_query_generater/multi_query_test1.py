"""
build_slot_based_generate_prompt 병렬 테스트

각 상품 카테고리에 대해 async 병렬로 LLM 호출하고
LangSmith로 토큰 사용량을 추적합니다.
"""
import sys
import os
import asyncio
import json
from pathlib import Path

# ── 환경변수 로드 (.env) ─────────────────────────────────────
from dotenv import load_dotenv

dotenv_path = Path(__file__).parent.parent.parent / "backend" / "app" / ".env"
load_dotenv(dotenv_path, override=True)

# ── 프로젝트 루트를 sys.path에 추가 ────────────────────────────
PROJECT_ROOT = str(Path(__file__).parent.parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ── LangSmith 상태 출력 (트레이싱 활성화 여부 확인) ─────────────
tracing_on = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
project_name = os.getenv("LANGCHAIN_PROJECT", "default")
print(f"[LangSmith] tracing={'ON' if tracing_on else 'OFF'}, project={project_name}")

from backend.app.agents.crm_agent.prompts.slot_keywords_generate_prompt import get_prompt_by_category_type
from backend.app.core.llm_factory import get_llm

# ── LLM 인스턴스 ────────────────────────────────────────────
_llm = get_llm("gpt-4o-mini", temperature=0.7)

# ── 페르소나 정보 ────────────────────────────────────────────
persona_info = """{"multi_level_analysis": {"basic_profile": {"inferred_lifestyle": "21세 여대생으로 하루 활동이 야외/이동 중심인 활동적인 학생 라이프. 뷰티에는 트렌드 민감하고 프리미엄 제품에 투자하는 성향으로, 미니멀 올인원 루틴을 선호하여 제품 수는 적지만 하나당 기대 효과가 높음. 반려동물과 함께 생활해 알레르기·안전성에도 민감하며 친환경 가치를 중요시함.", "key_characteristics": ["건조하면서도 트러블이 나는 '악건성+트러블성'의 혼합형 피부", "미니멀·올인원 루틴 선호 + 고급 제품에 대한 지출 의향", "친환경·무첨가 지향 + 향(머스크) 등 감성적 요소 중요"]}, "lifestyle_pattern": {"environmental_factors": ["야외 활동과 이동이 잦아 자외선, 대기오염, 마찰(마스크·모자 등) 노출 증가", "반려동물로 인한 미세먼지·털·알레르겐 접촉 가능성", "기온·습도 변화에 따른 피부 건조 심화"], "daily_routine_features": "미니멀 루틴을 선호해 제품 사용 단계가 적고 하나로 여러 기능을 해결하는 제품을 선택. 이동이 잦아 휴대성이 좋고 빠르게 흡수되는 제품을 선호하나, 텍스처는 꾸덕·영양감을 좋아함. 스트레스가 높아 장기적으로 피부 장벽 저하 및 염증성 트러블 악화 가능성이 있음."}, "beauty_needs": {"core_skincare_needs": ["손상된 피부장벽 회복(세라마이드, 지질보충)", "강력한 보습(히알루론산, 오일·에몰리언트)으로 악건성 개선", "저자극으로 블랙헤드·트러블 관리(저농도 BHA, 티트리 국소 적용)", "다크서클·잡티 개선을 위한 브라이트닝(알부틴, 비타민 유사 성분, 광보호)", "외부 자극(자외선/오염)으로부터 보호하는 항산화·자외선 차단"], "makeup_needs": ["보습감 있는 비비/쿠션류: 21호 베이스에 맞는 뉴트럴 톤 표현", "다크서클 커버용 컨실러(얇게 발리면서도 밀착되는 포뮬러)", "브라운 계열 색조 중심의 자연스러운 음영 메이크업", "논코메도제닉·실리콘 프리 또는 저실리콘 제품 선호"], "latent_needs": ["멀티·올인원 제품의 성능(보습+진정+톤업+자외선차단을 하나로)", "친환경·리필 가능한 고급 패키지 (프리미엄 + 친환경)", "반려동물 안전성(특정 에센셜오일 회피)과 저자극 보장", "즉각적인 가시적 변화(수분감·광채)와 장기 개선(잡티·다크서클 감소)를 동시에 느끼고 싶음", "머스크 향을 자연유래 또는 저자극 방식으로 구현한 제품"], "priority_top3": ["피부 장벽 강화 및 고농축 보습", "블랙헤드·트러블(모공관리)과 건조의 균형 유지", "잡티·다크서클 개선을 위한 저자극 브라이트닝 + 자외선 차단"]}, "situational_needs": {"routine_requirements": {"morning": "가벼운 세안 → 수분부스터(세럼/앰플) 또는 올인원 크림 → SPF 물리·무실리콘 제형 권장 → 가벼운 쿠션/비비로 톤 보정. 이동이 잦아 미스트/쿠션팩트처럼 빠르게 덧바를 수 있는 포맷 필요.", "evening": "부드러운 클렌징(오일·크림 타입으로 메이크업·피부 보습 유지) → 저자극 결합 세럼(세라마이드·히알루론산) → 영양감 있는 크림/밤으로 장벽 강화 → 필요 시 국소 티트리(스팟)·저농도 BHA 주 1~2회"}, "special_requirements": ["이동·야외 활동 대비 휴대용 SPF/미스트(무실리콘·무색소)", "트러블 급증 시 사용할 수 있는 즉효성 스팟 패치·스팟 세럼", "펫과 함께하는 환경에서 안전한 성분 표기(피부·호흡기 자극 낮은 포뮬러)"]}, "improvement_goals": {"short_term": ["즉각적 수분 보충과 장벽 보호(7~14일 내 건조감 완화)", "블랙헤드·트러블 급증 억제(저자극 각질 관리로 모공 정리)", "자극을 줄여 염증 빈도 감소"], "mid_term": ["3~6개월 내 잡티(색소 침착) 완화 및 피부 톤 정돈", "지속적인 장벽 개선으로 피부 민감도 저하", "눈 밑 다크서클 완화(보습·충전·혈류 개선 보조 제품 활용)"], "value_direction": "친환경·클린뷰티를 기반으로 한 '효능 중심의 미니멀 프리미엄'을 추구 — 성분 안전성, 투명한 라벨링, 지속 가능한 패키지, 동물실험 배제 등이 핵심 가치."}}, "multi_dimensional_analysis": {"skin_science": {"skin_type_compatibility": "악건성+트러블성 혼합형으로 보습과 장벽 회복이 최우선이지만 모공·필링 관리도 필요한 복합적 타입에 적합한 포뮬레이션 필요.", "problem_solving_mechanism": ["장벽 복구: 외부 자극 차단 및 지질층 보충으로 트러블 민감도 저하", "수분 유지: 고·중량 히알루론산과 보습 오일의 3단계 수분 전략", "선택적 각질 용해(모공 관리): 저농도 BHA로 과각질·블랙헤드 개선", "항염·항마이크로비얼: 티트리(또는 안심된 항균 성분)로 국소 트러블 완화", "멜라닌 억제/브라이트닝: 알부틴/아젤라익산/나이아신아마이드로 잡티·색소 개선"], "required_functional_ingredients": ["세라마이드(장벽복구)", "히알루론산/글리세린(수분공급)", "스쿠알란·식물성 오일(영양·보습)", "저농도 살리실산(BHA, 블랙헤드/모공 관리)", "알부틴(브라이트닝)", "아젤라익애씨드/나이아신아마이드(잡티·항염)", "센텔라(시카, 진정)", "티트리(스팟, 저농도)", "펩타이드·콜라겐(피부 탄력/충전 보조)", "광범위 물리적 자외선차단제(티타늄·징크)"]}, "ingredients": {"preferred_match": ["알부틴 → 잡티·과색소에 직접적 작용, 나이아신아마이드와 병용 시 톤업 시너지", "콜라겐(하이드롤라이즈드)·펩타이드 → 표면 탄력·수분감 보강 (즉각적 충전감)", "티트리 → 국소 항균·항염(스팟에 유효)", "세라마이드 → 필수 장벽복구 성분, 악건성 핵심", "시카(센텔라) → 진정·손상회복 촉진"], "avoid_strategy": ["실리콘 회피: 실리콘 감촉을 대신할 에스터류·식물성 오일·스쿠알란 기반 포뮬러 추천", "인공색소 회피: 무색소·미백 성분으로 톤 보정(알부틴, 광확산 펄 프리) 활용", "합성방부제 우려: 저자극·효과적인 보존체계(에어리스 패키지, 소량 포장, 미생물 안전 검증 제품) 권장; 천연계 보존제만 의존하지 않고 안전성 표기가 된 조합 선택"], "effective_combination": ["세라마이드 + 히알루론산 + 스쿠알란: 기본 보습·장벽 복구의 3중 효과", "저농도 살리실산(BHA) 주 1~2회 + 세라마이드 집중 보습: 블랙헤드 제거 후 장벽 보호", "알부틴 + 나이아신아마이드(저자극 배합): 잡티 개선과 톤 균일화", "센텔라 + 피토스테롤류: 진정과 항염 시너지 (티트리의 국소 사용 보조)", "펩타이드/콜라겐 + 보습 제형: 눈가·건조 부위 충전감 증대"]}, "lifestyle": {"routine_fit": {"morning": "스킨케어 단계를 최소화하면서도 보습·자외선차단 기능을 갖춘 '세럼-크림-무실리콘 SPF' 또는 올인원 쿠션 타입 권장", "evening": "클렌징과 한 단계의 고보습 밤(오일/밤 타입) 혹은 세럼-영양크림 조합으로 간단하지만 집중 보습"}, "environment_fit": "야외 활동이 잦아 자외선·오염 방어가 필수. 이동 중 덧바르기 쉬운 포맷(미스트, 쿠션 리필, 스틱형)과 내구성 있는 포장 필요.", "usage_convenience": "미니멀 루틴에 맞춘 다기능 제품과 소용량·에어리스 패키지로 위생성·휴대성 확보. 꾸덕한 제형을 선호하므로 밤·리치 크림의 사용감은 만족도가 높음."}, "values_emotion": {"value_match": ["친환경(리필·재활용 패키지)", "클린·무첨가(인공색소·불필요 합성물 최소화)", "프리미엄 경험(고급스러운 텍스처·향개선)"], "brand_philosophy_preference": "성분의 투명성, 지속 가능한 패키징, 동물실험 반대, 안전성 데이터(저자극·피부과 테스트)를 명확히 제시하는 브랜드에 호감.", "emotional_satisfaction": ["꾸덕하고 영양감 있는 텍스처에서 오는 안도감", "머스크 계열의 고급스러운 향(저자극·자연유래 표기가 선호)", "눈에 보이는 빠른 개선(수분광채·모공 개선)으로 인한 만족"]}, "color_makeup": {"personal_color_match": "뉴트럴톤 퍼스널 컬러로 웜·쿨 중간 색조가 조화되어 브라운 계열이 자연스럽고 안정적으로 어울림.", "base_shade": "21호 (밝은 중간톤, 노란기 조금 섞인 뉴트럴)", "preferred_colors_textures": ["아이섀도우: 웜 브라운, 토프, 소프트 모브", "립: 누드 브라운·코랄 브라운", "피부 표현: 촉촉한 세미-드루(데워) 피니시, 광채가 도는 쿠션/비비 질감 선호", "텍스처: 크리미하고 밀착되는 포뮬러(꾸덕한 보습감)"]}, "price_value": {"budget_range": "프리미엄 (~중고가 이상). 가격보다 성분·효능·브랜드 가치(친환경 등)를 우선시함.", "purchase_decision_factors": ["신상/트렌드(새로운 포뮬러에 대한 관심)", "성분 안전성·효능(임상 데이터 또는 성분 근거)", "패키지·브랜드의 친환경성 및 감성(향·텍스처)", "리뷰·인플루언서·전문가 추천"], "value_priority": "효능(가시적 개선)과 성분 안전성·친환경 가치를 높은 우선순위로 둠. 가격은 수단."}, "usability": {"preferred_formulation": ["리치 크림/밤(고보습)", "세럼-크림 하이브리드(영양+흡수 균형)", "오일/클렌징 밤(메이크업 제거 시 장벽 손상 최소화)", "스틱·쿠션·미스트 등 휴대용 포맷"], "portability_convenience": "야외 이동이 잦으므로 누수 없는 컴팩트한 패키지와 소용량 리필이 중요. 에어리스 펌프는 위생·보존성 측면에서 적합.", "application_absorption": "꾸덕한 제형을 선호하나 빠르게 흡수되어 끈적임이 적은 '영양감 있으나 밀착되는' 흡수 프로파일이 이상적."}, "safety_risk": {"sensitivity_considerations": ["악건성으로 인한 장벽 손상으로 자극에 취약(강한 각질제거·고농도 레티노이드 주의)", "트러블성 소견으로 무거운 오일·코메도제닉 성분 사용 시 여드름 악화 위험", "향(머스크)이나 천연 에센셜 오일이 자극 유발 가능성"], "pet_safety": "반려동물(강아지/고양이) 동거로서 주의 필요: 티트리(멜라레우카)와 일부 에센셜 오일은 반려동물에 독성이 있을 수 있으므로 고농도 원액 사용 금지. 제품 선택 시 '펫-세이프' 표기 또는 저농도·안전성 검증된 성분 우선.", "allergy_irritation_risks": ["머스크 향(특히 합성 머스크)은 알레르기·접촉성 피부염 유발 가능성 — 저자극·무향 옵션도 필요", "천연 유래 보존제/향료도 민감인에게 자극 가능 — 패치 테스트 권장", "살리실산·아하·레티노이드 등 각질제거 성분은 건조 피부에 과용 시 자극 초래"]}}}"""

# ── 테스트 대상 카테고리 ─────────────────────────────────────
test_product_categories = [
    ["클렌징 폼","스킨케어"], ["스킨 토너","스킨케어"], ["립스틱","색조"], 
    ["파운데이션","색조"], ["샴푸","헤어"], ["향수","향수/바디"], 
    ["네일컬러","네일"], ["얼굴브러쉬", "뷰티 툴"], ["이너뷰티", "이너뷰티"],
    ["혀클러너", "기타"]
]

async def run_single(persona_info, category_type, category, _llm) -> dict:
    """카테고리 하나에 대해 슬롯 기반 쿼리 생성 (LangSmith 자동 추적)"""
    prompt = get_prompt_by_category_type(category_type, persona_info, category)
    response = await _llm.ainvoke(prompt)

    # 토큰 사용량 추출 (LangChain AIMessage.usage_metadata)
    usage = getattr(response, "usage_metadata", None)
    tokens = {
        "input": usage.get("input_tokens", "?") if usage else "?",
        "output": usage.get("output_tokens", "?") if usage else "?",
        "total": usage.get("total_tokens", "?") if usage else "?",
    }

    return {
        "category": category,
        "content": response.content,
        "tokens": tokens,
    }


async def main():
    print(f"\n총 {len(test_product_categories)}개 카테고리 병렬 처리 시작...\n")

    tasks = [run_single(persona_info, cat[1], cat[0], _llm) for cat in test_product_categories]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    total_input = 0
    total_output = 0

    for r in results:
        if isinstance(r, Exception):
            print(f"[ERROR] {r}")
            continue

        print("=" * 70)
        print(f"[카테고리] {r['category']}")
        tok = r["tokens"]
        print(f"[토큰] input={tok['input']}, output={tok['output']}, total={tok['total']}")
        print()
        print(r["content"])
        print()

        if isinstance(tok["input"], int):
            total_input += tok["input"]
        if isinstance(tok["output"], int):
            total_output += tok["output"]

    print("=" * 70)
    print(f"[합계] input={total_input}, output={total_output}, total={total_input + total_output}")
    if tracing_on:
        print(f"[LangSmith] 결과 확인: https://smith.langchain.com/  (project: {project_name})")


if __name__ == "__main__":
    asyncio.run(main())
