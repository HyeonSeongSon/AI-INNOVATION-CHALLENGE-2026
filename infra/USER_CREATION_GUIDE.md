# User 계정 생성 가이드

> AWS ECS 배포 환경에서 admin 및 일반 유저 계정을 생성하는 방법을 정리한다.
> API 서버: `https://<ALB-도메인>` (포트 8005, ALB를 통해 외부 노출)

---

## 계정 생성 경로 요약

| 방법 | 대상 | 경로 | 사전 조건 |
|------|------|------|-----------|
| Terraform seed | 첫 번째 admin | 배포 시 자동 | GitHub Secrets 설정 |
| Admin API | admin / user 추가 | `POST /auth/admin/users` | admin 로그인 필요 |
| 자가 가입 | 일반 user | `POST /auth/register` | 없음 (rate limit 있음) |
| ECS exec | 긴급 admin | CLI 스크립트 | AWS CLI, ECS exec 권한 |

---

## 비밀번호 규칙

모든 경로 공통 적용:

- 최소 **8자** 이상
- **대문자** 1개 이상 (A-Z)
- **소문자** 1개 이상 (a-z)
- **숫자** 1개 이상 (0-9)

예시: `MyPass1!`, `Admin2026`

---

## 방법 1: 첫 번째 Admin 생성 (배포 시 1회)

첫 배포 직후에는 DB에 어떤 계정도 없다. Terraform이 앱 시작 시 환경변수로 admin을 자동 생성하는 메커니즘이 내장되어 있다 (`backend/main.py` — `_seed_admin_if_needed()`).

### 1-1. GitHub Secrets 등록

GitHub 레포지토리 → **Settings → Secrets and variables → Actions**에서 추가:

| Secret 이름 | 값 예시 |
|-------------|---------|
| `ADMIN_SEED_EMAIL` | `admin@example.com` |
| `ADMIN_SEED_PASSWORD` | `MyAdmin2026!` |

### 1-2. 배포 실행

`main` 브랜치에 push → GitHub Actions 자동 실행:
- Terraform이 Secrets Manager에 시크릿 생성
- ECS 컨테이너 재시작 → 앱 시작 시 admin 계정 자동 생성

### 1-3. 생성 확인

CloudWatch Logs (`/ecs/ai-innovation`)에서 아래 로그 확인:

```
{"event": "admin_seeded", ...}
```

로그인으로 2차 검증:

```bash
curl -X POST https://<ALB-도메인>/auth/login \
  -c cookies.txt \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@example.com&password=MyAdmin2026!"
```

### 1-4. 시크릿 삭제 (보안 필수)

생성 확인 후 즉시 처리:

1. GitHub Secrets에서 `ADMIN_SEED_EMAIL`, `ADMIN_SEED_PASSWORD`를 **빈 문자열(`""`)로 교체**
2. 재배포 → Terraform이 `count=0`으로 Secrets Manager 시크릿 즉시 삭제

---

## 방법 2: Admin API로 유저 생성 (방법 A — 운영 중 계정 추가)

admin 계정이 있으면 API로 추가 계정을 생성할 수 있다.

### 2-1. Admin 로그인

```bash
curl -X POST https://<ALB-도메인>/auth/login \
  -c cookies.txt \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@example.com&password=MyAdmin2026!"
```

성공 시 `cookies.txt`에 `access_token`(HttpOnly Cookie) 저장.

### 2-2. 유저 생성

```bash
# 일반 user 생성
curl -X POST https://<ALB-도메인>/auth/admin/users \
  -b cookies.txt \
  -H "Content-Type: application/json" \
  -d '{
    "email": "newuser@example.com",
    "password": "UserPass1!",
    "role": "user"
  }'

# admin 계정 추가 생성
curl -X POST https://<ALB-도메인>/auth/admin/users \
  -b cookies.txt \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin2@example.com",
    "password": "AdminPass2!",
    "role": "admin"
  }'
```

**응답 예시 (201 Created):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "newuser@example.com",
  "role": "user",
  "created_at": "2026-06-11T10:00:00Z"
}
```

- `role`: `"user"` 또는 `"admin"` 선택 가능
- Rate limit 없음 (인증만 필요)

---

## 방법 3: 일반 유저 자가 가입

누구나 회원가입 가능. `role`은 `"user"`로 고정.

```bash
curl -X POST https://<ALB-도메인>/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "UserPass1!"
  }'
```

- Rate limit: IP당 **5회 / 60초** 제한
- admin 계정은 이 경로로 만들 수 없음

---

## 방법 4: ECS exec로 직접 생성 (긴급)

Terraform 배포 없이 ECS 컨테이너에 직접 접속해서 admin을 만드는 방법.

### 4-1. Task ID 조회

```bash
aws ecs list-tasks \
  --cluster ai-innovation-cluster \
  --service-name backend \
  --query "taskArns[0]" \
  --output text
```

### 4-2. 컨테이너 접속 및 스크립트 실행

```bash
aws ecs execute-command \
  --cluster ai-innovation-cluster \
  --task <task-id> \
  --container fastapi-backend \
  --interactive \
  --command "python -m scripts.create_admin --email admin@example.com"
```

- 비밀번호를 대화형으로 입력 (셸 히스토리에 남지 않음)
- ECS exec 사전 조건: Task에 `enableExecuteCommand=true` 설정 필요

---

## 토큰 만료 및 갱신

| 토큰 | 유효 기간 | 갱신 방법 |
|------|-----------|-----------|
| `access_token` | 15분 | `POST /auth/refresh` 자동 갱신 |
| `refresh_token` | 7일 | 재로그인 |

```bash
# access_token 만료 시 자동 갱신
curl -X POST https://<ALB-도메인>/auth/refresh \
  -b cookies.txt \
  -c cookies.txt
```

---

## 관련 파일

| 파일 | 역할 |
|------|------|
| `backend/main.py` | `_seed_admin_if_needed()` — 앱 시작 시 seed 실행 |
| `backend/scripts/create_admin.py` | ECS exec용 CLI 스크립트 |
| `backend/app/api/auth_router.py` | `/auth/*` 엔드포인트 구현 |
| `infra/ec2/secrets.tf` | Secrets Manager 시크릿 관리 |
| `.github/workflows/deploy.yml` | `TF_VAR_admin_seed_*` GitHub Secrets 주입 |
