import asyncio
import hmac
import json
import re

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, AfterValidator
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send
from typing import Annotated, Dict, Literal, Optional, List, Union
import logging
import os
from dotenv import load_dotenv
from opensearch_hybrid import OpenSearchHybridClient

# 환경 변수 로드
load_dotenv()

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

_INTERNAL_TOKEN = os.getenv("INTERNAL_TOKEN", "")
if not _INTERNAL_TOKEN:
    raise RuntimeError("INTERNAL_TOKEN 환경변수가 설정되지 않았습니다.")
if len(_INTERNAL_TOKEN) < 32:
    raise RuntimeError("INTERNAL_TOKEN은 최소 32자 이상이어야 합니다.")
_SKIP_PATHS = {"/", "/health", "/ready"}
_MAX_BODY_BYTES = 10 * 1024 * 1024  # 10MB


class _PayloadTooLargeError(Exception):
    pass


class _BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_body_bytes: int = _MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_length_raw = headers.get(b"content-length")
        if content_length_raw is not None:
            try:
                content_length = int(content_length_raw)
            except ValueError:
                content_length = 0
            if content_length > self.max_body_bytes:
                await self._send_413(send)
                return

        total_bytes = 0

        async def limited_receive() -> dict:
            nonlocal total_bytes
            message = await receive()
            if message.get("type") == "http.request":
                total_bytes += len(message.get("body", b""))
                if total_bytes > self.max_body_bytes:
                    raise _PayloadTooLargeError()
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _PayloadTooLargeError:
            await self._send_413(send)

    @staticmethod
    async def _send_413(send: Send) -> None:
        body = json.dumps({"detail": "요청 바디가 너무 큽니다."}).encode()
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        })
        await send({"type": "http.response.body", "body": body})

ALLOWED_INDEX_NAMES: frozenset[str] = frozenset({
    "product_index_v3",
    "forbidden_sentences",
    "product_v4_combined",
    "product_v4_function_desc",
    "product_v4_attribute_desc",
    "product_v4_target_user",
    "product_v4_spec_feature",
})

ALLOWED_PIPELINE_IDS: frozenset[str] = frozenset({
    "hybrid-minmax-pipeline",
})

ALLOWED_VECTOR_FIELDS: frozenset[str] = frozenset({
    "combined_vector",
    "function_desc_vector",
    "attribute_desc_vector",
    "target_user_vector",
    "spec_feature_vector",
})

# BM25 필드명: 알파벳·밑줄로 시작, 알파벳·밑줄·숫자로 구성, 선택적으로 boost 접미사(^숫자)
_BM25_FIELD_RE = re.compile(r'^[a-zA-Z_][a-zA-Z_0-9]*(\^[0-9]+(\.[0-9]+)?)?$')


def _validate_index_name(v: str) -> str:
    if v not in ALLOWED_INDEX_NAMES:
        raise ValueError(f"허용되지 않는 인덱스 이름입니다: '{v}'")
    return v


def _validate_pipeline_id(v: str) -> str:
    if v not in ALLOWED_PIPELINE_IDS:
        raise ValueError(f"허용되지 않는 파이프라인 ID입니다: '{v}'")
    return v


def _validate_bm25_field(v: str) -> str:
    if not _BM25_FIELD_RE.match(v):
        raise ValueError(f"유효하지 않은 BM25 필드명입니다: '{v}'")
    return v


def _validate_vector_field(v: str) -> str:
    if v not in ALLOWED_VECTOR_FIELDS:
        raise ValueError(f"허용되지 않는 벡터 필드입니다: '{v}'")
    return v


ValidatedIndexName = Annotated[str, AfterValidator(_validate_index_name)]
ValidatedPipelineId = Annotated[str, AfterValidator(_validate_pipeline_id)]
ValidatedBm25Field = Annotated[str, AfterValidator(_validate_bm25_field)]
ValidatedVectorField = Annotated[str, AfterValidator(_validate_vector_field)]


class InternalTokenMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path in _SKIP_PATHS:
            return await call_next(request)
        token = request.headers.get("X-Internal-Token", "")
        if not token or not hmac.compare_digest(token, _INTERNAL_TOKEN):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)


