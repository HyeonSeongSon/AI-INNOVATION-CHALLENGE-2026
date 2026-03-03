# 컬러 추출 스크립트 - 빠른 시작 가이드

## 🎯 한 줄 요약
화장품 제품 이미지 URL에서 GPT-4o-mini API로 컬러값(HEX, RGB, HSV, LAB)을 자동 추출하는 스크립트

## ⚡ 빠른 시작

```bash
# 1. 패키지 설치
pip install openai python-dotenv

# 2. API 키 설정 (.env 파일 생성)
echo "OPENAI_API_KEY=your_api_key_here" > ../../.env

# 3. 실행
python extract_image_colors.py
```

## 📂 파일 구조

```
data/color_product/
├── extract_image_colors.py                              # 메인 스크립트
├── product_documents_included_tags_with_color_RE.jsonl  # 입력 파일
├── product_documents_with_extracted_colors_RE.jsonl     # 출력 파일 (자동 생성)
├── requirements.txt                                     # 필요 패키지
├── README_COLOR_EXTRACTION.md                           # 상세 문서
└── USAGE_SUMMARY.md                                     # 이 파일
```

## 📊 입출력 예시

### 입력 (원본 데이터)
```json
{
  "브랜드": "라네즈",
  "color_info": {
    "colors": [
      {
        "color_name": "스트로베리 스프링클",
        "image_url": "https://images-kr.amoremall.com/..."
      }
    ]
  }
}
```

### 출력 (컬러 추출 후)
```json
{
  "브랜드": "라네즈",
  "color_info": {
    "colors": [
      {
        "color_name": "스트로베리 스프링클",
        "image_url": "https://images-kr.amoremall.com/...",
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

## 🔧 주요 기능

✅ **자동 Rate Limit 처리**
- API 호출 간 1초 자동 대기
- Rate limit 에러 시 자동 재시도 (2초 → 4초 → 6초)

✅ **정확한 컬러 분석**
- 패키지/케이스/배경 제외, 제품 색상만 분석
- HEX, RGB, HSV, LAB 4가지 색상 포맷 제공

✅ **에러 핸들링**
- 실패한 이미지는 에러 정보와 함께 기록
- 전체 프로세스는 계속 진행

## ⚙️ 설정 변경

### 전체 데이터 처리하기

[extract_image_colors.py](./extract_image_colors.py:246) 수정:
```python
# 현재 (전체 처리)
max_records=None

# 변경 후 (테스트용 - 처음 10개만)
max_records=10
```

### API 호출 간격 조정 (Rate Limit 방지)

[extract_image_colors.py](./extract_image_colors.py:247) 수정:
```python
# 현재 (3초 대기)
delay_seconds=3.0

# 변경 후 (예: 5초 대기 - Rate limit이 계속 발생하는 경우)
delay_seconds=5.0
```

## ⏱️ 예상 처리 시간

| 이미지 수 | 예상 시간 | 설명 |
|---------|----------|-----|
| 10개 | ~30초 | 테스트용 |
| 100개 | ~5분 | 소규모 배치 |
| 1,000개 | ~50분 | 중규모 배치 |
| 10,000개 | ~8시간 | 대규모 배치 (배치 분할 권장) |

*각 이미지당 약 3초 소요 (API 호출 + 3초 대기)*

## 🚨 문제 해결

### Rate Limit 에러
```
Error code: 429 - Rate limit reached
```
➡️ 자동으로 재시도되므로 기다리세요. 계속 발생하면 `delay_seconds=3.0`을 `delay_seconds=5.0` 이상으로 변경

### API 키 에러
```
OPENAI_API_KEY 환경 변수가 설정되지 않았습니다
```
➡️ 프로젝트 루트에 `.env` 파일을 생성하고 `OPENAI_API_KEY=your_key` 추가

### 파일을 찾을 수 없음
```
에러: 입력 파일이 존재하지 않습니다
```
➡️ `data/color_product/` 디렉토리에서 스크립트를 실행하세요

## 💰 비용 예상

GPT-4o-mini 기준 (2024년 12월):
- 입력: $0.15 / 1M tokens
- 출력: $0.60 / 1M tokens

예상 비용:
- 이미지 1개당: ~$0.001 (약 1.3원)
- 1,000개: ~$1 (약 1,300원)
- 10,000개: ~$10 (약 13,000원)

*실제 비용은 이미지 크기와 복잡도에 따라 달라질 수 있습니다.*

## 📚 추가 문서

- 상세 사용법: [README_COLOR_EXTRACTION.md](./README_COLOR_EXTRACTION.md)
- OpenAI API 문서: https://platform.openai.com/docs/
- GPT Vision 가이드: https://platform.openai.com/docs/guides/vision
