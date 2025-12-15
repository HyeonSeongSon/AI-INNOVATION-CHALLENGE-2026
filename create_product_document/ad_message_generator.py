"""
광고 메시지 자동 생성 엔진
RAG + OpenAI GPT를 사용하여 브랜드별, 페르소나별 맞춤 광고 메시지를 생성합니다.
"""

import os
import json
from typing import List, Dict, Optional
from dotenv import load_dotenv
from openai import OpenAI
import chromadb
from pydantic import BaseModel, Field

from personas import get_persona

# 환경 변수 로드
load_dotenv()


class MessageVariation(BaseModel):
    """메시지 배리에이션 모델"""
    strategy: str = Field(description="메시지 전략 (효능/감성/혜택/리뷰/희소성)")
    subject: str = Field(description="제목 (40자 이내)", max_length=40)
    body: str = Field(description="본문 (350자 이내)", max_length=350)
    recommended_product_ids: List[str] = Field(default=[], description="추천 상품 ID 리스트")
    brand_alignment_score: float = Field(default=0.0, description="브랜드 톤 일치도 (0-1)")
    emotion_score: float = Field(default=0.0, description="감성 점수 (0-1)")


class AdMessageResult(BaseModel):
    """광고 메시지 생성 결과"""
    persona_id: str
    persona_name: str
    brand: str
    campaign_goal: str
    variations: List[MessageVariation]
    recommended_products: List[Dict]
    metadata: Dict = {}


