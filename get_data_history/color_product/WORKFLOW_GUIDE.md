# 화장품 컬러 분석 워크플로우 가이드

화장품 제품 이미지에서 컬러를 추출하고, 톤을 분석하는 전체 프로세스 가이드입니다.

## 📊 전체 워크플로우

```
1단계: 원본 데이터
product_documents_included_tags_with_color_RE.jsonl
↓
2단계: 컬러 추출
extract_image_colors.py
↓
product_documents_with_extracted_colors_RE.jsonl
↓
3단계: 톤 분석
analyze_color_tones.py
↓
product_documents_with_tones_RE.jsonl (최종 결과)
```

## 🚀 단계별 실행 가이드

### 0단계: 환경 설정

```bash
# 필요 패키지 설치
pip install openai python-dotenv

# API 키 설정 (.env 파일 생성)
echo "OPENAI_API_KEY=your_api_key_here" > ../../.env
```

### 1단계: 컬러 추출 (이미지 → HEX/RGB/HSV/LAB)

```bash
python extract_image_colors.py
```

**소요 시간**: 이미지 1개당 약 3초
- 100개 이미지: ~5분
- 1,000개 이미지: ~50분

**입력**: 이미지 URL이 포함된 JSONL
**출력**: HEX, RGB, HSV, LAB 컬러값 추가

### 2단계: 톤 분석 (컬러 → 톤 분류)

```bash
python analyze_color_tones.py
```

**소요 시간**: 제품 1개당 약 2초
- 100개 제품: ~3-4분
- 1,000개 제품: ~30-40분

**입력**: 컬러 추출 완료된 JSONL
**출력**: 톤 분류 결과 추가

## 📁 파일 구조

```
data/color_product/
├── product_documents_included_tags_with_color_RE.jsonl   # 원본
├── product_documents_with_extracted_colors_RE.jsonl      # 1단계 결과
├── product_documents_with_tones_RE.jsonl                 # 2단계 결과 (최종)
│
├── extract_image_colors.py                               # 1단계 스크립트
├── analyze_color_tones.py                                # 2단계 스크립트
│
├── README_COLOR_EXTRACTION.md                            # 컬러 추출 가이드
├── README_TONE_ANALYSIS.md                               # 톤 분석 가이드
└── WORKFLOW_GUIDE.md                                     # 이 파일
```

## 📊 데이터 변환 과정

### 원본 데이터
```json
{
  "브랜드": "라네즈",
  "상품명": "틴티드 립 세럼",
  "color_info": {
    "colors": [
      {
        "color_name": "스트로베리 스프링클",
        "image_url": "https://..."
      }
    ]
  }
}
```

### 1단계 후: 컬러 추출 완료
```json
{
  "브랜드": "라네즈",
  "상품명": "틴티드 립 세럼",
  "color_info": {
    "colors": [
      {
        "color_name": "스트로베리 스프링클",
        "image_url": "https://...",
        "extracted_color": {
          "color": {
            "hex": "#F5A1B3",
            "rgb": [245, 161, 179],
            "hsv": { "h": 348, "s": 34, "v": 96 },
            "lab": { "l": 82.48, "a": 16.71, "b": -6.91 }
          }
        }
      }
    ]
  }
}
```

### 2단계 후: 톤 분석 완료 (최종)
```json
{
  "브랜드": "라네즈",
  "상품명": "틴티드 립 세럼",
  "color_info": {
    "colors": [ ... ]
  },
  "tone_info": ["웜톤", "봄웜톤", "뉴트럴톤"]
}
```

## ⚙️ 설정 최적화

### 테스트 실행 (빠른 확인)

```python
# extract_image_colors.py
max_records=3
delay_seconds=3.0

# analyze_color_tones.py
max_records=3
delay_seconds=2.0
```

### 전체 실행 (프로덕션)

```python
# extract_image_colors.py
max_records=None
delay_seconds=3.0

# analyze_color_tones.py
max_records=None
delay_seconds=2.0
```

