from opensearch_hybrid import OpenSearchHybridClient
from opensearchpy import OpenSearch, exceptions, helpers

def _create_search_pipe_line_body():
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
                            "weights": [0.2, 0.8]
                        }
                    }
                }
            }
        ]
    }
    return pipeline_body

if __name__=="__main__":
    client = OpenSearchHybridClient()
    body = _create_search_pipe_line_body()
    client.create_search_pipeline(pipeline_id="0.2_0.8", pipeline_body=_create_search_pipe_line_body())