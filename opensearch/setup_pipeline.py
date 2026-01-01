"""
OpenSearch 데이터 파이프라인 통합 스크립트

전체 파이프라인을 자동으로 실행합니다:
1. 데이터 색인 (index_products.py)
2. VectorDB ID 추출 (export_product_ids.py)
3. 데이터 병합 (merge_product_data.py)
"""

import logging
import sys
from pathlib import Path

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# 개별 스크립트의 함수들 임포트
from index_products import index_products_to_opensearch
from export_product_ids import export_product_id_mapping
from merge_product_data import merge_product_data
from path_utils import get_absolute_path


class OpenSearchPipeline:
    """OpenSearch 데이터 처리 파이프라인"""

    def __init__(
        self,
        jsonl_file_path=None,
        index_name="product_index",
        mapping_output_file=None,
        final_output_file=None,
        recreate_index=True
    ):
        """
        파이프라인 초기화

        Args:
            jsonl_file_path: 원본 JSONL 파일 경로
            index_name: OpenSearch 인덱스 이름
            mapping_output_file: ID 매핑 출력 파일 경로
            final_output_file: 최종 병합 파일 경로
            recreate_index: 인덱스 재생성 여부
        """
        # 기본 경로 설정
        self.jsonl_file_path = jsonl_file_path or get_absolute_path("data", "product_data_251231.jsonl")
        self.index_name = index_name
        self.mapping_output_file = mapping_output_file or get_absolute_path("data", "product_id_mapping.jsonl")
        self.final_output_file = final_output_file or get_absolute_path("data", "product_data_for_db.jsonl")
        self.recreate_index = recreate_index

        self.logger = logging.getLogger(__name__)

    def validate_input_files(self):
        """입력 파일 존재 여부 확인"""
        input_file = Path(self.jsonl_file_path)
        if not input_file.exists():
            self.logger.error(f"❌ 입력 파일을 찾을 수 없습니다: {self.jsonl_file_path}")
            return False

        self.logger.info(f"✅ 입력 파일 확인: {self.jsonl_file_path}")
        return True

    def step1_index_products(self):
        """
        스텝 1: OpenSearch에 상품 데이터 색인

        Returns:
            bool: 성공 여부
        """
        self.logger.info("\n" + "=" * 80)
        self.logger.info("📊 STEP 1: OpenSearch에 상품 데이터 색인")
        self.logger.info("=" * 80)

        try:
            success = index_products_to_opensearch(
                jsonl_file_path=self.jsonl_file_path,
                index_name=self.index_name,
                recreate_index=self.recreate_index
            )

            if success:
                self.logger.info("✅ STEP 1 완료: 상품 데이터 색인 성공")
            else:
                self.logger.error("❌ STEP 1 실패: 상품 데이터 색인 실패")

            return success

        except Exception as e:
            self.logger.error(f"❌ STEP 1 오류: {e}")
            import traceback
            traceback.print_exc()
            return False

    def step2_export_ids(self):
        """
        스텝 2: VectorDB ID 매핑 추출

        Returns:
            bool: 성공 여부
        """
        self.logger.info("\n" + "=" * 80)
        self.logger.info("🔍 STEP 2: VectorDB ID 매핑 추출")
        self.logger.info("=" * 80)

        try:
            success = export_product_id_mapping(
                index_name=self.index_name,
                output_file=self.mapping_output_file
            )

            if success:
                self.logger.info("✅ STEP 2 완료: ID 매핑 추출 성공")
            else:
                self.logger.error("❌ STEP 2 실패: ID 매핑 추출 실패")

            return success

        except Exception as e:
            self.logger.error(f"❌ STEP 2 오류: {e}")
            import traceback
            traceback.print_exc()
            return False

    def step3_merge_data(self):
        """
        스텝 3: 원본 데이터와 ID 매핑 병합

        Returns:
            bool: 성공 여부
        """
        self.logger.info("\n" + "=" * 80)
        self.logger.info("🔄 STEP 3: 데이터 병합")
        self.logger.info("=" * 80)

        try:
            # merge_product_data는 반환값이 없으므로 예외가 없으면 성공으로 간주
            merge_product_data()

            # 출력 파일이 생성되었는지 확인
            output_file = Path(self.final_output_file)
            if output_file.exists():
                self.logger.info("✅ STEP 3 완료: 데이터 병합 성공")
                return True
            else:
                self.logger.error("❌ STEP 3 실패: 출력 파일이 생성되지 않음")
                return False

        except Exception as e:
            self.logger.error(f"❌ STEP 3 오류: {e}")
            import traceback
            traceback.print_exc()
            return False

    def run(self):
        """
        전체 파이프라인 실행

        Returns:
            bool: 성공 여부
        """
        self.logger.info("\n" + "=" * 80)
        self.logger.info("🚀 OpenSearch 데이터 파이프라인 시작")
        self.logger.info("=" * 80)
        self.logger.info(f"입력 파일: {self.jsonl_file_path}")
        self.logger.info(f"인덱스 이름: {self.index_name}")
        self.logger.info(f"매핑 파일: {self.mapping_output_file}")
        self.logger.info(f"최종 출력 파일: {self.final_output_file}")
        self.logger.info(f"인덱스 재생성: {self.recreate_index}")
        self.logger.info("=" * 80)

        # 입력 파일 확인
        if not self.validate_input_files():
            return False

        # 스텝별 실행
        steps = [
            ("색인", self.step1_index_products),
            ("ID 추출", self.step2_export_ids),
            ("데이터 병합", self.step3_merge_data)
        ]

        for step_name, step_func in steps:
            try:
                if not step_func():
                    self.logger.error(f"\n❌ 파이프라인 실패: {step_name} 단계에서 오류 발생")
                    return False
            except KeyboardInterrupt:
                self.logger.warning(f"\n⚠️  사용자가 파이프라인을 중단했습니다 ({step_name} 단계)")
                return False
            except Exception as e:
                self.logger.error(f"\n❌ 파이프라인 실패: {step_name} 단계에서 예상치 못한 오류 발생")
                self.logger.error(f"오류 내용: {e}")
                import traceback
                traceback.print_exc()
                return False

        # 최종 결과 요약
        self.print_summary()

        return True

    def print_summary(self):
        """파이프라인 실행 결과 요약 출력"""
        self.logger.info("\n" + "=" * 80)
        self.logger.info("✅ 파이프라인 완료!")
        self.logger.info("=" * 80)

        # 파일 정보 출력
        files_info = [
            ("원본 데이터", self.jsonl_file_path),
            ("ID 매핑", self.mapping_output_file),
            ("최종 출력", self.final_output_file)
        ]

        for name, file_path in files_info:
            path = Path(file_path)
            if path.exists():
                size_mb = path.stat().st_size / 1024 / 1024
                self.logger.info(f"{name}: {file_path}")
                self.logger.info(f"  크기: {size_mb:.2f} MB")
            else:
                self.logger.warning(f"{name}: {file_path} (파일 없음)")

        self.logger.info("=" * 80)
        self.logger.info("🎉 모든 작업이 성공적으로 완료되었습니다!")
        self.logger.info("=" * 80)


def main():
    """메인 실행 함수"""
    # 기본 설정
    config = {
        "jsonl_file_path": get_absolute_path("data", "product_data_251231.jsonl"),
        "index_name": "product_index",
        "mapping_output_file": get_absolute_path("data", "product_id_mapping.jsonl"),
        "final_output_file": get_absolute_path("data", "product_data_for_db.jsonl"),
        "recreate_index": True  # 기존 인덱스 삭제 후 재생성
    }

    # 파이프라인 실행
    pipeline = OpenSearchPipeline(**config)
    success = pipeline.run()

    # 종료 코드 반환
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
