"""
AI Innovation Challenge 2026 Database Models
SQLAlchemy ORM Models for PostgreSQL
새로운 테이블 스키마 (table_type.md 기준)
"""

import uuid
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DECIMAL, TIMESTAMP, SmallInteger, Boolean, Numeric,
    ForeignKey, ARRAY, UniqueConstraint, JSON, BigInteger, Index
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
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
    concerns = Column(ARRAY(Text), default=[])
    personal_color = Column(Text)
    shade_number = Column(Integer)

    # 선호 사항
    preferred_colors = Column(ARRAY(Text), default=[])
    preferred_ingredients = Column(ARRAY(Text), default=[])
    avoided_ingredients = Column(ARRAY(Text), default=[])
    preferred_scents = Column(ARRAY(Text), default=[])
    lifestyle_values = Column(ARRAY(Text), default=[])

    # 라이프스타일
    skincare_routine = Column(ARRAY(Text), default=[])
    main_environment = Column(ARRAY(Text), default=[])
    preferred_texture = Column(ARRAY(Text), default=[])
    hair_type = Column(ARRAY(Text), default=[])
    beauty_interests = Column(ARRAY(Text), default=[])
    pets = Column(ARRAY(Text), default=[])
    avg_sleep_hours = Column(Integer)
    stress_level = Column(Text)
    daily_screen_hours = Column(Integer)

    # 쇼핑 성향
    shopping_style = Column(ARRAY(Text), default=[])
    purchase_decision_factors = Column(ARRAY(Text), default=[])
    price_sensitivity = Column(Text)
    preferred_brands = Column(ARRAY(Text), default=[])
    avoided_brands = Column(ARRAY(Text), default=[])

    # AI 요약
    persona_summary = Column(Text)

    # 생성자
    user_id = Column(String(100), nullable=True, index=True)

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
    vectordb_id = Column(JSONB)
    product_name = Column(String(500), nullable=False)
    brand = Column(String(100), index=True)
    category = Column(String(200), index=True)
    tag = Column(String(200))
    sub_tag = Column(String(200), index=True)

    # 평점/리뷰
    rating = Column(DECIMAL(3, 2))
    review_count = Column(Integer, default=0)

    # 가격 정보
    original_price = Column(Integer)
    discount_rate = Column(Integer)
    sale_price = Column(Integer)

    # 페르소나 매칭 속성
    skin_type = Column(ARRAY(Text), default=[])
    concerns = Column(ARRAY(Text), default=[])
    preferred_colors = Column(ARRAY(Text), default=[])
    preferred_ingredients = Column(ARRAY(Text), default=[])
    avoided_ingredients = Column(ARRAY(Text), default=[])
    preferred_scents = Column(ARRAY(Text), default=[])
    lifestyle_values = Column(ARRAY(Text), default=[])
    exclusive_product = Column(String(200))
    personal_color = Column(ARRAY(Text), default=[])
    skin_shades = Column(ARRAY(Integer), default=[])

    # URL 및 이미지
    product_image_url = Column(ARRAY(Text), default=[])
    product_page_url = Column(Text)

    # 상품 한줄소개
    product_comment = Column(Text)

    # 카테고리별 가변 상품 정보
    product_details = Column(JSONB)

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
    messages       = Column(JSON, default=list)  # 프론트 UI 메시지 전체 (제품 그리드 포함)
    created_at     = Column(TIMESTAMP(timezone=True), server_default=func.now())
    last_active_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Conversation(id='{self.id}', user_id='{self.user_id}', title='{self.title}')>"


# ============================================================
# 5b. Conversation Message Table
# ============================================================

class ConversationMessage(Base):
    """대화 메시지 테이블 — 메시지당 1행"""
    __tablename__ = 'conversation_messages'

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id = Column(
        String(36),
        ForeignKey('conversations.id', ondelete='CASCADE'),
        nullable=False,
    )
    message_data    = Column(JSONB, nullable=False)
    created_at      = Column(TIMESTAMP(timezone=True), server_default=func.now())

    __table_args__ = (
        Index('idx_conv_messages_conv_id', 'conversation_id', 'id'),
    )


# ============================================================
# 6. Generated Message Table
# ============================================================

class GeneratedMessage(Base):
    """생성된 마케팅 메시지 테이블"""
    __tablename__ = 'generated_messages'

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String(36), ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id         = Column(String(100), nullable=False)
    product_id      = Column(String(100), ForeignKey('products.product_id', ondelete='SET NULL'), nullable=True, index=True)
    product_name    = Column(String(500))
    brand           = Column(String(100))
    sub_tag         = Column(String(200))

    # 메시지 생성 컨텍스트
    purpose         = Column(String(200))
    user_input      = Column(Text)

    # 메시지 내용
    title           = Column(Text)
    content         = Column(Text, nullable=False)

    # 품질 평가 요약
    quality_passed        = Column(Boolean)
    quality_failed_stage  = Column(String(50))
    quality_failure_reason = Column(Text)

    # LLM-as-a-Judge 점수
    llm_score_accuracy        = Column(SmallInteger)
    llm_score_tone            = Column(SmallInteger)
    llm_score_personalization = Column(SmallInteger)
    llm_score_naturalness     = Column(SmallInteger)
    llm_score_cta_clarity     = Column(SmallInteger)
    llm_score_overall         = Column(Numeric(3, 2))
    llm_feedback              = Column(Text)

    # 품질 평가 상세 raw 데이터
    quality_details   = Column(JSONB)

    # 재생성 추적
    regeneration_count = Column(SmallInteger, default=0)

    thread_id       = Column(String(36))  # LangSmith 트레이싱용
    created_at      = Column(TIMESTAMP(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<GeneratedMessage(id='{self.id}', product_id='{self.product_id}', user_id='{self.user_id}')>"


# ============================================================
# 7. User Table
# ============================================================

class User(Base):
    """사용자 계정 테이블"""
    __tablename__ = 'users'

    id            = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email         = Column(String(255), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    role          = Column(String(20), nullable=False, default='user')  # 'admin' | 'user'
    is_active     = Column(Boolean, nullable=False, default=True)
    created_at    = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at    = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())

    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id='{self.id}', email='{self.email}', role='{self.role}')>"


# ============================================================
# 8. RefreshToken Table
# ============================================================

class RefreshToken(Base):
    """Refresh Token 저장 테이블 (raw 값 아닌 SHA-256 해시만 저장)"""
    __tablename__ = 'refresh_tokens'

    id         = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id    = Column(PG_UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    token_hash = Column(String(255), nullable=False, unique=True)
    expires_at = Column(TIMESTAMP(timezone=True), nullable=False)
    revoked    = Column(Boolean, nullable=False, default=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    user_agent = Column(Text)
    ip_address = Column(String(45))

    user = relationship("User", back_populates="refresh_tokens")

    def __repr__(self):
        return f"<RefreshToken(id='{self.id}', user_id='{self.user_id}', revoked={self.revoked})>"


# ============================================================
# 9. RateLimitEntry Table
# ============================================================

class RateLimitEntry(Base):
    """Rate limit 카운터 테이블. 분산 환경에서 공유 카운터 역할."""
    __tablename__ = "rate_limits"

    key          = Column(String(255), primary_key=True)
    count        = Column(Integer, nullable=False, default=1)
    window_start = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    prev_count   = Column(Integer, nullable=False, default=0)
