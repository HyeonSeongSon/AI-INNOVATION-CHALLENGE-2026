from opensearchpy import OpenSearch, exceptions, helpers
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
from typing import Optional, Dict
import logging
import json
import os
import math

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

            logging.info(f"OpenSearch 연결 시도 중... (비밀번호 길이: {len(password)})")

            host = os.getenv("OPENSEARCH_HOST")
            if not host:
                raise ValueError("환경 변수 OPENSEARCH_HOST가 설정되지 않았습니다. .env 파일에 호스트를 설정해주세요.")

            port_str = os.getenv("OPENSEARCH_PORT")
            if not port_str:
                raise ValueError("환경 변수 OPENSEARCH_PORT가 설정되지 않았습니다. .env 파일에 포트를 설정해주세요.")

            port = int(port_str)

            logging.info(f"OpenSearch 연결 대상: {host}:{port}")

            self.client = OpenSearch(
                hosts=[{"host": host, "port": port}],
                timeout=30,
            )
            
            if not self.client.ping():
                raise exceptions.ConnectionError("OpenSearch에 연결할 수 없습니다.")
            logging.info("OpenSearch에 성공적으로 연결되었습니다.")
        except exceptions.OpenSearchException as e:
            logging.error(f"OpenSearch 클라이언트 초기화 중 오류 발생: {e}")
            self.client = None

        self.model = self._embeddings_model()

    def _embeddings_model(self):
        """
        임베딩 모델 초기화
        """
        model = SentenceTransformer("nlpai-lab/KURE-v1")
        vec_dim = len(model.encode("dummy_text"))
        print(f"모델 차원: {vec_dim}")
        return model
    
    def create_index_with_mapping(self, index_name: str, mapping: dict) -> bool:
        """
        지정한 매핑으로 인덱스를 생성합니다.
        """
        if not self.client:
            logging.error("클라이언트가 초기화되지 않아 인덱스를 생성할 수 없습니다.")
            return False
        try:
            if not self.client.indices.exists(index=index_name):
                self.client.indices.create(index=index_name, body=mapping)
                logging.info(f"'{index_name}' 인덱스를 매핑과 함께 생성했습니다.")
                return True
            logging.info(f"'{index_name}' 인덱스가 이미 존재합니다.")
            return True
        except exceptions.RequestError as e:
            logging.error(f"인덱스 생성 중 오류 발생 (잘못된 매핑): {e}")
        except exceptions.OpenSearchException as e:
            logging.error(f"인덱스 생성 중 예상치 못한 오류 발생: {e}")
        return False

    def bulk_index_documents(self, index_name: str, documents: list[dict], refresh: bool = False) -> bool:
        """
        주어진 인덱스에 여러 문서를 bulk로 색인합니다.
        """
        if not self.client:
            logging.error("클라이언트가 초기화되지 않아 문서를 색인할 수 없습니다.")
            return False

        actions = [
            {"_index": index_name, "_source": doc}
            for doc in documents
        ]

        try:
            success, failed = helpers.bulk(self.client, actions, refresh=refresh)
            logging.info(f"Bulk 작업 완료: 성공 {success}건, 실패 {len(failed)}건")
            return not failed
        except exceptions.OpenSearchException as e:
            logging.error(f"Bulk 색인 중 예상치 못한 오류 발생: {e}")
            return False
    
    def delete_index(self, index_name: str) -> None:
        """
        인덱스를 삭제합니다.
        """
        if not self.client:
            logging.error("클라이언트가 초기화되지 않아 인덱스를 삭제할 수 없습니다.")
            return
        try:
            if self.client.indices.exists(index=index_name):
                self.client.indices.delete(index=index_name)
                logging.info(f"'{index_name}' 인덱스를 삭제했습니다.")
        except exceptions.OpenSearchException as e:
            logging.error(f"인덱스 삭제 중 예상치 못한 오류 발생: {e}")

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
            print(f"✅ Search pipeline '{pipeline_id}' 생성/업데이트 완료")
            print(f"응답: {response}")
            return True
        except Exception as e:
            print(f"❌ Search pipeline 생성 실패: {e}")
            logging.error(f"Search pipeline 생성 오류: {e}")
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
            print(f"🗑️ Search pipeline '{pipeline_id}' 삭제 완료")
            return True
        except Exception as e:
            print(f"❌ Search pipeline 삭제 실패: {e}")
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
        print(f"\n=== Search Pipeline 기반 하이브리드 검색 시작 ===")
        print(f"Pipeline ID: {pipeline_id}")
        print(f"Query: {query_text}")

        if query_body is None:
            logging.error("query_body가 None입니다. 검색을 실행할 수 없습니다.")
            return []

        try:
            # Search pipeline 파라미터 설정
            params = {"search_pipeline": pipeline_id}

            # 검색 실행
            response = self.client.search(index=index_name, body=query_body, params=params)

            # 결과 처리
            hits = response.get("hits", {}).get("hits", [])
            results = []

            print(f"✅ Search pipeline 검색 완료: {len(hits)}개 결과")

            for i, hit in enumerate(hits):
                result = {
                    "score": hit["_score"],
                    "source": hit["_source"]
                }
                results.append(result)

                # 결과 출력
                source = hit["_source"]
                print(f"\n{i+1}. Pipeline 점수: {hit['_score']:.6f}")
                print(f"   product_id: {source.get('product_id', 'N/A')}")

            return results
            
        except Exception as e:
            print(f"❌ Search pipeline 검색 오류: {e}")
            logging.error(f"Search pipeline 검색 상세 오류: {e}")
            return []
        
    def _create_combined_query_body(self, query_vector: list, product_ids: list, top_k: int) -> dict:
        """
        combined_vector(KNN) + retrieval_query(BM25) 하이브리드 쿼리 보디 생성
        """
        return {
            "size": top_k,
            "query": {
                "hybrid": {
                    "queries": [
                        # BM25 - structured 텍스트 필드 매칭
                        {
                            "bool": {
                                "must": {
                                    "multi_match": {
                                        "query": "",  # 호출 시 치환
                                        "fields": [
                                            "combined^3.0",
                                            # "target_user^2.5",
                                            # "function_desc^2.0",
                                            # "attribute_desc^1.5",
                                            # "concern^1.5",
                                            # "summary^1.0",
                                        ],
                                        "type": "best_fields",
                                    }
                                },
                                "filter": {
                                    "terms": {"product_id": product_ids}
                                }
                            }
                        },
                        # KNN - combined_vector 유사도 검색
                        {
                            "bool": {
                                "must": {
                                    "knn": {
                                        "combined_vector": {
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
        index_name: str = "product_index_v2",
        pipeline_id: str = "hybrid-minmax-pipeline",
    ) -> list:
        """
        combined_vector(KNN) + retrieval_query(BM25) 하이브리드 검색 실행

        Args:
            query_text: 검색 쿼리 텍스트 (retrieval_query)
            product_ids: 검색 범위를 제한할 상품 ID 리스트
            top_k: 반환할 최대 결과 수
            index_name: 검색 대상 인덱스
            pipeline_id: 사용할 search pipeline ID

        Returns:
            List[Dict]: 검색 결과 (score + source)
        """
        query_vector = self.model.encode(query_text).tolist()
        query_body = self._create_combined_query_body(query_vector, product_ids, top_k)

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
        bm25_field: str,
        vector_field: str,
        product_ids: list,
        top_k: int,
    ) -> dict:
        """
        특정 필드를 대상으로 한 하이브리드 쿼리 보디 생성
        BM25: bm25_field 단일 필드 / KNN: vector_field
        """
        return {
            "size": top_k,
            "query": {
                "hybrid": {
                    "queries": [
                        {
                            "bool": {
                                "must": {
                                    "match": {
                                        bm25_field: {
                                            "query": "",  # 호출 시 치환
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
        bm25_field: str,
        vector_field: str,
        product_ids: list,
        top_k: int = 50,
        index_name: str = "product_index_v2",
        pipeline_id: str = "hybrid-minmax-pipeline",
    ) -> list:
        """
        특정 필드를 대상으로 한 하이브리드 검색 실행

        Args:
            query_text: 검색 쿼리 텍스트
            bm25_field: BM25 검색 대상 필드 (예: function_desc, attribute_desc, target_user)
            vector_field: KNN 검색 대상 벡터 필드 (예: function_desc_vector)
            product_ids: 검색 범위를 제한할 상품 ID 리스트
            top_k: 반환할 최대 결과 수
            index_name: 검색 대상 인덱스
            pipeline_id: 사용할 search pipeline ID

        Returns:
            List[Dict]: score + product_id 검색 결과
        """
        query_vector = self.model.encode(query_text).tolist()
        query_body = self._create_field_specific_query_body(
            query_vector, bm25_field, vector_field, product_ids, top_k
        )
        # BM25 쿼리 텍스트 주입
        query_body["query"]["hybrid"]["queries"][0]["bool"]["must"]["match"][bm25_field]["query"] = query_text

        return self.search_with_pipeline(
            query_text=query_text,
            pipeline_id=pipeline_id,
            index_name=index_name,
            query_body=query_body,
            top_k=top_k,
        )

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