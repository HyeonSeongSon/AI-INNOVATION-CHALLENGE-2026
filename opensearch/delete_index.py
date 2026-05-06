from opensearchpy import OpenSearch, exceptions
from dotenv import load_dotenv
import logging
import os

load_dotenv()

logging.basicConfig(level=logging.INFO)

INDEX_NAME = "product_index_v2"


def get_client() -> OpenSearch:
    host = os.getenv("OPENSEARCH_HOST")
    port = int(os.getenv("OPENSEARCH_PORT"))

    client = OpenSearch(
        hosts=[{"host": host, "port": port}],
        timeout=30,
    )

    if not client.ping():
        raise exceptions.ConnectionError("OpenSearch에 연결할 수 없습니다.")

    logging.info("OpenSearch에 성공적으로 연결되었습니다.")
    return client


def delete_index(index_name: str) -> None:
    client = get_client()

    if not client.indices.exists(index=index_name):
        logging.warning(f"인덱스 '{index_name}'가 존재하지 않습니다.")
        return

    response = client.indices.delete(index=index_name)
    if response.get("acknowledged"):
        logging.info(f"인덱스 '{index_name}' 삭제 완료.")
    else:
        logging.error(f"인덱스 '{index_name}' 삭제 실패: {response}")


if __name__ == "__main__":
    delete_index(INDEX_NAME)
