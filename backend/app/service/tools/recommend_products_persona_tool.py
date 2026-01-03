"""
페르소나 기반 상품 추천 Tool (디버깅 로그 추가)
다단계×다차원 분석 + 멀티 쿼리 검색
"""

from typing import Dict, Any, List, Optional
from langchain_core.tools import tool
import json
import traceback
from .recommend_products import ProductRecommender


@tool
def recommend_products_persona(
    persona_id: str,
    user_input: str,
    brands: Optional[List[str]] = None,
    product_categories: Optional[List[str]] = None,
    exclusive_target: Optional[str] = None,
    top_k: int = 5
) -> str:
    """페르소나 기반 다단계×다차원 분석으로 제품을 추천합니다.

    이 도구는 페르소나 정보를 심층 분석하여 최적의 제품을 추천합니다.

    **작동 방식:**
    1. 페르소나 정보 조회
    2. 다단계×다차원 분석 수행
       - 다단계: 기본 프로필, 라이프스타일 패턴, 뷰티 니즈, 상황별 니즈, 개선 목표
       - 다차원: 피부 과학, 성분, 라이프스타일, 감성/가치관, 색조, 가격/가성비, 사용 편의성, 안전성/리스크
    3. 멀티 쿼리 생성 (3~5개의 다각도 검색 쿼리)
    4. 벡터 검색 수행 (각 쿼리로 검색 후 중복 제거)
    5. 최고 스코어 상품 반환

    Args:
        persona_id: 페르소나 ID (필수)
        user_input: 사용자 요청 텍스트 (필수, 예: "겨울철 건조한 피부에 좋은 크림 추천해줘")
        brands: 브랜드 필터 (선택, 예: ["설화수", "헤라"])
        product_categories: 상품 카테고리 필터 (선택, 예: ["스킨케어-크림", "메이크업-립스틱"])
        exclusive_target: 특정 대상 전용 제품 (선택, 예: "임산부전용")
        top_k: 각 쿼리당 검색할 상품 수 (기본값: 5)

    Returns:
        추천 제품 리스트 (JSON 문자열)
    """
    # ============================================
    # 🔍 디버깅: 시작 로그
    # ============================================
    print(f"\n{'='*60}", flush=True)
    print(f"[TOOL CALLED] recommend_products_persona", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"📋 입력 파라미터:", flush=True)
    print(f"  - persona_id: {persona_id} (type: {type(persona_id).__name__})", flush=True)
    print(f"  - user_input: {user_input[:100]}{'...' if len(str(user_input)) > 100 else ''}", flush=True)
    print(f"  - user_input type: {type(user_input).__name__}", flush=True)
    print(f"  - brands: {brands}", flush=True)
    print(f"  - product_categories: {product_categories}", flush=True)
    print(f"  - exclusive_target: {exclusive_target}", flush=True)
    print(f"  - top_k: {top_k}", flush=True)
    print(f"{'='*60}\n", flush=True)

    # ============================================
    # 🔍 디버깅: user_input이 JSON인지 확인 및 파싱
    # ============================================
    original_user_input = user_input
    if isinstance(user_input, str) and user_input.strip().startswith('{'):
        print(f"[DEBUG] user_input이 JSON 형식으로 의심됩니다. 파싱 시도...")
        try:
            parsed_input = json.loads(user_input)
            print(f"  ✓ JSON 파싱 성공!")
            print(f"  📦 파싱된 내용:")
            for key, value in parsed_input.items():
                if isinstance(value, (dict, list)):
                    print(f"    - {key}: {type(value).__name__} (length: {len(value)})")
                else:
                    print(f"    - {key}: {value}")
            
            # 실제 user_input 추출
            if 'purpose' in parsed_input:
                user_input = parsed_input['purpose']
                print(f"  ✓ 실제 user_input 추출: '{user_input}'")
            
            # 다른 필드도 추출
            if 'persona_id' in parsed_input:
                persona_id = parsed_input['persona_id']
                print(f"  ✓ persona_id 업데이트: {persona_id}")
            
            if 'product_categories' in parsed_input:
                product_categories = parsed_input['product_categories']
                print(f"  ✓ product_categories 업데이트: {product_categories}")
                
        except json.JSONDecodeError as e:
            print(f"  ✗ JSON 파싱 실패: {e}")
            print(f"  → 원본 user_input 사용")

    try:
        # ============================================
        # ProductRecommender 인스턴스 생성
        # ============================================
        print(f"\n[초기화] ProductRecommender 인스턴스 생성 중...")
        recommender = ProductRecommender()
        print(f"  ✓ ProductRecommender 생성 완료")
        
        # 사용 가능한 메서드 확인
        methods = [m for m in dir(recommender) if not m.startswith('_') and callable(getattr(recommender, m))]
        print(f"  ℹ️  사용 가능한 메서드: {', '.join(methods[:10])}...")

        # ============================================
        # [1단계] 페르소나 정보 조회
        # ============================================
        print(f"\n{'─'*60}")
        print(f"[1단계] 페르소나 정보 조회")
        print(f"{'─'*60}")
        print(f"  🔍 조회할 persona_id: {persona_id}")
        
        try:
            persona_info = recommender.get_persona_info(persona_id)
            print(f"  ✅ 페르소나 조회 성공")
            print(f"    - 이름: {persona_info.get('이름', 'Unknown')}")
            print(f"    - 나이: {persona_info.get('나이', 'Unknown')}")
            print(f"    - 피부타입: {persona_info.get('피부타입', [])}")
            print(f"    - 고민: {persona_info.get('고민 키워드', [])}")
        except Exception as e:
            error_msg = f"페르소나 정보 조회 실패: {str(e)}"
            print(f"  ❌ {error_msg}")
            print(f"  📋 Traceback:\n{traceback.format_exc()}")
            return json.dumps({
                "error": error_msg,
                "status": "error",
                "products": []
            }, ensure_ascii=False)

        # ============================================
        # [2단계] 기존 분석 결과 확인
        # ============================================
        print(f"\n{'─'*60}")
        print(f"[2단계] 기존 분석 결과 확인")
        print(f"{'─'*60}")
        
        try:
            existing_analysis = recommender.get_existing_analysis(persona_id)
            
            if existing_analysis:
                print(f"  ✅ 기존 분석 발견!")
                print(f"    - analysis_id: {existing_analysis.get('analysis_id')}")
                analysis_result_text = existing_analysis['analysis_result']
                analysis_id = existing_analysis['analysis_id']
                
                try:
                    analysis_result = json.loads(analysis_result_text)
                    print(f"  ✅ 분석 결과 파싱 성공")
                    print(f"    - multi_level_analysis 키: {list(analysis_result.get('multi_level_analysis', {}).keys())}")
                    print(f"    - multi_dimensional_analysis 키: {list(analysis_result.get('multi_dimensional_analysis', {}).keys())}")
                except json.JSONDecodeError as je:
                    print(f"  ❌ 분석 결과 파싱 실패: {je}")
                    analysis_result = None
            else:
                print(f"  ℹ️  기존 분석 없음 → 새로 생성 필요")
                analysis_result = None
                analysis_id = None
        except Exception as e:
            print(f"  ⚠️  분석 확인 중 에러 (무시하고 진행): {e}")
            analysis_result = None
            analysis_id = None

        # ============================================
        # [3-4단계] 페르소나 분석 (필요시)
        # ============================================
        if not analysis_result:
            print(f"\n{'─'*60}")
            print(f"[3단계] 페르소나 분석 수행 (LLM 호출)")
            print(f"{'─'*60}")
            print(f"  ⏱️  분석 시작... (10-30초 소요 예상)")
            
            try:
                analysis_result = recommender.recommend_persona(
                    user_input=user_input,
                    persona_id=persona_id
                )
                print(f"  ✅ 분석 완료!")
                print(f"    - multi_level_analysis: {len(analysis_result.get('multi_level_analysis', {}))}개 레벨")
                print(f"    - multi_dimensional_analysis: {len(analysis_result.get('multi_dimensional_analysis', {}))}개 차원")
                
                # DB 저장
                print(f"\n{'─'*60}")
                print(f"[4단계] 분석 결과 DB 저장")
                print(f"{'─'*60}")
                
                analysis_id = recommender.save_analysis_result(
                    persona_id=persona_id,
                    analysis_result=analysis_result
                )
                print(f"  ✅ 저장 완료 (analysis_id: {analysis_id})")
                
            except Exception as e:
                error_msg = f"페르소나 분석 실패: {str(e)}"
                print(f"  ❌ {error_msg}")
                print(f"  📋 Traceback:\n{traceback.format_exc()}")
                return json.dumps({
                    "error": error_msg,
                    "status": "error",
                    "products": []
                }, ensure_ascii=False)
        else:
            print(f"\n{'─'*60}")
            print(f"[3-4단계] 기존 분석 사용 (SKIP)")
            print(f"{'─'*60}")
            print(f"  ✅ 기존 analysis_id: {analysis_id} 사용")

        # ============================================
        # [5단계] 멀티 쿼리 생성
        # ============================================
        print(f"\n{'─'*60}")
        print(f"[5단계] 멀티 쿼리 생성 (LLM 호출)")
        print(f"{'─'*60}")
        print(f"  ⏱️  쿼리 생성 시작... (5-10초 소요 예상)")
        
        try:
            queries = recommender.generate_multi_queries(
                user_input=user_input,
                analysis_result=analysis_result,
                product_categories=product_categories
            )
            print(f"  ✅ 쿼리 생성 완료: {len(queries)}개")
            for i, q in enumerate(queries, 1):
                print(f"    {i}. {q}")
        except Exception as e:
            error_msg = f"쿼리 생성 실패: {str(e)}"
            print(f"  ❌ {error_msg}")
            print(f"  📋 Traceback:\n{traceback.format_exc()}")
            # 폴백: 기본 쿼리 사용
            queries = [user_input]
            print(f"  ⚠️  폴백: 사용자 입력을 기본 쿼리로 사용")

        # ============================================
        # [6단계] 쿼리 DB 저장
        # ============================================
        print(f"\n{'─'*60}")
        print(f"[6단계] 쿼리 DB 저장")
        print(f"{'─'*60}")
        
        try:
            recommender.save_search_queries(
                analysis_id=analysis_id,
                queries=queries
            )
            print(f"  ✅ {len(queries)}개 쿼리 저장 완료")
        except Exception as e:
            print(f"  ⚠️  쿼리 저장 실패 (무시하고 진행): {e}")

        # ============================================
        # [7단계] 멀티 쿼리 검색
        # ============================================
        print(f"\n{'─'*60}")
        print(f"[7단계] 멀티 쿼리 벡터 검색")
        print(f"{'─'*60}")
        print(f"  🔍 검색 조건:")
        print(f"    - 쿼리 수: {len(queries)}개")
        print(f"    - brands: {brands}")
        print(f"    - product_categories: {product_categories}")
        print(f"    - top_k: {top_k}")
        
        try:
            search_results = recommender.search_with_multi_queries(
                queries=queries,
                brands=brands,
                product_categories=product_categories,
                exclusive_target=exclusive_target,
                top_k=top_k
            )
            print(f"  ✅ 검색 완료: {len(search_results)}개 상품")
            
            # 상위 3개 스코어 출력
            if search_results:
                print(f"  📊 상위 3개 스코어:")
                for i, result in enumerate(search_results[:3], 1):
                    score = result.get('score', 0)
                    product_id = result.get('product_id', 'Unknown')
                    print(f"    {i}. {product_id}: {score:.4f}")
                    
        except Exception as e:
            error_msg = f"벡터 검색 실패: {str(e)}"
            print(f"  ❌ {error_msg}")
            print(f"  📋 Traceback:\n{traceback.format_exc()}")
            return json.dumps({
                "error": error_msg,
                "status": "error",
                "products": []
            }, ensure_ascii=False)

        if not search_results:
            print(f"  ⚠️  검색 결과 없음")
            return json.dumps({
                "error": "검색 결과가 없습니다.",
                "status": "no_results",
                "persona_info": persona_info,
                "analysis_result": analysis_result,
                "queries": queries,
                "products": []
            }, ensure_ascii=False)

        # ============================================
        # [8단계] 상품 데이터 병합
        # ============================================
        print(f"\n{'─'*60}")
        print(f"[8단계] 상품 데이터 병합")
        print(f"{'─'*60}")
        
        try:
            all_products = recommender.get_filtered_products(
                brands=brands,
                product_categories=product_categories,
                exclusive_target=exclusive_target
            )
            print(f"  ℹ️  필터링된 전체 상품: {len(all_products)}개")

            merged_products = recommender.merge_product_data(
                search_results=search_results,
                all_products=all_products
            )
            print(f"  ✅ 병합 완료: {len(merged_products)}개")
            
        except Exception as e:
            error_msg = f"상품 데이터 병합 실패: {str(e)}"
            print(f"  ❌ {error_msg}")
            print(f"  📋 Traceback:\n{traceback.format_exc()}")
            return json.dumps({
                "error": error_msg,
                "status": "error",
                "products": []
            }, ensure_ascii=False)

        # ============================================
        # [9단계] 상위 3개 선택
        # ============================================
        print(f"\n{'─'*60}")
        print(f"[9단계] 상위 3개 선택")
        print(f"{'─'*60}")
        
        top_3_products = merged_products[:3]
        print(f"  ✅ 선택 완료: {len(top_3_products)}개")
        
        if top_3_products:
            print(f"  📦 선택된 상품:")
            for i, product in enumerate(top_3_products, 1):
                print(f"    {i}. {product.get('product_name', 'Unknown')} ({product.get('brand', 'Unknown')})")
                print(f"       - 가격: {product.get('sale_price', 0):,}원")
                print(f"       - 스코어: {product.get('vector_search_score', 0):.4f}")

        # ============================================
        # [10단계] 결과 반환
        # ============================================
        result = {
            "status": "success",
            "persona_info": persona_info,
            "analysis_result": analysis_result,
            "analysis_id": analysis_id,
            "queries": queries,
            "products": top_3_products,
            "count": len(top_3_products)
        }

        print(f"\n{'='*60}")
        print(f"[✅ SUCCESS] 상품 추천 완료")
        print(f"{'='*60}")
        print(f"  📊 최종 결과:")
        print(f"    - 추천 상품 수: {len(top_3_products)}개")
        print(f"    - 페르소나: {persona_info.get('이름', 'Unknown')}")
        print(f"    - 사용된 쿼리: {len(queries)}개")
        print(f"    - 전체 검색 결과: {len(merged_products)}개")
        print(f"{'='*60}\n")

        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        error_msg = f"예상치 못한 에러: {str(e)}"
        print(f"\n{'='*60}")
        print(f"[❌ FATAL ERROR]")
        print(f"{'='*60}")
        print(f"  에러 메시지: {error_msg}")
        print(f"  📋 전체 Traceback:")
        print(traceback.format_exc())
        print(f"{'='*60}\n")
        
        return json.dumps({
            "error": error_msg,
            "status": "fatal_error",
            "products": []
        }, ensure_ascii=False)