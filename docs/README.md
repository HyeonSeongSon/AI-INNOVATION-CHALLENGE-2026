# docs/ — README 이미지 자산

루트 `README.md`의 **데모** 섹션이 참조하는 스크린샷 2개를 이 디렉터리에 둔다.
파일이 없으면 README에서 깨진 이미지로 표시되므로, 푸시 전에 반드시 채워야 한다.

| 파일명 | 내용 | 촬영 지점 |
|---|---|---|
| `screenshot-persona.png` | 페르소나 검색 쿼리 4종(니즈·선호·검색·페르소나) 상세 | `/persona` (`frontend/src/pages/Persona.jsx`) |
| `screenshot-generated-messages.png` | 생성 메시지 + 품질 점수 + AI 평가 코멘트 | `/generated-messages` (`frontend/src/pages/GeneratedMessages.jsx`) |
| `screenshot-product-detail.png` | 등록 상품의 재설계 스키마(Concern·Summary·Texture·Function·Attribute·Search_tags) | 상품 상세 모달 — **README가 아니라 `portfolio/deck_short.js` 3번 슬라이드가 참조한다.** 상단 상품카드(이미지·가격·ID)를 잘라낸 크롭본이다 |

시연 영상은 YouTube로 대체했다(`https://youtu.be/BhDjZy1cUeg`).
썸네일은 `https://img.youtube.com/vi/<VIDEO_ID>/maxresdefault.jpg`로 자동 생성되므로
저장소에 파일을 둘 필요가 없다. GitHub은 `<iframe>` 임베드를 허용하지 않으므로
**썸네일 이미지 + 링크**가 유일한 방법이다.

## 촬영 시 주의

- 공개 저장소다. **계정 이메일·실명 등 개인정보가 화면에 남지 않도록** 확인한다
  (로그인 계정 표시, 사이드바 프로필, 페르소나 이름)
- 폭 1200px 내외 권장 — 표 안에서 2열로 나란히 렌더링된다

## GIF를 추가한다면 (선택)

영상이 있으므로 필수는 아니다. 자동 재생되는 훅이 필요하면 `demo.gif`를 만들어
YouTube 썸네일 위에 배치한다.

- 길이 15~20초, 무한 반복. 실제 응답은 p50 약 200초라 그대로 녹화하면 너무 길다
- SSE 로그가 흐르는 구간은 실시간 속도로 살리고, 대기 구간만 잘라내거나 배속 처리
- 파일 크기 10MB 이하 — GitHub에서 로딩이 끊기지 않는 수준

이미지를 모두 배치한 뒤에는 이 파일을 삭제해도 된다.
