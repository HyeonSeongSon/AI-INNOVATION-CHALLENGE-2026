"""
고객 페르소나 정의
"""

PERSONAS = {
    "premium_antiaging_40s": {
        "id": "premium_antiaging_40s",
        "name": "프리미엄 안티에이징 추구자",
        "description": """
        연령: 40-50대
        소득: 상위 20%
        직업: 전문직, 경영진

        뷰티 특성:
        - 주요 고민: 주름, 탄력 저하, 피부 노화
        - 구매 패턴: 고가 라인 선호, 세트 구매, 백화점/공식몰
        - 의사결정: 효능 중심, 성분 분석, 브랜드 신뢰도

        라이프스타일:
        - 자기관리에 투자하는 시간과 비용
        - 프리미엄 경험 추구
        - SNS보다 입소문/전문가 추천 신뢰

        선호 톤: 우아하고 격조있는 표현, 효능과 과학적 근거 강조
        감성 키워드: 여유, 품격, 지혜, 투자, 근본
        """,
        "metadata": {
            "age_group": "40-50대",
            "income_level": "high",
            "skin_concerns": ["주름", "탄력 저하", "피부 노화"],
            "preferred_brands": ["설화수", "헤라", "후"],
            "decision_factors": ["효능", "성분", "브랜드 신뢰도"],
            "tone": "elegant_professional",
            "keywords": ["여유", "품격", "지혜", "투자", "근본"]
        }
    },

    "trendy_beauty_20s": {
        "id": "trendy_beauty_20s",
        "name": "트렌디 뷰티 얼리어답터",
        "description": """
        연령: 20-30대
        소득: 중상위
        직업: 직장인, 대학생

        뷰티 특성:
        - 주요 관심: SNS 트렌드, 신제품, 컬러 메이크업
        - 구매 패턴: 소량 다품목, 시즌 한정 선호, 모바일 구매
        - 의사결정: 비주얼, 후기, 인플루언서 추천

        라이프스타일:
        - 인스타그램/틱톡 활발
        - 새로운 것 시도 좋아함
        - YOLO 소비 성향

        선호 톤: 발랄하고 트렌디한 표현, 감성과 비주얼 중심
        감성 키워드: 지금, 핫한, 요즘, 득템, 완판
        """,
        "metadata": {
            "age_group": "20-30대",
            "income_level": "mid_high",
            "interests": ["SNS 트렌드", "신제품", "컬러 메이크업"],
            "preferred_brands": ["에스쁘아", "에뛰드", "마몽드"],
            "decision_factors": ["비주얼", "후기", "인플루언서"],
            "tone": "trendy_energetic",
            "keywords": ["지금", "핫한", "요즘", "득템", "완판"]
        }
    },

    "value_seeker_30s": {
        "id": "value_seeker_30s",
        "name": "합리적 가성비 추구자",
        "description": """
        연령: 30-40대
        소득: 중위
        직업: 직장인, 주부

        뷰티 특성:
        - 주요 관심: 프로모션, 세트 상품, 대용량
        - 구매 패턴: 리뷰 꼼꼼히 확인, 가격 비교, 기획세트
        - 의사결정: 가성비, 실용성, 사회적 증거

        라이프스타일:
        - 알뜰한 소비 습관
        - 쿠폰/적립금 적극 활용
        - 커뮤니티 정보 공유

        선호 톤: 실용적이고 구체적인 표현, 혜택과 절약 강조
        감성 키워드: 할인, 득템, 가성비, 혜택, 실속
        """,
        "metadata": {
            "age_group": "30-40대",
            "income_level": "mid",
            "interests": ["프로모션", "세트 상품", "대용량"],
            "preferred_brands": ["브랜드 무관"],
            "decision_factors": ["가성비", "실용성", "리뷰"],
            "tone": "practical_specific",
            "keywords": ["할인", "득템", "가성비", "혜택", "실속"]
        }
    },

    "sensitive_skin_care": {
        "id": "sensitive_skin_care",
        "name": "민감성 피부 케어 집중자",
        "description": """
        연령: 전 연령대
        피부 타입: 민감성, 아토피, 건조함

        뷰티 특성:
        - 주요 관심: 성분, 저자극, 피부과 추천
        - 구매 패턴: 성분 분석, 샘플 테스트, 신중한 구매
        - 의사결정: 안전성, 저자극, 전문가 의견

        라이프스타일:
        - 피부 고민으로 스트레스
        - 정보 탐색 많이 함
        - 장기적 관점의 피부 관리

        선호 톤: 신뢰감 있고 전문적인 표현, 안심과 안전 강조
        감성 키워드: 순한, 저자극, 안심, 전문가, 테스트 완료
        """,
        "metadata": {
            "age_group": "전연령",
            "skin_type": ["민감성", "건조성", "아토피"],
            "interests": ["성분", "저자극", "피부과 추천"],
            "preferred_brands": ["일리윤", "아모레퍼시픽", "라보에이치"],
            "decision_factors": ["안전성", "저자극", "전문가 의견"],
            "tone": "trustworthy_professional",
            "keywords": ["순한", "저자극", "안심", "전문가", "테스트완료"]
        }
    },

    "busy_working_mom": {
        "id": "busy_working_mom",
        "name": "바쁜 워킹맘 실속파",
        "description": """
        연령: 30-40대
        직업: 직장인 + 육아
        특징: 시간 부족, 멀티태스킹

        뷰티 특성:
        - 주요 관심: 빠른 효과, 간편한 루틴, 시간 절약
        - 구매 패턴: 정기 구독, 대용량, 한 번에 구매
        - 의사결정: 편리함, 효율성, 시간 대비 효과

        라이프스타일:
        - 아침 루틴 5분 이내
        - 밤늦게 퇴근 후 육아
        - 나를 위한 시간 부족

        선호 톤: 공감형, 친근한 표현, 편리함과 시간 절약 강조
        감성 키워드: 간편, 5분, 올인원, 바쁜, 시간절약
        """,
        "metadata": {
            "age_group": "30-40대",
            "lifestyle": ["시간부족", "멀티태스킹", "육아"],
            "interests": ["올인원", "빠른효과", "간편루틴"],
            "preferred_brands": ["라네즈", "아이오페"],
            "decision_factors": ["편리함", "효율성", "시간절약"],
            "tone": "empathetic_friendly",
            "keywords": ["간편", "5분", "올인원", "바쁜", "시간절약"]
        }
    }
}


def get_persona(persona_id: str) -> dict:
    """페르소나 ID로 페르소나 정보 가져오기"""
    return PERSONAS.get(persona_id)


def list_personas() -> list:
    """모든 페르소나 리스트 반환"""
    return [
        {
            "id": persona["id"],
            "name": persona["name"],
            "age_group": persona["metadata"].get("age_group", "전연령")
        }
        for persona in PERSONAS.values()
    ]


def get_persona_for_embedding(persona_id: str) -> str:
    """Vector DB 임베딩용 텍스트 생성"""
    persona = PERSONAS.get(persona_id)
    if not persona:
        return ""

    return f"""
페르소나 ID: {persona['id']}
페르소나 이름: {persona['name']}
{persona['description']}
"""


if __name__ == "__main__":
    # 테스트
    print("=== 페르소나 목록 ===")
    for p in list_personas():
        print(f"- {p['name']} ({p['age_group']})")

    print("\n=== 페르소나 상세 정보 ===")
    persona = get_persona("premium_antiaging_40s")
    print(f"이름: {persona['name']}")
    print(f"설명:\n{persona['description']}")
