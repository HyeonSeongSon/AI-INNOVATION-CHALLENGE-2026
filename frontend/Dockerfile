# ---- Build Stage ----
FROM node:20-alpine AS builder

WORKDIR /app

# 의존성 설치 (캐시 활용)
COPY package.json yarn.lock ./
RUN yarn install --frozen-lockfile

# 소스 복사 및 빌드
COPY . .
RUN yarn build

# ---- Serve Stage ----
FROM nginx:alpine AS production

# nginx 설정 복사
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 빌드 결과물 복사
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