### Rate Limit이 발생하는 경우

```python
# extract_image_colors.py
delay_seconds=5.0  # 3초 → 5초

# analyze_color_tones.py
delay_seconds=3.0  # 2초 → 3초
```

## 💰 예상 비용 (GPT-4o-mini 기준)

### 컬러 추출 (Vision API)
- 이미지 1개: ~$0.001
- 1,000개 이미지: ~$1

### 톤 분석 (Text API)
- 제품 1개: ~$0.0001
- 1,000개 제품: ~$0.1

### 전체 비용
- 1,000개 제품 (평균 5개 컬러): ~$1.1

## ⏱️ 전체 소요 시간

| 제품 수 | 평균 컬러/제품 | 컬러 추출 | 톤 분석 | 합계 |
|--------|--------------|---------|--------|------|
| 10개 | 5개 | ~2.5분 | ~20초 | ~3분 |
| 100개 | 5개 | ~25분 | ~3분 | ~28분 |
| 1,000개 | 5개 | ~4시간 | ~30분 | ~4.5시간 |

## 🚨 문제 해결

### 1단계 실패 시

```bash
# 로그 확인
python extract_image_colors.py 2>&1 | tee color_extraction.log

# 일부만 처리된 경우, 처리된 레코드 수 확인 후 재개
# (중복 처리를 피하려면 별도 스크립트 수정 필요)
```

### 2단계 실패 시

```bash
# 1단계 결과 확인
python -c "import json; [print(json.loads(line)['color_info'].get('colors', [])) for line in open('product_documents_with_extracted_colors_RE.jsonl')]" | head

# 문제가 있으면 1단계부터 재실행
```

### Rate Limit 계속 발생

```python
# 두 스크립트 모두 대기 시간 증가
delay_seconds=5.0  # 또는 더 큰 값
```

## 📈 결과 활용 예시

### 1. 톤별 제품 필터링

```python
import json

# 봄웜톤 제품만 추출
spring_warm_products = []
with open('product_documents_with_tones_RE.jsonl', 'r') as f:
    for line in f:
        product = json.loads(line)
        tones = product.get('tone_info', [])
        if '봄웜톤' in tones:
            spring_warm_products.append(product)

print(f"봄웜톤 제품: {len(spring_warm_products)}개")
```

### 2. 컬러 팔레트 생성

```python
# 특정 제품의 모든 HEX 컬러 추출
import json

with open('product_documents_with_tones_RE.jsonl', 'r') as f:
    for line in f:
        product = json.loads(line)
        if '라네즈' in product.get('브랜드', ''):
            colors = []
            for color in product['color_info']['colors']:
                if 'extracted_color' in color:
                    hex_val = color['extracted_color']['color'].get('hex')
                    if hex_val:
                        colors.append(hex_val)
            print(f"{product['상품명']}: {colors}")
```

### 3. 통계 분석

```python
from collections import Counter
import json

tone_stats = Counter()
total_products = 0

with open('product_documents_with_tones_RE.jsonl', 'r') as f:
    for line in f:
        product = json.loads(line)
        tones = product.get('tone_info', [])
        tone_stats.update(tones)
        total_products += 1

print(f"전체 제품 수: {total_products}")
print("\n톤별 분포:")
for tone, count in tone_stats.most_common():
    percentage = (count / total_products) * 100
    print(f"  {tone}: {count}개 ({percentage:.1f}%)")
```

## 🔗 참고 문서

- [컬러 추출 상세 가이드](./README_COLOR_EXTRACTION.md)
- [톤 분석 상세 가이드](./README_TONE_ANALYSIS.md)
- [빠른 시작 가이드](./USAGE_SUMMARY.md)
- [OpenAI API 문서](https://platform.openai.com/docs/)

## 📞 지원

문제가 발생하면 프로젝트 이슈 트래커에 등록하거나 개발 팀에 문의하세요.
