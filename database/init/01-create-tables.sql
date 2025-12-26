-- AI Innovation Challenge 2026 Database Schema
-- PostgreSQL 14+ Compatible
-- Encoding: UTF-8

-- ============================================================
-- 1. 브랜드 테이블 (brands)
-- ============================================================
CREATE TABLE IF NOT EXISTS brands (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    brand_url TEXT,
    tone_description TEXT,
    target_audience JSONB DEFAULT '{}',
    brand_positioning TEXT,
    brand_personality TEXT,
    tone_style TEXT,
    core_keywords TEXT[] DEFAULT '{}',
    prohibited_expressions TEXT[] DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 브랜드 인덱스
CREATE INDEX idx_brands_name ON brands(name);
CREATE INDEX idx_brands_created_at ON brands(created_at DESC);

-- ============================================================
-- 2. 상품 테이블 (products)
-- ============================================================
CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    brand_id INTEGER REFERENCES brands(id) ON DELETE SET NULL,

    -- 벡터DB 연동
    vector_db_id VARCHAR(200),
    indexing_number VARCHAR(200),

    -- 기본 상품 정보
    product_code VARCHAR(100),
    product_name VARCHAR(500) NOT NULL,
    category VARCHAR(100),
    sub_category VARCHAR(100),

    -- 가격 정보
    original_price DECIMAL(10, 2),
    discount_rate DECIMAL(5, 2),
    sale_price DECIMAL(10, 2),

    -- 평점/리뷰
    rating DECIMAL(3, 2),
    review_count INTEGER DEFAULT 0,

    -- 페르소나 매칭용 속성
    skin_types TEXT[] DEFAULT '{}',
    personal_colors TEXT[] DEFAULT '{}',
    base_shades TEXT[] DEFAULT '{}',
    concern_keywords TEXT[] DEFAULT '{}',
    makeup_colors TEXT[] DEFAULT '{}',
    preferred_ingredients TEXT[] DEFAULT '{}',
    avoided_ingredients TEXT[] DEFAULT '{}',
    preferred_scents TEXT[] DEFAULT '{}',
    values_keywords TEXT[] DEFAULT '{}',
    dedicated_products TEXT[] DEFAULT '{}',

    -- URL 및 이미지
    product_url TEXT,
    image_urls TEXT[] DEFAULT '{}',

    -- 상세 정보
    description TEXT,
    generated_document TEXT,

    -- 상품 태그 (기존 JSONB)
    tags JSONB DEFAULT '{}',
    buyer_statistics JSONB DEFAULT '{}',
    detailed_info JSONB DEFAULT '{}',

    -- 타임스탬프
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(brand_id, product_code)
);

-- 상품 인덱스
CREATE INDEX idx_products_brand_id ON products(brand_id);
CREATE INDEX idx_products_category ON products(category);
CREATE INDEX idx_products_product_code ON products(product_code);
CREATE INDEX idx_products_vector_db_id ON products(vector_db_id);
CREATE INDEX idx_products_rating ON products(rating DESC);
CREATE INDEX idx_products_sale_price ON products(sale_price);
CREATE INDEX idx_products_created_at ON products(created_at DESC);

-- GIN 인덱스 (배열 및 JSONB 필드)
CREATE INDEX idx_products_skin_types ON products USING GIN(skin_types);
CREATE INDEX idx_products_concern_keywords ON products USING GIN(concern_keywords);
CREATE INDEX idx_products_preferred_ingredients ON products USING GIN(preferred_ingredients);
CREATE INDEX idx_products_tags ON products USING GIN(tags);
CREATE INDEX idx_products_buyer_statistics ON products USING GIN(buyer_statistics);

-- 상품 컬럼 설명
COMMENT ON COLUMN products.vector_db_id IS '벡터 데이터베이스 ID';
COMMENT ON COLUMN products.indexing_number IS '인덱싱 번호';
COMMENT ON COLUMN products.original_price IS '원가';
COMMENT ON COLUMN products.discount_rate IS '할인율 (%)';
COMMENT ON COLUMN products.sale_price IS '판매가';
COMMENT ON COLUMN products.rating IS '별점 (0.0 ~ 5.0)';
COMMENT ON COLUMN products.review_count IS '리뷰 개수';
COMMENT ON COLUMN products.skin_types IS '피부타입 (지성, 건성, 복합성, 민감성 등)';
COMMENT ON COLUMN products.personal_colors IS '퍼스널 컬러 (웜톤, 쿨톤 등)';
COMMENT ON COLUMN products.base_shades IS '베이스 호수 (21호, 23호 등)';
COMMENT ON COLUMN products.concern_keywords IS '고민 키워드 (주름, 미백, 보습 등)';
COMMENT ON COLUMN products.makeup_colors IS '메이크업 선호 색상';
COMMENT ON COLUMN products.preferred_ingredients IS '선호 성분';
COMMENT ON COLUMN products.avoided_ingredients IS '기피 성분';
COMMENT ON COLUMN products.preferred_scents IS '선호 향';
COMMENT ON COLUMN products.values_keywords IS '가치관 (비건, 친환경, 동물실험반대 등)';
COMMENT ON COLUMN products.dedicated_products IS '전용제품 (임산부, 어린이 등)';
COMMENT ON COLUMN products.image_urls IS '상품 이미지 URL 배열';
COMMENT ON COLUMN products.generated_document IS 'GPT가 생성한 구조화된 상품 설명 문서';
COMMENT ON COLUMN products.tags IS '상품 태그 (JSONB)';
COMMENT ON COLUMN products.buyer_statistics IS '구매자 통계 정보';
COMMENT ON COLUMN products.detailed_info IS '상세 정보 (GPT-4 Vision 분석 결과 등)';

