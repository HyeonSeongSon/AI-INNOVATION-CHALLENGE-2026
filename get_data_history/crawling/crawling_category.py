import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from crawling251205 import BrandPageCrawler, logger
from selenium.webdriver.common.by import By
from urllib.parse import urljoin
from typing import List
from datetime import datetime

CATEGORY_URL = 'https://www.amoremall.com/kr/ko/display/category?displayCategorySn=98&searchCategory=%EB%A9%94%EC%9D%B4%ED%81%AC%EC%97%85'

# 카테고리 페이지 상품 컨테이너 XPath
PRODUCT_CONTAINER_XPATH = '//*[@id="__next"]/section/section[1]/section/section[2]/div[2]'


class CategoryPageCrawler(BrandPageCrawler):
    """카테고리 페이지 크롤러 (메이크업 등)"""

    def click_load_more_until_done(self):
        """스크롤을 끝까지 내리며 DOM 상품 수가 더 이상 늘지 않을 때까지 대기"""
        import time
        STABLE_THRESHOLD = 7  # 연속 N회 변화 없으면 완료로 판단
        SCROLL_DELAY = 3.0    # 렌더링 대기 시간 (초)

        stable_count = 0
        prev_count = 0
        prev_height = 0

        logger.info("스크롤 기반 전체 상품 로드 시작...")
        while True:
            # 현재 페이지 끝까지 스크롤
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(SCROLL_DELAY)

            current_height = self.driver.execute_script("return document.body.scrollHeight")

            try:
                items = self.driver.find_elements(By.XPATH, f'{PRODUCT_CONTAINER_XPATH}/div')
                current_count = len(items)
            except Exception:
                current_count = prev_count

            if current_count > prev_count or current_height > prev_height:
                logger.info(f"상품 수 증가: {prev_count} → {current_count} (페이지 높이: {current_height})")
                prev_count = current_count
                prev_height = current_height
                stable_count = 0
            else:
                stable_count += 1
                logger.debug(f"변화 없음 ({stable_count}/{STABLE_THRESHOLD}), 현재 {current_count}개")
                if stable_count >= STABLE_THRESHOLD:
                    logger.info(f"상품 수 안정화 완료. 총 {current_count}개 로드됨.")
                    break

    def get_product_links(self) -> List[str]:
        """카테고리 페이지 컨테이너에서 상품 링크 일괄 추출"""
        product_links = []
        try:
            elements = self.driver.find_elements(By.XPATH, f'{PRODUCT_CONTAINER_XPATH}/div/a')
            for element in elements:
                href = element.get_attribute('href')
                if href:
                    full_url = urljoin('https://www.amoremall.com', href)
                    product_links.append(full_url)

            logger.info(f"총 찾은 상품 수: {len(product_links)}")
        except Exception as e:
            logger.error(f"상품 링크 추출 중 오류: {e}")

        return product_links


def main():
    print("=== 메이크업 카테고리 크롤러 ===")
    print(f"URL: {CATEGORY_URL}")
    print()

    crawler = CategoryPageCrawler(urls=[CATEGORY_URL])
    products = crawler.crawl()

    if products:
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
        timestamp = datetime.now().strftime('%y%m%d%H%M')
        filename = f'makeup_category_{timestamp}.jsonl'
        crawler.save_data(products, output_dir=output_dir, filename=filename)
    else:
        print("[WARNING] 수집된 상품이 없습니다.")


if __name__ == '__main__':
    main()
