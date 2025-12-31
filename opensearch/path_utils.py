"""
프로젝트 루트 기준 경로 유틸리티

AI-INNOVATION-CHALLENGE-2026 폴더의 위치와 상관없이
프로젝트 루트를 기준으로 파일 경로를 생성합니다.
"""
import os
from pathlib import Path


def get_project_root():
    """
    프로젝트 루트 디렉토리(AI-INNOVATION-CHALLENGE-2026)를 반환합니다.

    Returns:
        Path: 프로젝트 루트 디렉토리 경로
    """
    # 현재 파일(path_utils.py)의 위치
    current_file = Path(__file__).resolve()

    # opensearch 디렉토리
    opensearch_dir = current_file.parent

    # 프로젝트 루트 (opensearch의 부모 디렉토리)
    project_root = opensearch_dir.parent

    return project_root


def get_absolute_path(*path_parts):
    """
    프로젝트 루트를 기준으로 절대 경로를 생성합니다.

    Args:
        *path_parts: 경로 구성 요소들 (예: 'opensearch', 'data.jsonl')

    Returns:
        str: 절대 경로

    Example:
        >>> get_absolute_path('opensearch', 'product_data.jsonl')
        'C:/Users/user/Documents/GitHub/AI-INNOVATION-CHALLENGE-2026/opensearch/product_data.jsonl'

        >>> get_absolute_path('backend', 'app', 'config.py')
        'C:/Users/user/Documents/GitHub/AI-INNOVATION-CHALLENGE-2026/backend/app/config.py'
    """
    project_root = get_project_root()
    full_path = project_root.joinpath(*path_parts)
    return str(full_path)


def get_opensearch_path(*path_parts):
    """
    opensearch 디렉토리 기준 절대 경로를 생성합니다.

    Args:
        *path_parts: opensearch 디렉토리 내 경로 구성 요소들

    Returns:
        str: 절대 경로

    Example:
        >>> get_opensearch_path('product_data.jsonl')
        'C:/Users/user/Documents/GitHub/AI-INNOVATION-CHALLENGE-2026/opensearch/product_data.jsonl'
    """
    return get_absolute_path('opensearch', *path_parts)


if __name__ == "__main__":
    # 테스트
    print("=" * 60)
    print("프로젝트 경로 테스트")
    print("=" * 60)

    print(f"프로젝트 루트: {get_project_root()}")
    print(f"\nOpenSearch 디렉토리: {get_absolute_path('opensearch')}")
    print(f"Backend 디렉토리: {get_absolute_path('backend')}")

    print(f"\n예제 파일 경로:")
    print(f"  - {get_opensearch_path('product_data.jsonl')}")
    print(f"  - {get_opensearch_path('product_id_mapping.jsonl')}")
    print(f"  - {get_absolute_path('backend', 'app', 'main.py')}")
