"""
상품 추천 Tool (Tool Calling 방식)
LLM이 호출하는 단순 Tool - 워크플로우 없음
"""

from typing import Dict, Any, List, Optional
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import os
import json
import requests

# .env 로드
load_dotenv(os.path.join(os.path.dirname(__file__), "../../../.env"))


class ProductRecommender:
    """상품 추천 로직"""
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY가 .env 파일에 설정되어 있지 않습니다.")

        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.7,
            api_key=api_key
        )

    def get_persona_info(self, persona_id: str) -> Dict[str, Any]:
        """페르소나 정보 조회"""
        try:
            response = requests.post(
                "http://host.docker.internal:8005/api/pipeline/personas/get",
                json={"persona_id": persona_id}
            )
            response.raise_for_status()
            api_data = response.json()

            persona_info = {
                "persona_id": api_data.get("persona_id"),
                "이름": api_data.get("name"),
                "나이": api_data.get("age"),
                "성별": api_data.get("gender"),
                "직업": api_data.get("occupation"),
                "피부타입": api_data.get("skin_type", []),
                "고민 키워드": api_data.get("skin_concerns", []),
                "퍼스널 컬러": api_data.get("personal_color"),
                "베이스 호수": api_data.get("shade_number"),
                "메이크업 선호 색상": api_data.get("preferred_colors", []),
                "선호 성분": api_data.get("preferred_ingredients", []),
                "기피 성분": api_data.get("avoided_ingredients", []),
                "선호 향": api_data.get("preferred_scents", []),
                "가치관": api_data.get("values", []),
                "스킨케어 루틴": api_data.get("skincare_routine"),
                "주 활동 환경": api_data.get("main_environment"),
                "선호 제형(텍스처)": api_data.get("preferred_texture", []),
                "반려동물": api_data.get("pets"),
                "수면 시간": f"{api_data.get('avg_sleep_hours')}시간" if api_data.get('avg_sleep_hours') else None,
                "스트레스": api_data.get("stress_level"),
                "디지털 기기 사용": f"하루 {api_data.get('digital_device_usage_time')}시간" if api_data.get('digital_device_usage_time') else None,
                "쇼핑 스타일&예산": api_data.get("shopping_style"),
                "구매 결정 요인": api_data.get("purchase_decision_factors", [])
            }

            print(f"[INFO] 페르소나 정보 조회 성공: {persona_info.get('이름')}")
            return persona_info

        except Exception as e:
            print(f"[ERROR] 페르소나 정보 조회 실패: {e}")
            raise

    def get_existing_analysis(self, persona_id: str) -> Optional[Dict[str, Any]]:
        """DB에서 기존 분석 결과 조회 (가장 최신 결과 1개)"""
        try:
            response = requests.post(
                "http://host.docker.internal:8005/api/api/analysis-results/get",
                json={"persona_id": persona_id}
            )
            response.raise_for_status()
            results = response.json()

            if results and len(results) > 0:
                # 가장 최신 결과 반환 (이미 시간순 정렬되어 있음)
                return results[0]
            return None

        except requests.exceptions.HTTPException as e:
            if e.response.status_code == 404:
                return None
            print(f"[ERROR] 분석 결과 조회 실패: {e}")
            raise
        except Exception as e:
            print(f"[ERROR] 분석 결과 조회 실패: {e}")
            return None

    def save_analysis_result(self, persona_id: str, analysis_result: Dict[str, Any]) -> int:
        """분석 결과를 DB에 저장"""
        try:
            # JSON을 문자열로 변환
            analysis_result_text = json.dumps(analysis_result, ensure_ascii=False)

            response = requests.post(
                "http://host.docker.internal:8005/api/api/analysis-results/get",
                json={
                    "persona_id": persona_id,
                    "analysis_result": analysis_result_text
                }
            )
            response.raise_for_status()
            result = response.json()

            # analysis_id 반환
            return result.get("analysis_id")

        except Exception as e:
            print(f"[ERROR] 분석 결과 저장 실패: {e}")
            raise

    def save_search_queries(self, analysis_id: int, queries: List[str]) -> None:
        """검색 쿼리를 DB에 저장"""
        try:
            for query in queries:
                response = requests.post(
                    "http://host.docker.internal:8005/api/api/search-queries",
                    json={
                        "analysis_id": analysis_id,
                        "search_query": query
                    }
                )
                response.raise_for_status()

            print(f"[INFO] {len(queries)}개 쿼리 저장 완료")

        except Exception as e:
            print(f"[ERROR] 쿼리 저장 실패: {e}")
            raise

    def get_filtered_products(
        self,
        brands: Optional[List[str]] = None,
        product_categories: Optional[List[str]] = None,
        exclusive_target: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """필터 조건에 맞는 상품 조회"""
        filters = {}
        if brands:
            filters["brands"] = brands
        if product_categories:
            filters["product_categories"] = product_categories
        if exclusive_target:
            filters["exclusive_target"] = exclusive_target

        try:
            response = requests.post(
                "http://host.docker.internal:8005/api/api/products/filter",
                json=filters
            )
            response.raise_for_status()
            products = response.json()
            print(f"[INFO] 필터링된 상품 수: {len(products)}개")
            return products

        except Exception as e:
            print(f"[ERROR] 상품 필터링 실패: {e}")
            raise
        
    def recommend_persona(self, user_input: str, persona_id: str) -> Dict[str, Any]:
        """
        페르소나 기반 다단계 × 다차원 분석

        Args:
            user_input: 사용자 입력 텍스트 (예: "겨울철 건조한 피부에 좋은 크림 추천해줘")
            persona_id: 페르소나 ID

        Returns:
            Dict[str, Any]: 다단계 × 다차원 분석 결과
            {
                "multi_level_analysis": {
                    "basic_profile": {...},
                    "lifestyle_pattern": {...},
                    "beauty_needs": {...},
                    "situational_needs": {...},
                    "improvement_goals": {...}
                },
                "multi_dimensional_analysis": {
                    "skin_science": {...},
                    "ingredients": {...},
                    "lifestyle": {...},
                    "values_emotion": {...},
                    "color_makeup": {...},
                    "price_value": {...},
                    "usability": {...},
                    "safety_risk": {...}
                }
            }
        """
        # 1. 페르소나 정보 가져오기
        persona_info = self.get_persona_info(persona_id)

        # 2. 프롬프트 생성
        prompt = self._build_analysis_prompt(user_input, persona_info)

        # 3. LLM 호출하여 분석 수행
        response = self.llm.invoke(prompt)

        # 4. 응답 파싱 (JSON 형태로 받음)
        try:
            result = json.loads(response.content)
            print(f"[INFO] 페르소나 분석 완료")
            print(f"  - 다단계 분석: {len(result.get('multi_level_analysis', {}))}개 레벨")
            print(f"  - 다차원 분석: {len(result.get('multi_dimensional_analysis', {}))}개 차원")
            return result
        except json.JSONDecodeError:
            print(f"[ERROR] LLM 응답 파싱 실패: {response.content}")
            # 폴백: 빈 분석 결과 반환
            return {
                "multi_level_analysis": {},
                "multi_dimensional_analysis": {}
            }

    def _build_analysis_prompt(self, user_input: str, persona_info: Dict[str, Any]) -> str:
        """다단계 × 다차원 분석을 위한 프롬프트 구성"""

        prompt = f"""당신은 뷰티 전문가입니다. 사용자의 요청과 페르소나 정보를 분석하여 다단계 × 다차원 분석 결과를 생성하세요.

**사용자 요청:**
{user_input}

**페르소나 정보:**
{json.dumps(persona_info, ensure_ascii=False, indent=2)}

---

## 분석 프레임워크

### [1단계] 다단계 페르소나 분석

1️⃣ **기본 프로필 (basic_profile)**
   - 나이, 성별, 직업에서 추론되는 라이프스타일
   - 핵심 특징 3가지

2️⃣ **라이프스타일 패턴 (lifestyle_pattern)**
   - 수면 시간, 스트레스, 디지털 기기 사용
   - 주 활동 환경에서 파악되는 환경적 요인
   - 일상 루틴의 특징

3️⃣ **뷰티 니즈 심층 분석 (beauty_needs)**
   - 피부타입 + 고민 키워드 → 핵심 니즈
   - 퍼스널 컬러 + 선호 색상 → 색조 니즈
   - 우선순위 TOP 3

4️⃣ **상황별 니즈 (situational_needs)**
   - 스킨케어 루틴 → 사용 시점/단계별 요구사항
   - 반려동물, 환경 → 특수 요구사항
   - 시간대/상황별 니즈

5️⃣ **개선 목표 (improvement_goals)**
   - 고민 키워드에서 도출되는 해결 목표
   - 가치관에서 추구하는 방향성
   - 단기/중기 목표

### [2단계] 다차원 제품 분석

🔬 **피부 과학 차원 (skin_science)**
   - 피부타입별 적합성
   - 고민 해결 메커니즘
   - 필요한 기능성 성분

🧪 **성분 차원 (ingredients)**
   - 선호 성분 매칭 (효과/안전성)
   - 기피 성분 회피 전략
   - 유효 성분 조합 추천

🌱 **라이프스타일 차원 (lifestyle)**
   - 루틴 적합성 (아침/저녁, 소요 시간)
   - 환경 적합성 (실내/야외, 계절)
   - 사용 빈도 및 편의성

💝 **감성/가치관 차원 (values_emotion)**
   - 비건, 크루얼티프리, 친환경 등 가치 매칭
   - 브랜드 철학 선호도
   - 감성적 만족 요소

🎨 **색조 차원 (color_makeup)**
   - 퍼스널 컬러 매칭
   - 베이스 호수 정보
   - 선호 색상/질감

💰 **가격/가성비 차원 (price_value)**
   - 쇼핑 스타일 & 예산 범위
   - 구매 결정 요인 (가격/품질/리뷰 등)
   - 가성비 우선순위

⚡ **사용 편의성 차원 (usability)**
   - 선호 제형/텍스처
   - 휴대성, 사용 간편성
   - 적용 시간 및 흡수력

🛡️ **안전성/리스크 차원 (safety_risk)**
   - 민감도 고려사항
   - 반려동물 안전성 (해당 시)
   - 알레르기/자극 위험 요소

---

## 출력 형식 (JSON)

다음 형식으로 응답하세요:

{{
  "multi_level_analysis": {{
    "basic_profile": {{
      "inferred_lifestyle": "추론된 라이프스타일",
      "key_characteristics": ["특징1", "특징2", "특징3"]
    }},
    "lifestyle_pattern": {{
      "environmental_factors": ["요인1", "요인2"],
      "daily_routine_features": "루틴 특징 설명"
    }},
    "beauty_needs": {{
      "core_skincare_needs": ["니즈1", "니즈2"],
      "makeup_needs": ["니즈1", "니즈2"],
      "priority_top3": ["1순위", "2순위", "3순위"]
    }},
    "situational_needs": {{
      "routine_requirements": {{"morning": "아침 요구사항", "evening": "저녁 요구사항"}},
      "special_requirements": ["특수 요구사항1", "특수 요구사항2"]
    }},
    "improvement_goals": {{
      "short_term": ["단기 목표1", "단기 목표2"],
      "mid_term": ["중기 목표1", "중기 목표2"],
      "value_direction": "가치관 기반 방향성"
    }}
  }},
  "multi_dimensional_analysis": {{
    "skin_science": {{
      "skin_type_compatibility": "피부타입 적합성 설명",
      "problem_solving_mechanism": ["메커니즘1", "메커니즘2"],
      "required_functional_ingredients": ["성분1", "성분2"]
    }},
    "ingredients": {{
      "preferred_match": ["선호 성분1 + 효과", "선호 성분2 + 효과"],
      "avoid_strategy": ["기피 성분1 회피 방법", "기피 성분2 회피 방법"],
      "effective_combination": ["조합1", "조합2"]
    }},
    "lifestyle": {{
      "routine_fit": {{"morning": "아침 적합도", "evening": "저녁 적합도"}},
      "environment_fit": "환경 적합성",
      "usage_convenience": "사용 편의성 평가"
    }},
    "values_emotion": {{
      "value_match": ["가치 매칭1", "가치 매칭2"],
      "brand_philosophy_preference": "브랜드 철학 선호",
      "emotional_satisfaction": ["감성 요소1", "감성 요소2"]
    }},
    "color_makeup": {{
      "personal_color_match": "퍼스널 컬러 매칭 정보",
      "base_shade": "베이스 호수 정보",
      "preferred_colors_textures": ["색상/질감1", "색상/질감2"]
    }},
    "price_value": {{
      "budget_range": "예산 범위",
      "purchase_decision_factors": ["요인1", "요인2"],
      "value_priority": "가성비 우선순위"
    }},
    "usability": {{
      "preferred_formulation": ["제형1", "제형2"],
      "portability_convenience": "휴대성/간편성",
      "application_absorption": "적용/흡수 특성"
    }},
    "safety_risk": {{
      "sensitivity_considerations": ["고려사항1", "고려사항2"],
      "pet_safety": "반려동물 안전성 (해당 시)",
      "allergy_irritation_risks": ["위험요소1", "위험요소2"]
    }}
  }}
}}

**중요:**
- 반드시 JSON 형식으로만 응답하세요.
- 모든 분석 항목을 빠짐없이 채워주세요.
- 페르소나 정보와 사용자 요청을 종합적으로 고려하여 분석하세요.
"""

        return prompt

    def generate_multi_queries(
        self,
        user_input: str,
        analysis_result: Dict[str, Any],
        product_categories: Optional[List[str]] = None
    ) -> List[str]:
        """
        분석 결과를 기반으로 멀티 쿼리 생성

        Args:
            user_input: 사용자 입력 텍스트
            analysis_result: recommend_persona 함수의 분석 결과
            product_categories: 제품 카테고리 리스트 (선택, 예: ["스킨케어-크림", "메이크업-립스틱"])

        Returns:
            List[str]: 3~5개의 다각도 검색 쿼리
        """
        # 프롬프트 생성
        prompt = self._build_multi_query_prompt(user_input, analysis_result, product_categories)

        # LLM 호출하여 멀티 쿼리 생성
        response = self.llm.invoke(prompt)

        # 응답 파싱
        try:
            result = json.loads(response.content)
            queries = result.get("queries", [])
            print(f"[INFO] 생성된 쿼리 수: {len(queries)}개")
            for i, q in enumerate(queries, 1):
                print(f"  {i}. {q}")
            return queries
        except json.JSONDecodeError:
            print(f"[ERROR] LLM 응답 파싱 실패: {response.content}")
            # 폴백: 사용자 입력을 기본 쿼리로 사용
            return [user_input]

    def _build_multi_query_prompt(
        self,
        user_input: str,
        analysis_result: Dict[str, Any],
        product_categories: Optional[List[str]] = None
    ) -> str:
        """멀티 쿼리 생성을 위한 프롬프트 구성"""

        # 제품 카테고리 정보 추가
        category_info = ""
        if product_categories:
            category_info = f"""
**제품 카테고리 (필수 고려):**
{json.dumps(product_categories, ensure_ascii=False, indent=2)}
→ 쿼리는 반드시 이 카테고리에 맞춰 생성해야 합니다.
"""

        prompt = f"""당신은 뷰티 전문가입니다. 사용자의 요청과 페르소나 분석 결과를 바탕으로 최적의 제품을 찾기 위한 3~5개의 검색 쿼리를 생성하세요.

**사용자 요청:**
{user_input}
{category_info}
**페르소나 분석 결과:**
{json.dumps(analysis_result, ensure_ascii=False, indent=2)}

---

## 쿼리 생성 가이드

### 페르소나 분석 결과 활용
위에서 제공된 페르소나 분석 결과는 이미 다단계(5단계) × 다차원(8차원) 분석이 완료된 상태입니다.
- **multi_level_analysis**: 기본 프로필, 라이프스타일 패턴, 뷰티 니즈, 상황별 니즈, 개선 목표
- **multi_dimensional_analysis**: 피부 과학, 성분, 라이프스타일, 감성/가치관, 색조, 가격/가성비, 사용 편의성, 안전성/리스크

### 제품 카테고리 최적화
**중요:** 제품 카테고리가 제공된 경우, 모든 쿼리는 해당 카테고리에 맞춰 생성해야 합니다.
- 예: "스킨케어-크림" → 크림 관련 키워드 중심 (보습, 텍스처, 흡수력 등)
- 예: "메이크업-립스틱" → 립스틱 관련 키워드 중심 (색상, 지속력, 발색 등)

### 크로스 매칭 전략
분석 결과의 여러 차원을 조합하여 **3~5개의 서로 다른 관점의 쿼리**를 생성하세요.

**쿼리 생성 원칙:**
1. 각 쿼리는 분석 결과의 2~3개 차원을 조합
2. 서로 다른 우선순위/관점 반영
3. 구체적이고 검색 가능한 키워드 사용
4. 제품 카테고리가 있다면 필수 반영

**예시 조합 패턴:**
- 쿼리1: 피부 과학 차원 + 성분 차원 + 가치관 차원
- 쿼리2: 라이프스타일 차원 + 사용 편의성 차원 + 가격 차원
- 쿼리3: 색조 차원 + 감성 차원 + 안전성 차원
- 쿼리4: 뷰티 니즈 + 선호 제형 + 루틴 적합성
- 쿼리5: 환경 적합성 + 성분 + 브랜드 가치

**쿼리 예시 (제품 카테고리: "스킨케어-크림"):**
- "건성 피부 세라마이드 고보습 크림 비건 인증"
- "저자극 수분크림 간편한 아침 루틴 가성비"
- "민감성 피부 무향 크림 반려동물 안전"

---

## 출력 형식 (JSON)

다음 형식으로 응답하세요:

{{
  "queries": [
    "쿼리1: 구체적인 검색 키워드 조합",
    "쿼리2: 다른 관점의 키워드 조합",
    "쿼리3: 또 다른 관점의 키워드 조합",
    "쿼리4: 추가 관점 (선택)",
    "쿼리5: 추가 관점 (선택)"
  ]
}}

**중요:**
- 반드시 JSON 형식으로만 응답하세요.
- queries 배열에 3~5개의 문자열을 포함하세요.
- 각 쿼리는 실제 제품 검색에 사용될 구체적인 키워드여야 합니다.
"""

        return prompt

    def search_with_multi_queries(
        self,
        queries: List[str],
        brands: Optional[List[str]] = None,
        product_categories: Optional[List[str]] = None,
        exclusive_target: Optional[str] = None,
        top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """
        멀티 쿼리로 벡터 검색 수행 및 결과 병합

        Args:
            queries: 검색 쿼리 리스트 (3~5개)
            brands: 브랜드 필터 (선택)
            product_categories: 상품 카테고리 필터 (선택)
            exclusive_target: 타겟 필터 (선택)
            top_k: 각 쿼리당 가져올 상품 수

        Returns:
            List[Dict[str, Any]]: 중복 제거된 검색 결과 (스코어 높은 순)
            [
                {
                    "product_id": "PROD001",
                    "score": 0.95,
                    ...
                }
            ]
        """
        # 1. 필터링된 상품 조회
        filtered_products = self.get_filtered_products(
            brands=brands,
            product_categories=product_categories,
            exclusive_target=exclusive_target
        )
        product_ids = [p["product_id"] for p in filtered_products]

        if not product_ids:
            print("[WARNING] 필터링 결과 상품이 없습니다.")
            return []

        all_results = []

        # 2. 각 쿼리로 검색 수행
        for i, query in enumerate(queries, 1):
            print(f"[INFO] 쿼리 {i}/{len(queries)} 검색 중: {query}")
            try:
                response = requests.post(
                    "http://host.docker.internal:8010/api/search/product-ids",
                    json={
                        "index_name": "product_index",
                        "pipeline_id": "hybrid-minmax-pipeline",
                        "product_ids": product_ids,
                        "query": query,
                        "top_k": top_k
                    }
                )
                response.raise_for_status()
                api_response = response.json()

                # 응답 형식 처리
                if isinstance(api_response, dict) and "results" in api_response:
                    results = api_response["results"]
                else:
                    results = api_response

                # 결과를 전체 리스트에 추가
                all_results.extend(results)
                print(f"  → {len(results)}개 상품 검색됨")

            except Exception as e:
                print(f"[ERROR] 쿼리 {i} 검색 실패: {e}")
                continue

        # 중복 제거: product_id별로 최고 스코어만 유지
        product_score_map = {}
        for result in all_results:
            product_id = result.get("product_id")
            score = result.get("score", 0)

            if product_id not in product_score_map:
                product_score_map[product_id] = result
            else:
                # 기존 스코어보다 높으면 교체
                if score > product_score_map[product_id].get("score", 0):
                    product_score_map[product_id] = result

        # 스코어 높은 순으로 정렬
        merged_results = sorted(
            product_score_map.values(),
            key=lambda x: x.get("score", 0),
            reverse=True
        )

        print(f"[INFO] 멀티 쿼리 검색 완료")
        print(f"  - 전체 검색 결과: {len(all_results)}개")
        print(f"  - 중복 제거 후: {len(merged_results)}개")

        return merged_results

    def merge_product_data(
        self,
        search_results: List[Dict[str, Any]],
        all_products: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """검색 결과와 전체 상품 데이터 병합"""
        product_map = {p["product_id"]: p for p in all_products}

        merged = []
        for result in search_results:
            product_id = result.get("product_id")
            if product_id in product_map:
                product_data = product_map[product_id].copy()
                product_data["vector_search_score"] = result.get("score")
                merged.append(product_data)

        print(f"[INFO] 상품 데이터 병합 완료: {len(merged)}개")
        return merged