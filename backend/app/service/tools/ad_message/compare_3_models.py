"""
4가지 임베딩 모델 비교: jina-v2, snowflake-arctic, gte-multilingual, e5-large
각 모델로 Vector DB를 생성하고 검색 성능을 비교합니다.
"""

import os
import sys
import time
import json
from dotenv import load_dotenv
import chromadb
from tqdm import tqdm

# Disable TensorFlow to avoid Keras compatibility issues
os.environ['USE_TF'] = '0'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
os.environ['TRANSFORMERS_VERBOSITY'] = 'error'

# Windows 콘솔 인코딩 설정
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

from embedding_models import get_embedding_model
from ad_message_generator import AdMessageGenerator

load_dotenv()


class ModelComparison:
    """4가지 모델 비교 클래스"""

    def __init__(self):
        self.models = ["jina-v2", "snowflake-arctic", "gte-multilingual", "e5-large"]
        self.results = {}
        # 3개의 JSONL 파일 모두 사용
        self.jsonl_files = [
            r"C:\Users\82104\Desktop\vscode\AI-INNOVATION-CHALLENGE-2026-son_branch\data\crawling_result\product_crawling_2512060138.jsonl",
            r"C:\Users\82104\Desktop\vscode\AI-INNOVATION-CHALLENGE-2026-son_branch\data\crawling_result\product_crawling_2512060343.jsonl",
            r"C:\Users\82104\Desktop\vscode\AI-INNOVATION-CHALLENGE-2026-son_branch\data\crawling_result\product_crawling_2512081458.jsonl"
        ]

    def create_vectordb(self, model_name: str):
        """특정 모델로 Vector DB 생성"""
        print(f"\n{'='*80}")
        print(f"🔧 [{model_name.upper()}] Vector DB 생성 중...")
        print(f"{'='*80}")

        # 모델 로딩
        start_time = time.time()
        embedder = get_embedding_model(model_name)
        load_time = time.time() - start_time

        print(f"✅ 모델: {embedder.get_name()}")
        print(f"   차원: {embedder.get_dimension()}")
        print(f"   로딩 시간: {load_time:.2f}초")

        # Chroma DB (모델별 경로)
        db_path = f"./chroma_db_{model_name}"
        client = chromadb.PersistentClient(path=db_path)

        try:
            client.delete_collection("products")
        except:
            pass

        collection = client.create_collection(
            name="products",
            metadata={"description": f"상품 ({model_name})"}
        )

        # 데이터 로드 (3개 파일 모두 읽기)
        products = []
        for jsonl_file in self.jsonl_files:
            if not os.path.exists(jsonl_file):
                print(f"⚠️ 파일을 찾을 수 없습니다: {jsonl_file}")
                continue

            with open(jsonl_file, 'r', encoding='utf-8') as f:
                file_products = 0
                for line in f:
                    if line.strip():
                        try:
                            product = json.loads(line)
                            if product is not None:  # None 체크
                                products.append(product)
                                file_products += 1
                        except json.JSONDecodeError:
                            continue  # 잘못된 JSON 라인 건너뛰기
                print(f"   ✓ {os.path.basename(jsonl_file)}: {file_products}개 상품")

        print(f"📦 총 {len(products)}개 상품 (3개 파일 통합)")

        # 임베딩 생성
        embed_start = time.time()
        ids, embeddings, documents, metadatas = [], [], [], []

        for idx, product in enumerate(tqdm(products, desc=f"{model_name} 임베딩")):
            try:
                # None 체크
                if product is None:
                    continue

                # 가격 파싱 (이미 int)
                price = product.get('판매가', 0)
                original_price = product.get('원가', 0)

                # 별점 파싱 (null 처리)
                rating = product.get('별점', 0)
                rating = 0.0 if rating is None else float(rating)

                # 리뷰 개수
                review_count = product.get('리뷰_갯수', 0) or 0

                # 할인율
                discount = product.get('할인율', 0)

                # 구매자 통계 (None 체크)
                buyer_stats = product.get('구매자_통계') or {}
                skin_type_stats = buyer_stats.get('피부타입별', {})
                age_stats = buyer_stats.get('연령대별', {})

                # 임베딩 텍스트 (더 상세하게)
                text = f"""
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

                embedding = embedder.embed(text)

                if embedding:
                    ids.append(f"product_{idx}")
                    embeddings.append(embedding)
                    documents.append(text)
                    metadatas.append({
                        "brand": product.get('브랜드', 'N/A'),
                        "product_name": product.get('상품명', 'N/A'),
                        "price": int(price),
                        "discount_rate": str(discount) + '%',
                        "rating": rating,
                        "review_count": int(review_count),
                        "url": product.get('url', ''),
                    })

            except Exception as e:
                print(f"⚠️ 오류 (상품 {idx}): {e}")
                continue

        # 배치 저장
        batch_size = 100
        for i in range(0, len(ids), batch_size):
            collection.add(
                ids=ids[i:i+batch_size],
                embeddings=embeddings[i:i+batch_size],
                documents=documents[i:i+batch_size],
                metadatas=metadatas[i:i+batch_size]
            )

        embed_time = time.time() - embed_start

        print(f"✅ 임베딩 완료: {len(ids)}개")
        print(f"   시간: {embed_time:.2f}초 ({len(ids)/embed_time:.2f}개/초)")

        self.results[model_name] = {
            "load_time": load_time,
            "embed_time": embed_time,
            "total": len(ids),
            "speed": len(ids) / embed_time,
            "dimension": embedder.get_dimension(),
            "collection": collection,
            "embedder": embedder
        }

        return collection, embedder

    def test_search(self, model_name: str):
        """검색 품질 테스트"""
        print(f"\n🔍 [{model_name.upper()}] 검색 테스트")

        collection = self.results[model_name]["collection"]
        embedder = self.results[model_name]["embedder"]

        queries = [
            "주름 개선 안티에이징 크림",
            "보습 수분 크림",
            "민감성 피부 진정",
            "메이크업 베이스",
            "아이섀도우 팔레트"
        ]

        search_times = []
        results_list = []

        for query in queries:
            start = time.time()
            q_emb = embedder.embed(query)
            res = collection.query(query_embeddings=[q_emb], n_results=3)
            search_time = time.time() - start
            search_times.append(search_time)

            if res['metadatas'] and len(res['metadatas'][0]) > 0:
                top1 = res['metadatas'][0][0]
                results_list.append({
                    "query": query,
                    "top1_product": top1['product_name'],
                    "brand": top1['brand']
                })
                print(f"   '{query}' → {top1['brand']} - {top1['product_name']} ({search_time*1000:.1f}ms)")

        avg_search = sum(search_times) / len(search_times)
        self.results[model_name]["avg_search"] = avg_search
        self.results[model_name]["search_results"] = results_list

        print(f"   평균 검색: {avg_search*1000:.2f}ms")

    def test_ad_generation(self, model_name: str):
        """실제 광고 메시지 생성 테스트"""
        print(f"\n📝 [{model_name.upper()}] 광고 메시지 생성 테스트")

        collection = self.results[model_name]["collection"]
        embedder = self.results[model_name]["embedder"]

        # 테스트용 페르소나 선택 (40대 안티에이징)
        persona_id = "premium_antiaging_40s"

        # 브랜드 선택 (이니스프리로 테스트)
        brand_name = "이니스프리"
        campaign_goal = "신규 고객 확보"

        # 광고 메시지 생성
        try:
            # 현재 모델의 컬렉션과 임베더를 주입
            generator = AdMessageGenerator(
                products_collection=collection,
                embedder=embedder
            )

            start_time = time.time()
            result = generator.generate(
                brand=brand_name,
                persona_id=persona_id,
                campaign_goal=campaign_goal
            )
            gen_time = time.time() - start_time

            if result.variations and len(result.variations) > 0:
                # 첫 번째 배리에이션만 저장
                first_var = result.variations[0]
                print(f"\n   생성 시간: {gen_time:.2f}초")
                print(f"   전략: {first_var.strategy}")
                print(f"   제목: {first_var.subject}")
                print(f"   본문 길이: {len(first_var.body)}자")
                print(f"   본문 미리보기: {first_var.body[:100]}...")

                self.results[model_name]["ad_generation"] = {
                    "generation_time": gen_time,
                    "message": {
                        "strategy": first_var.strategy,
                        "subject": first_var.subject,
                        "body": first_var.body
                    },
                    "products_used": [p['product_name'] for p in result.recommended_products[:3]]
                }
            else:
                print(f"   ⚠️ 메시지 생성 실패")
                self.results[model_name]["ad_generation"] = None

        except Exception as e:
            print(f"   ❌ 광고 생성 오류: {e}")
            import traceback
            traceback.print_exc()
            self.results[model_name]["ad_generation"] = None

    def run(self):
        """전체 비교 실행"""
        print("\n" + "="*80)
        print("🚀 4가지 임베딩 모델 비교")
        print("   모델: jina-v2, snowflake-arctic, gte-multilingual, e5-large")
        print("="*80)

        for model in self.models:
            try:
                self.create_vectordb(model)
                self.test_search(model)
                self.test_ad_generation(model)  # 광고 메시지 생성 테스트 추가
            except Exception as e:
                print(f"❌ {model} 오류: {e}")
                import traceback
                traceback.print_exc()

        self.print_summary()

    def print_summary(self):
        """결과 요약"""
        print("\n" + "="*80)
        print("📊 비교 결과 요약")
        print("="*80)

        print("\n1️⃣ 모델 로딩 시간")
        print("-" * 60)
        for m, r in self.results.items():
            print(f"   {m:12s}: {r['load_time']:6.2f}초")

        print("\n2️⃣ 임베딩 생성 시간")
        print("-" * 60)
        for m, r in self.results.items():
            print(f"   {m:12s}: {r['embed_time']:6.2f}초 ({r['speed']:.1f}개/초)")

        print("\n3️⃣ 검색 속도")
        print("-" * 60)
        for m, r in self.results.items():
            if "avg_search" in r:
                print(f"   {m:12s}: {r['avg_search']*1000:6.2f}ms")

        print("\n4️⃣ 임베딩 차원")
        print("-" * 60)
        for m, r in self.results.items():
            print(f"   {m:12s}: {r['dimension']}차원")

        print("\n5️⃣ 광고 메시지 생성 결과")
        print("-" * 60)
        for m, r in self.results.items():
            if "ad_generation" in r and r["ad_generation"]:
                ad = r["ad_generation"]
                print(f"\n   [{m.upper()}]")
                print(f"   생성 시간: {ad['generation_time']:.2f}초")
                print(f"   제목: {ad['message']['subject']}")
                print(f"   본문 길이: {len(ad['message']['body'])}자")
                print(f"   사용 상품: {', '.join(ad['products_used'])}")
                print(f"   본문 미리보기: {ad['message']['body'][:120]}...")
            else:
                print(f"   {m:12s}: 생성 실패")

        # 순위
        print("\n" + "="*80)
        print("🏆 성능 순위")
        print("="*80)

        sorted_embed = sorted(self.results.items(), key=lambda x: x[1]['embed_time'])
        print("\n⚡ 임베딩 속도 (빠른 순):")
        for rank, (m, r) in enumerate(sorted_embed, 1):
            print(f"   {rank}. {m:12s}: {r['embed_time']:.2f}초")

        sorted_search = sorted(
            [(k, v) for k, v in self.results.items() if "avg_search" in v],
            key=lambda x: x[1]['avg_search']
        )
        print("\n🔍 검색 속도 (빠른 순):")
        for rank, (m, r) in enumerate(sorted_search, 1):
            print(f"   {rank}. {m:12s}: {r['avg_search']*1000:.2f}ms")

        # 추천
        print("\n" + "="*80)
        print("💡 추천")
        print("="*80)
        fastest = sorted_embed[0][0]
        print(f"\n⚡ 가장 빠름: {fastest}")
        print(f"   속도: {self.results[fastest]['embed_time']:.2f}초")
        print(f"   차원: {self.results[fastest]['dimension']}")

        # JSON 저장
        output = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "models": {}
        }
        for m, r in self.results.items():
            output["models"][m] = {
                "load_time": r["load_time"],
                "embed_time": r["embed_time"],
                "total": r["total"],
                "speed": r["speed"],
                "dimension": r["dimension"],
                "avg_search": r.get("avg_search", 0),
                "search_results": r.get("search_results", []),
                "ad_generation": r.get("ad_generation", None)
            }

        filename = f"model_comparison_{time.strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        print(f"\n💾 결과 저장: {filename}")


if __name__ == "__main__":
    comparison = ModelComparison()
    comparison.run()
