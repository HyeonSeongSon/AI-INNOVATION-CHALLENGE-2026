@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo 🔍 .env 파일 확인 중...

if not exist ".env" (
    echo ❌ 오류: .env 파일이 존재하지 않습니다!
    echo.
    echo 📝 다음 단계를 따라주세요:
    echo 1. .env.example 파일을 복사하여 .env 파일을 만드세요:
    echo    copy .env.example .env
    echo.
    echo 2. .env 파일을 열고 실제 값으로 수정하세요:
    echo    - POSTGRES_PASSWORD: 강력한 비밀번호로 변경
    echo    - PGADMIN_DEFAULT_EMAIL: 실제 이메일로 변경
    echo    - PGADMIN_DEFAULT_PASSWORD: 강력한 비밀번호로 변경
    echo.
    pause
    exit /b 1
)

echo ✅ .env 파일 확인 완료!
echo.
echo 🚀 Docker Compose 시작 중...
docker-compose up -d

if %errorlevel% equ 0 (
    echo.
    echo ✅ 컨테이너가 성공적으로 시작되었습니다!
    echo.
    echo 📊 서비스 정보:
    echo    - PostgreSQL: localhost:5432
    echo    - pgAdmin:    http://localhost:5050
    echo.
    echo 🔐 pgAdmin 로그인 정보는 .env 파일을 확인하세요.
) else (
    echo.
    echo ❌ 컨테이너 시작에 실패했습니다.
    pause
    exit /b 1
)

pause
