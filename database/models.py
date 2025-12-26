"""
AI Innovation Challenge 2026 Database Models
SQLAlchemy ORM Models for PostgreSQL
"""

from datetime import datetime
from typing import List, Optional
from sqlalchemy import (
    Column, Integer, String, Text, DECIMAL, TIMESTAMP,
    ForeignKey, UniqueConstraint, CheckConstraint, ARRAY
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 Base class"""
    pass


class Brand(Base):
    """브랜드 정보 테이블"""
    __tablename__ = 'brands'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    brand_url = Column(Text, nullable=True)
    tone_description = Column(Text, nullable=True)
    target_audience = Column(JSONB, default={})
    brand_positioning = Column(Text, nullable=True)
    brand_personality = Column(Text, nullable=True)
    tone_style = Column(Text, nullable=True)
    core_keywords = Column(ARRAY(Text), default=[])
    prohibited_expressions = Column(ARRAY(Text), default=[])
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    products = relationship("Product", back_populates="brand")

    def __repr__(self):
        return f"<Brand(id={self.id}, name='{self.name}')>"


class Product(Base):
    """상품 정보 테이블"""
    __tablename__ = 'products'

    id = Column(Integer, primary_key=True, autoincrement=True)
    brand_id = Column(Integer, ForeignKey('brands.id', ondelete='SET NULL'), index=True)

    # 벡터DB 연동
    vector_db_id = Column(String(200), index=True, comment='벡터 데이터베이스 ID')
    indexing_number = Column(String(200), comment='인덱싱 번호')

    # 기본 상품 정보
    product_code = Column(String(100), index=True)
    product_name = Column(String(500), nullable=False)
    category = Column(String(100), index=True)
    sub_category = Column(String(100))

    # 가격 정보
    original_price = Column(DECIMAL(10, 2), comment='원가')
    discount_rate = Column(DECIMAL(5, 2), comment='할인율 (%)')
    sale_price = Column(DECIMAL(10, 2), index=True, comment='판매가')

    # 평점/리뷰
    rating = Column(DECIMAL(3, 2), index=True, comment='별점 (0.0 ~ 5.0)')
    review_count = Column(Integer, default=0, comment='리뷰 개수')

    # 페르소나 매칭용 속성 (배열)
    skin_types = Column(ARRAY(Text), default=[], comment='피부타입')
    personal_colors = Column(ARRAY(Text), default=[], comment='퍼스널 컬러')
    base_shades = Column(ARRAY(Text), default=[], comment='베이스 호수')
    concern_keywords = Column(ARRAY(Text), default=[], comment='고민 키워드')
    makeup_colors = Column(ARRAY(Text), default=[], comment='메이크업 선호 색상')
    preferred_ingredients = Column(ARRAY(Text), default=[], comment='선호 성분')
    avoided_ingredients = Column(ARRAY(Text), default=[], comment='기피 성분')
    preferred_scents = Column(ARRAY(Text), default=[], comment='선호 향')
    values_keywords = Column(ARRAY(Text), default=[], comment='가치관')
    dedicated_products = Column(ARRAY(Text), default=[], comment='전용제품')

    # URL 및 이미지
    product_url = Column(Text, comment='판매 URL')
    image_urls = Column(ARRAY(Text), default=[], comment='상품 이미지 URL 배열')

    # 상세 정보
    description = Column(Text)
    generated_document = Column(Text, comment='GPT가 생성한 구조화된 상품 설명 문서')

    # 상품 태그 (JSONB)
    tags = Column(JSONB, default={}, comment='상품 태그 정보')
    buyer_statistics = Column(JSONB, default={}, comment='구매자 통계 정보')
    detailed_info = Column(JSONB, default={}, comment='상세 정보 (GPT-4 Vision 분석 결과 등)')

    # 타임스탬프
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())

    # Constraints
    __table_args__ = (
        UniqueConstraint('brand_id', 'product_code', name='uq_brand_product_code'),
    )

    # Relationships
    brand = relationship("Brand", back_populates="products")
    product_personas = relationship("ProductPersona", back_populates="product", cascade="all, delete-orphan")
    analysis_results = relationship("PersonaAnalysisResult", back_populates="product")

    def __repr__(self):
        return f"<Product(id={self.id}, name='{self.product_name}', brand_id={self.brand_id})>"


class Persona(Base):
    """페르소나 정보 테이블 (persona_categories.json 기반, 프론트엔드에서 추가)"""
    __tablename__ = 'personas'

    id = Column(Integer, primary_key=True, autoincrement=True)
    persona_key = Column(String(100), nullable=False, unique=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)

    # 1. 기본 정보
    gender = Column(String(20), index=True)
    age_group = Column(String(50), index=True)

    # 2. 피부 스펙
    skin_types = Column(ARRAY(Text), default=[])
    personal_color = Column(String(50), index=True)
    base_shade = Column(String(10))

    # 3. 피부 고민 (최대 3개)
    skin_concerns = Column(ARRAY(Text), default=[])

    # 4. 메이크업 선호
    preferred_point_colors = Column(ARRAY(Text), default=[])

    # 5. 성분 선호
    preferred_ingredients = Column(ARRAY(Text), default=[])
    avoided_ingredients = Column(ARRAY(Text), default=[])
    preferred_scents = Column(ARRAY(Text), default=[])

    # 6. 가치관
    special_conditions = Column(ARRAY(Text), default=[])

    # 추가 정보
    budget_range = Column(String(50))

    # 메타데이터
    persona_metadata = Column('metadata', JSONB, default={})

    # 타임스탬프
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    product_personas = relationship("ProductPersona", back_populates="persona", cascade="all, delete-orphan")
    analysis_results = relationship("PersonaAnalysisResult", back_populates="persona", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Persona(id={self.id}, key='{self.persona_key}', name='{self.name}')>"


class ProductPersona(Base):
    """상품-페르소나 매핑 테이블 (다대다 관계)"""
    __tablename__ = 'product_personas'

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey('products.id', ondelete='CASCADE'), nullable=False, index=True)
    persona_id = Column(Integer, ForeignKey('personas.id', ondelete='CASCADE'), nullable=False, index=True)
    relevance_score = Column(
        DECIMAL(5, 4),
        CheckConstraint('relevance_score >= 0 AND relevance_score <= 1'),
        comment='상품과 페르소나 간 연관도 점수 (0.0 ~ 1.0)',
        index=True
    )
    matched_attributes = Column(JSONB, default={})
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    # Constraints
    __table_args__ = (
        UniqueConstraint('product_id', 'persona_id', name='uq_product_persona'),
    )

    # Relationships
    product = relationship("Product", back_populates="product_personas")
    persona = relationship("Persona", back_populates="product_personas")

    def __repr__(self):
        return f"<ProductPersona(product_id={self.product_id}, persona_id={self.persona_id}, score={self.relevance_score})>"


class PersonaAnalysisResult(Base):
    """페르소나 분석 결과 테이블"""
    __tablename__ = 'persona_analysis_results'

    id = Column(Integer, primary_key=True, autoincrement=True)
    persona_id = Column(Integer, ForeignKey('personas.id', ondelete='CASCADE'), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey('products.id', ondelete='SET NULL'), index=True)
    analysis_type = Column(String(50), nullable=False, index=True, comment='분석 유형 (예: recommendation, trend_analysis)')
    analysis_result = Column(JSONB, default={})
    confidence_score = Column(
        DECIMAL(5, 4),
        CheckConstraint('confidence_score >= 0 AND confidence_score <= 1')
    )
    generated_message = Column(Text)
    analysis_metadata = Column('metadata', JSONB, default={})
    analyzed_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), index=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    # Relationships
    persona = relationship("Persona", back_populates="analysis_results")
    product = relationship("Product", back_populates="analysis_results")
    solutions = relationship("PersonaSolution", back_populates="analysis_result", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<PersonaAnalysisResult(id={self.id}, persona_id={self.persona_id}, type='{self.analysis_type}')>"


class PersonaSolution(Base):
    """페르소나별 솔루션 테이블"""
    __tablename__ = 'persona_solutions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_result_id = Column(
        Integer,
        ForeignKey('persona_analysis_results.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    solution_type = Column(String(50), nullable=False, index=True, comment='솔루션 유형 (예: product_bundle, skincare_routine)')
    title = Column(String(500), nullable=False)
    description = Column(Text)
    recommended_products = Column(JSONB, default=[])
    priority = Column(Integer, default=0, index=True)
    effectiveness_score = Column(
        DECIMAL(5, 4),
        CheckConstraint('effectiveness_score >= 0 AND effectiveness_score <= 1'),
        index=True
    )
    implementation_guide = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    analysis_result = relationship("PersonaAnalysisResult", back_populates="solutions")

    def __repr__(self):
        return f"<PersonaSolution(id={self.id}, type='{self.solution_type}', title='{self.title}')>"