# FastAPI 앱 초기화
app = FastAPI(
    title="OpenSearch Hybrid Search API",
    description="하이브리드 검색 (BM25 + KNN) API",
    version="1.0.0"
)

app.add_middleware(InternalTokenMiddleware)
app.add_middleware(_BodySizeLimitMiddleware, max_body_bytes=_MAX_BODY_BYTES)

# OpenSearch 클라이언트 (싱글톤)
opensearch_client = None


# 요청/응답 모델
class ProductIDSearchRequest(BaseModel):
    query: str = Field(..., description="검색 쿼리 텍스트", min_length=1)
    product_ids: List[str] = Field(..., description="검색할 product_id 리스트", min_length=1, max_length=500)
    index_name: ValidatedIndexName = Field(default="product_index_v3", description="검색할 인덱스 이름")
    pipeline_id: ValidatedPipelineId = Field(default="hybrid-minmax-pipeline", description="사용할 search pipeline ID")
    top_k: int = Field(default=3, ge=1, le=100, description="반환할 결과 개수 (1-100)")
    bm25_fields: Optional[List[ValidatedBm25Field]] = Field(
        default=None,
        description="BM25 multi_match 대상 필드 리스트 (기본: search_tags^2.0, search_phrases)"
    )
    vector_field: Optional[ValidatedVectorField] = Field(
        default="combined_vector",
        description="KNN 대상 벡터 필드 (기본: combined_vector)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "query": "촉촉한 립스틱",
                "product_ids": ["PROD001", "PROD002", "PROD003"],
                "index_name": "product_index_v3",
                "pipeline_id": "hybrid-minmax-pipeline",
                "top_k": 3,
                "bm25_fields": ["search_tags^2.0", "search_phrases"],
                "vector_field": "combined_vector"
            }
        }


class SimilarSentenceRequest(BaseModel):
    index_name: ValidatedIndexName = Field(..., description="검색할 인덱스 이름 (예: forbidden_sentences)")
    query: str = Field(..., description="유사 문장을 찾을 검색 쿼리 텍스트", min_length=1)
    top_k: int = Field(default=3, ge=1, le=100, description="반환할 유사 문장 개수 (기본값: 3)")

    class Config:
        json_schema_extra = {
            "example": {
                "index_name": "forbidden_sentences",
                "query": "이 제품은 피부 트러블을 완전히 치료합니다",
                "top_k": 3
            }
        }


class SimilarSentenceResult(BaseModel):
    score: float
    sentence: Optional[str] = None
    source: Optional[dict] = None


class SimilarSentenceResponse(BaseModel):
    success: bool
    total_results: int
    query: str
    index_name: str
    results: List[SimilarSentenceResult]


class ProductResult(BaseModel):
    score: float
    product_id: Optional[str] = None
    브랜드: Optional[str] = None
    상품명: Optional[str] = None
    태그: Optional[str] = None
    피부타입: Optional[str] = None
    고민키워드: Optional[str] = None
    전용제품: Optional[str] = None
    퍼스널컬러: Optional[List[str]] = None
    피부호수: Optional[List[int]] = None
    문서: Optional[str] = None


class SearchResponse(BaseModel):
    success: bool
    total_results: int
    query: str
    product_id_filter: Optional[List[str]] = None
    results: List[ProductResult]


class CombinedSearchResult(BaseModel):
    score: float
    product_id: str


class CombinedSearchResponse(BaseModel):
    success: bool
    total_results: int
    query: str
    results: List[CombinedSearchResult]


