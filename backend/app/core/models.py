"""
AI Innovation Challenge 2026 Database Models
SQLAlchemy ORM Models for PostgreSQL
새로운 테이블 스키마 (table_type.md 기준)
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DECIMAL, TIMESTAMP,
    ForeignKey, ARRAY, UniqueConstraint
)
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 Base class"""
    pass


# ============================================================
# 1. Persona Table
# ============================================================

class Persona(Base):
    """페르소나 정보 테이블"""
    __tablename__ = 'personas'

    persona_id = Column(String(100), primary_key=True)
    name = Column(String(200), nullable=False)
    gender = Column(String(20))
    age = Column(Integer)
    occupation = Column(String(100))

    # 피부 관련
    skin_type = Column(ARRAY(Text), default=[])
    skin_concerns = Column(ARRAY(Text), default=[])
    personal_color = Column(String(50))
    shade_number = Column(Integer)

    # 선호 사항
    preferred_colors = Column(ARRAY(Text), default=[])
    preferred_ingredients = Column(ARRAY(Text), default=[])
    avoided_ingredients = Column(ARRAY(Text), default=[])
    preferred_scents = Column(ARRAY(Text), default=[])
    values = Column(ARRAY(Text), default=[])

    # 라이프스타일
    skincare_routine = Column(String(100))
    main_environment = Column(String(100))
    preferred_texture = Column(ARRAY(Text), default=[])
    pets = Column(String(50))
    avg_sleep_hours = Column(Integer)
    stress_level = Column(String(50))
    digital_device_usage_time = Column(Integer)

    # 쇼핑 성향
    shopping_style = Column(String(100))
    purchase_decision_factors = Column(ARRAY(Text), default=[])

    # AI 요약
    persona_summary = Column(Text)

    # 타임스탬프
    persona_created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    # Relationships
    analysis_results = relationship("AnalysisResult", back_populates="persona", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Persona(persona_id='{self.persona_id}', name='{self.name}')>"


# ============================================================
# 2. Analysis Results Table
# ============================================================

class AnalysisResult(Base):
    """분석 결과 테이블"""
    __tablename__ = 'analysis_results'

    analysis_id = Column(Integer, primary_key=True, autoincrement=True)
    persona_id = Column(String(100), ForeignKey('personas.persona_id', ondelete='CASCADE'), nullable=False, index=True)
    analysis_result = Column(Text)
    analysis_created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint('persona_id', name='uq_analysis_results_persona_id'),
    )

    # Relationships
    persona = relationship("Persona", back_populates="analysis_results")
    search_queries = relationship("SearchQuery", back_populates="analysis_result", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<AnalysisResult(analysis_id={self.analysis_id}, persona_id='{self.persona_id}')>"


# ============================================================
# 3. Search Query Table
# ============================================================

class SearchQuery(Base):
    """검색 쿼리 테이블"""
    __tablename__ = 'search_queries'

    query_id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_id = Column(Integer, ForeignKey('analysis_results.analysis_id', ondelete='CASCADE'), nullable=False, index=True)
    search_query = Column(Text)
    query_created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    # Relationships
    analysis_result = relationship("AnalysisResult", back_populates="search_queries")

    def __repr__(self):
        return f"<SearchQuery(query_id={self.query_id}, analysis_id={self.analysis_id})>"


# ============================================================
# 4. Product Table
# ============================================================

class Product(Base):
    """상품 정보 테이블"""
    __tablename__ = 'products'

    product_id = Column(String(100), primary_key=True)
    vectordb_id = Column(String(100), index=True)
    product_name = Column(String(500), nullable=False)
    brand = Column(String(100), index=True)
    product_tag = Column(String(200))

    # 평점/리뷰
    rating = Column(DECIMAL(3, 2))
    review_count = Column(Integer, default=0)

    # 가격 정보
    original_price = Column(Integer)
    discount_rate = Column(Integer)
    sale_price = Column(Integer)

    # 페르소나 매칭 속성
    skin_type = Column(ARRAY(Text), default=[])
    skin_concerns = Column(ARRAY(Text), default=[])
    preferred_colors = Column(ARRAY(Text), default=[])
    preferred_ingredients = Column(ARRAY(Text), default=[])
    avoided_ingredients = Column(ARRAY(Text), default=[])
    preferred_scents = Column(ARRAY(Text), default=[])
    values = Column(ARRAY(Text), default=[])
    exclusive_product = Column(String(200))
    personal_color = Column(ARRAY(Text), default=[])
    skin_shades = Column(ARRAY(Integer), default=[])

    # URL 및 이미지
    product_image_url = Column(ARRAY(Text), default=[])
    product_page_url = Column(Text)

    # 상품 한줄소개
    product_comment = Column(Text)

    # 타임스탬프
    product_created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Product(product_id='{self.product_id}', name='{self.product_name}', brand='{self.brand}')>"
