#!/usr/bin/env python3
"""
상품 문서를 분석하여 페르소나 태그를 추가하는 스크립트
"""

import json
import time
import os
from pathlib import Path
from typing import Dict, Optional
from openai import OpenAI
from dotenv import load_dotenv


class PersonaTagger:
    def __init__(self):
        # .env 파일 로드
        env_path = Path(__file__).parent / '.env'
        load_dotenv(env_path)

        # 환경변수에서 API 키 읽기
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다. .env 파일을 확인하세요.")
        self.client = OpenAI(api_key=api_key)
        self.persona_prompt = """# 역할
당신은 화장품 상품 문서를 분석하여 관련 태그를 추출하는 전문 태그 분류기입니다.

# 작업 지침
상품 문서를 정밀하게 분석하여 문서 내용과 관련된 모든 태그를 식별하고 분류합니다.

## 태깅 규칙
1. **명시적 언급**: 문서에 직접적으로 언급된 키워드를 우선 태깅
2. **맥락적 추론**: 문서의 설명이나 효능/효과에서 암묵적으로 해당하는 태그 포함
3. **중복 태깅 허용**: 하나의 문서에 여러 태그가 해당될 경우 모두 태깅
4. **근거 기반 태깅**: 추측이 아닌 문서 내용에 근거한 태깅만 수행

## 특수 태깅 규칙
- **선호포인트색상**: 메이크업 제품(립스틱, 아이섀도우, 블러셔, 틴트 등)에만 적용
  - 제품의 색상 포인트나 컬러 라인업이 강조될 때 태깅
  - 스킨케어 제품의 패키징 색상은 태깅 제외
- 베이비 태그는 아기(인간)도 사용할 수 있다는 내용이 포함된 제품만 태깅
- 전용제품의 태그는 중복 태깅할 수 없다.

# 기준 태그 카테고리

**피부타입**
[건성, 중성, 복합성, 지성, 민감성, 악건성, 트러블성, 수분부족지성]

**고민키워드**
[잡티, 미백, 주름, 각질, 여드름, 블랙헤드, 피지과다, 아토피, 민감성, 다크서클, 기미, 홍조, 유수분밸런스, 탄력, 트러블자국, 비듬, 탈모]

**메이크업선호포인트색상**
[레드, 핑크, 코랄, 오렌지, 베이지, 브라운]

**선호성분**
[히알루론산, 나이아신아마이드, 레티놀, 비타민C, 펩타이드, 시카, 티트리, 세라마이드, 콜라겐, 알부틴]

**기피성분**
[파라벤, 알코올, 인공향료, 인공색소, 미네랄오일, 실리콘, SLS/SLES, 합성방부제]

**선호향**
[무향, 플로럴, 시트러스, 허브, 우디, 머스크]

**가치관**
[천연/유기농, 비건/크루얼티프리, 친환경패키징, 임산부/수유부]

**전용제품**
[남성, 베이비, 반려동물]

# 출력 형식
반드시 아래의 JSON 형식으로 출력하세요:
```json
{
  "피부타입": [],
  "고민키워드": [],
  "선호포인트색상": [],
  "선호성분": [],
  "기피성분": [],
  "선호향": [],
  "가치관": [],
  "전용제품": []
}
```

# 출력 예시
```json
{
  "피부타입": ["건성", "민감성"],
  "고민키워드": ["주름", "탄력"],
  "선호포인트색상": [],
  "선호성분": ["히알루론산", "펩타이드"],
  "기피성분": ["파라벤", "인공향료"],
  "선호향": ["무향"],
  "가치관": ["비건/크루얼티프리"],
  "전용제품": []
}
```

# 주의사항
- 해당하는 태그가 없는 카테고리는 빈 배열([])로 출력
- 태그명은 기준 태그와 정확히 일치해야 함
- JSON 형식 외 다른 텍스트는 출력하지 않음"""

    def extract_persona_tags(self, document: str) -> Optional[Dict]:
        """
        GPT-4o-mini를 사용하여 문서에서 페르소나 태그 추출

        Args:
            document: 상품 문서 텍스트

        Returns:
            페르소나 태그 딕셔너리 또는 None
        """
        if not document or document.strip() == "":
            return {
                "피부타입": [],
                "고민키워드": [],
                "선호포인트색상": [],
                "선호성분": [],
                "기피성분": [],
                "선호향": [],
                "가치관": [],
                "전용제품": []
            }

        try:
            response = self.client.chat.completions.create(
                model="gpt-5.1",
                messages=[
                    {
                        "role": "system",
                        "content": self.persona_prompt
                    },
                    {
                        "role": "user",
                        "content": f"다음 상품 문서를 분석하여 페르소나 태그를 추출해주세요:\n\n{document}"
                    }
                ],
                temperature=0
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

            # JSON 파싱
            persona_tags = json.loads(result)
            return persona_tags

        except Exception as e:
            print(f"  [오류] 페르소나 태그 추출 실패: {e}")
            return None

    def process_all(self, input_file: Path, output_file: Path) -> None:
        """
        모든 상품에 페르소나 태그 추가

        Args:
            input_file: 입력 JSONL 파일
            output_file: 출력 JSONL 파일
        """
        print(f"입력 파일: {input_file}")
        print(f"출력 파일: {output_file}")

        if not input_file.exists():
            print(f"오류: 입력 파일이 존재하지 않습니다: {input_file}")
            return

        # 데이터 로드
        records = []
        with open(input_file, 'r', encoding='utf-8') as f:
            for line in f:
                records.append(json.loads(line.strip()))

        print(f"총 {len(records)}개 레코드 로드 완료\n")

        # 페르소나 태그 추가
        results = []
        success_count = 0
        fail_count = 0

        for i, record in enumerate(records, 1):
            url = record.get('url', '')
            product_name = record.get('상품명', '')
            document = record.get('document', '')
            tag = record.get('tag', '')

            print(f"[{i}/{len(records)}] {product_name}")

            # 페르소나 태그 추출
            persona_tags = self.extract_persona_tags(document)

            if persona_tags is not None:
                # 결과 생성 (url, 상품명, document, tag, 페르소나태그만 포함)
                result = {
                    'url': url,
                    '상품명': product_name,
                    'document': document,
                    'tag': tag,
                    '페르소나태그': persona_tags
                }
                results.append(result)
                success_count += 1
                print(f"  성공")
            else:
                # 실패한 경우에도 빈 페르소나 태그로 추가
                result = {
                    'url': url,
                    '상품명': product_name,
                    'document': document,
                    'tag': tag,
                    '페르소나태그': {
                        "피부타입": [],
                        "고민키워드": [],
                        "선호포인트색상": [],
                        "선호성분": [],
                        "기피성분": [],
                        "선호향": [],
                        "가치관": [],
                        "전용제품": []
                    }
                }
                results.append(result)
                fail_count += 1
                print(f"  실패 (빈 태그로 처리)")

            # API 호출 제한 방지
            time.sleep(0.5)

        # 결과 저장
        print(f"\n결과 저장 중...")
        with open(output_file, 'w', encoding='utf-8') as f:
            for item in results:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')

        print(f"\n완료!")
        print(f"총 처리: {len(results)}개")
        print(f"성공: {success_count}개")
        print(f"실패: {fail_count}개")
        print(f"저장 경로: {output_file}")


if __name__ == "__main__":
    # 파일 경로 설정
    BASE_DIR = Path(__file__).parent
    CRAWLING_DIR = BASE_DIR.parent / "crawling_result"

    input_file = CRAWLING_DIR / "product_data_251225a.jsonl"
    output_file = CRAWLING_DIR / "product_data_251225a_with_persona_tags.jsonl"

    # 페르소나 태거 실행
    tagger = PersonaTagger()
    tagger.process_all(input_file, output_file)
