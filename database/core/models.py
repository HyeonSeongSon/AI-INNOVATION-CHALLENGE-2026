"""
AI Innovation Challenge 2026 Database Models
SQLAlchemy ORM Models for PostgreSQL
새로운 테이블 스키마 (table_type.md 기준)
"""

import uuid
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DECIMAL, TIMESTAMP,
    ForeignKey, ARRAY, UniqueConstraint, JSON, Boolean, Numeric
)
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func, text


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 Base class"""
    pass


# ============================================================
# 1. Persona Table
# ============================================================

class Persona(Base):
    """페르소나 정보 테이블"""
    __tablename__ = 'personas'

    persona_id = Column(String(20), primary_key=True, server_default=text("'PERSONA_' || LPAD(nextval('persona_seq')::text, 5, '0')"))
    name = Column(String(200), nullable=False)
    gender = Column(String(20))
    age = Column(Integer)
    occupation = Column(Text)

    # 피부 관련
    skin_type = Column(ARRAY(Text), default=[])
    skin_concerns = Column(ARRAY(Text), default=[])
    personal_color = Column(Text)
    shade_number = Column(Integer)

    # 선호 사항
    preferred_colors = Column(ARRAY(Text), default=[])
    preferred_ingredients = Column(ARRAY(Text), default=[])
    avoided_ingredients = Column(ARRAY(Text), default=[])
    preferred_scents = Column(ARRAY(Text), default=[])
    values = Column(ARRAY(Text), default=[])

    # 라이프스타일
    skincare_routine = Column(Text)
    main_environment = Column(Text)
    preferred_texture = Column(ARRAY(Text), default=[])
    pets = Column(Text)
    avg_sleep_hours = Column(Integer)
    stress_level = Column(Text)
    digital_device_usage_time = Column(Integer)

    # 쇼핑 성향
    shopping_style = Column(Text)
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
    persona_id = Column(String(20), ForeignKey('personas.persona_id', ondelete='CASCADE'), nullable=False, index=True)
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

    # 카테고리별 가변 상품 정보
    product_details = Column(JSON)

    # 타임스탬프
    product_created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Product(product_id='{self.product_id}', name='{self.product_name}', brand='{self.brand}')>"


# ============================================================
# 5. Conversation Table
# ============================================================

class Conversation(Base):
    """마케팅 대화 세션 테이블"""
    __tablename__ = 'conversations'

    id             = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id        = Column(String(100), nullable=False, index=True)
    thread_id      = Column(String(36), nullable=False, unique=True)
    session_id     = Column(String(100))
    title          = Column(String(500), default="새 대화")
    messages       = Column(JSON, default=list)
    created_at     = Column(TIMESTAMP(timezone=True), server_default=func.now())
    last_active_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Conversation(id='{self.id}', user_id='{self.user_id}', title='{self.title}')>"


# ============================================================
# 6. Generated Message Table
# ============================================================

class GeneratedMessage(Base):
    """생성된 마케팅 메시지 테이블"""
    __tablename__ = 'generated_messages'

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String(36), ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id         = Column(String(100), nullable=False, index=True)
    product_id      = Column(String(100), nullable=False, index=True)
    product_name    = Column(String(500))
    brand           = Column(String(100))
    product_tag     = Column(String(200))
    purpose         = Column(String(200))
    title           = Column(Text)
    content         = Column(Text, nullable=False)
    quality_passed  = Column(Boolean)
    llm_score_overall = Column(Numeric(3, 2))
    llm_feedback    = Column(Text)
    thread_id       = Column(String(36))
    created_at      = Column(TIMESTAMP(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<GeneratedMessage(id='{self.id}', product_id='{self.product_id}', user_id='{self.user_id}')>"
