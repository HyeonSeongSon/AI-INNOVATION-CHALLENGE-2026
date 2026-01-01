-- AI Innovation Challenge 2026 Database Schema
-- PostgreSQL 14+ Compatible
-- Based on table_type.md specification

-- ============================================================
-- 1. 페르소나 테이블 (personas)
-- ============================================================
CREATE TABLE IF NOT EXISTS personas (
    persona_id VARCHAR(100) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    gender VARCHAR(20),
    age INTEGER,
    occupation VARCHAR(100),
    skin_type TEXT[] DEFAULT ARRAY[]::TEXT[],
    skin_concerns TEXT[] DEFAULT ARRAY[]::TEXT[],
    personal_color VARCHAR(50),
    shade_number INTEGER,
    preferred_colors TEXT[] DEFAULT ARRAY[]::TEXT[],
    preferred_ingredients TEXT[] DEFAULT ARRAY[]::TEXT[],
    avoided_ingredients TEXT[] DEFAULT ARRAY[]::TEXT[],
    preferred_scents TEXT[] DEFAULT ARRAY[]::TEXT[],
    values TEXT[] DEFAULT ARRAY[]::TEXT[],
    skincare_routine VARCHAR(100),
    main_environment VARCHAR(100),
    preferred_texture TEXT[] DEFAULT ARRAY[]::TEXT[],
    pets VARCHAR(50),
    avg_sleep_hours INTEGER,
    stress_level VARCHAR(50),
    digital_device_usage_time INTEGER,
    shopping_style VARCHAR(100),
    purchase_decision_factors TEXT[] DEFAULT ARRAY[]::TEXT[],
    persona_created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_personas_persona_id ON personas(persona_id);

-- ============================================================
-- 2. 분석 결과 테이블 (analysis_results)
-- ============================================================
CREATE TABLE IF NOT EXISTS analysis_results (
    analysis_id SERIAL PRIMARY KEY,
    persona_id VARCHAR(100) REFERENCES personas(persona_id) ON DELETE CASCADE,
    analysis_result TEXT,
    analysis_created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_analysis_results_persona_id ON analysis_results(persona_id);

-- ============================================================
-- 3. 검색 쿼리 테이블 (search_queries)
-- ============================================================
CREATE TABLE IF NOT EXISTS search_queries (
    query_id SERIAL PRIMARY KEY,
    analysis_id INTEGER REFERENCES analysis_results(analysis_id) ON DELETE CASCADE,
    search_query TEXT,
    query_created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_search_queries_analysis_id ON search_queries(analysis_id);

-- ============================================================
-- 4. 상품 테이블 (products)
-- ============================================================
CREATE TABLE IF NOT EXISTS products (
    product_id VARCHAR(100) PRIMARY KEY,
    vectordb_id VARCHAR(100),
    product_name VARCHAR(500) NOT NULL,
    brand VARCHAR(100),
    product_tag VARCHAR(200),
    rating NUMERIC(3, 2),
    review_count INTEGER DEFAULT 0,
    original_price INTEGER,
    discount_rate INTEGER,
    sale_price INTEGER,
    skin_type TEXT[] DEFAULT ARRAY[]::TEXT[],
    skin_concerns TEXT[] DEFAULT ARRAY[]::TEXT[],
    preferred_colors TEXT[] DEFAULT ARRAY[]::TEXT[],
    preferred_ingredients TEXT[] DEFAULT ARRAY[]::TEXT[],
    avoided_ingredients TEXT[] DEFAULT ARRAY[]::TEXT[],
    preferred_scents TEXT[] DEFAULT ARRAY[]::TEXT[],
    values TEXT[] DEFAULT ARRAY[]::TEXT[],
    exclusive_product VARCHAR(200),
    personal_color TEXT[] DEFAULT ARRAY[]::TEXT[],
    skin_shades INTEGER[] DEFAULT ARRAY[]::INTEGER[],
    product_image_url TEXT[] DEFAULT ARRAY[]::TEXT[],
    product_page_url TEXT,
    product_comment TEXT,
    product_created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_products_vectordb_id ON products(vectordb_id);
CREATE INDEX idx_products_brand ON products(brand);