class AdMessageGenerator:
    """광고 메시지 생성 엔진"""

    def __init__(self, products_collection=None, embedder=None):
        """
        Args:
            products_collection: 외부에서 주입받은 Chroma 상품 컬렉션 (선택)
            embedder: 외부에서 주입받은 임베더 모델 (선택)
        """
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.chat_model = os.getenv("CHAT_MODEL", "gpt-4-turbo-preview")
        self.temperature = float(os.getenv("TEMPERATURE", "0.7"))

        # 외부 주입 또는 기본 Chroma DB 사용
        if products_collection is not None and embedder is not None:
            # 외부에서 주입받은 경우
            self.products_collection = products_collection
            self.embedder = embedder
            self.brands_collection = None
            self.personas_collection = None
            print("✅ AdMessageGenerator 초기화 완료 (외부 컬렉션 사용)")
        else:
            # 기본 Chroma DB 사용
            db_path = os.getenv("CHROMA_DB_PATH", "./chroma_db")
            self.chroma_client = chromadb.PersistentClient(path=db_path)

            # Collections 로드
            self.brands_collection = self.chroma_client.get_collection(
                os.getenv("COLLECTION_NAME_BRANDS", "brand_guidelines")
            )
            self.products_collection = self.chroma_client.get_collection(
                os.getenv("COLLECTION_NAME_PRODUCTS", "products")
            )
            self.personas_collection = self.chroma_client.get_collection(
                os.getenv("COLLECTION_NAME_PERSONAS", "personas")
            )
            self.embedder = None
            print("✅ AdMessageGenerator 초기화 완료 (기본 Chroma DB)")

    def get_brand_guidelines(self, brand: str) -> str:
        """브랜드 가이드라인 검색"""
        try:
            results = self.brands_collection.get(
                ids=[f"brand_{brand}"]
            )
            if results['documents']:
                return results['documents'][0]
            else:
                # 유사한 브랜드 검색
                results = self.brands_collection.query(
                    query_texts=[f"브랜드: {brand}"],
                    n_results=1
                )
                if results['documents'] and results['documents'][0]:
                    return results['documents'][0][0]
        except Exception as e:
            print(f"⚠️ 브랜드 가이드라인 검색 오류: {e}")

        return f"브랜드: {brand}\n(가이드라인 없음)"

    def get_persona_info(self, persona_id: str) -> Dict:
        """페르소나 정보 가져오기"""
        persona = get_persona(persona_id)
        if not persona:
            raise ValueError(f"페르소나를 찾을 수 없습니다: {persona_id}")
        return persona

    def search_recommended_products(
        self,
        brand: str,
        persona: Dict,
        top_k: int = 5
    ) -> List[Dict]:
        """페르소나에 맞는 상품 추천"""
        # 검색 쿼리 생성
        search_query = f"""
브랜드: {brand}
연령대: {persona['metadata'].get('age_group', '')}
피부 고민: {', '.join(persona['metadata'].get('skin_concerns', []))}
관심사: {', '.join(persona['metadata'].get('interests', []))}
        """.strip()

        try:
            # 외부 임베더가 있으면 사용, 없으면 query_texts 사용
            if self.embedder:
                query_embedding = self.embedder.embed(search_query)
                results = self.products_collection.query(
                    query_embeddings=[query_embedding],
                    n_results=top_k,
                    where={"brand": brand}
                )
            else:
                results = self.products_collection.query(
                    query_texts=[search_query],
                    n_results=top_k,
                    where={"brand": brand}
                )

            products = []
            if results['metadatas'] and results['metadatas'][0]:
                for i, metadata in enumerate(results['metadatas'][0]):
                    product = {
                        "id": results['ids'][0][i] if results['ids'] else "",
                        "brand": metadata.get('brand', ''),
                        "product_name": metadata.get('product_name', ''),
                        "price": metadata.get('price', 0),
                        "discount_rate": metadata.get('discount_rate', '0%'),
                        "rating": metadata.get('rating', 0),
                        "review_count": metadata.get('review_count', 0),
                        "url": metadata.get('url', ''),
                        "description": results['documents'][0][i] if results['documents'] else ""
                    }
                    products.append(product)

            return products
        except Exception as e:
            print(f"⚠️ 상품 검색 오류: {e}")
            return []

    def create_system_prompt(self) -> str:
        """시스템 프롬프트 생성"""
        return """당신은 아모레퍼시픽의 전문 마케팅 카피라이터입니다.

역할:
- 브랜드별 톤앤매너를 정확히 준수
- 페르소나에 맞는 공감형 메시지 작성
- 감성적이면서도 구체적인 혜택 전달
- 추천 상품의 구체적인 이름, 가격, 혜택을 반드시 포함
- 제약 조건을 철저히 지킴

제약 조건:
- 제목: 40자 이내 (공백 포함)
- 본문: 300-350자 (최대한 350자에 가깝게 작성)
- 브랜드 금지어 사용 금지
- 이모티콘 사용 금지 (단, 브랜드가 명시적으로 허용한 경우만 예외)

중요 작성 원칙:
1. 본문은 반드시 300자 이상으로 풍부하게 작성
2. 추천 상품의 구체적인 이름을 본문에 2-3개 명시
3. 가격, 할인율 등 구체적인 수치 정보 포함
4. 상품의 핵심 성분이나 기술을 구체적으로 언급
5. 페르소나의 피부 고민과 상품의 효능을 명확히 연결

출력 형식:
반드시 JSON 형식으로 5개의 배리에이션을 생성하세요.
각 배리에이션은 다음 전략 중 하나를 따라야 합니다:
1. 효능 중심: 제품의 핵심 베네핏, 성분, 기술을 구체적으로 강조
2. 감성 중심: 페르소나의 감정과 라이프스타일에 공감하되 상품 연계
3. 혜택 중심: 할인율, 가격, 프로모션을 구체적 수치와 함께 전달
4. 사회적 증거: 리뷰 평점, 구매자 수를 구체적으로 언급
5. 희소성: 기간 한정, 수량 한정 등 긴급성 부여

JSON 스키마:
{
  "variations": [
    {
      "strategy": "효능 중심",
      "subject": "제목 (40자 이내)",
      "body": "본문 (300-350자, 상품명 2-3개 포함, 구체적 수치 포함)",
      "brand_alignment_score": 0.95,
      "emotion_score": 0.85
    }
  ]
}
"""

    def create_user_prompt(
        self,
        brand_guidelines: str,
        persona: Dict,
        products: List[Dict],
        campaign_goal: str
    ) -> str:
        """사용자 프롬프트 생성 (Few-shot)"""
        # 상품 정보 포맷팅 (더 상세하게)
        products_text = ""
        for i, product in enumerate(products[:5], 1):  # 상위 5개로 확대
            # description에서 핵심 정보 추출
            desc_lines = product['description'].split('\n')
            product_details = '\n   '.join([line.strip() for line in desc_lines if line.strip()][:4])

            products_text += f"""
{i}. 상품명: {product['product_name']}
   브랜드: {product['brand']}
   가격: ₩{product['price']:,}
   할인: {product['discount_rate']}
   평점: {product['rating']}/5.0 (리뷰 {product['review_count']:,}개)
   상세 정보:
   {product_details}
"""

        # 페르소나 피부 고민 추출
        skin_concerns = persona['metadata'].get('skin_concerns', [])
        if isinstance(skin_concerns, str):
            skin_concerns_text = skin_concerns
        else:
            skin_concerns_text = ", ".join(skin_concerns)

        return f"""
## 브랜드 정보
{brand_guidelines}

## 타겟 페르소나
이름: {persona['name']}
연령대: {persona['metadata'].get('age_group', 'N/A')}
주요 피부 고민: {skin_concerns_text}
구매 패턴: {persona['metadata'].get('decision_factors', 'N/A')}

페르소나 상세:
{persona['description']}

## 추천 상품 (페르소나 맞춤)
{products_text}

## 캠페인 목표
{campaign_goal}

---

위 정보를 바탕으로 5가지 마케팅 메시지 배리에이션을 생성해주세요.

**필수 작성 요구사항**:
1. 본문은 반드시 300-350자로 풍부하게 작성 (현재 너무 짧음)
2. 추천 상품 중 최소 2-3개의 구체적인 상품명을 본문에 언급
3. 가격(₩), 할인율(%), 평점 등 구체적 수치 포함
4. 상품의 핵심 성분, 기술, 효능을 구체적으로 언급
5. 페르소나의 피부 고민({skin_concerns_text})과 상품 효능을 명확히 연결
6. 브랜드 톤앤매너를 정확히 반영
7. 제목 40자 이내 준수
8. 금지 표현 절대 사용 금지

**작성 예시 (본문 길이 참고)**:
"40대가 되면서 눈가 주름과 탄력 저하가 고민이셨죠? 설화수 자음생 에센스(₩180,000, 20% 할인)는 3000년 한방 연구의 정수를 담아 피부 깊은 곳부터 탄력을 채워줍니다. 여기에 자음생 크림(₩220,000)을 함께 사용하시면 더욱 강력한 안티에이징 효과를 경험하실 수 있습니다. 실제 사용자 평점 4.8점, 2,000개 이상의 리뷰가 그 효과를 증명합니다. 오늘만 특별히 세트 구매 시 추가 10% 할인 혜택을 드립니다."

반드시 JSON 형식으로만 응답하세요.
"""

    def validate_message(self, variation: Dict) -> bool:
        """메시지 제약 조건 검증"""
        subject = variation.get('subject', '')
        body = variation.get('body', '')

        max_subject = int(os.getenv("MAX_SUBJECT_LENGTH", "40"))
        max_body = int(os.getenv("MAX_BODY_LENGTH", "350"))

        if len(subject) > max_subject:
            print(f"⚠️ 제목이 너무 깁니다: {len(subject)}자 (최대 {max_subject}자)")
            return False

        if len(body) > max_body:
            print(f"⚠️ 본문이 너무 깁니다: {len(body)}자 (최대 {max_body}자)")
            return False

        return True

    def generate(
        self,
        brand: str,
        persona_id: str,
        campaign_goal: str = "재구매 유도"
    ) -> AdMessageResult:
        """광고 메시지 생성"""
        print(f"\n{'='*80}")
        print(f"광고 메시지 생성 시작")
        print(f"브랜드: {brand}")
        print(f"페르소나: {persona_id}")
        print(f"목표: {campaign_goal}")
        print(f"{'='*80}\n")

        # 1. 브랜드 가이드라인 검색
        print("1. 브랜드 가이드라인 검색 중...")
        brand_guidelines = self.get_brand_guidelines(brand)

        # 2. 페르소나 정보 가져오기
        print("2. 페르소나 정보 로드 중...")
        persona = self.get_persona_info(persona_id)

        # 3. 추천 상품 검색
        print("3. 추천 상품 검색 중...")
        recommended_products = self.search_recommended_products(brand, persona)
        print(f"   → {len(recommended_products)}개 상품 발견")

        if not recommended_products:
            print("⚠️ 추천 상품이 없습니다. 기본 메시지를 생성합니다.")

        # 4. 프롬프트 생성
        print("4. 프롬프트 생성 중...")
        system_prompt = self.create_system_prompt()
        user_prompt = self.create_user_prompt(
            brand_guidelines, persona, recommended_products, campaign_goal
        )

        # 5. OpenAI API 호출
        print(f"5. GPT-4 메시지 생성 중 (모델: {self.chat_model})...")
        try:
            response = self.openai_client.chat.completions.create(
                model=self.chat_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.temperature,
                response_format={"type": "json_object"}
            )

            # 응답 파싱
            content = response.choices[0].message.content
            result_json = json.loads(content)

            # 6. 검증 및 변환
            print("6. 메시지 검증 중...")
            variations = []
            for var in result_json.get('variations', []):
                if self.validate_message(var):
                    variations.append(MessageVariation(**var))
                else:
                    print(f"   ⚠️ 제약 조건 위반으로 제외됨")

            print(f"   ✅ {len(variations)}개 배리에이션 생성 완료\n")

            # 결과 반환
            return AdMessageResult(
                persona_id=persona_id,
                persona_name=persona['name'],
                brand=brand,
                campaign_goal=campaign_goal,
                variations=variations,
                recommended_products=recommended_products,
                metadata={
                    "model": self.chat_model,
                    "temperature": self.temperature,
                    "total_tokens": response.usage.total_tokens,
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens
                }
            )

        except Exception as e:
            print(f"❌ 메시지 생성 오류: {e}")
            raise

    def save_result(self, result: AdMessageResult, filename: str = None):
        """결과를 JSON 파일로 저장"""
        if filename is None:
            filename = f"ad_message_{result.brand}_{result.persona_id}.json"

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(result.model_dump(), f, ensure_ascii=False, indent=2)

        print(f"✅ 결과 저장 완료: {filename}")


def main():
    """테스트용 메인 함수"""
    # 생성기 초기화
    generator = AdMessageGenerator()

    # 테스트: 설화수 × 프리미엄 안티에이징 페르소나
    result = generator.generate(
        brand="설화수",
        persona_id="premium_antiaging_40s",
        campaign_goal="신제품 프로모션"
    )

    # 결과 출력
    print("\n" + "="*80)
    print(f"브랜드: {result.brand}")
    print(f"페르소나: {result.persona_name}")
    print(f"캠페인 목표: {result.campaign_goal}")
    print("="*80)

    for i, var in enumerate(result.variations, 1):
        print(f"\n【배리에이션 {i}: {var.strategy}】")
        print(f"제목 ({len(var.subject)}자): {var.subject}")
        print(f"본문 ({len(var.body)}자):\n{var.body}")
        print(f"브랜드 일치도: {var.brand_alignment_score:.2f}")
        print(f"감성 점수: {var.emotion_score:.2f}")
        print("-" * 80)

    # 저장
    generator.save_result(result)


if __name__ == "__main__":
    main()
