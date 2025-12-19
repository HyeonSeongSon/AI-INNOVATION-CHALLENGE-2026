# PostgreSQL Docker 설정

이 디렉토리에는 PostgreSQL 데이터베이스와 pgAdmin을 Docker 컨테이너로 실행하기 위한 설정 파일들이 포함되어 있습니다.

## 파일 구조

```
database/
├── docker-compose.yml    # Docker Compose 설정 파일
├── .env                  # 환경 변수 설정 파일 (필수, Git 무시됨)
├── .env.example          # 환경 변수 예제 파일
├── .gitignore           # Git 무시 파일 목록
├── start.sh             # Linux/Mac 시작 스크립트
├── start.bat            # Windows 시작 스크립트
├── init/                # 초기화 SQL 스크립트 디렉토리
│   └── 01-init.sql     # 데이터베이스 초기화 스크립트
└── README.md           # 이 파일
```

## ⚠️ 시작하기 전 필수 설정

### 1. `.env` 파일 생성

**이 단계는 필수입니다!** `.env` 파일이 없으면 컨테이너가 시작되지 않습니다.

#### Linux/Mac:
```bash
cd database
cp .env.example .env
```

#### Windows:
```cmd
cd database
copy .env.example .env
```

### 2. `.env` 파일 수정

`.env` 파일을 열고 다음 값들을 **반드시 수정**하세요:

```env
# PostgreSQL 설정
POSTGRES_USER=postgres
POSTGRES_PASSWORD=여기에_강력한_비밀번호_입력     # ⚠️ 반드시 변경!
POSTGRES_DB=ai_innovation_db
POSTGRES_PORT=5432

# pgAdmin 설정
PGADMIN_DEFAULT_EMAIL=your_email@example.com      # ⚠️ 반드시 변경!
PGADMIN_DEFAULT_PASSWORD=여기에_강력한_비밀번호_입력  # ⚠️ 반드시 변경!
PGADMIN_PORT=5050
```

**비밀번호 권장사항:**
- 최소 12자 이상
- 대문자, 소문자, 숫자, 특수문자 조합
- 예: `MyS3cur3P@ssw0rd!2024`

## 사용 방법

### 방법 1: 자동 시작 스크립트 사용 (권장)

#### Linux/Mac:
```bash
cd database
./start.sh
```

#### Windows:
```cmd
cd database
start.bat
```

스크립트가 자동으로:
- ✅ `.env` 파일 존재 여부 확인
- ✅ 필수 환경 변수 검증
- ✅ Docker Compose 실행
- ✅ 서비스 정보 출력

### 방법 2: 수동 실행

#### 1. PostgreSQL & pgAdmin 시작
```bash
cd database
docker-compose up -d
```

#### 2. 컨테이너 상태 확인
```bash
docker-compose ps
```

#### 3. 로그 확인
```bash
# PostgreSQL 로그
docker-compose logs -f postgres

# pgAdmin 로그
docker-compose logs -f pgadmin

# 전체 로그
docker-compose logs -f
```

#### 4. PostgreSQL 접속

**컨테이너 내부에서:**
```bash
docker-compose exec postgres psql -U postgres -d ai_innovation_db
```

**호스트에서 (psql 설치 필요):**
```bash
psql -h localhost -p 5432 -U postgres -d ai_innovation_db
```

#### 5. 컨테이너 중지
```bash
docker-compose down
```

#### 6. 데이터 완전 삭제 (볼륨 포함)
```bash
docker-compose down -v
```

## pgAdmin 사용법

### 1. 웹 브라우저 접속

```
http://localhost:5050
```

### 2. 로그인

- **Email**: `.env` 파일의 `PGADMIN_DEFAULT_EMAIL`
- **Password**: `.env` 파일의 `PGADMIN_DEFAULT_PASSWORD`

### 3. PostgreSQL 서버 연결

1. 왼쪽 메뉴에서 **"Add New Server"** 클릭
2. **General 탭**:
   - Name: `AI Innovation DB` (원하는 이름)
3. **Connection 탭**:
   - Host: `postgres` (컨테이너 이름)
   - Port: `5432`
   - Maintenance database: `ai_innovation_db`
   - Username: `.env` 파일의 `POSTGRES_USER`
   - Password: `.env` 파일의 `POSTGRES_PASSWORD`
   - ✅ "Save password" 체크
4. **Save** 클릭

## 초기화 스크립트

`init/` 디렉토리에 SQL 스크립트를 추가하면 컨테이너가 처음 시작될 때 자동으로 실행됩니다.

