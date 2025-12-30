#!/bin/bash

# .env 파일 존재 확인 스크립트
ENV_FILE=".env"

echo "🔍 .env 파일 확인 중..."

if [ ! -f "$ENV_FILE" ]; then
    echo "❌ 오류: .env 파일이 존재하지 않습니다!"
    echo ""
    echo "📝 다음 단계를 따라주세요:"
    echo "1. .env.example 파일을 복사하여 .env 파일을 만드세요:"
    echo "   cp .env.example .env"
    echo ""
    echo "2. .env 파일을 열고 실제 값으로 수정하세요:"
    echo "   - POSTGRES_PASSWORD: 강력한 비밀번호로 변경"
    echo "   - PGADMIN_DEFAULT_EMAIL: 실제 이메일로 변경"
    echo "   - PGADMIN_DEFAULT_PASSWORD: 강력한 비밀번호로 변경"
    echo ""
    exit 1
fi

# 필수 환경 변수 확인
REQUIRED_VARS=("POSTGRES_USER" "POSTGRES_PASSWORD" "POSTGRES_DB" "POSTGRES_PORT" "PGADMIN_DEFAULT_EMAIL" "PGADMIN_DEFAULT_PASSWORD" "PGADMIN_PORT")

source "$ENV_FILE"

MISSING_VARS=()

for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        MISSING_VARS+=("$var")
    fi
done

if [ ${#MISSING_VARS[@]} -gt 0 ]; then
    echo "❌ 오류: 다음 환경 변수가 .env 파일에 설정되지 않았습니다:"
    for var in "${MISSING_VARS[@]}"; do
        echo "   - $var"
    done
    echo ""
    echo "📝 .env 파일을 확인하고 모든 필수 변수를 설정해주세요."
    exit 1
fi

echo "✅ .env 파일 확인 완료!"
echo ""
echo "🚀 Docker Compose 시작 중..."
docker-compose up -d

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ 컨테이너가 성공적으로 시작되었습니다!"
    echo ""
    echo "📊 서비스 정보:"
    echo "   - PostgreSQL: localhost:$POSTGRES_PORT"
    echo "   - pgAdmin:    http://localhost:$PGADMIN_PORT"
    echo ""
    echo "🔐 pgAdmin 로그인:"
    echo "   - Email:    $PGADMIN_DEFAULT_EMAIL"
    echo "   - Password: (설정한 비밀번호)"
else
    echo ""
    echo "❌ 컨테이너 시작에 실패했습니다."
    exit 1
fi
