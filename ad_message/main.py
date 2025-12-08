"""
광고 메시지 자동 생성 시스템 - 메인 실행 스크립트
사용자 인터페이스를 제공하고 전체 워크플로우를 관리합니다.
"""

import os
import sys
import io
from typing import List, Dict
from dotenv import load_dotenv

from personas import list_personas, get_persona
from ad_message_generator import AdMessageGenerator

# Windows 콘솔 UTF-8 설정
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 환경 변수 로드
load_dotenv()


def print_header():
    """헤더 출력"""
    print("\n" + "="*80)
    print("  🎯 AI 광고 메시지 자동 생성 시스템")
    print("  아모레퍼시픽 브랜드별 × 페르소나별 맞춤 메시지")
    print("="*80 + "\n")


def check_environment():
    """환경 설정 확인"""
    print("환경 설정 확인 중...")

    # OpenAI API 키 확인
    if not os.getenv("OPENAI_API_KEY"):
        print("\n❌ OPENAI_API_KEY가 설정되지 않았습니다.")
        print("\n다음 단계를 따라주세요:")
        print("1. .env.example 파일을 복사하여 .env 파일 생성")
        print("2. .env 파일에 OpenAI API 키 입력")
        print("   OPENAI_API_KEY=your-api-key-here")
        print("\nAPI 키는 https://platform.openai.com/api-keys 에서 생성 가능합니다.")
        sys.exit(1)

    # Vector DB 확인
    db_path = os.getenv("CHROMA_DB_PATH", "./chroma_db")
    if not os.path.exists(db_path):
        print(f"\n⚠️ Vector Database가 초기화되지 않았습니다: {db_path}")
        print("\n먼저 다음 명령어를 실행하여 데이터베이스를 설정해주세요:")
        print("  python vector_db_setup.py")
        response = input("\n지금 설정하시겠습니까? (y/n): ").strip().lower()
        if response == 'y':
            print("\nVector DB 설정을 시작합니다...")
            os.system("python vector_db_setup.py")
        else:
            sys.exit(1)

    print("✅ 환경 설정 확인 완료\n")


def select_brand() -> str:
    """브랜드 선택"""
    # brand_ton.yaml에서 브랜드 목록을 읽어올 수도 있지만,
    # 간단하게 주요 브랜드만 제공
    brands = [
        "설화수", "헤라", "라네즈", "아이오페", "마몽드",
        "에스쁘아", "에뛰드", "려", "라보에이치", "일리윤"
    ]

    print("="*80)
    print("1단계: 브랜드 선택")
    print("="*80)
    print("\n사용 가능한 브랜드:")

    for i, brand in enumerate(brands, 1):
        print(f"  {i}. {brand}")

    print(f"  0. 직접 입력")

    while True:
        try:
            choice = input("\n브랜드 번호를 선택하세요: ").strip()

            if choice == '0':
                brand = input("브랜드명을 입력하세요: ").strip()
                if brand:
                    return brand
            else:
                idx = int(choice) - 1
                if 0 <= idx < len(brands):
                    return brands[idx]

            print("❌ 올바른 번호를 입력하세요.")
        except (ValueError, IndexError):
            print("❌ 올바른 번호를 입력하세요.")


def select_persona() -> str:
    """페르소나 선택"""
    personas = list_personas()

    print("\n" + "="*80)
    print("2단계: 타겟 페르소나 선택")
    print("="*80)
    print("\n사용 가능한 페르소나:")

    for i, persona in enumerate(personas, 1):
        print(f"  {i}. {persona['name']} ({persona['age_group']})")

    while True:
        try:
            choice = input("\n페르소나 번호를 선택하세요: ").strip()
            idx = int(choice) - 1

            if 0 <= idx < len(personas):
                persona_id = personas[idx]['id']
                persona = get_persona(persona_id)

                # 페르소나 상세 정보 표시
                print(f"\n✅ 선택된 페르소나: {persona['name']}")
                print(f"\n특성:")
                print(persona['description'][:200] + "...")

                confirm = input("\n이 페르소나로 진행하시겠습니까? (y/n): ").strip().lower()
                if confirm == 'y':
                    return persona_id

            print("❌ 올바른 번호를 입력하세요.")
        except (ValueError, IndexError):
            print("❌ 올바른 번호를 입력하세요.")