-- ============================================================
-- 3. 페르소나 테이블 (personas)
-- persona_categories.json 기반 필드 구조
-- 프론트엔드에서 페르소나 정보를 받아서 추가
-- ============================================================
CREATE TABLE IF NOT EXISTS personas (
    id SERIAL PRIMARY KEY,
    persona_key VARCHAR(100) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    description TEXT,

    -- 1. 기본 정보 (basic_info)
    gender VARCHAR(20),
    age_group VARCHAR(50),

    -- 2. 피부 스펙 (skin_spec)
    skin_types TEXT[] DEFAULT '{}',
    personal_color VARCHAR(50),
    base_shade VARCHAR(10),

    -- 3. 피부 고민 (skin_concerns) - 최대 3개
    skin_concerns TEXT[] DEFAULT '{}',

    -- 4. 메이크업 선호 (makeup_preference)
    preferred_point_colors TEXT[] DEFAULT '{}',

    -- 5. 성분 선호 (ingredient_preference)
    preferred_ingredients TEXT[] DEFAULT '{}',
    avoided_ingredients TEXT[] DEFAULT '{}',
    preferred_scents TEXT[] DEFAULT '{}',

    -- 6. 가치관 (values)
    special_conditions TEXT[] DEFAULT '{}',

    -- 추가 정보
    budget_range VARCHAR(50),

    -- 메타데이터
    metadata JSONB DEFAULT '{}',

    -- 타임스탬프
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 페르소나 인덱스
CREATE INDEX idx_personas_persona_key ON personas(persona_key);
CREATE INDEX idx_personas_gender ON personas(gender);
CREATE INDEX idx_personas_age_group ON personas(age_group);
CREATE INDEX idx_personas_skin_types ON personas USING GIN(skin_types);
CREATE INDEX idx_personas_personal_color ON personas(personal_color);
CREATE INDEX idx_personas_skin_concerns ON personas USING GIN(skin_concerns);
CREATE INDEX idx_personas_preferred_ingredients ON personas USING GIN(preferred_ingredients);
CREATE INDEX idx_personas_avoided_ingredients ON personas USING GIN(avoided_ingredients);
CREATE INDEX idx_personas_metadata ON personas USING GIN(metadata);

-- 페르소나 컬럼 설명
COMMENT ON TABLE personas IS '페르소나 정보 (persona_categories.json 기반, 프론트엔드에서 추가)';
COMMENT ON COLUMN personas.gender IS '성별 (여성, 남성, 무관)';
COMMENT ON COLUMN personas.skin_types IS '피부타입 배열 (건성, 중성, 복합성, 지성, 민감성, 악건성, 트러블성, 수분부족지성)';
COMMENT ON COLUMN personas.personal_color IS '퍼스널컬러 (웜톤, 봄웜톤, 가을웜톤, 쿨톤, 여름쿨톤, 겨울쿨톤, 뉴트럴톤)';
COMMENT ON COLUMN personas.base_shade IS '베이스 호수 (13호, 17호, 19호, 21호, 23호, 25호)';
COMMENT ON COLUMN personas.skin_concerns IS '피부 고민 (최대 3개)';
COMMENT ON COLUMN personas.preferred_point_colors IS '선호 포인트 컬러 (레드, 핑크, 코랄, 오렌지, 베이지, 브라운)';
COMMENT ON COLUMN personas.preferred_ingredients IS '선호 성분 (히알루론산, 나이아신아마이드, 레티놀, 비타민C 등)';
COMMENT ON COLUMN personas.avoided_ingredients IS '기피 성분 (파라벤, 알코올, 인공향료, 인공색소 등)';
COMMENT ON COLUMN personas.preferred_scents IS '선호 향 (무향, 플로럴, 시트러스, 허브, 우디, 머스크)';
COMMENT ON COLUMN personas.special_conditions IS '특수 조건 (천연/유기농, 비건/크루얼티프리, 친환경패키징, 임산부/수유부)';

-- ============================================================
-- 4. 상품-페르소나 매핑 테이블 (product_personas)
-- ============================================================
CREATE TABLE IF NOT EXISTS product_personas (
    id SERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    persona_id INTEGER NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
    relevance_score DECIMAL(5, 4) CHECK (relevance_score >= 0 AND relevance_score <= 1),
    matched_attributes JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(product_id, persona_id)
);

-- 상품-페르소나 인덱스
CREATE INDEX idx_product_personas_product_id ON product_personas(product_id);
CREATE INDEX idx_product_personas_persona_id ON product_personas(persona_id);
CREATE INDEX idx_product_personas_relevance_score ON product_personas(relevance_score DESC);
CREATE INDEX idx_product_personas_matched_attributes ON product_personas USING GIN(matched_attributes);

-- ============================================================
-- 5. 페르소나 분석 결과 테이블 (persona_analysis_results)
-- ============================================================
CREATE TABLE IF NOT EXISTS persona_analysis_results (
    id SERIAL PRIMARY KEY,
    persona_id INTEGER NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
    product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
    analysis_type VARCHAR(50) NOT NULL,
    analysis_result JSONB DEFAULT '{}',
    confidence_score DECIMAL(5, 4) CHECK (confidence_score >= 0 AND confidence_score <= 1),
    generated_message TEXT,
    metadata JSONB DEFAULT '{}',
    analyzed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 페르소나 분석 결과 인덱스
CREATE INDEX idx_persona_analysis_persona_id ON persona_analysis_results(persona_id);
CREATE INDEX idx_persona_analysis_product_id ON persona_analysis_results(product_id);
CREATE INDEX idx_persona_analysis_type ON persona_analysis_results(analysis_type);
CREATE INDEX idx_persona_analysis_analyzed_at ON persona_analysis_results(analyzed_at DESC);
CREATE INDEX idx_persona_analysis_result ON persona_analysis_results USING GIN(analysis_result);

-- ============================================================
-- 6. 페르소나 솔루션 테이블 (persona_solutions)
-- ============================================================
CREATE TABLE IF NOT EXISTS persona_solutions (
    id SERIAL PRIMARY KEY,
    analysis_result_id INTEGER NOT NULL REFERENCES persona_analysis_results(id) ON DELETE CASCADE,
    solution_type VARCHAR(50) NOT NULL,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    recommended_products JSONB DEFAULT '[]',
    priority INTEGER DEFAULT 0,
    effectiveness_score DECIMAL(5, 4) CHECK (effectiveness_score >= 0 AND effectiveness_score <= 1),
    implementation_guide TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 페르소나 솔루션 인덱스
CREATE INDEX idx_persona_solutions_analysis_result_id ON persona_solutions(analysis_result_id);
CREATE INDEX idx_persona_solutions_solution_type ON persona_solutions(solution_type);
CREATE INDEX idx_persona_solutions_priority ON persona_solutions(priority DESC);
CREATE INDEX idx_persona_solutions_effectiveness_score ON persona_solutions(effectiveness_score DESC);
CREATE INDEX idx_persona_solutions_recommended_products ON persona_solutions USING GIN(recommended_products);

-- ============================================================
-- 트리거: updated_at 자동 업데이트
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- brands 테이블 트리거
CREATE TRIGGER update_brands_updated_at
    BEFORE UPDATE ON brands
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- products 테이블 트리거
CREATE TRIGGER update_products_updated_at
    BEFORE UPDATE ON products
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- personas 테이블 트리거
CREATE TRIGGER update_personas_updated_at
    BEFORE UPDATE ON personas
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- persona_solutions 테이블 트리거
CREATE TRIGGER update_persona_solutions_updated_at
    BEFORE UPDATE ON persona_solutions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- 권한 설정
-- ============================================================
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO postgres;

-- ============================================================
-- 코멘트 추가
-- ============================================================
COMMENT ON TABLE brands IS '브랜드 정보 테이블';
COMMENT ON TABLE products IS '상품 정보 테이블';
COMMENT ON TABLE personas IS '페르소나 정보 테이블';
COMMENT ON TABLE product_personas IS '상품-페르소나 매핑 테이블 (다대다 관계)';
COMMENT ON TABLE persona_analysis_results IS '페르소나 분석 결과 테이블';
COMMENT ON TABLE persona_solutions IS '페르소나별 솔루션 테이블';

COMMENT ON COLUMN products.buyer_statistics IS '구매자 통계 정보 (연령대별, 피부타입별 등)';
COMMENT ON COLUMN products.tags IS '상품 태그 정보 (category_tags, ingredient_tags, concern_tags, feature_tags, texture_tags, scent_tags)';
COMMENT ON COLUMN products.detailed_info IS '상세 정보 (GPT-4 Vision 분석 결과 등)';
COMMENT ON COLUMN product_personas.relevance_score IS '상품과 페르소나 간 연관도 점수 (0.0 ~ 1.0)';
COMMENT ON COLUMN persona_analysis_results.analysis_type IS '분석 유형 (예: recommendation, trend_analysis, preference_analysis)';
COMMENT ON COLUMN persona_solutions.solution_type IS '솔루션 유형 (예: product_bundle, skincare_routine, makeup_look)';
