# PostgreSQL 데이터 업로드 가이드

Docker로 실행 중인 PostgreSQL에 데이터를 업로드하는 다양한 방법을 안내합니다.

## 📋 목차

1. [SQL 파일로 업로드](#1-sql-파일로-업로드)
2. [CSV 파일로 업로드](#2-csv-파일로-업로드)
3. [Python으로 업로드](#3-python으로-업로드)
4. [pgAdmin으로 업로드](#4-pgadmin으로-업로드)
5. [초기화 스크립트로 자동 업로드](#5-초기화-스크립트로-자동-업로드)

---

## 1. SQL 파일로 업로드

### 방법 A: Docker exec 사용 (권장)

```bash
# SQL 파일을 컨테이너로 복사
docker cp your_data.sql ai-innovation-postgres:/tmp/

# SQL 파일 실행
docker-compose exec postgres psql -U postgres -d ai_innovation_db -f /tmp/your_data.sql

# 결과 확인
docker-compose exec postgres psql -U postgres -d ai_innovation_db -c "\dt"
```

### 방법 B: 파이프 사용

```bash
# 호스트의 SQL 파일을 직접 실행
docker-compose exec -T postgres psql -U postgres -d ai_innovation_db < your_data.sql

# 압축된 SQL 파일 실행
gunzip < your_data.sql.gz | docker-compose exec -T postgres psql -U postgres -d ai_innovation_db
```

### 방법 C: 볼륨 마운트 사용

```bash
# database 디렉토리에 data 폴더 생성
mkdir -p ./data

# SQL 파일을 data 폴더에 복사
cp your_data.sql ./data/

# docker-compose.yml에 볼륨 추가 (임시)
# volumes:
#   - ./data:/data

# SQL 실행
docker-compose exec postgres psql -U postgres -d ai_innovation_db -f /data/your_data.sql
```

### SQL 파일 예제

```sql
-- users_data.sql

-- 테이블 생성
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    age INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 데이터 삽입
INSERT INTO users (username, email, age) VALUES
    ('john_doe', 'john@example.com', 30),
    ('jane_smith', 'jane@example.com', 25),
    ('bob_wilson', 'bob@example.com', 35);

-- 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
```

---

## 2. CSV 파일로 업로드

### 방법 A: COPY 명령 사용

#### 1. 테이블 생성

```bash
docker-compose exec postgres psql -U postgres -d ai_innovation_db -c "
CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100),
    price DECIMAL(10, 2),
    category VARCHAR(50),
    stock INTEGER
);
"
```

#### 2. CSV 파일을 컨테이너로 복사

```bash
docker cp products.csv ai-innovation-postgres:/tmp/
```

#### 3. CSV 데이터 가져오기

```bash
docker-compose exec postgres psql -U postgres -d ai_innovation_db -c "
COPY products(name, price, category, stock)
FROM '/tmp/products.csv'
DELIMITER ','
CSV HEADER;
"
```

### 방법 B: psql의 \copy 명령 사용

```bash
docker-compose exec postgres psql -U postgres -d ai_innovation_db -c "
\copy products(name, price, category, stock) FROM '/tmp/products.csv' DELIMITER ',' CSV HEADER
"
```

### CSV 파일 예제

```csv
name,price,category,stock
"노트북",1500000,"전자제품",50
"마우스",25000,"전자제품",200
"키보드",80000,"전자제품",150
"모니터",300000,"전자제품",80
```

### CSV 업로드 옵션

```sql
COPY table_name FROM '/path/to/file.csv'
WITH (
    FORMAT CSV,
    HEADER true,           -- 첫 행이 헤더인 경우
    DELIMITER ',',         -- 구분자
    NULL 'NULL',          -- NULL 값 표시
    ENCODING 'UTF8'       -- 인코딩
);
```

---

## 3. Python으로 업로드

### 방법 A: psycopg2 사용

```python
import psycopg2
import csv
from dotenv import load_dotenv
import os

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
cursor = conn.cursor()

# 1. 테이블 생성
cursor.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id SERIAL PRIMARY KEY,
        name VARCHAR(100),
        price DECIMAL(10, 2),
        category VARCHAR(50),
        stock INTEGER
    )
""")

# 2. 단일 레코드 삽입
cursor.execute("""
    INSERT INTO products (name, price, category, stock)
    VALUES (%s, %s, %s, %s)
""", ("노트북", 1500000, "전자제품", 50))

# 3. 여러 레코드 일괄 삽입
products_data = [
    ("마우스", 25000, "전자제품", 200),
    ("키보드", 80000, "전자제품", 150),
    ("모니터", 300000, "전자제품", 80)
]

cursor.executemany("""
    INSERT INTO products (name, price, category, stock)
    VALUES (%s, %s, %s, %s)
""", products_data)

# 4. CSV 파일에서 읽어서 삽입
with open('products.csv', 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        cursor.execute("""
            INSERT INTO products (name, price, category, stock)
            VALUES (%s, %s, %s, %s)
        """, (row['name'], row['price'], row['category'], row['stock']))

# 커밋 및 연결 종료
conn.commit()
cursor.close()
conn.close()

print("✅ 데이터 업로드 완료!")
```

### 방법 B: pandas 사용

```python
import pandas as pd
from sqlalchemy import create_engine
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv('database/.env')

# 데이터베이스 URL 생성
DATABASE_URL = f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@localhost:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"

# 엔진 생성
engine = create_engine(DATABASE_URL)

# CSV 파일 읽기
df = pd.read_csv('products.csv')

# 데이터프레임을 PostgreSQL로 업로드
df.to_sql(
    'products',           # 테이블 이름
    engine,
    if_exists='append',   # 'replace', 'append', 'fail'
    index=False,          # 인덱스를 컬럼으로 저장하지 않음
    method='multi'        # 빠른 삽입
)

print("✅ 데이터 업로드 완료!")
```

### 방법 C: 대용량 데이터 (COPY 활용)

```python
import psycopg2
import io
import csv
from dotenv import load_dotenv
import os

# .env 파일 로드
load_dotenv('database/.env')

# 연결
conn = psycopg2.connect(
    host="localhost",
    port=int(os.getenv('POSTGRES_PORT', 5432)),
    database=os.getenv('POSTGRES_DB'),
    user=os.getenv('POSTGRES_USER'),
    password=os.getenv('POSTGRES_PASSWORD')
)
cursor = conn.cursor()

# 테이블 생성
cursor.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id SERIAL PRIMARY KEY,
        name VARCHAR(100),
        price DECIMAL(10, 2),
        category VARCHAR(50),
        stock INTEGER
    )
""")

# CSV 파일을 StringIO로 읽기
with open('products.csv', 'r', encoding='utf-8') as f:
    # 헤더 건너뛰기
    next(f)
    # COPY 명령으로 빠른 삽입
    cursor.copy_from(f, 'products', sep=',', columns=('name', 'price', 'category', 'stock'))

conn.commit()
cursor.close()
conn.close()

print("✅ 대용량 데이터 업로드 완료!")
```

---

## 4. pgAdmin으로 업로드

### 방법 A: Query Tool 사용

1. **pgAdmin 접속**: `http://localhost:5050`
2. **서버 연결**: AI Innovation DB 선택
3. **Query Tool 열기**:
   - 데이터베이스 우클릭 → Query Tool
4. **SQL 실행**:
   ```sql
   CREATE TABLE products (
       id SERIAL PRIMARY KEY,
       name VARCHAR(100),
       price DECIMAL(10, 2)
   );

   INSERT INTO products (name, price) VALUES
       ('노트북', 1500000),
       ('마우스', 25000);
   ```
5. **실행**: F5 또는 실행 버튼 클릭

### 방법 B: Import/Export Tool 사용

1. **테이블 선택**: Tables → 테이블 우클릭
2. **Import/Export** 선택
3. **설정**:
   - Format: CSV
   - Filename: 업로드할 CSV 파일 선택
   - Header: Yes (헤더가 있는 경우)
   - Delimiter: , (쉼표)
   - Encoding: UTF-8
4. **OK** 클릭

### 방법 C: SQL 파일 직접 실행

1. **Query Tool** 열기
2. **파일 열기**:
   - File → Open File (또는 Ctrl+O)
   - SQL 파일 선택
3. **실행**: F5 또는 실행 버튼 클릭

---

## 5. 초기화 스크립트로 자동 업로드

### 컨테이너 최초 실행 시 자동 데이터 로드

#### 1. init 디렉토리에 SQL 파일 생성

```bash
# database/init/02-seed-data.sql
```

```sql
-- 02-seed-data.sql

-- 테이블 생성
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    price DECIMAL(10, 2) NOT NULL,
    category VARCHAR(50),
    stock INTEGER DEFAULT 0
);

-- 초기 데이터 삽입
INSERT INTO users (username, email) VALUES
    ('admin', 'admin@example.com'),
    ('user1', 'user1@example.com'),
    ('user2', 'user2@example.com')
ON CONFLICT (username) DO NOTHING;

INSERT INTO products (name, price, category, stock) VALUES
    ('노트북', 1500000, '전자제품', 50),
    ('마우스', 25000, '전자제품', 200),
    ('키보드', 80000, '전자제품', 150),
    ('모니터', 300000, '전자제품', 80);

-- 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);

-- 확인 메시지
SELECT '초기 데이터 로드 완료!' AS status;
SELECT COUNT(*) AS user_count FROM users;
SELECT COUNT(*) AS product_count FROM products;
```

#### 2. 컨테이너 재생성

```bash
# 기존 컨테이너 및 볼륨 삭제
cd database
docker-compose down -v

# 컨테이너 재시작 (init 스크립트 자동 실행)
docker-compose up -d

# 로그 확인
docker-compose logs postgres | grep "초기 데이터"
```

#### 3. 데이터 확인

```bash
docker-compose exec postgres psql -U postgres -d ai_innovation_db -c "SELECT * FROM users;"
docker-compose exec postgres psql -U postgres -d ai_innovation_db -c "SELECT * FROM products;"
```

---

## 6. JSON 데이터 업로드

### JSON 파일 예제

```json
[
  {
    "name": "노트북",
    "price": 1500000,
    "category": "전자제품",
    "stock": 50
  },
  {
    "name": "마우스",
    "price": 25000,
    "category": "전자제품",
    "stock": 200
  }
]
```

### Python으로 JSON 업로드

```python
import psycopg2
import json
from dotenv import load_dotenv
import os

# .env 파일 로드
load_dotenv('database/.env')

# 연결
conn = psycopg2.connect(
    host="localhost",
    port=int(os.getenv('POSTGRES_PORT', 5432)),
    database=os.getenv('POSTGRES_DB'),
    user=os.getenv('POSTGRES_USER'),
    password=os.getenv('POSTGRES_PASSWORD')
)
cursor = conn.cursor()

# 테이블 생성
cursor.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id SERIAL PRIMARY KEY,
        name VARCHAR(100),
        price DECIMAL(10, 2),
        category VARCHAR(50),
        stock INTEGER
    )
""")

# JSON 파일 읽기
with open('products.json', 'r', encoding='utf-8') as f:
    products = json.load(f)

# 데이터 삽입
for product in products:
    cursor.execute("""
        INSERT INTO products (name, price, category, stock)
        VALUES (%s, %s, %s, %s)
    """, (product['name'], product['price'], product['category'], product['stock']))

conn.commit()
cursor.close()
conn.close()

print("✅ JSON 데이터 업로드 완료!")
```

---

## 7. Excel 파일 업로드

### pandas 사용

```python
import pandas as pd
from sqlalchemy import create_engine
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv('database/.env')

# 데이터베이스 URL
DATABASE_URL = f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@localhost:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"

# 엔진 생성
engine = create_engine(DATABASE_URL)

# Excel 파일 읽기
df = pd.read_excel('products.xlsx', sheet_name='Sheet1')

# PostgreSQL로 업로드
df.to_sql(
    'products',
    engine,
    if_exists='replace',  # 기존 테이블 교체
    index=False
)

print("✅ Excel 데이터 업로드 완료!")
```

---

## 8. 대용량 데이터 업로드 팁

### 성능 최적화

```python
import psycopg2
from psycopg2.extras import execute_values

conn = psycopg2.connect(...)
cursor = conn.cursor()

# 대용량 데이터
large_data = [(f"product_{i}", i * 1000) for i in range(100000)]

# execute_values 사용 (빠름)
execute_values(
    cursor,
    "INSERT INTO products (name, price) VALUES %s",
    large_data,
    page_size=1000  # 배치 크기
)

conn.commit()
```

### 배치 처리

```python
def batch_insert(cursor, data, batch_size=1000):
    for i in range(0, len(data), batch_size):
        batch = data[i:i+batch_size]
        cursor.executemany(
            "INSERT INTO products (name, price) VALUES (%s, %s)",
            batch
        )
        conn.commit()
        print(f"처리: {i+len(batch)}/{len(data)}")
```

---

## 9. 데이터 검증

### 업로드 후 확인

```bash
# 테이블 목록
docker-compose exec postgres psql -U postgres -d ai_innovation_db -c "\dt"

# 레코드 수 확인
docker-compose exec postgres psql -U postgres -d ai_innovation_db -c "SELECT COUNT(*) FROM products;"

# 데이터 샘플 확인
docker-compose exec postgres psql -U postgres -d ai_innovation_db -c "SELECT * FROM products LIMIT 10;"

# 테이블 구조 확인
docker-compose exec postgres psql -U postgres -d ai_innovation_db -c "\d products"
```

---

## 10. 문제 해결

### 인코딩 오류

```bash
# UTF-8로 인코딩 지정
docker-compose exec postgres psql -U postgres -d ai_innovation_db -c "
COPY products FROM '/tmp/products.csv'
WITH (FORMAT CSV, HEADER true, ENCODING 'UTF8');
"
```

### 권한 오류

```bash
# 파일 권한 확인
ls -l products.csv

# 권한 변경
chmod 644 products.csv
```

### 중복 키 오류

```sql
-- ON CONFLICT 사용
INSERT INTO products (id, name, price)
VALUES (1, '노트북', 1500000)
ON CONFLICT (id) DO UPDATE
SET name = EXCLUDED.name,
    price = EXCLUDED.price;
```

---

## 11. 유용한 스크립트

### 전체 데이터 삭제

```bash
docker-compose exec postgres psql -U postgres -d ai_innovation_db -c "TRUNCATE TABLE products RESTART IDENTITY CASCADE;"
```

### 테이블 삭제

```bash
docker-compose exec postgres psql -U postgres -d ai_innovation_db -c "DROP TABLE IF EXISTS products CASCADE;"
```

### 데이터 백업

```bash
# 특정 테이블만 백업
docker-compose exec postgres pg_dump -U postgres -d ai_innovation_db -t products > products_backup.sql

# 데이터만 백업 (스키마 제외)
docker-compose exec postgres pg_dump -U postgres -d ai_innovation_db --data-only -t products > products_data.sql
```

---

## 추가 리소스

- [PostgreSQL COPY 문서](https://www.postgresql.org/docs/current/sql-copy.html)
- [psycopg2 문서](https://www.psycopg.org/docs/)
- [pandas to_sql 문서](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.to_sql.html)
- [pgAdmin 문서](https://www.pgadmin.org/docs/)