- 파일명은 알파벳 순서로 실행됩니다 (예: `01-init.sql`, `02-seed.sql`)
- 이미 생성된 컨테이너에서는 실행되지 않습니다
- 초기화 스크립트를 다시 실행하려면:
  ```bash
  docker-compose down -v  # 볼륨 삭제
  docker-compose up -d    # 재시작
  ```

## Python 연결 예제

### psycopg2 사용

```python
import psycopg2
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv('database/.env')

# 데이터베이스 연결
conn = psycopg2.connect(
    host="localhost",
    port=int(os.getenv('POSTGRES_PORT', 5432)),
    database=os.getenv('POSTGRES_DB'),
    user=os.getenv('POSTGRES_USER'),
    password=os.getenv('POSTGRES_PASSWORD')
)

# 커서 생성
cursor = conn.cursor()

# 쿼리 실행
cursor.execute("SELECT version();")
result = cursor.fetchone()
print(result[0])

# 연결 종료
cursor.close()
conn.close()
```

### SQLAlchemy 사용

```python
from sqlalchemy import create_engine
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv('database/.env')

# 데이터베이스 URL 생성
DATABASE_URL = f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@localhost:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"

# 엔진 생성
engine = create_engine(DATABASE_URL)

# 연결 테스트
with engine.connect() as connection:
    result = connection.execute("SELECT version();")
    print(result.fetchone()[0])
```

## 보안 주의사항

### ⚠️ 중요!

1. **`.env` 파일을 Git에 커밋하지 마세요!**
   - 이미 `.gitignore`에 포함되어 있습니다
   - 실수로 커밋한 경우 즉시 비밀번호를 변경하세요

2. **강력한 비밀번호 사용**
   - 기본 비밀번호는 절대 사용하지 마세요
   - 프로덕션 환경에서는 더욱 엄격한 정책 적용

3. **프로덕션 환경**
   - 환경 변수를 안전한 시크릿 관리 시스템 사용 (AWS Secrets Manager, Azure Key Vault 등)
   - 네트워크 접근 제한 (방화벽, Security Group)
   - SSL/TLS 연결 강제
   - 정기적인 백업

4. **포트 노출 최소화**
   - 개발 환경에서만 외부 포트 노출
   - 프로덕션에서는 내부 네트워크만 사용

## 문제 해결

### 포트가 이미 사용 중인 경우

**Windows:**
```cmd
netstat -ano | findstr :5432
taskkill /PID <PID번호> /F
```

**Linux/Mac:**
```bash
lsof -i :5432
kill -9 <PID번호>
```

또는 `.env` 파일에서 포트 번호 변경:
```env
POSTGRES_PORT=5433  # 다른 포트로 변경
```

### `.env` 파일이 없다는 오류

```bash
cp .env.example .env
# .env 파일을 편집하여 실제 값으로 수정
```

### 컨테이너가 시작되지 않는 경우

```bash
# 로그 확인
docker-compose logs

# 볼륨 삭제 후 재시작
docker-compose down -v
docker-compose up -d
```

### pgAdmin에서 PostgreSQL 연결 실패

1. PostgreSQL 컨테이너가 healthy 상태인지 확인:
   ```bash
   docker-compose ps
   ```

2. Host 이름을 `postgres` (컨테이너 이름)로 설정했는지 확인

3. `.env` 파일의 비밀번호가 정확한지 확인

## 데이터 백업 및 복원

### 백업

```bash
# 전체 데이터베이스 백업
docker-compose exec postgres pg_dump -U postgres ai_innovation_db > backup.sql

# 압축 백업
docker-compose exec postgres pg_dump -U postgres ai_innovation_db | gzip > backup.sql.gz
```

### 복원

```bash
# SQL 파일에서 복원
docker-compose exec -T postgres psql -U postgres ai_innovation_db < backup.sql

# 압축 파일에서 복원
gunzip < backup.sql.gz | docker-compose exec -T postgres psql -U postgres ai_innovation_db
```

## 성능 튜닝

`docker-compose.yml` 파일의 `command` 섹션에서 PostgreSQL 설정을 조정할 수 있습니다:

```yaml
-c max_connections=200           # 최대 연결 수
-c shared_buffers=256MB          # 공유 버퍼
-c effective_cache_size=1GB      # 효과적인 캐시 크기
-c work_mem=1310kB               # 작업 메모리
```

서버 사양에 맞게 조정하세요.

## 추가 리소스

- [PostgreSQL 공식 문서](https://www.postgresql.org/docs/)
- [pgAdmin 공식 문서](https://www.pgadmin.org/docs/)
- [Docker Compose 공식 문서](https://docs.docker.com/compose/)
