import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from typing import Dict, List, Optional, Tuple
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
from difflib import SequenceMatcher
import json
import os
import time
import re

load_dotenv()

class AutoTagger:
    """
    GPT-5-mini를 사용한 자동 태그 분류 시스템
    """
    def __init__(self):
        """
        OpenAI API 클라이언트 초기화 및 카테고리 로드
        """
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다.")
        self.client = OpenAI(api_key=api_key)
        self.categories = self.load_categories()
        self.documents = self.load_documents()

    def load_categories(self) -> List[str]:
        """카테고리 파일 로드 (JSON)"""
        BASE_DIR = Path(__file__).parent.parent
        category_file = BASE_DIR / "tag" / "categories.json"

        print(f"카테고리 파일 로드: {category_file}")

        if not category_file.exists():
            raise FileNotFoundError(f"카테고리 파일을 찾을 수 없습니다: {category_file}")

        with open(category_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            categories = data.get('categories', [])

        print(f"총 {len(categories)}개 카테고리 로드 완료\n")
        return categories

    def load_documents(self) -> List[Dict]:
        """생성된 상품 문서 로드"""
        BASE_DIR = Path(__file__).parent.parent
        input_file = BASE_DIR / "create_product_document" / "product_documents_v4.jsonl"

        print(f"문서 파일 로드: {input_file}")

        if not input_file.exists():
            raise FileNotFoundError(f"문서 파일을 찾을 수 없습니다: {input_file}")

        documents = []
        with open(input_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    documents.append(json.loads(line))

        print(f"총 {len(documents)}개 문서 로드 완료\n")
        return documents

    def calculate_similarity(self, str1: str, str2: str) -> float:
        """
        두 문자열 간의 유사도 계산 (0.0 ~ 1.0)
        """
        return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()

    def find_best_match(self, tag: str, threshold: float = 0.6) -> Tuple[str, float]:
        """
        GPT 출력 태그와 가장 유사한 카테고리 찾기

        Args:
            tag: GPT가 반환한 태그
            threshold: 최소 유사도 임계값

        Returns:
            (매칭된 카테고리, 유사도) 튜플
        """
        best_match = None
        best_score = 0.0

        for category in self.categories:
            score = self.calculate_similarity(tag, category)
            if score > best_score:
                best_score = score
                best_match = category

        # 임계값 이상인 경우에만 반환
        if best_score >= threshold:
            return best_match, best_score
        else:
            return tag, best_score  # 원본 반환

    def flatten_tags(self, tags: List) -> List:
        """
        중첩된 리스트를 평탄화

        Args:
            tags: 중첩될 수 있는 태그 리스트

        Returns:
            평탄화된 태그 리스트
        """
        flattened = []
        for tag in tags:
            if isinstance(tag, list):
                # 재귀적으로 평탄화
                flattened.extend(self.flatten_tags(tag))
            else:
                flattened.append(tag)
        return flattened

    def validate_and_correct_tags(self, tags: List) -> Tuple[List[str], List[str]]:
        """
        태그 검증 및 보정

        Args:
            tags: GPT가 반환한 태그 리스트 (문자열 또는 딕셔너리)

        Returns:
            (보정된 태그 리스트, 보정 로그 리스트)
        """
        corrected_tags = []
        correction_logs = []

        # 먼저 중첩된 리스트 평탄화
        original_length = len(tags)
        tags = self.flatten_tags(tags)
        if len(tags) != original_length:
            correction_logs.append(f"INFO 중첩 리스트 평탄화: {original_length}개 -> {len(tags)}개")

        for tag in tags:
            # 타입 체크 및 문자열 변환
            if isinstance(tag, dict):
                # 딕셔너리인 경우: 가능한 키에서 값 추출 시도
                possible_keys = ['category', 'name', 'tag', '카테고리', '태그']
                tag_str = None
                for key in possible_keys:
                    if key in tag:
                        tag_str = str(tag[key])
                        break

                if tag_str is None:
                    # 키를 찾지 못한 경우: 첫 번째 값 사용
                    if tag:
                        tag_str = str(list(tag.values())[0])
                    else:
                        correction_logs.append(f"FAIL 빈 딕셔너리 -> '미분류'")
                        corrected_tags.append("미분류")
                        continue

                correction_logs.append(f"INFO 딕셔너리 변환: {tag} -> '{tag_str}'")
                tag = tag_str
            elif not isinstance(tag, str):
                # 문자열이 아닌 다른 타입: 문자열로 변환
                tag_str = str(tag)
                correction_logs.append(f"INFO 타입 변환: {type(tag).__name__} -> '{tag_str}'")
                tag = tag_str

            # 정확히 일치하는 경우
            if tag in self.categories:
                corrected_tags.append(tag)
                correction_logs.append(f"OK '{tag}' (정확 일치)")
            else:
                # 유사도 매칭
                matched_category, score = self.find_best_match(tag, threshold=0.6)

                if matched_category != tag:
                    corrected_tags.append(matched_category)
                    correction_logs.append(f"-> '{tag}' -> '{matched_category}' (유사도: {score:.2f})")
                else:
                    # 매칭 실패 - 가장 유사한 것으로 대체
                    if score > 0:
                        corrected_tags.append(matched_category)
                        correction_logs.append(f"WARN '{tag}' -> '{matched_category}' (낮은 유사도: {score:.2f})")
                    else:
                        corrected_tags.append("미분류")
                        correction_logs.append(f"FAIL '{tag}' -> '미분류' (매칭 실패)")

        return corrected_tags, correction_logs

    def classify_product(self, document: Dict) -> Tuple[List[str], List[str]]:
        """
        GPT-5-mini를 사용하여 상품 분류 + 유사도 검증

        Args:
            document: 상품 문서 (브랜드, 상품명, 생성된_문서 포함)

        Returns:
            (보정된 태그 리스트, 보정 로그 리스트)
        """
        brand = document.get('브랜드', '')
        product_name = document.get('상품명', '')
        product_doc = document.get('생성된_문서', '')

        # 카테고리 리스트를 JSON 형식으로 변환
        categories_json = json.dumps(self.categories, ensure_ascii=False)

        # GPT-5-mini에게 분류 요청
        prompt = f"""당신은 화장품/뷰티 상품 분류 전문가입니다.

[사용 가능한 카테고리 목록]
{categories_json}

[분류할 상품]
브랜드: {brand}
상품명: {product_name}

상품 문서:
{product_doc[:2000]}

[분류 단계]
1. 상품의 '브랜드', '상품명', '문서 내용'을 분석하십시오.
2. 이 상품이 스킨케어, 메이크업, 헤어, 바디, 반려동물, 전자기기, 기타 중 어디에 속하는지 먼저 생각하십시오.
3. 그 후, 위 [사용 가능한 카테고리 목록]에서 가장 적합한 카테고리를 1개만 선택하십시오.
4. 전자기기/디바이스 상품은 "뷰티디바이스"로 분류
5. 상품명/정보에 '세트','기획','N종' 포함 시 구성품을 고려하여 "스킨케어세트","향수세트","브러쉬세트","차세트" 중 선택


[출력 형식]
- 반드시 문자열로만 출력
- 1상품당 1개 카테고리만
- 색상 정보 제외

출력 예시:
"스킨&토너"

출력:"""

        try:
            response = self.client.chat.completions.create(
                model="gpt-5-mini",
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            result = response.choices[0].message.content.strip()

            # JSON 파싱
            # ```json ``` 마크다운 제거
            if result.startswith("```json"):
                result = result[7:]
            if result.startswith("```"):
                result = result[3:]
            if result.endswith("```"):
                result = result[:-3]
            result = result.strip()

            # JSON 또는 문자열 파싱 시도
            try:
                parsed = json.loads(result)
                # JSON 배열인 경우 (색상 정보 포함)
                if isinstance(parsed, list):
                    tags = parsed
                # JSON 문자열인 경우 (일반 카테고리)
                elif isinstance(parsed, str):
                    tags = parsed
                else:
                    tags = [parsed]
            except json.JSONDecodeError:
                # JSON이 아닌 경우 순수 문자열로 처리
                if result.startswith('"') and result.endswith('"'):
                    tags = result[1:-1]  # 따옴표 제거
                else:
                    tags = result

            # 타입별 처리
            if isinstance(tags, str):
                # 문자열인 경우
                corrected_tags, correction_logs = self.validate_and_correct_tags([tags])
                return corrected_tags[0], correction_logs

            elif isinstance(tags, list):
                # 리스트인 경우 첫 번째 요소만 사용
                if len(tags) == 0:
                    return "미분류", [f"FAIL 빈 태그 리스트"]

                corrected_tags, correction_logs = self.validate_and_correct_tags([tags[0]])
                return corrected_tags[0], correction_logs  # 문자열로 반환

            else:
                return "미분류", [f"FAIL 예상치 못한 타입: {type(tags).__name__}"]

        except Exception as e:
            print(f"  [경고] 분류 실패: {e}")
            print(f"  에러 타입: {type(e).__name__}")
            import traceback
            print(f"  상세 트레이스백:")
            traceback.print_exc()
            return ["미분류"], [f"FAIL 에러: {type(e).__name__}: {str(e)}"]

    def process_all(self):
        """모든 문서 처리"""
        results = []
        start_time = datetime.now()

        print("=" * 60)
        print("상품 자동 태깅 시작")
        print("=" * 60)
        print(f"처리 문서 수: {len(self.documents)}개")
        print(f"모델: gpt-5-mini")
        print(f"시작 시간: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        print()

        for idx, doc in enumerate(self.documents, 1):
            try:
                brand = doc.get('브랜드', '')
                product_name = doc.get('상품명', '')

                print(f"[{idx}/{len(self.documents)}] {brand} - {product_name[:40]}{'...' if len(product_name) > 40 else ''}")

                # 태그 분류 + 유사도 검증
                tags, _ = self.classify_product(doc)

                # 결과 저장
                result = {
                    '브랜드': brand,
                    '상품명': product_name,
                    '생성된_문서': doc.get('생성된_문서', ''),
                    '태그': tags
                }
                results.append(result)

                # 태그 출력
                print(f"  OK 태그: {tags}\n")

                # API 호출 제한 방지
                time.sleep(0.5)

            except Exception as e:
                print(f"  [ERROR] 실패: {str(e)}\n")
                # 실패해도 원본 데이터는 유지
                result = {
                    '브랜드': doc.get('브랜드', ''),
                    '상품명': doc.get('상품명', ''),
                    '생성된_문서': doc.get('생성된_문서', ''),
                    '태그': ["미분류"]
                }
                results.append(result)

        # 결과 저장
        self.save_results(results, start_time)

        return results

    def save_results(self, results: List[Dict], start_time: datetime):
        """결과를 JSONL 파일로 저장"""
        BASE_DIR = Path(__file__).parent.parent
        output_path = BASE_DIR / "data" / "product_document" / "product_documents_v4_tagged.jsonl"

        print("=" * 60)
        print("결과 저장 중...")
        print("=" * 60)

        with open(output_path, 'w', encoding='utf-8') as f:
            for item in results:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')

        print(f"OK 총 {len(results)}개의 상품이 태깅되었습니다.")
        print(f"  저장 경로: {output_path}")

if __name__ == "__main__":
    tagger = AutoTagger()
    tagger.process_all()