class FieldSearchRequest(BaseModel):
    query: str = Field(..., description="검색 쿼리 텍스트", min_length=1)
    bm25_fields: List[ValidatedBm25Field] = Field(
        ...,
        description="BM25 multi_match 대상 필드 리스트 (예: ['function_tags', 'function_desc'])"
    )
    vector_field: ValidatedVectorField = Field(..., description="KNN 검색 대상 벡터 필드 (예: function_desc_vector)")
    product_ids: List[str] = Field(..., description="검색할 product_id 리스트", min_length=1, max_length=500)
    index_name: ValidatedIndexName = Field(default="product_index_v3", description="검색할 인덱스 이름")
    pipeline_id: ValidatedPipelineId = Field(default="hybrid-minmax-pipeline", description="사용할 search pipeline ID")
    top_k: int = Field(default=50, ge=1, le=200, description="반환할 결과 개수 (1-200)")

    class Config:
        json_schema_extra = {
            "example": {
                "query": "보습에 특화된 세럼",
                "bm25_fields": ["function_tags", "function_desc"],
                "vector_field": "function_desc_vector",
                "product_ids": ["PROD001", "PROD002"],
                "index_name": "product_index_v3",
                "pipeline_id": "hybrid-minmax-pipeline",
                "top_k": 50,
            }
        }


class FieldSearchResult(BaseModel):
    score: float
    product_id: str


class FieldSearchResponse(BaseModel):
    success: bool
    total_results: int
    query: str
    bm25_fields: List[str]
    results: List[FieldSearchResult]


class MultiVectorSearchRequest(BaseModel):
    query: str = Field(..., description="검색 쿼리 텍스트", min_length=1)
    index_name: ValidatedIndexName = Field(..., description="검색 대상 인덱스 (예: product_v4_combined)")
    product_ids: List[str] = Field(..., description="검색 범위를 제한할 상품 ID 리스트", min_length=1, max_length=500)
    top_k: int = Field(default=100, ge=1, le=200, description="반환할 상품 수")
    aggregation: Literal["max", "topk_avg"] = Field(default="max", description="집계 방식")
    pipeline_id: ValidatedPipelineId = Field(default="hybrid-minmax-pipeline")


class MultiVectorSearchResponse(BaseModel):
    success: bool
    total_results: int
    query: str
    index_name: str
    results: List[FieldSearchResult]


class IndexMultivectorRequest(BaseModel):
    product_id: str = Field(..., description="등록할 상품 ID")
    group: Literal["A", "B", "C", "D", "E", "F", "G"] = Field(..., description="멀티벡터 그룹")
    multivector: Dict[str, List[str]] = Field(
        ..., description="필드명 → 문장 리스트 (combined, function_desc, attribute_desc, target_user, spec_feature)"
    )


class IndexMultivectorResponse(BaseModel):
    success: bool
    product_id: str
    indexed_counts: Dict[str, int]
    vectordb_id: Dict[str, List[str]]
    partial_failure: bool = False
    failed_counts: Dict[str, int] = {}


def get_opensearch_client() -> OpenSearchHybridClient:
    """OpenSearch 클라이언트 싱글톤"""
    global opensearch_client
    if opensearch_client is None:
        opensearch_client = OpenSearchHybridClient()
        if not opensearch_client.client:
            raise HTTPException(status_code=500, detail="OpenSearch 클라이언트 초기화 실패")
    return opensearch_client


@app.on_event("startup")
async def startup_event():
    """서버 시작 시 OpenSearch 클라이언트 초기화"""
    logging.info("FastAPI 서버 시작 중...")
    try:
        get_opensearch_client()
        logging.info("OpenSearch 클라이언트 초기화 완료")
    except Exception as e:
        logging.error(f"서버 시작 중 오류 발생: {e}")


@app.get("/")
async def root():
    """루트 엔드포인트"""
    return {
        "message": "OpenSearch Hybrid Search API",
        "version": "1.0.0",
        "endpoints": {
            "get_product_by_id": "/api/product/{product_id}",
            "search_by_product_ids": "/api/search/product-ids",
            "search_similar_sentences": "/api/search/similar-sentences",
            "docs": "/docs"
        }
    }


@app.get("/health")
async def health_check():
    """헬스체크 엔드포인트"""
    try:
        client = get_opensearch_client()
        if client.client and client.client.ping():
            return {"status": "healthy", "opensearch": "connected"}
        else:
            return {"status": "unhealthy", "opensearch": "disconnected"}
    except Exception:
        logging.error("health_check_failed", exc_info=True)
        return {"status": "unhealthy"}


