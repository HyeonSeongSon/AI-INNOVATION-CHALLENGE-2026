# 데이터베이스 마이그레이션 가이드

## 목차
1. [개요](#개요)
2. [Alembic 설정](#alembic-설정)
3. [마이그레이션 환경](#마이그레이션-환경)
4. [데이터베이스 모델](#데이터베이스-모델)
5. [마이그레이션 사용법](#마이그레이션-사용법)
6. [Docker 통합](#docker-통합)
7. [마이그레이션 워크플로우](#마이그레이션-워크플로우)
8. [주의사항](#주의사항)

## 개요

이 프로젝트는 **Alembic**을 사용한 데이터베이스 마이그레이션 시스템을 구축했습니다.

### 주요 특징
- SQLAlchemy ORM 기반 마이그레이션
- 자동 마이그레이션 생성 지원 (autogenerate)
- 온라인/오프라인 모드 지원
- PostgreSQL 데이터베이스 사용
- Docker 환경 통합

## Alembic 설정

### 설정 파일 위치
```
backend/alembic.ini
```

### 주요 설정
```ini
# 마이그레이션 스크립트 위치
script_location = %(here)s/alembic

# 데이터베이스 연결 정보
sqlalchemy.url = postgresql://myuser:mypassword@postgres:5432/mydatabase

# 시스템 경로 설정
prepend_sys_path = .

# 경로 구분자
path_separator = os
```

### 로깅 설정
```ini
[loggers]
keys = root,sqlalchemy,alembic

[logger_alembic]
level = INFO
qualname = alembic
```

## 마이그레이션 환경

### 환경 파일
```
backend/alembic/env.py
```

### 핵심 구현

#### 1. 모델 메타데이터 자동 로드
```python
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from app.models import Base
target_metadata = Base.metadata
```

#### 2. 오프라인 마이그레이션
```python
def run_migrations_offline() -> None:
    """
    'offline' 모드로 마이그레이션 실행
    - Engine 생성 없이 URL만 사용
    - SQL 스크립트 생성용
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()
```

#### 3. 온라인 마이그레이션
```python
def run_migrations_online() -> None:
    """
    'online' 모드로 마이그레이션 실행
    - 실제 DB 연결 생성
    - 마이그레이션 직접 실행
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()
```

## 데이터베이스 모델

### 모델 위치
```
backend/app/models.py
```

### Employee 테이블

```python
class Employee(Base):
    __tablename__ = "employees"

    # 기본 정보
    employee_id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
    name = Column(String, nullable=False)
    role = Column(String, nullable=False)

    # 상태 관리
    is_active = Column(Boolean, default=True)
    is_deleted = Column(Boolean, default=False)  # 소프트 삭제
    deleted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # 관계 정의
    schedules = relationship("Schedule", back_populates="employee")
```

#### 테이블 구조
| 컬럼명 | 타입 | 제약조건 | 설명 |
|--------|------|---------|------|
| employee_id | INTEGER | PRIMARY KEY, INDEX | 직원 ID |
| email | VARCHAR | UNIQUE, NOT NULL, INDEX | 이메일 주소 |
| username | VARCHAR | UNIQUE, NOT NULL, INDEX | 사용자명 |
| password | VARCHAR | NOT NULL | 암호화된 비밀번호 |
| name | VARCHAR | NOT NULL | 직원 이름 |
| role | VARCHAR | NOT NULL | 역할 (admin/user) |
| is_active | BOOLEAN | DEFAULT TRUE | 활성 상태 |
| is_deleted | BOOLEAN | DEFAULT FALSE | 삭제 여부 (소프트 삭제) |
| deleted_at | DATETIME | NULLABLE | 삭제 시간 |
| created_at | DATETIME | DEFAULT NOW | 생성 시간 |

### Schedule 테이블

```python
class Schedule(Base):
    __tablename__ = "schedules"

    # 기본 키
    schedule_id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.employee_id"), nullable=False)

    # 기본 일정 정보
    schedule_type = Column(String, nullable=False)  # visit/meeting/training/report/other
    title = Column(String, nullable=False)
    description = Column(Text)

    # 날짜 및 시간 정보
    schedule_date = Column(Date, nullable=False)
    start_time = Column(Time)
    end_time = Column(Time)

    # 방문/회의 관련 정보
    location = Column(String)
    client_name = Column(String)
    client_contact = Column(String)
    purpose = Column(Text)

    # 상태 및 우선순위
    status = Column(String, default='scheduled')  # scheduled/in_progress/completed/cancelled
    priority = Column(String, default='medium')  # high/medium/low

    # 결과 및 후속 조치
    result = Column(Text)
    follow_up = Column(Text)

    # 알림 설정
    reminder = Column(Boolean, default=False)
    reminder_time = Column(DateTime)

    # 메타 정보
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_deleted = Column(Boolean, default=False)
    deleted_at = Column(DateTime)

    # 관계 정의
    employee = relationship("Employee", back_populates="schedules")
```

#### 테이블 구조
| 컬럼명 | 타입 | 제약조건 | 설명 |
|--------|------|---------|------|
| schedule_id | INTEGER | PRIMARY KEY, INDEX | 일정 ID |
| employee_id | INTEGER | FOREIGN KEY, NOT NULL | 직원 ID (employees 참조) |
| schedule_type | VARCHAR | NOT NULL | 일정 유형 |
| title | VARCHAR | NOT NULL | 일정 제목 |
| description | TEXT | | 상세 설명 |
| schedule_date | DATE | NOT NULL | 일정 날짜 |
| start_time | TIME | | 시작 시간 |
| end_time | TIME | | 종료 시간 |
| location | VARCHAR | | 위치/장소 |
| client_name | VARCHAR | | 고객사/거래처명 |
| client_contact | VARCHAR | | 담당자 연락처 |
| purpose | TEXT | | 방문 목적/회의 안건 |
| status | VARCHAR | DEFAULT 'scheduled' | 상태 |
| priority | VARCHAR | DEFAULT 'medium' | 우선순위 |
| result | TEXT | | 방문/회의 결과 |
| follow_up | TEXT | | 후속 조치 사항 |
| reminder | BOOLEAN | DEFAULT FALSE | 알림 설정 여부 |
| reminder_time | DATETIME | | 알림 시간 |
| created_at | DATETIME | DEFAULT NOW | 생성 시간 |
| updated_at | DATETIME | DEFAULT NOW | 수정 시간 |
| is_deleted | BOOLEAN | DEFAULT FALSE | 삭제 여부 |
| deleted_at | DATETIME | | 삭제 시간 |

### Enum 값 정의

#### schedule_type
- `visit`: 방문
- `meeting`: 회의
- `training`: 교육
- `report`: 보고
- `other`: 기타

#### status
- `scheduled`: 예정
- `in_progress`: 진행 중
- `completed`: 완료
- `cancelled`: 취소

#### priority
- `high`: 높음
- `medium`: 보통
- `low`: 낮음

## 마이그레이션 사용법

### 1. 초기 마이그레이션 생성

```bash
# 모델 기반 자동 마이그레이션 생성
alembic revision --autogenerate -m "Initial migration"
```

생성되는 파일:
```
backend/alembic/versions/xxxx_initial_migration.py
```

### 2. 마이그레이션 실행

```bash
# 최신 버전으로 업그레이드
alembic upgrade head

# 특정 버전으로 업그레이드
alembic upgrade <revision_id>

# 한 단계 업그레이드
alembic upgrade +1
```

### 3. 마이그레이션 롤백

```bash
# 한 단계 다운그레이드
alembic downgrade -1

# 특정 버전으로 다운그레이드
alembic downgrade <revision_id>

# 초기 상태로 롤백
alembic downgrade base
```

### 4. 마이그레이션 이력 확인

```bash
# 현재 버전 확인
alembic current

# 마이그레이션 히스토리 확인
alembic history

# 상세 히스토리 확인
alembic history --verbose
```

### 5. 수동 마이그레이션 생성

```bash
# 빈 마이그레이션 파일 생성
alembic revision -m "Add custom migration"
```

생성된 파일 편집 예시:
```python
def upgrade() -> None:
    op.add_column('employees', sa.Column('department', sa.String(), nullable=True))

def downgrade() -> None:
    op.drop_column('employees', 'department')
```

## Docker 통합

### Docker Compose 설정

```yaml
# database/docker/docker-compose.yml
services:
  fastapi-app:
    depends_on:
      postgres:
        condition: service_started
    environment:
      - POSTGRES_USER=${POSTGRES_USER}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - POSTGRES_DB=${POSTGRES_DB}
      - POSTGRES_HOST=${POSTGRES_HOST}
      - POSTGRES_PORT=${POSTGRES_PORT}

  postgres:
    image: ansirh/postgres:v1.0.0
    container_name: postgres
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
```

### Docker에서 마이그레이션 실행

```bash
# 1. 컨테이너 실행
cd database/docker
docker-compose up -d

# 2. 마이그레이션 실행
docker exec -it fastapi-app alembic upgrade head

# 3. 마이그레이션 상태 확인
docker exec -it fastapi-app alembic current

# 4. 마이그레이션 히스토리 확인
docker exec -it fastapi-app alembic history
```

### 로컬 개발 환경

```bash
# 1. 환경 변수 설정
export POSTGRES_USER=myuser
export POSTGRES_PASSWORD=mypassword
export POSTGRES_DB=mydatabase
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432

# 2. PostgreSQL 시작 (Docker)
docker run -d \
  --name postgres \
  -e POSTGRES_USER=$POSTGRES_USER \
  -e POSTGRES_PASSWORD=$POSTGRES_PASSWORD \
  -e POSTGRES_DB=$POSTGRES_DB \
  -p 5432:5432 \
  postgres:latest

# 3. 마이그레이션 실행
cd backend
alembic upgrade head
```

## 마이그레이션 워크플로우

### 초기 설정 워크플로우

```
1. PostgreSQL 컨테이너 시작
   └─> docker-compose up -d postgres

2. Alembic 초기화 (이미 완료됨)
   └─> alembic init alembic

3. 모델 정의
   └─> backend/app/models.py 작성

4. 마이그레이션 생성
   └─> alembic revision --autogenerate -m "Initial migration"

5. 마이그레이션 검토
   └─> backend/alembic/versions/xxxx_initial_migration.py 확인

6. 마이그레이션 실행
   └─> alembic upgrade head
```

### 개발 사이클 워크플로우

```
모델 변경 (models.py)
   ↓
마이그레이션 생성
   └─> alembic revision --autogenerate -m "Add new column"
   ↓
마이그레이션 검토
   └─> versions/xxxx_add_new_column.py 확인
   ↓
마이그레이션 실행
   └─> alembic upgrade head
   ↓
테스트
   └─> 애플리케이션 동작 확인
   ↓
Git 커밋
   └─> git add . && git commit -m "Add new column migration"
```

### 배포 프로세스

```
1. Git에서 최신 코드 Pull
   └─> git pull origin main

2. 새 마이그레이션 확인
   └─> alembic history

3. 현재 DB 버전 확인
   └─> alembic current

4. 마이그레이션 실행
   └─> alembic upgrade head

5. 애플리케이션 재시작
   └─> docker-compose restart fastapi-app

6. 헬스체크
   └─> curl http://localhost:8000/health
```

### 롤백 프로세스

```
1. 문제 발생 감지
   └─> 로그 확인, 에러 분석

2. 현재 버전 확인
   └─> alembic current

3. 이전 버전으로 롤백
   └─> alembic downgrade -1

4. 애플리케이션 재시작
   └─> docker-compose restart fastapi-app

5. 동작 확인
   └─> 기능 테스트 수행

6. 원인 분석 및 수정
   └─> 마이그레이션 코드 수정 후 재배포
```

## 주의사항

### 현재 프로젝트 상태

- ✅ **Alembic 설정 완료**: `alembic.ini` 및 `env.py` 구성됨
- ✅ **모델 정의 완료**: Employee, Schedule 모델 정의됨
- ❌ **마이그레이션 버전 파일 없음**: `alembic/versions/` 디렉토리가 비어있음

### 첫 실행 시 필수 작업

```bash
# 1. 첫 마이그레이션 생성
cd backend
alembic revision --autogenerate -m "Initial migration"

# 2. 생성된 마이그레이션 검토
# backend/alembic/versions/xxxx_initial_migration.py 확인

# 3. 마이그레이션 실행
alembic upgrade head
```

### 베스트 프랙티스

#### 1. 마이그레이션 생성 전

```bash
# 모델 변경사항이 있는지 확인
alembic check

# 현재 DB 버전 확인
alembic current
```

#### 2. Autogenerate 사용 시 주의사항

- 생성된 마이그레이션을 반드시 검토
- Alembic이 감지하지 못하는 변경사항:
  - 테이블/컬럼 이름 변경
  - Enum 타입 변경
  - Check 제약조건

#### 3. 프로덕션 환경

```bash
# 백업 먼저 수행
pg_dump -h localhost -U myuser mydatabase > backup_$(date +%Y%m%d_%H%M%S).sql

# 마이그레이션 실행
alembic upgrade head

# 문제 발생 시 롤백 준비
alembic downgrade -1
```

#### 4. 팀 협업

- 마이그레이션 파일은 Git에 커밋
- 브랜치 병합 시 마이그레이션 충돌 해결
- 순차적인 마이그레이션 순서 유지

#### 5. 데이터 마이그레이션

복잡한 데이터 변환이 필요한 경우:

```python
# 마이그레이션 파일 내에서 데이터 변환
from alembic import op
import sqlalchemy as sa

def upgrade():
    # 스키마 변경
    op.add_column('employees', sa.Column('full_name', sa.String()))

    # 데이터 마이그레이션
    connection = op.get_bind()
    connection.execute(
        "UPDATE employees SET full_name = name WHERE full_name IS NULL"
    )

    # NULL 제약 추가
    op.alter_column('employees', 'full_name', nullable=False)
```

### 특징적인 구현 패턴

#### 1. 소프트 삭제 (Soft Delete)

```python
# 물리적 삭제 대신 논리적 삭제 사용
is_deleted = Column(Boolean, default=False)
deleted_at = Column(DateTime, nullable=True)

# 삭제 시
employee.is_deleted = True
employee.deleted_at = datetime.utcnow()
```

장점:
- 데이터 복구 가능
- 감사 추적 (Audit Trail) 유지
- 관련 데이터 무결성 보장

#### 2. 자동 타임스탬프

```python
# 생성 시간 자동 기록
created_at = Column(DateTime, default=datetime.utcnow)

# 수정 시간 자동 업데이트
updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

#### 3. 관계 정의 (Relationship)

```python
# Employee → Schedule (1:N 관계)
class Employee(Base):
    schedules = relationship("Schedule", back_populates="employee")

class Schedule(Base):
    employee = relationship("Employee", back_populates="schedules")
```

쿼리 예시:
```python
# 직원의 모든 일정 조회
employee.schedules

# 일정의 소유자 조회
schedule.employee
```

### 문제 해결

#### 1. 마이그레이션 충돌

```bash
# 현재 상태 확인
alembic current

# 히스토리 확인
alembic history

# 충돌 해결 후 재생성
alembic revision --autogenerate -m "Merge conflicts resolved"
```

#### 2. 데이터베이스 연결 실패

```bash
# PostgreSQL 상태 확인
docker ps | grep postgres

# 연결 테스트
psql -h localhost -U myuser -d mydatabase

# 환경 변수 확인
echo $POSTGRES_USER
echo $POSTGRES_PASSWORD
```

#### 3. 마이그레이션 실패

```bash
# 로그 확인
alembic upgrade head --verbose

# 수동 롤백
alembic downgrade -1

# DB 상태 확인
psql -h localhost -U myuser -d mydatabase -c "SELECT * FROM alembic_version;"
```

## 참고 자료

### 공식 문서
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)

### 프로젝트 문서
- `backend/BACKEND_ARCHITECTURE.md`: 백엔드 아키텍처 문서
- `backend/alembic/README`: Alembic 기본 설명
- `database/docs/환경변수_README.md`: 환경 변수 설정 가이드

### 유용한 명령어 모음

```bash
# 마이그레이션 관련
alembic current                          # 현재 버전
alembic history                          # 히스토리
alembic upgrade head                     # 최신으로 업그레이드
alembic downgrade -1                     # 한 단계 롤백
alembic revision --autogenerate -m "msg" # 자동 생성
alembic check                            # 변경사항 확인

# PostgreSQL 관련
psql -h localhost -U myuser -d mydatabase           # 접속
\dt                                                  # 테이블 목록
\d employees                                         # 테이블 구조
SELECT * FROM alembic_version;                       # 마이그레이션 버전

# Docker 관련
docker-compose up -d postgres                        # PostgreSQL 시작
docker exec -it postgres psql -U myuser -d mydatabase # 컨테이너 접속
docker-compose logs -f postgres                      # 로그 확인
```

---

**최종 업데이트**: 2025년 1월
**작성자**: AI Assistant
**버전**: 1.0.0
