# 아모레몰 브랜드 크롤러 사용 가이드

## 개요

이 크롤러는 아모레몰의 브랜드 페이지에서 상품 정보를 자동으로 수집하는 도구입니다.

### 수집 가능한 정보
- 브랜드명
- 상품명
- 별점 및 리뷰 수
- 원가, 할인율, 판매가
- 상품 썸네일 이미지
- 상품 상세 이미지
- 구매자 통계 (연령대별, 피부타입별)

---

## 사용법

### 1단계: URL 설정

`brand_home_url.json` 파일을 열어서 크롤링할 브랜드 URL을 설정합니다.

**파일 위치:** `./crawling/brand_home_url.json`

**예시:**
```json
{
  "brand_home_urls": [
    "https://www.amoremall.com/kr/ko/display/brand/detail?brandSn=236",
    "https://www.amoremall.com/kr/ko/display/brand/detail?brandSn=174",
    "https://www.amoremall.com/kr/ko/display/brand/detail?brandSn=31"
  ]
}
```

### 2단계: 크롤러 실행

터미널에서 다음 명령어를 실행합니다:

```bash
cd crawling
python crawling251205.py
```

### 3단계: 결과 확인

크롤링이 완료되면 결과 파일이 자동으로 생성됩니다.

**저장 위치:**
```
C:\Users\user\Documents\GitHub\AI-INNOVATION-CHALLENGE-2026\data\crawling_result\
```

**파일명 형식:**
```
product_crawling_YYMMDDHHMM.jsonl
```
- 예시: `product_crawling_2512052351.jsonl` (2025년 12월 5일 23시 51분)

**출력 예시:**
```
=== 브랜드 페이지 크롤러 ===
JSON 파일에서 3개의 URL을 로드했습니다.

크롤링 시작... (총 3개 URL)
URL 1/3 처리 중: https://www.amoremall.com/...
상품 1/20 처리 중...
...
크롤링 완료: 60개 상품 정보 수집

[SUCCESS] 저장 완료!
  파일 위치: C:\...\data\crawling_result\product_crawling_2512052351.jsonl
  상품 수: 60개
```

---

## ⚙️ 설정

### 수집 상품 수 변경

크롤러는 기본적으로 브랜드당 **최대 20개** 상품을 수집합니다.

변경하려면 `crawling251205.py` 파일의 다음 부분을 수정하세요:

```python
class BrandPageCrawler:
    def __init__(self, urls: List[str] = None):
        ...
        self.max_products = 20  # 이 값을 변경
```

---

## 주의사항

### 1. 파일 위치
- `brand_home_url.json`와 `crawling251205.py` 파일은 **같은 디렉토리**(`./crawling/`)에 있어야 합니다.

### 2. 상품 페이지 UI 호환성
- 대부분의 아모레몰 상품을 크롤링할 수 있습니다.
- 일부 특수한 레이아웃의 상품 페이지는 데이터 수집이 불완전할 수 있습니다.
- 작성자가 담당한 브랜드 상품들은 모두 정상적으로 크롤링됩니다.

### 3. 실행 시간
- 브랜드당 약 2~5분 소요 (상품 수에 따라 다름)
- 여러 브랜드를 크롤링할 경우 시간이 오래 걸릴 수 있습니다.

### 4. Chrome 브라우저
- Selenium이 Chrome 브라우저를 사용하므로, Chrome이 설치되어 있어야 합니다.
- ChromeDriver는 자동으로 관리됩니다.

---

## 출력 파일 구조

### 저장 위치 및 파일명

- **디렉토리**: `./data/crawling_result/`
- **파일명**: `product_crawling_YYMMDDHHMM.jsonl`
  - YY: 연도 2자리 (예: 25)
  - MM: 월 2자리 (예: 12)
  - DD: 일 2자리 (예: 05)
  - HH: 시 2자리 (예: 23)
  - MM: 분 2자리 (예: 51)

### 파일 형식

JSONL 형식(줄마다 하나의 JSON 객체)으로 저장됩니다.

**예시:**
```json
{
  "url": "https://www.amoremall.com/kr/ko/product/detail?...",
  "브랜드": "설화수",
  "상품명": "윤조3종 세트",
  "별점": 4.8,
  "리뷰_갯수": 1234,
  "원가": 100000,
  "할인율": 10,
  "판매가": 90000,
  "상품이미지": ["url1", "url2"],
  "상품상세_이미지": ["url1", "url2", "url3"],
  "구매자_통계": {
    "연령대별": {"20대": 30, "30대": 40},
    "피부타입별": {"복합성": 35, "건성": 25}
  }
}
```

---

## 문제 해결

### 문제: "JSON 파일을 찾을 수 없습니다"
**해결:**
- `brand_home_url.json` 파일이 `crawling/` 디렉토리에 있는지 확인
- 파일 이름 철자가 정확한지 확인

### 문제: "WebDriver 초기화 실패"
**해결:**
- Chrome 브라우저가 설치되어 있는지 확인
- 인터넷 연결 확인

### 문제: "상품 이미지를 찾지 못했습니다"
**해결:**
- 일부 상품은 레이아웃이 달라서 이미지 수집이 안 될 수 있습니다.
- 문제가 지속되면 작성자에게 문의하세요.

### 문제: 크롤링 속도가 너무 느림
**해결:**
- `max_products` 값을 줄여서 상품 수를 제한
- 네트워크 속도 확인

---

## 문의

문제 발생 시 작성자에게 연락 주세요.