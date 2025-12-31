"""
[최종 확정 모델]
AI Innovation Challenge 2026 표준 스키마 (SQLModel 버전)
- table_type.md 명세 반영
"""
import uuid
from typing import Optional, List, Dict
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column, Integer, String, Text, DECIMAL, TIMESTAMP, func, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

# =========================================================
# [1] Persona Table
# =========================================================
class Persona(SQLModel, table=True):
    __tablename__ = "personas"
    
    # PK를 varchar로 설정 (UUID 사용 권장)
    persona_id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)
    
    name: str = Field(max_length=200)
    gender: Optional[str] = Field(default=None)
    age: Optional[int] = Field(default=None)
    occupation: Optional[str] = Field(default=None)
    
    # 배열(List) 데이터
    skin_type: List[str] = Field(default=[], sa_column=Column(ARRAY(Text)))
    skin_concerns: List[str] = Field(default=[], sa_column=Column(ARRAY(Text)))
    
    personal_color: Optional[str] = Field(default=None)
    shade_number: Optional[int] = Field(default=None) # integer
    
    preferred_colors: List[str] = Field(default=[], sa_column=Column(ARRAY(Text)))
    preferred_ingredients: List[str] = Field(default=[], sa_column=Column(ARRAY(Text)))
    avoided_ingredients: List[str] = Field(default=[], sa_column=Column(ARRAY(Text)))
    preferred_scents: List[str] = Field(default=[], sa_column=Column(ARRAY(Text)))
    values: List[str] = Field(default=[], sa_column=Column(ARRAY(Text)))
    
    skincare_routine: Optional[str] = Field(default=None)
    main_environment: Optional[str] = Field(default=None)
    preferred_texture: List[str] = Field(default=[], sa_column=Column(ARRAY(Text)))
    pets: Optional[str] = Field(default=None)
    
    avg_sleep_hours: Optional[int] = Field(default=None) # integer
    stress_level: Optional[str] = Field(default=None)
    digital_device_usage_time: Optional[int] = Field(default=None) # integer
    shopping_style: Optional[str] = Field(default=None)
    
    purchase_decision_factors: List[str] = Field(default=[], sa_column=Column(ARRAY(Text)))
    
    persona_created_at: Optional[datetime] = Field(sa_column=Column(TIMESTAMP(timezone=True), server_default=func.now()))

    # 관계 설정
    analysis_results: List["AnalysisResult"] = Relationship(back_populates="persona")


# =========================================================
# [2] Analysis Results Table
# =========================================================
class AnalysisResult(SQLModel, table=True):
    __tablename__ = "analysis_results"
    
    analysis_id: Optional[int] = Field(default=None, primary_key=True) # serial (auto-increment)
    persona_id: str = Field(foreign_key="personas.persona_id")
    
    analysis_result: Optional[str] = Field(default=None, sa_column=Column(Text))
    analysis_created_at: Optional[datetime] = Field(sa_column=Column(TIMESTAMP(timezone=True), server_default=func.now()))

    persona: Optional[Persona] = Relationship(back_populates="analysis_results")
    search_queries: List["SearchQuery"] = Relationship(back_populates="analysis_result")


# =========================================================
# [3] Search Query Table
# =========================================================
class SearchQuery(SQLModel, table=True):
    __tablename__ = "search_queries"
    
    query_id: Optional[int] = Field(default=None, primary_key=True)
    analysis_id: int = Field(foreign_key="analysis_results.analysis_id")
    
    search_query: Optional[str] = Field(default=None, sa_column=Column(Text))
    query_created_at: Optional[datetime] = Field(sa_column=Column(TIMESTAMP(timezone=True), server_default=func.now()))

    analysis_result: Optional[AnalysisResult] = Relationship(back_populates="search_queries")


# =========================================================
# [4] Product Table
# =========================================================
class Product(SQLModel, table=True):
    __tablename__ = "products"
    
    product_id: str = Field(primary_key=True) # varchar PK
    vectordb_id: Optional[str] = Field(default=None)
    
    product_name: str = Field(max_length=500)
    brand: Optional[str] = Field(default=None)
    product_tag: Optional[str] = Field(default=None)
    
    rating: Optional[float] = Field(default=0.0, sa_column=Column(Numeric))
    review_count: Optional[int] = Field(default=0)
    
    original_price: Optional[int] = Field(default=0)
    discount_rate: Optional[int] = Field(default=0)
    sale_price: Optional[int] = Field(default=0)
    
    # 배열 데이터
    skin_type: List[str] = Field(default=[], sa_column=Column(ARRAY(Text)))
    skin_concerns: List[str] = Field(default=[], sa_column=Column(ARRAY(Text)))
    preferred_colors: List[str] = Field(default=[], sa_column=Column(ARRAY(Text)))
    preferred_ingredients: List[str] = Field(default=[], sa_column=Column(ARRAY(Text)))
    avoided_ingredients: List[str] = Field(default=[], sa_column=Column(ARRAY(Text)))
    preferred_scents: List[str] = Field(default=[], sa_column=Column(ARRAY(Text)))
    values: List[str] = Field(default=[], sa_column=Column(ARRAY(Text)))
    
    exclusive_product: Optional[str] = Field(default=None)
    
    personal_color: List[str] = Field(default=[], sa_column=Column(ARRAY(Text)))
    skin_shades: List[str] = Field(default=[], sa_column=Column(ARRAY(Text))) # text array로 처리
    
    product_image_url: List[str] = Field(default=[], sa_column=Column(ARRAY(Text)))
    product_page_url: Optional[str] = Field(default=None, sa_column=Column(Text))
    
    product_created_at: Optional[datetime] = Field(sa_column=Column(TIMESTAMP(timezone=True), server_default=func.now()))