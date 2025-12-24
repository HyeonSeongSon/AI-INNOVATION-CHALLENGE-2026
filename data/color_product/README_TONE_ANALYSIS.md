# 컬러 톤 분석 가이드

이 스크립트는 화장품 제품의 HEX 컬러 리스트를 GPT-4o-mini API로 분석하여 해당 상품 라인업에 포함된 톤을 자동으로 분류합니다.

## 📋 개요

- **입력 파일**: `product_documents_with_extracted_colors_RE.jsonl` (컬러 추출 완료된 파일)
- **출력 파일**: `product_documents_with_tones_RE.jsonl`
- **작동 방식**: 각 제품의 컬러 HEX 값들을 LLM에 전달하여 해당 제품에 포함된 톤을 분석

## 🎨 분석 가능한 톤

- **웜톤** - 따뜻한 톤
- **봄웜톤** - 밝고 선명한 웜톤
- **가을웜톤** - 깊고 차분한 웜톤
- **쿨톤** - 차가운 톤
- **여름쿨톤** - 부드럽고 차분한 쿨톤
- **겨울쿨톤** - 선명하고 강렬한 쿨톤
- **뉴트럴톤** - 중립 톤

## 🚀 사용 방법

### 1단계: 컬러 추출 완료 확인

먼저 `extract_image_colors.py`를 실행하여 컬러 추출이 완료되어야 합니다.

```bash
python extract_image_colors.py
```

### 2단계: 톤 분석 실행

```bash
python analyze_color_tones.py
```

## 📊 입출력 예시

### 입력 (컬러 추출 완료 데이터)
```json
{
  "브랜드": "라네즈",
  "상품명": "틴티드 립 세럼",
  "color_info": {
    "colors": [
      {
        "color_name": "스트로베리 스프링클",
        "extracted_color": {
          "color": {
            "hex": "#F5A1B3"
          }
        }
      },
      {
        "color_name": "라즈베리 잼",
        "extracted_color": {
          "color": {
            "hex": "#D50032"
          }
        }
      }
    ]
  }
}
```

### 출력 (톤 분석 완료)
```json
{
  "브랜드": "라네즈",
  "상품명": "틴티드 립 세럼",
  "color_info": {
    "colors": [ ... ]
  },
  "tone_info": ["웜톤", "봄웜톤", "가을웜톤"]
}
```

## 🔧 스크립트 커스터마이징

### 처리할 레코드 수 조정

```python
# 테스트용 (처음 5개만)
process_jsonl_file(
    input_file=input_file,
    output_file=output_file,
    max_records=5
)

# 전체 처리
process_jsonl_file(
    input_file=input_file,
    output_file=output_file,
    max_records=None
)
```

### API 호출 간격 조정

```python
# 기본 (2초 대기)
delay_seconds=2.0

# 더 긴 대기 (Rate limit 방지)
delay_seconds=3.0
```

## ⚠️ 주의사항

1. **전제 조건**: 컬러 추출이 완료된 파일이 필요합니다
   - `extract_image_colors.py` 실행 필수

2. **처리 시간**:
   - 각 제품당 약 2초 소요
   - 100개 제품: 약 3-4분

3. **Rate Limit 관리**:
   - 기본 2초 대기 (컬러 추출보다 짧은 응답)
   - 필요시 `delay_seconds` 조정

4. **API 비용**:
   - 제품당 1회 호출 (컬러 개수와 무관)
   - 텍스트 기반이라 Vision API보다 저렴

## 🐛 문제 해결

### "컬러 정보 없음" 경고

```
⚠️ 추출된 컬러 없음 - 건너뜀
```
➡️ `extract_image_colors.py`를 먼저 실행하여 컬러 추출을 완료하세요

### Rate Limit 에러

```
Error code: 429 - Rate limit reached
```
➡️ `delay_seconds=2.0`을 `delay_seconds=3.0` 이상으로 변경

### 빈 톤 리스트

```json
{
  "tone_info": []
}
```
➡️ 해당 제품의 컬러가 특정 톤에 명확히 분류되지 않음 (정상 동작)

## 📝 예제 실행 결과

```
입력 파일: C:\...\product_documents_with_extracted_colors_RE.jsonl
출력 파일: C:\...\product_documents_with_tones_RE.jsonl
--------------------------------------------------------------------------------

[1] 처리 중: 라네즈 - [도넛립세럼] 글레이즈 크레이즈 틴티드 립 세럼 (8종) 12g
상품 톤 분석 중: [도넛립세럼] 글레이즈 크레이즈 틴티드 립 세럼 (8종) 12g (컬러 8개)
  → 분석 완료: 웜톤, 봄웜톤, 가을웜톤, 뉴트럴톤

[2] 처리 중: 라네즈 - 네오 쿠션 뮤이 더블 SPF42/PA++ 15g*2
상품 톤 분석 중: 네오 쿠션 뮤이 더블 SPF42/PA++ 15g*2 (컬러 7개)
  → 분석 완료: 웜톤, 쿨톤, 뉴트럴톤

...

================================================================================
처리 완료!
  - 처리된 레코드: 50
  - 건너뛴 레코드: 2
  - 출력 파일: C:\...\product_documents_with_tones_RE.jsonl
================================================================================
```

## 🔗 관련 스크립트

1. **[extract_image_colors.py](./extract_image_colors.py)** - 이미지에서 컬러 추출 (선행 작업)
2. **[analyze_color_tones.py](./analyze_color_tones.py)** - 컬러 톤 분석 (현재 스크립트)

## 💡 활용 예시

### 1. 톤별 제품 검색
```python
# 봄웜톤 제품 찾기
with open('product_documents_with_tones_RE.jsonl', 'r') as f:
    for line in f:
        product = json.loads(line)
        tones = product.get('tone_info', [])
        if '봄웜톤' in tones:
            print(product['상품명'])
```

### 2. 톤 분포 분석
```python
from collections import Counter

tone_counter = Counter()
with open('product_documents_with_tones_RE.jsonl', 'r') as f:
    for line in f:
        product = json.loads(line)
        tones = product.get('tone_info', [])
        tone_counter.update(tones)

print(tone_counter.most_common())
# 출력: [('웜톤', 120), ('뉴트럴톤', 95), ('쿨톤', 80), ...]
```

## 📞 지원

문제가 발생하면 프로젝트 이슈 트래커에 등록하거나 개발 팀에 문의하세요.
