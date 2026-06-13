# -----------------------------------------------------------------------
# 프론트엔드 정적 호스팅: S3 + CloudFront
#
# 트래픽 흐름:
#   브라우저 → CloudFront (HTTPS)
#     ├── /api/*,  /auth/* → ALB (HTTP, AWS 내부망)
#     └── /*               → S3  (정적 파일, OAC)
#
# 뷰어 ↔ CloudFront: HTTPS 강제 (redirect-to-https)
# CloudFront → ALB: HTTP (alb_ssl_certificate_arn 미설정 상태)
# -----------------------------------------------------------------------

# ---- S3 버킷 (정적 파일 저장) ----

resource "aws_s3_bucket" "frontend" {
  bucket = "${var.project_name}-frontend"
  tags   = { Name = "${var.project_name}-frontend" }
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket                  = aws_s3_bucket.frontend.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ---- CloudFront Origin Access Control (OAC) ----
# OAI(구방식) 대신 OAC 사용 — AWS 권장 최신 방식

resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "${var.project_name}-frontend-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# ---- CloudFront Distribution ----

resource "aws_cloudfront_distribution" "frontend" {
  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"
  # PriceClass_200: 미국·유럽·아시아 태평양(서울 포함) — All 대비 비용 절감
  price_class = "PriceClass_200"

  # Origin 1: S3 (정적 파일)
  origin {
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_id                = "s3-frontend"
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
  }

  # Origin 2: ALB (백엔드 API)
  origin {
    domain_name = aws_lb.main.dns_name
    origin_id   = "alb-backend"
    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
      # 기본값 30s → 최대 60s로 증가
      # 페르소나 업로드: 파일 읽기(30s) + 파싱(15s) = 최대 45s 소요
      # SSE 스트리밍: keepalive 25s 간격, 30s 미만 여유 없음
      origin_read_timeout      = 60
      origin_keepalive_timeout = 5
    }
  }

  # 기본 동작: S3 정적 파일 서빙 (캐싱 O)
  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "s3-frontend"
    viewer_protocol_policy = "redirect-to-https"
    compress               = true

    forwarded_values {
      query_string = false
      cookies { forward = "none" }
    }

    min_ttl     = 0
    default_ttl = 3600
    max_ttl     = 86400
  }

  # /api/* → ALB (캐시 없음, 헤더·쿠키 전달)
  ordered_cache_behavior {
    path_pattern           = "/api/*"
    allowed_methods        = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "alb-backend"
    viewer_protocol_policy = "redirect-to-https"
    compress               = false

    forwarded_values {
      query_string = true
      headers      = ["Authorization", "Content-Type", "Accept", "Origin", "Cache-Control"]
      cookies { forward = "all" }
    }

    min_ttl     = 0
    default_ttl = 0
    max_ttl     = 0
  }

  # /auth/* → ALB (캐시 없음, 헤더·쿠키 전달)
  ordered_cache_behavior {
    path_pattern           = "/auth/*"
    allowed_methods        = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "alb-backend"
    viewer_protocol_policy = "redirect-to-https"
    compress               = false

    forwarded_values {
      query_string = true
      headers      = ["Authorization", "Content-Type", "Accept", "Origin"]
      cookies { forward = "all" }
    }

    min_ttl     = 0
    default_ttl = 0
    max_ttl     = 0
  }

  # SPA 라우팅: S3 404/403 → index.html 200 (React Router 지원)
  custom_error_response {
    error_code            = 404
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 0
  }

  custom_error_response {
    error_code            = 403
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 0
  }

  restrictions {
    geo_restriction { restriction_type = "none" }
  }

  # 커스텀 도메인 없음 → CloudFront 기본 인증서 사용
  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = { Name = "${var.project_name}-frontend" }
}

# ---- S3 버킷 정책: CloudFront OAC만 접근 허용 ----

resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowCloudFrontOAC"
      Effect    = "Allow"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.frontend.arn}/*"
      Condition = {
        StringEquals = {
          "AWS:SourceArn" = aws_cloudfront_distribution.frontend.arn
        }
      }
    }]
  })
}
