from opensearchpy import OpenSearch, exceptions, helpers
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
from typing import Optional, Dict
import structlog
import json
import os
import math

logger = structlog.get_logger("opensearch_hybrid")

load_dotenv()

class OpenSearchHybridClient:
    def __init__(self):
        """
        OpenSearch 클라이언트 초기화 및 연결 설정 (하이브리드 쿼리 기반)
        """
        try:
            password = os.getenv("OPENSEARCH_ADMIN_PASSWORD")
            if not password:
                raise ValueError("환경 변수 OPENSEARCH_ADMIN_PASSWORD가 설정되지 않았습니다. .env 파일에 패스워드를 설정해주세요.")

            user = os.getenv("OPENSEARCH_ADMIN_USER", "admin")

            host = os.getenv("OPENSEARCH_HOST")
            if not host:
                raise ValueError("환경 변수 OPENSEARCH_HOST가 설정되지 않았습니다. .env 파일에 호스트를 설정해주세요.")

            port_str = os.getenv("OPENSEARCH_PORT")
            if not port_str:
                raise ValueError("환경 변수 OPENSEARCH_PORT가 설정되지 않았습니다. .env 파일에 포트를 설정해주세요.")

            port = int(port_str)

            # OPENSEARCH_USE_SSL=true 시 HTTPS + 자체 서명 인증서(verify_certs=False)로 연결.
            # AWS EC2 환경(opensearch-api systemd)과 로컬 docker-compose 모두 true로 주입.
            use_ssl = os.getenv("OPENSEARCH_USE_SSL", "false").lower() == "true"

            logger.info("opensearch_connecting", host=host, port=port, use_ssl=use_ssl)

            client_kwargs = {
                "hosts": [{"host": host, "port": port}],
                "http_auth": (user, password),
                "timeout": 30,
            }
            if use_ssl:
                client_kwargs.update(
                    use_ssl=True,
                    verify_certs=False,      # 데모 인증서 (내부망)
                    ssl_assert_hostname=False,
                    ssl_show_warn=False,
                )

            self.client = OpenSearch(**client_kwargs)

            if not self.client.ping():
                raise exceptions.ConnectionError("OpenSearch에 연결할 수 없습니다.")
            logger.info("opensearch_connected")
        except Exception as e:
            logger.error("opensearch_init_failed", error_type=type(e).__name__)
            self.client = None

        self.model = self._embeddings_model() if self.client is not None else None

    def _embeddings_model(self):
        """
        임베딩 모델 초기화
        """
        model = SentenceTransformer("nlpai-lab/KURE-v1")
        vec_dim = len(model.encode("dummy_text"))
        logger.debug("embeddings_model_loaded", dimension=vec_dim)
        return model
    
    def create_index_with_mapping(self, index_name: str, mapping: dict) -> bool:
        """
        지정한 매핑으로 인덱스를 생성합니다.
        """
        if not self.client:
            logger.error("client_not_initialized", method="create_index")
            return False
        try:
            if not self.client.indices.exists(index=index_name):
                self.client.indices.create(index=index_name, body=mapping)
                logger.info("index_created", index=index_name)
                return True
            logger.info("index_exists", index=index_name)
            return True
        except exceptions.RequestError as e:
            logger.error("index_create_failed", index=index_name, error_type=type(e).__name__)
        except exceptions.OpenSearchException as e:
            logger.error("index_create_error", index=index_name, error_type=type(e).__name__)
        return False

    def bulk_index_documents(self, index_name: str, documents: list[dict], refresh: bool = False) -> bool:
        """
        주어진 인덱스에 여러 문서를 bulk로 색인합니다.
        """
        if not self.client:
            logger.error("client_not_initialized", method="bulk_index")
            return False

        actions = [
            {"_index": index_name, "_source": doc}
            for doc in documents
        ]

        try:
            success, failed = helpers.bulk(self.client, actions, refresh=refresh)
            logger.info("bulk_indexed", success=success, failed=len(failed))
            return not failed
        except exceptions.OpenSearchException as e:
            logger.error("bulk_index_failed", error_type=type(e).__name__)
            return False
    
    def delete_index(self, index_name: str) -> None:
        """
        인덱스를 삭제합니다.
        """
        if not self.client:
            logger.error("client_not_initialized", method="delete_index")
            return
        try:
            if self.client.indices.exists(index=index_name):
                self.client.indices.delete(index=index_name)
                logger.info("index_deleted", index=index_name)
        except exceptions.OpenSearchException as e:
            logger.error("index_delete_failed", index=index_name, error_type=type(e).__name__)

    def create_search_pipeline(self,
                               pipeline_id: str = "hybrid-minmax-pipeline", 
                               pipeline_body: Optional[Dict] = None):
        """
        OpenSearch 3.0+ 호환 하이브리드 검색용 search pipeline 생성
        """
        try:
            # 파이프라인 생성 또는 업데이트
            response = self.client.transport.perform_request(
                method="PUT",
                url=f"/_search/pipeline/{pipeline_id}",
                body=pipeline_body
            )
            logger.info("pipeline_created", pipeline_id=pipeline_id)
            return True
        except Exception as e:
            logger.error("pipeline_create_failed", pipeline_id=pipeline_id, error_type=type(e).__name__)
            return False
        
    def delete_search_pipeline(self, pipeline_id: str = "hybrid-minmax-pipeline"):
        """
        search pipeline 삭제
        """
        try:
            response = self.client.transport.perform_request(
                method="DELETE",
                url=f"/_search/pipeline/{pipeline_id}"
            )
            logger.info("pipeline_deleted", pipeline_id=pipeline_id)
            return True
        except Exception as e:
            logger.error("pipeline_delete_failed", pipeline_id=pipeline_id, error_type=type(e).__name__)
            return False
    
    def search_with_pipeline(self,
                           query_text: str,
                           pipeline_id: str = "hybrid-minmax-pipeline",
                           index_name: str = "pharma_test_index",
                           query_body: Optional[Dict] = None,
                           top_k: int = 3):
        """
        Search pipeline을 사용한 하이브리드 검색

        Args:
            query_text (str): 검색 쿼리 텍스트
            pipeline_id (str): 사용할 search pipeline ID
            index_name (str): 검색 대상 인덱스
            top_k (int): 반환할 결과 수

        Returns:
            List[Dict]: 검색 결과
        """
        logger.debug("hybrid_search_started", pipeline_id=pipeline_id)

        if query_body is None:
            logger.error("search_aborted_no_query_body")
            return []

        try:
            params = {"search_pipeline": pipeline_id}
            response = self.client.search(index=index_name, body=query_body, params=params)

            hits = response.get("hits", {}).get("hits", [])
            results = [{"score": hit["_score"], "source": hit["_source"]} for hit in hits]

            logger.debug("hybrid_search_done", hits=len(hits))
            return results

        except Exception as e:
            logger.error("search_pipeline_error", error_type=type(e).__name__, exc_info=True)
            return []
        
    def _create_combined_query_body(
        self,
        query_vector: list,
        product_ids: list,
        top_k: int,
        bm25_fields: list = None,
        vector_field: str = "combined_vector",
    ) -> dict:
        """
        combined_vector(KNN) + retrieval_query(BM25) 하이브리드 쿼리 보디 생성

        Args:
            bm25_fields: BM25 multi_match 대상 필드 리스트 (기본: search_tags^2.0, search_phrases)
            vector_field: KNN 대상 벡터 필드 (기본: combined_vector)
        """
        if bm25_fields is None:
            bm25_fields = ["search_tags^2.0", "search_phrases"]

        return {
            "size": top_k,
            "query": {
                "hybrid": {
                    "queries": [
                        # BM25 - search_tags + search_phrases 매칭
                        {
                            "bool": {
                                "must": {
                                    "multi_match": {
                                        "query": "",  # 호출 시 치환
                                        "fields": bm25_fields,
                                        "type": "best_fields",
                                    }
                                },
                                "filter": {
                                    "terms": {"product_id": product_ids}
                                }
                            }
                        },
                        # KNN - vector_field 유사도 검색
                        {
                            "bool": {
                                "must": {
                                    "knn": {
                                        vector_field: {
                                            "vector": query_vector,
                                            "k": top_k * 10,
                                            "filter": {
                                                "terms": {"product_id": product_ids}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    ]
                }
            },
            "_source": ["product_id"]
        }

    def search_combined(
        self,
        query_text: str,
        product_ids: list,
        top_k: int = 10,
        index_name: str = "product_index_v3",
        pipeline_id: str = "hybrid-minmax-pipeline",
        bm25_fields: list = None,
        vector_field: str = "combined_vector",
        query_vector: list = None,
    ) -> list:
        """
        combined_vector(KNN) + retrieval_query(BM25) 하이브리드 검색 실행

        Args:
            query_text: 검색 쿼리 텍스트 (retrieval_query)
            product_ids: 검색 범위를 제한할 상품 ID 리스트
            top_k: 반환할 최대 결과 수
            index_name: 검색 대상 인덱스
            pipeline_id: 사용할 search pipeline ID
            bm25_fields: BM25 대상 필드 리스트 (기본: search_tags^2.0, search_phrases)
            vector_field: KNN 대상 벡터 필드 (기본: combined_vector)
            query_vector: 미리 인코딩된 쿼리 벡터. 주어지면 내부 인코딩을 스킵한다
                          (호출자가 별도 CPU 동시성 한도로 인코딩을 보호하기 위함).

        Returns:
            List[Dict]: 검색 결과 (score + source)
        """
        if query_vector is None:
            query_vector = self.model.encode(query_text).tolist()
        query_body = self._create_combined_query_body(
            query_vector, product_ids, top_k, bm25_fields, vector_field
        )

        # BM25 query 텍스트 주입
        query_body["query"]["hybrid"]["queries"][0]["bool"]["must"]["multi_match"]["query"] = query_text

        return self.search_with_pipeline(
            query_text=query_text,
            pipeline_id=pipeline_id,
            index_name=index_name,
            query_body=query_body,
            top_k=top_k,
        )

    def _create_field_specific_query_body(
        self,
        query_vector: list,
        bm25_fields: list,
        vector_field: str,
        product_ids: list,
        top_k: int,
    ) -> dict:
        """
        특정 필드를 대상으로 한 하이브리드 쿼리 보디 생성
        BM25: bm25_fields multi_match / KNN: vector_field
        """
        return {
            "size": top_k,
            "query": {
                "hybrid": {
                    "queries": [
                        {
                            "bool": {
                                "must": {
                                    "multi_match": {
                                        "query": "",  # 호출 시 치환
                                        "fields": bm25_fields,
                                        "type": "best_fields",
                                    }
                                },
                                "filter": {"terms": {"product_id": product_ids}},
                            }
                        },
                        {
                            "bool": {
                                "must": {
                                    "knn": {
                                        vector_field: {
                                            "vector": query_vector,
                                            "k": top_k * 10,
                                            "filter": {
                                                "terms": {"product_id": product_ids}
                                            },
                                        }
                                    }
                                }
                            }
                        },
                    ]
                }
            },
            "_source": ["product_id"],
        }

    def search_by_field(
        self,
        query_text: str,
        bm25_fields: list,
        vector_field: str,
        product_ids: list,
        top_k: int = 50,
        index_name: str = "product_index_v3",
        pipeline_id: str = "hybrid-minmax-pipeline",
        query_vector: list = None,
    ) -> list:
        """
        특정 필드를 대상으로 한 하이브리드 검색 실행

        Args:
            query_text: 검색 쿼리 텍스트
            bm25_fields: BM25 multi_match 대상 필드 리스트
                         (예: ["function_tags", "function_desc"])
            vector_field: KNN 검색 대상 벡터 필드 (예: function_desc_vector)
            product_ids: 검색 범위를 제한할 상품 ID 리스트
            top_k: 반환할 최대 결과 수
            index_name: 검색 대상 인덱스
            pipeline_id: 사용할 search pipeline ID
            query_vector: 미리 인코딩된 쿼리 벡터. 주어지면 내부 인코딩을 스킵한다.

        Returns:
            List[Dict]: score + product_id 검색 결과
        """
        if query_vector is None:
            query_vector = self.model.encode(query_text).tolist()
        query_body = self._create_field_specific_query_body(
            query_vector, bm25_fields, vector_field, product_ids, top_k
        )
        # BM25 쿼리 텍스트 주입
        query_body["query"]["hybrid"]["queries"][0]["bool"]["must"]["multi_match"]["query"] = query_text

        return self.search_with_pipeline(
            query_text=query_text,
            pipeline_id=pipeline_id,
            index_name=index_name,
            query_body=query_body,
            top_k=top_k,
        )

    def search_multivector_field(
        self,
        query_text: str,
        index_name: str,
        product_ids: list,
        top_k: int = 100,
        aggregation: str = "max",
        topk_k: int = 2,
        pipeline_id: str = "hybrid-minmax-pipeline",
        query_vector: list = None,
    ) -> list:
        """
        멀티벡터 인덱스(문장 단위 문서)에서 하이브리드 검색 후 product_id별 스코어 집계

        v4 인덱스 공통 필드: text (BM25), vector (KNN)
        동일 상품의 여러 문장 히트를 aggregation 방식으로 product_id당 1개 스코어로 집계

        Args:
            query_text: 검색 쿼리 텍스트
            index_name: 검색 대상 인덱스 (예: product_v4_combined)
            product_ids: 검색 범위를 제한할 상품 ID 리스트
            top_k: 최종 반환할 상품 수
            aggregation: 집계 방식 "max" | "topk_avg"
            topk_k: topk_avg 사용 시 상위 k개 문장 수 (기본 2)
            pipeline_id: 하이브리드 파이프라인 ID
            query_vector: 미리 인코딩된 쿼리 벡터. 주어지면 내부 인코딩을 스킵한다.

        Returns:
            [{"product_id": str, "score": float}, ...] 내림차순 top_k개
        """
        from collections import defaultdict

        if query_vector is None:
            query_vector = self.model.encode(query_text).tolist()

        # 문장이 상품당 최대 6~7개이므로 size를 충분히 크게
        fetch_size = min(top_k * 10, 2000)

        query_body = {
            "size": fetch_size,
            "query": {
                "hybrid": {
                    "queries": [
                        {
                            "bool": {
                                "must": {
                                    "match": {
                                        "text": {
                                            "query": query_text,
                                        }
                                    }
                                },
                                "filter": {"terms": {"product_id": product_ids}},
                            }
                        },
                        {
                            "bool": {
                                "must": {
                                    "knn": {
                                        "vector": {
                                            "vector": query_vector,
                                            "k": fetch_size,
                                            "filter": {
                                                "terms": {"product_id": product_ids}
                                            },
                                        }
                                    }
                                }
                            }
                        },
                    ]
                }
            },
            "_source": ["product_id"],
        }

        raw_results = self.search_with_pipeline(
            query_text=query_text,
            pipeline_id=pipeline_id,
            index_name=index_name,
            query_body=query_body,
            top_k=fetch_size,
        )

        # product_id별 스코어 수집
        product_scores: dict = defaultdict(list)
        for item in raw_results:
            pid = item.get("source", {}).get("product_id")
            score = item.get("score", 0.0)
            if pid:
                product_scores[pid].append(score)

        # 집계
        aggregated = []
        for pid, scores in product_scores.items():
            if aggregation == "max":
                agg_score = max(scores)
            else:  # topk_avg
                top = sorted(scores, reverse=True)[:topk_k]
                agg_score = sum(top) / len(top)
            aggregated.append({"product_id": pid, "score": agg_score})

        return sorted(aggregated, key=lambda x: x["score"], reverse=True)[:top_k]

    def _create_search_pipe_line_body(self):
        pipeline_body = {
            "description": "하이브리드 점수 정규화 및 결합 파이프라인",
            "phase_results_processors": [
                {
                    "normalization-processor": {
                        "normalization": { 
                            "technique": "min_max" 
                        },
                        "combination": {
                            "technique": "arithmetic_mean",
                            "parameters": {
                                "weights": [0.4, 0.6]
                            }
                        }
                    }
                }
            ]
        }
        return pipeline_body