def select_campaign_goal() -> str:
    """캠페인 목표 선택"""
    goals = [
        "신규 고객 유치",
        "재구매 유도",
        "신제품 프로모션",
        "계절 맞춤 프로모션",
        "재고 소진",
        "브랜드 인지도 제고"
    ]

    print("\n" + "="*80)
    print("3단계: 캠페인 목표 선택")
    print("="*80)
    print("\n캠페인 목표:")

    for i, goal in enumerate(goals, 1):
        print(f"  {i}. {goal}")

    print(f"  0. 직접 입력")

    while True:
        try:
            choice = input("\n목표 번호를 선택하세요: ").strip()

            if choice == '0':
                goal = input("캠페인 목표를 입력하세요: ").strip()
                if goal:
                    return goal
            else:
                idx = int(choice) - 1
                if 0 <= idx < len(goals):
                    return goals[idx]

            print("❌ 올바른 번호를 입력하세요.")
        except (ValueError, IndexError):
            print("❌ 올바른 번호를 입력하세요.")


def display_results(result):
    """결과 출력"""
    print("\n" + "="*80)
    print("  📊 생성 결과")
    print("="*80)

    print(f"\n브랜드: {result.brand}")
    print(f"페르소나: {result.persona_name}")
    print(f"캠페인 목표: {result.campaign_goal}")
    print(f"\n총 {len(result.variations)}개 배리에이션 생성")

    if result.recommended_products:
        print(f"\n추천 상품 ({len(result.recommended_products)}개):")
        for i, product in enumerate(result.recommended_products[:3], 1):
            print(f"  {i}. {product['product_name']}")
            print(f"     가격: ₩{product['price']:,} (할인: {product['discount_rate']})")
            print(f"     평점: {product['rating']}/5.0 ({product['review_count']}개 리뷰)")

    print("\n" + "="*80)
    print("  메시지 배리에이션")
    print("="*80)

    for i, var in enumerate(result.variations, 1):
        print(f"\n【배리에이션 {i}: {var.strategy}】")
        print("-" * 80)
        print(f"제목 ({len(var.subject)}자):")
        print(f"  {var.subject}")
        print(f"\n본문 ({len(var.body)}자):")
        # 본문을 50자마다 줄바꿈
        body_lines = [var.body[i:i+50] for i in range(0, len(var.body), 50)]
        for line in body_lines:
            print(f"  {line}")
        print(f"\n브랜드 일치도: {var.brand_alignment_score:.1%}")
        print(f"감성 점수: {var.emotion_score:.1%}")

    # 비용 정보
    if result.metadata:
        print("\n" + "="*80)
        print("  생성 정보")
        print("="*80)
        print(f"모델: {result.metadata.get('model', 'N/A')}")
        print(f"총 토큰: {result.metadata.get('total_tokens', 0):,}")
        print(f"프롬프트 토큰: {result.metadata.get('prompt_tokens', 0):,}")
        print(f"응답 토큰: {result.metadata.get('completion_tokens', 0):,}")


def save_results(result):
    """결과 저장 옵션"""
    print("\n" + "="*80)
    save = input("결과를 파일로 저장하시겠습니까? (y/n): ").strip().lower()

    if save == 'y':
        filename = f"ad_message_{result.brand}_{result.persona_id}.json"
        generator = AdMessageGenerator()
        generator.save_result(result, filename)
        print(f"\n✅ 저장 완료: {filename}")


def main():
    """메인 함수"""
    print_header()

    # 환경 확인
    check_environment()

    try:
        # 1. 브랜드 선택
        brand = select_brand()

        # 2. 페르소나 선택
        persona_id = select_persona()

        # 3. 캠페인 목표 선택
        campaign_goal = select_campaign_goal()

        # 4. 메시지 생성
        print("\n" + "="*80)
        print("  🤖 AI 메시지 생성 중...")
        print("="*80)

        generator = AdMessageGenerator()
        result = generator.generate(
            brand=brand,
            persona_id=persona_id,
            campaign_goal=campaign_goal
        )

        # 5. 결과 출력
        display_results(result)

        # 6. 결과 저장
        save_results(result)

        print("\n" + "="*80)
        print("  ✅ 완료!")
        print("="*80 + "\n")

    except KeyboardInterrupt:
        print("\n\n❌ 사용자가 중단했습니다.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
