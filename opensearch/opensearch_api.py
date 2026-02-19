from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List
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

# FastAPI 앱 초기화
app = FastAPI(
    title="OpenSearch Hybrid Search API",
    description="하이브리드 검색 (BM25 + KNN) API",
    version="1.0.0"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 특정 origin만 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OpenSearch 클라이언트 (싱글톤)
opensearch_client = None


# 요청/응답 모델
class ProductIDSearchRequest(BaseModel):
    query: str = Field(..., description="검색 쿼리 텍스트", min_length=1)
    product_ids: List[str] = Field(..., description="검색할 product_id 리스트", min_items=1)
    index_name: str = Field(default="product_index", description="검색할 인덱스 이름")
    pipeline_id: str = Field(default="hybrid-minmax-pipeline", description="사용할 search pipeline ID")
    top_k: int = Field(default=3, ge=1, le=100, description="반환할 결과 개수 (1-100)")

    class Config:
        json_schema_extra = {
            "example": {
                "query": "촉촉한 립스틱",
                "product_ids": ["PROD001", "PROD002", "PROD003"],
                "index_name": "product_index",
                "pipeline_id": "hybrid-minmax-pipeline",
                "top_k": 3
            }
        }


class SimilarSentenceRequest(BaseModel):
    index_name: str = Field(..., description="검색할 인덱스 이름 (예: forbidden_sentences)")
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
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


@app.get("/api/product/{product_id}")
async def get_product_by_id(
    product_id: str,
    index_name: str = Query(default="product_index", description="검색할 인덱스 이름")
):
    """
    Product ID로 단일 상품 문서 조회

    - **product_id**: 조회할 상품 ID (필수)
    - **index_name**: 검색할 인덱스 이름 (기본값: product_index)
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
        response = client.client.search(
            index=index_name,
            body=query_body
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
        logging.error(f"Product ID 조회 중 오류 발생: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"조회 중 오류가 발생했습니다: {str(e)}"
        )


@app.post("/api/search/product-ids", response_model=SearchResponse)
async def search_by_product_ids(request: ProductIDSearchRequest):
    """
    Product ID 리스트로 필터링된 하이브리드 검색 엔드포인트

    - **query**: 검색 쿼리 텍스트 (필수)
    - **product_ids**: 검색할 product_id 리스트 (필수)
    - **index_name**: 검색할 인덱스 이름 (기본값: product_index)
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
        query_vector = client.model.encode(request.query).tolist()
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
                                            "k": request.top_k * 10,
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
        raw_results = client.search_with_pipeline(
            query_text=request.query,
            pipeline_id=request.pipeline_id,
            index_name=request.index_name,
            query_body=query_body,
            top_k=request.top_k
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
        logging.error(f"검색 중 오류 발생: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"검색 중 오류가 발생했습니다: {str(e)}"
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
        query_vector = client.model.encode(request.query).tolist()

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

        response = client.client.search(
            index=request.index_name,
            body=query_body
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
        logging.error(f"유사 문장 검색 중 오류 발생: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"검색 중 오류가 발생했습니다: {str(e)}"
        )


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