@app.get("/api/product/{product_id}")
async def get_product_by_id(
    product_id: str,
    index_name: ValidatedIndexName = Query(default="product_index_v3", description="검색할 인덱스 이름")
):
    """
    Product ID로 단일 상품 문서 조회

    - **product_id**: 조회할 상품 ID (필수)
    - **index_name**: 검색할 인덱스 이름 (기본값: product_index_v3)
    """
    try:
        logging.info(f"Product ID 조회 요청 - product_id: {product_id}")

        # OpenSearch 클라이언트 가져오기
        client = get_opensearch_client()

        # Product ID로 문서 조회
        query_body = {
            "query": {
                "term": {
                    "product_id": product_id
                }
            },
            "_source": {
                "excludes": ["content_vector"]
            }
        }

        # 검색 실행
        response = await asyncio.to_thread(
            client.client.search,
            index=index_name,
            body=query_body,
        )

        hits = response.get("hits", {}).get("hits", [])

        if not hits:
            raise HTTPException(
                status_code=404,
                detail=f"Product ID '{product_id}'를 찾을 수 없습니다."
            )

        # 첫 번째 결과 반환
        document = hits[0].get("_source", {})

        logging.info(f"Product ID 조회 성공 - product_id: {product_id}")

        return {
            "success": True,
            "product_id": product_id,
            "document": document
        }

    except HTTPException:
        raise
    except Exception as e:
        logging.error("product_id_lookup_failed", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="조회 중 오류가 발생했습니다."
        )


