# docs/ — README 이미지 자산

루트 `README.md`의 **데모** 섹션이 참조하는 이미지 3개를 이 디렉터리에 둔다.
파일이 없으면 README에서 깨진 이미지로 표시되므로, 푸시 전에 반드시 채워야 한다.

| 파일명 | 내용 | 촬영 지점 |
|---|---|---|
| `demo.gif` | 채팅 입력 → SSE 노드 진행 로그 실시간 출력 → 추천 상품 3개 → CRM 메시지 생성 | `/message` (`frontend/src/pages/Message.jsx`) |
| `screenshot-persona.png` | 페르소나 등록/목록 화면 | `/persona` (`frontend/src/pages/Persona.jsx`) |
| `screenshot-generated-messages.png` | 생성 메시지 이력 + 품질 점수 | `/generated-messages` (`frontend/src/pages/GeneratedMessages.jsx`) |

## demo.gif 촬영 가이드

- **길이 15~20초, 무한 반복.** 실제 응답은 p50 약 200초이므로 그대로 녹화하면 너무 길다
- SSE 로그가 흐르는 구간은 **실시간 속도로 살리고**, 대기 구간만 잘라내거나 배속 처리한다
  (README 캡션에 배속 표기가 이미 들어가 있음)
- 폭 1200px 내외, 파일 크기 10MB 이하 권장 — GitHub에서 로딩이 끊기지 않는 수준
- 계정 이메일·실명 등 개인정보가 화면에 남지 않도록 확인

이미지를 모두 배치한 뒤에는 이 파일을 삭제해도 된다.
