# 이미지 컬러 추출 가이드

이 스크립트는 화장품 제품 이미지의 URL로부터 GPT-4o-mini Vision API를 사용하여 컬러값을 자동으로 추출합니다.

## 📋 개요

- **입력 파일**: `product_documents_included_tags_with_color_RE.jsonl`
- **출력 파일**: `product_documents_with_extracted_colors.jsonl`
- **작동 방식**: 각 제품의 `color_info.colors` 리스트에 있는 이미지 URL을 직접 GPT Vision API에 전달하여 컬러 정보를 추출하고 원본 데이터에 추가

## 🚀 사용 방법

### 1단계: 환경 설정

#### 필요한 패키지 설치

```bash
cd data/color_product
pip install -r requirements.txt
```

#### API 키 설정

프로젝트 루트 디렉토리에 `.env` 파일을 생성하고 OpenAI API 키를 추가합니다:

```bash
# .env 파일
OPENAI_API_KEY=your_api_key_here
```

### 2단계: 스크립트 실행

```bash
python extract_image_colors.py
```

## 📊 출력 데이터 구조

스크립트는 원본 데이터의 각 색상 항목에 `extracted_colors` 필드를 추가합니다:

### 원본 데이터 구조
```json
{
  "브랜드": "라네즈",
  "상품명": "...",
  "color_info": {
    "colors": [
      {
        "color_name": "스트로베리 스프링클",
        "image_url": "https://example.com/image.png"
      }
    ]
  }
}
```

### 처리 후 데이터 구조
```json
{
  "브랜드": "라네즈",
  "상품명": "...",
  "color_info": {
    "colors": [
      {
        "color_name": "스트로베리 스프링클",
        "image_url": "https://example.com/image.png",
        "extracted_color": {
          "color": {
            "hex": "#FF6B9D",
            "rgb": [255, 107, 157],
            "hsv": { "h": 340, "s": 58, "v": 100 },
            "lab": { "l": 62.3, "a": 45.2, "b": -5.8 }
          }
        }
      }
    ]
  }
}
```

## 🔧 스크립트 커스터마이징

### 처리할 레코드 수 조정

스크립트의 `main()` 함수에서 `max_records` 파라미터를 수정합니다:

```python
# 테스트용: 처음 3개만 처리
process_jsonl_file(
    input_file=input_file,
    output_file=output_file,
    max_records=3
)

# 전체 처리
process_jsonl_file(
    input_file=input_file,
    output_file=output_file,
    max_records=None
)
```

### 파일 경로 변경

`main()` 함수에서 입력/출력 파일 경로를 수정합니다:

```python
input_file = "./your_input_file.jsonl"
output_file = "./your_output_file.jsonl"
```

## 📈 추출되는 컬러 정보

각 이미지에서 다음 정보가 추출됩니다:

**color 객체**:
1. **hex**: HEX 색상 코드 (예: `"#FF6B9D"`)
2. **rgb**: RGB 색상 배열 (예: `[255, 107, 157]`)
3. **hsv**: HSV 색상 객체
   - `h`: 색상 (0-360)
   - `s`: 채도 (0-100)
   - `v`: 명도 (0-100)
4. **lab**: LAB 색상 객체
   - `l`: 명도 (0-100)
   - `a`: 녹색-빨강 축 (-128 to 127)
   - `b`: 파랑-노랑 축 (-128 to 127)

**특징**:
- 색조 제품의 실제 색상만 분석 (패키지/케이스/배경 제외)
- 모든 값은 null 없이 숫자로 출력

## ⚠️ 주의사항

1. **API 비용**: GPT-4o-mini API 호출은 비용이 발생합니다. 테스트 시에는 `max_records`를 작게 설정하세요.

2. **처리 시간**:
   - API 호출로 인해 대량의 데이터 처리 시 시간이 오래 걸릴 수 있습니다.
   - 각 이미지 처리 후 3초 대기하므로 100개 이미지는 약 5분 소요됩니다.

3. **Rate Limit 관리**:
   - OpenAI API에는 분당 토큰 제한이 있습니다 (예: 200,000 TPM)
   - 스크립트는 자동으로 Rate limit 감지 시 재시도합니다 (5초 → 10초 → 15초 대기)
   - 각 이미지 처리 후 3초 자동 대기하여 Rate limit 방지
   - 대기 시간은 `delay_seconds` 파라미터로 조정 가능

4. **이미지 URL**: GPT Vision API가 직접 이미지 URL에 접근하므로 URL이 공개적으로 접근 가능해야 합니다.

5. **API 키 보안**: `.env` 파일을 `.gitignore`에 추가하여 API 키가 커밋되지 않도록 주의하세요.

## 🐛 문제 해결

### "OPENAI_API_KEY 환경 변수가 설정되지 않았습니다" 에러

- `.env` 파일이 올바른 위치에 있는지 확인
- `.env` 파일에 `OPENAI_API_KEY=your_key` 형식으로 작성되었는지 확인

### Rate Limit 에러 (Error code: 429)

- **자동 재시도**: 스크립트가 자동으로 재시도하므로 대부분의 경우 기다리면 해결됩니다
- **대기 시간 조정**: 스크립트의 `delay_seconds=3.0` 값을 늘려서 호출 간격을 더 벌릴 수 있습니다
  ```python
  process_jsonl_file(
      input_file=input_file,
      output_file=output_file,
      max_records=None,
      delay_seconds=5.0  # 3초에서 5초로 증가
  )
  ```
- **배치 처리**: 대량 데이터는 여러 번에 나누어 처리하세요

### 이미지 URL 접근 실패

- 이미지 URL이 유효한지 확인
- 이미지가 공개적으로 접근 가능한지 확인 (인증이 필요한 URL은 작동하지 않음)
- 해당 이미지가 여전히 호스팅되고 있는지 확인

### JSON 파싱 에러

- 입력 JSONL 파일의 형식이 올바른지 확인
- 각 라인이 유효한 JSON 객체인지 확인

## 📝 예제 실행 결과

```
입력 파일: ./data/color_product/product_documents_included_tags_with_color_RE.jsonl
출력 파일: ./data/color_product/product_documents_with_extracted_colors.jsonl
--------------------------------------------------------------------------------

[1] 처리 중: 라네즈 - [도넛립세럼] 글레이즈 크레이즈 틴티드 립 세럼 (8종) 12g
  총 8개 색상 변형 발견
  [1/8] 스트로베리 스프링클
이미지 컬러 추출 중: https://images-kr.amoremall.com/...
  → 추출 완료: #FF6B9D
  [2/8] 라즈베리 잼
이미지 컬러 추출 중: https://images-kr.amoremall.com/...
  → 추출 완료: #C41E3A

...

================================================================================
처리 완료!
  - 처리된 레코드: 3
  - 분석된 이미지: 15
  - 출력 파일: ./data/color_product/product_documents_with_extracted_colors.jsonl
================================================================================
```

## 🔗 관련 문서

- [OpenAI API 문서](https://platform.openai.com/docs/)
- [GPT-4 Vision 가이드](https://platform.openai.com/docs/guides/vision)

## 📞 지원

문제가 발생하면 프로젝트 이슈 트래커에 등록하거나 개발 팀에 문의하세요.
