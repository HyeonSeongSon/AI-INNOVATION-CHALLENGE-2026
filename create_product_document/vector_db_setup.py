"""
Vector Database 설정 및 데이터 임베딩
Chroma DB를 사용하여 브랜드 가이드라인, 상품 정보, 페르소나를 임베딩합니다.
"""

import os
import sys
import json
import yaml
from typing import List, Dict
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
import chromadb
from chromadb.config import Settings
from tqdm import tqdm

# Windows 콘솔 인코딩 설정
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

from personas import PERSONAS, get_persona_for_embedding
from embedding_models import get_embedding_model

# 환경 변수 로드
load_dotenv()


class VectorDBSetup:
    """Vector Database 설정 및 관리 클래스"""

    def __init__(self):
        # 임베딩 모델 초기화 (Snowflake Arctic - 최고 검색 품질)
        model_type = os.getenv("EMBEDDING_MODEL_TYPE", "snowflake-arctic")
        print(f"🔧 임베딩 모델 타입: {model_type}")
        self.embedder = get_embedding_model(model_type)
        print(f"✅ 임베딩 모델: {self.embedder.get_name()}")
        print(f"✅ 임베딩 차원: {self.embedder.get_dimension()}")

        # Chroma DB 클라이언트 초기화
        db_path = os.getenv("CHROMA_DB_PATH", "./chroma_db")
        self.chroma_client = chromadb.PersistentClient(path=db_path)

        print(f"✅ Chroma DB 초기화 완료: {db_path}")

    def get_embedding(self, text: str) -> List[float]:
        """텍스트를 임베딩 벡터로 변환"""
        try:
            return self.embedder.embed(text)
        except Exception as e:
            print(f"❌ 임베딩 생성 오류: {e}")
            return []

    def setup_brand_guidelines_collection(self, yaml_file: str = "brand_ton.yaml"):
        """브랜드 가이드라인을 Vector DB에 저장"""
        print("\n=== 브랜드 가이드라인 임베딩 시작 ===")

        # Collection 생성 (기존 것이 있으면 삭제)
        collection_name = os.getenv("COLLECTION_NAME_BRANDS", "brand_guidelines")
        try:
            self.chroma_client.delete_collection(collection_name)
        except:
            pass

        collection = self.chroma_client.create_collection(
            name=collection_name,
            metadata={"description": "브랜드별 톤앤매너 가이드라인"}
        )

        # YAML 파일 읽기
        with open(yaml_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        brand_prompts = data.get('brand_ton_prompt', {})
        print(f"총 {len(brand_prompts)}개 브랜드 발견")

        # 각 브랜드별로 임베딩
        ids = []
        embeddings = []
        documents = []
        metadatas = []

        for brand_name, content in tqdm(brand_prompts.items(), desc="브랜드 임베딩"):
            # 임베딩할 텍스트 생성
            embedding_text = f"브랜드: {brand_name}\n\n{content}"

            # OpenAI 임베딩 생성
            embedding = self.get_embedding(embedding_text)

            if embedding:
                ids.append(f"brand_{brand_name}")
                embeddings.append(embedding)
                documents.append(embedding_text)
                metadatas.append({
                    "brand": brand_name,
                    "category": "guidelines",
                    "type": "brand_tone"
                })

        # Collection에 저장
        if ids:
            collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )
            print(f"✅ {len(ids)}개 브랜드 가이드라인 저장 완료")
        else:
            print("❌ 저장할 데이터가 없습니다.")

        return collection

    def setup_products_collection(
        self,
        jsonl_file: str = r"C:\Users\82104\Desktop\vscode\AI-INNOVATION-CHALLENGE-2026-son_branch\data\crawling_result\product_crawling_2512081458.jsonl"
    ):
        """상품 정보를 Vector DB에 저장"""
        print("\n=== 상품 정보 임베딩 시작 ===")

        # Collection 생성
        collection_name = os.getenv("COLLECTION_NAME_PRODUCTS", "products")
        try:
            self.chroma_client.delete_collection(collection_name)
        except:
            pass

        collection = self.chroma_client.create_collection(
            name=collection_name,
            metadata={"description": "아모레몰 상품 정보"}
        )

        # JSONL 파일 읽기
        if not os.path.exists(jsonl_file):
            print(f"⚠️ 파일을 찾을 수 없습니다: {jsonl_file}")
            return collection

        products = []
        with open(jsonl_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        product = json.loads(line)
                        if product is not None:  # None 체크
                            products.append(product)
                    except json.JSONDecodeError:
                        continue  # 잘못된 JSON 라인 건너뛰기

        print(f"총 {len(products)}개 상품 발견")

        # 각 상품별로 임베딩
        ids = []
        embeddings = []
        documents = []
        metadatas = []

        for idx, product in enumerate(tqdm(products, desc="상품 임베딩")):
            try:
                # None 체크
                if product is None:
                    continue

                # 가격 파싱 (이미 int)
                price = product.get('판매가', 0)
                original_price = product.get('원가', 0)

                # 별점 파싱 (null 처리)
                rating = product.get('별점', 0)
                if rating is None:
                    rating = 0.0
                else:
                    rating = float(rating)

                # 리뷰 개수 파싱
                review_count = product.get('리뷰_갯수', 0)
                if review_count is None:
                    review_count = 0

                # 할인율 파싱
                discount = product.get('할인율', 0)

                # 구매자 통계 파싱 (None 체크)
                buyer_stats = product.get('구매자_통계') or {}
                skin_type_stats = buyer_stats.get('피부타입별', {})
                age_stats = buyer_stats.get('연령대별', {})

                # 임베딩할 텍스트 생성
                embedding_text = f"""
브랜드: {product.get('브랜드', 'N/A')}
상품명: {product.get('상품명', 'N/A')}
원가: ₩{original_price:,}
할인율: {discount}%
판매가: ₩{price:,}
별점: {rating}/5.0
리뷰: {review_count}개
피부타입별 구매비율: {', '.join([f'{k}: {v}%' for k, v in skin_type_stats.items()]) if skin_type_stats else 'N/A'}
연령대별 구매비율: {', '.join([f'{k}: {v}%' for k, v in age_stats.items()]) if age_stats else 'N/A'}
                """.strip()

                # 임베딩 생성
                embedding = self.get_embedding(embedding_text)

                if embedding:
                    product_id = f"product_{idx}"
                    ids.append(product_id)
                    embeddings.append(embedding)
                    documents.append(embedding_text)
                    metadatas.append({
                        "brand": product.get('브랜드', 'N/A'),
                        "product_name": product.get('상품명', 'N/A'),
                        "price": int(price),
                        "discount_rate": str(discount) + '%',
                        "rating": rating,
                        "review_count": int(review_count),
                        "url": product.get('url', ''),
                        "type": "product"
                    })

            except Exception as e:
                print(f"⚠️ 상품 {idx} 처리 중 오류: {e}")
                continue

        # Collection에 저장 (배치 단위로)
        batch_size = 100
        for i in range(0, len(ids), batch_size):
            batch_ids = ids[i:i+batch_size]
            batch_embeddings = embeddings[i:i+batch_size]
            batch_documents = documents[i:i+batch_size]
            batch_metadatas = metadatas[i:i+batch_size]

            collection.add(
                ids=batch_ids,
                embeddings=batch_embeddings,
                documents=batch_documents,
                metadatas=batch_metadatas
            )

        print(f"✅ {len(ids)}개 상품 정보 저장 완료")
        return collection

    def setup_personas_collection(self):
        """페르소나 정보를 Vector DB에 저장"""
        print("\n=== 페르소나 임베딩 시작 ===")

        # Collection 생성
        collection_name = os.getenv("COLLECTION_NAME_PERSONAS", "personas")
        try:
            self.chroma_client.delete_collection(collection_name)
        except:
            pass

        collection = self.chroma_client.create_collection(
            name=collection_name,
            metadata={"description": "고객 페르소나 정의"}
        )

        print(f"총 {len(PERSONAS)}개 페르소나 발견")

        # 각 페르소나별로 임베딩
        ids = []
        embeddings = []
        documents = []
        metadatas = []

        for persona_id, persona in tqdm(PERSONAS.items(), desc="페르소나 임베딩"):
            # 임베딩할 텍스트 생성
            embedding_text = get_persona_for_embedding(persona_id)

            # OpenAI 임베딩 생성
            embedding = self.get_embedding(embedding_text)

            if embedding:
                # Metadata 준비 (리스트를 문자열로 변환)
                metadata = {
                    "persona_id": persona_id,
                    "persona_name": persona['name'],
                    "type": "persona"
                }

                # persona['metadata']의 리스트를 문자열로 변환
                for key, value in persona['metadata'].items():
                    if isinstance(value, list):
                        metadata[key] = ", ".join(str(v) for v in value)
                    else:
                        metadata[key] = value

                ids.append(persona_id)
                embeddings.append(embedding)
                documents.append(embedding_text)
                metadatas.append(metadata)

        # Collection에 저장
        if ids:
            collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )
            print(f"✅ {len(ids)}개 페르소나 저장 완료")
        else:
            print("❌ 저장할 데이터가 없습니다.")

        return collection

    def setup_all(self):
        """모든 컬렉션 설정"""
        print("=" * 80)
        print("Vector Database 초기 설정 시작")
        print("=" * 80)

        # 1. 브랜드 가이드라인
        self.setup_brand_guidelines_collection()

        # 2. 상품 정보
        self.setup_products_collection()

        # 3. 페르소나
        self.setup_personas_collection()

        print("\n" + "=" * 80)
        print("✅ 모든 데이터 임베딩 완료!")
        print("=" * 80)

    def verify_collections(self):
        """컬렉션 검증"""
        print("\n=== 컬렉션 검증 ===")

        collections = self.chroma_client.list_collections()
        for collection in collections:
            count = collection.count()
            print(f"- {collection.name}: {count}개 항목")


def main():
    """메인 함수"""
    import sys

    # OpenAI API 키 확인
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY가 설정되지 않았습니다.")
        print("   .env 파일을 생성하고 API 키를 설정해주세요.")
        return

    setup = VectorDBSetup()

    if len(sys.argv) > 1 and sys.argv[1] == "--verify":
        # 검증만 수행
        setup.verify_collections()
    else:
        # 전체 설정 수행
        setup.setup_all()
        setup.verify_collections()


if __name__ == "__main__":
    main()