@app.post("/api/search/product-ids", response_model=SearchResponse)
async def search_by_product_ids(request: ProductIDSearchRequest):
    """
    Product ID 리스트로 필터링된 하이브리드 검색 엔드포인트

    - **query**: 검색 쿼리 텍스트 (필수)
    - **product_ids**: 검색할 product_id 리스트 (필수)
    - **index_name**: 검색할 인덱스 이름 (기본값: product_index_v3)
    - **pipeline_id**: 사용할 search pipeline ID (기본값: hybrid-minmax-pipeline)
    - **top_k**: 반환할 결과 개수 (기본값: 3, 최대: 100)
    """
    try:
        logging.info(f"Product ID 검색 요청 - 쿼리: '{request.query}', product_ids: {len(request.product_ids)}개")

        # OpenSearch 클라이언트 가져오기
        client = get_opensearch_client()

        # Search pipeline 생성 (존재하지 않는 경우)
        pipeline_body = client._create_search_pipe_line_body()
        client.create_search_pipeline(
            pipeline_id=request.pipeline_id,
            pipeline_body=pipeline_body
        )

        # 벡터 임베딩 생성
        query_vector = (await asyncio.to_thread(client.model.encode, request.query)).tolist()
        logging.info(f"쿼리 임베딩 생성 완료: 차원={len(query_vector)}")

        # Product ID 필터링 쿼리 구성
        query_body = {
            "size": request.top_k,
            "query": {
                "hybrid": {
                    "queries": [
                        # BM25 + Product ID 필터
                        {
                            "bool": {
                                "must": {
                                    "multi_match": {
                                        "query": request.query,
                                        "fields": [
                                            "문서^3.0",
                                            "상품명^2.0",
                                            "브랜드^2.0",
                                            "태그^1.5",
                                            "피부타입^1.2",
                                            "고민키워드^1.2",
                                            "전용제품^1.0",
                                            "퍼스널컬러^1.0",
                                            "피부호수^1.0"
                                        ],
                                        "type": "best_fields",
                                        "fuzziness": "AUTO"
                                    }
                                },
                                "filter": {
                                    "terms": {
                                        "product_id": request.product_ids
                                    }
                                }
                            }
                        },
                        # KNN + Product ID 필터
                        {
                            "bool": {
                                "must": {
                                    "knn": {
                                        "content_vector": {
                                            "vector": query_vector,
                                            "k": min(request.top_k * 10, 2000),
                                            "filter": {
                                                "terms": {
                                                    "product_id": request.product_ids
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    ]
                }
            },
            "_source": {
                "excludes": ["content_vector"]
            }
        }

        # 검색 실행
        raw_results = await asyncio.to_thread(
            client.search_with_pipeline,
            query_text=request.query,
            pipeline_id=request.pipeline_id,
            index_name=request.index_name,
            query_body=query_body,
            top_k=request.top_k,
        )

        # 결과 포맷팅
        results = []
        for item in raw_results:
            source = item.get("source", {})
            results.append(ProductResult(
                score=item.get("score", 0.0),
                product_id=source.get("product_id"),
                브랜드=source.get("브랜드"),
                상품명=source.get("상품명"),
                태그=source.get("태그"),
                피부타입=source.get("피부타입"),
                고민키워드=source.get("고민키워드"),
                전용제품=source.get("전용제품"),
                퍼스널컬러=source.get("퍼스널컬러"),
                피부호수=source.get("피부호수"),
                문서=source.get("문서")
            ))

        logging.info(f"검색 완료 - 결과: {len(results)}개")

        return SearchResponse(
            success=True,
            total_results=len(results),
            query=request.query,
            product_id_filter=request.product_ids,
            results=results
        )

    except Exception as e:
        logging.error("search_by_product_ids_failed", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="검색 중 오류가 발생했습니다."
        )


@app.post("/api/search/similar-sentences", response_model=SimilarSentenceResponse)
async def search_similar_sentences(request: SimilarSentenceRequest):
    """
    KNN 벡터 유사도 검색으로 유사한 문장 반환

    - **index_name**: 검색할 인덱스 이름 (예: forbidden_sentences)
    - **query**: 유사 문장을 찾을 검색 쿼리 텍스트 (필수)
    - **top_k**: 반환할 결과 개수 (기본값: 3)
    """
    try:
        logging.info(f"유사 문장 검색 요청 - 인덱스: '{request.index_name}', 쿼리: '{request.query}'")

        client = get_opensearch_client()

        # 쿼리 벡터 생성
        query_vector = (await asyncio.to_thread(client.model.encode, request.query)).tolist()

        query_body = {
            "size": request.top_k,
            "query": {
                "knn": {
                    "sentence_vector": {
                        "vector": query_vector,
                        "k": request.top_k
                    }
                }
            },
            "_source": {
                "excludes": ["sentence_vector"]
            }
        }

        response = await asyncio.to_thread(
            client.client.search,
            index=request.index_name,
            body=query_body,
        )

        hits = response.get("hits", {}).get("hits", [])

        results = []
        for hit in hits:
            source = hit.get("_source", {})
            results.append(SimilarSentenceResult(
                score=hit.get("_score", 0.0),
                sentence=source.get("sentence") or source.get("문장") or source.get("text"),
                source=source
            ))

        logging.info(f"유사 문장 검색 완료 - 결과: {len(results)}개")

        return SimilarSentenceResponse(
            success=True,
            total_results=len(results),
            query=request.query,
            index_name=request.index_name,
            results=results
        )

    except Exception as e:
        logging.error("search_similar_sentences_failed", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="검색 중 오류가 발생했습니다."
        )
    
@app.post("/api/search/combined", response_model=CombinedSearchResponse)
async def search_by_combined_vector(request: ProductIDSearchRequest):
    """
    combined_vector(KNN) + retrieval_query(BM25) 하이브리드 검색 엔드포인트
    score와 product_id만 반환
    """
    try:
        logging.info(f"combined_vector 검색 요청 - 쿼리: '{request.query}', product_ids: {len(request.product_ids)}개")

        client = get_opensearch_client()

        pipeline_body = client._create_search_pipe_line_body()
        client.create_search_pipeline(pipeline_id=request.pipeline_id, pipeline_body=pipeline_body)

        raw_results = await asyncio.to_thread(
            client.search_combined,
            query_text=request.query,
            product_ids=request.product_ids,
            top_k=request.top_k,
            index_name=request.index_name,
            pipeline_id=request.pipeline_id,
            bm25_fields=request.bm25_fields,
            vector_field=request.vector_field or "combined_vector",
        )

        results = [
            CombinedSearchResult(
                score=item.get("score", 0.0),
                product_id=item.get("source", {}).get("product_id", ""),
            )
            for item in raw_results
        ]

        logging.info(f"combined_vector 검색 완료 - 결과: {len(results)}개")

        return CombinedSearchResponse(
            success=True,
            total_results=len(results),
            query=request.query,
            results=results,
        )

    except Exception as e:
        logging.error("search_by_combined_vector_failed", exc_info=True)
        raise HTTPException(status_code=500, detail="검색 중 오류가 발생했습니다.")


@app.post("/api/search/by-field", response_model=FieldSearchResponse)
async def search_by_field(request: FieldSearchRequest):
    """
    특정 필드를 대상으로 한 하이브리드 검색 (BM25 multi_match + KNN)

    페르소나 차원별 검색에 사용:
    - need       → bm25_fields: [function_tags, function_desc],   vector_field: function_desc_vector
    - preference → bm25_fields: [attribute_tags, attribute_desc], vector_field: combined_vector
    - persona    → bm25_fields: [target_tags, target_user],       vector_field: target_user_vector
    """
    try:
        logging.info(
            f"by-field 검색 요청 - 쿼리: '{request.query}', "
            f"필드: {request.bm25_fields}, product_ids: {len(request.product_ids)}개"
        )

        client = get_opensearch_client()

        pipeline_body = client._create_search_pipe_line_body()
        client.create_search_pipeline(pipeline_id=request.pipeline_id, pipeline_body=pipeline_body)

        raw_results = await asyncio.to_thread(
            client.search_by_field,
            query_text=request.query,
            bm25_fields=request.bm25_fields,
            vector_field=request.vector_field,
            product_ids=request.product_ids,
            top_k=request.top_k,
            index_name=request.index_name,
            pipeline_id=request.pipeline_id,
        )

        results = [
            FieldSearchResult(
                score=item.get("score", 0.0),
                product_id=item.get("source", {}).get("product_id", ""),
            )
            for item in raw_results
        ]

        logging.info(f"by-field 검색 완료 - 결과: {len(results)}개")

        return FieldSearchResponse(
            success=True,
            total_results=len(results),
            query=request.query,
            bm25_fields=request.bm25_fields,
            results=results,
        )

    except Exception as e:
        logging.error("search_by_field_failed", exc_info=True)
        raise HTTPException(status_code=500, detail="검색 중 오류가 발생했습니다.")


@app.post("/api/search/multivector", response_model=MultiVectorSearchResponse)
async def search_multivector(request: MultiVectorSearchRequest):
    """
    멀티벡터 인덱스(v4) 하이브리드 검색 엔드포인트

    문장 단위로 색인된 v4 인덱스에서 검색 후 product_id별로 스코어를 집계해 반환.
    aggregation: "max" (기본) | "topk_avg"
    """
    try:
        logging.info(
            f"multivector 검색 요청 - 쿼리: '{request.query}', "
            f"인덱스: {request.index_name}, product_ids: {len(request.product_ids)}개"
        )

        client = get_opensearch_client()

        pipeline_body = client._create_search_pipe_line_body()
        client.create_search_pipeline(pipeline_id=request.pipeline_id, pipeline_body=pipeline_body)
        
        raw_results = await asyncio.to_thread(
            client.search_multivector_field,
            query_text=request.query,
            index_name=request.index_name,
            product_ids=request.product_ids,
            top_k=request.top_k,
            aggregation=request.aggregation,
            pipeline_id=request.pipeline_id,
        )

        results = [
            FieldSearchResult(score=item["score"], product_id=item["product_id"])
            for item in raw_results
        ]

        logging.info(f"multivector 검색 완료 - 결과: {len(results)}개 상품")

        return MultiVectorSearchResponse(
            success=True,
            total_results=len(results),
            query=request.query,
            index_name=request.index_name,
            results=results,
        )

    except Exception as e:
        logging.error("search_multivector_failed", exc_info=True)
        raise HTTPException(status_code=500, detail="검색 중 오류가 발생했습니다.")


_MULTIVECTOR_FIELD_NAMES = ["combined", "function_desc", "attribute_desc", "target_user", "spec_feature"]
_EMBEDDING_MODEL_VERSION = "KURE-v1"
_INDEX_PREFIX = "product_v4"


@app.post("/api/product/index-multivector", response_model=IndexMultivectorResponse)
async def index_multivector(request: IndexMultivectorRequest):
    """
    단일 상품의 멀티벡터 문서를 5개 product_v4_{field} 인덱스에 색인한다.
    """
    try:
        client = get_opensearch_client()
        indexed_counts: Dict[str, int] = {}
        failed_counts: Dict[str, int] = {}
        vectordb_id: Dict[str, List[str]] = {}

        for field in _MULTIVECTOR_FIELD_NAMES:
            sentences = [s.strip() for s in request.multivector.get(field, []) if s.strip()]
            if not sentences:
                indexed_counts[field] = 0
                vectordb_id[f"{_INDEX_PREFIX}_{field}"] = []
                continue

            vectors = await asyncio.to_thread(client.model.encode, sentences, batch_size=64)
            index_name = f"{_INDEX_PREFIX}_{field}"
            doc_ids: List[str] = []
            bulk_body = []

            for idx, (text, vec) in enumerate(zip(sentences, vectors)):
                doc_id = f"{request.product_id}_{field}_{idx}"
                doc_ids.append(doc_id)
                bulk_body.append({"index": {"_index": index_name, "_id": doc_id}})
                bulk_body.append({
                    "product_id":      request.product_id,
                    "group":           request.group,
                    "sentence_idx":    idx,
                    "text":            text,
                    "vector":          vec.tolist(),
                    "is_active":       True,
                    "embedding_model": _EMBEDDING_MODEL_VERSION,
                })

            response = await asyncio.to_thread(client.client.bulk, body=bulk_body, refresh=True)
            failed_ids = {
                item["index"]["_id"]
                for item in response.get("items", [])
                if "error" in item.get("index", {})
            }
            fail_count = len(failed_ids)
            indexed_counts[field] = len(doc_ids) - fail_count
            failed_counts[field] = fail_count
            vectordb_id[index_name] = [d for d in doc_ids if d not in failed_ids]

        has_failure = any(v > 0 for v in failed_counts.values())
        if has_failure:
            logging.warning(
                "index_multivector_partial_failure",
                product_id=request.product_id,
                failed_counts=failed_counts,
            )
        else:
            logging.info(
                "index_multivector_complete",
                product_id=request.product_id,
                indexed_counts=indexed_counts,
            )
        return IndexMultivectorResponse(
            success=not has_failure,
            product_id=request.product_id,
            indexed_counts=indexed_counts,
            vectordb_id=vectordb_id,
            partial_failure=has_failure,
            failed_counts=failed_counts,
        )

    except Exception as e:
        logging.error("index_multivector_failed", exc_info=True)
        raise HTTPException(status_code=500, detail="색인 중 오류가 발생했습니다.")


if __name__ == "__main__":
    import uvicorn

    # 환경 변수에서 설정 읽기
    host = os.getenv("FASTAPI_HOST", "0.0.0.0")
    port = int(os.getenv("FASTAPI_PORT", "8010"))
    environment = os.getenv("ENVIRONMENT", "local")

    # 프로덕션 환경에서는 reload 비활성화 및 workers 추가
    is_production = environment == "production"

    logging.info(f"FastAPI 서버 시작: {host}:{port} (환경: {environment})")

    if is_production:
        # 프로덕션: 멀티 워커, reload 비활성화
        uvicorn.run(
            "opensearch_api:app",
            host=host,
            port=port,
            workers=4,  # CPU 코어 수에 맞게 조정
            log_level="info",
            access_log=True
        )
    else:
        # 로컬: 단일 워커, reload 활성화
        uvicorn.run(
            "opensearch_api:app",
            host=host,
            port=port,
            reload=True,
            log_level="info"
        )
