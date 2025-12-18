import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
from typing import Optional, Dict, List
import logging
import json
from urllib.parse import urljoin
import re
import os
from datetime import datetime

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BrandPageCrawler:
    """브랜드 페이지 크롤러"""

    def __init__(self, urls: List[str] = None):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        self.urls = urls
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.driver = None
        self.max_products = 20

    def init_driver(self):
        """Selenium WebDriver 초기화"""
        try:
            options = webdriver.ChromeOptions()
            options.add_argument('--start-maximized')
            options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            self.driver = webdriver.Chrome(options=options)
            logger.info("WebDriver 초기화 완료")
        except Exception as e:
            logger.error(f"WebDriver 초기화 실패: {e}")
            return False
        return True

    def fetch_page_selenium(self, url: str) -> Optional[BeautifulSoup]:
        """Selenium으로 동적 페이지 가져오기"""
        try:
            logger.info(f"Selenium Fetching: {url}")
            self.driver.get(url)
            time.sleep(2)
            return BeautifulSoup(self.driver.page_source, 'html.parser')
        except Exception as e:
            logger.error(f"Selenium error: {e}")
            return None

    def get_product_links(self) -> List[str]:
        """XPath를 사용하여 상품 링크 추출 (div[3~8] 패턴 모두 시도)"""
        product_links = []
        try:
            # div[3]부터 div[8]까지 모두 시도
            for div_idx in range(2, 3):
                logger.info(f"div[{div_idx}] 패턴으로 상품 링크 추출 시도...")
                div_product_count = 0

                for i in range(1, self.max_products + 1):
                    xpath = f'//*[@id="__next"]/section/section[1]/section/div[{div_idx}]/div[2]/div[{i}]/a'
                    try:
                        element = self.driver.find_element(By.XPATH, xpath)
                        href = element.get_attribute('href')
                        if href:
                            full_url = urljoin('https://www.amoremall.com', href)
                            product_links.append(full_url)
                            div_product_count += 1
                            logger.info(f"(div[{div_idx}]) 상품 {i} 링크 추출: {full_url}")
                    except Exception as e:
                        logger.debug(f"(div[{div_idx}]) 상품 {i} 링크 추출 실패: {e}")
                        if div_product_count > 0:
                            # 이미 상품을 찾았으면 다음 div로 이동
                            break
                        continue

                if div_product_count > 0:
                    logger.info(f"div[{div_idx}]에서 {div_product_count}개 상품 추출 완료. 다른 div는 생략.")
                    # 성공했으므로 나머지 div는 시도하지 않음
                    break

            logger.info(f"총 찾은 상품 수: {len(product_links)}")
        except Exception as e:
            logger.error(f"상품 링크 추출 중 오류: {e}")

        return product_links

    def scrape_product_detail(self, url: str) -> Dict:
        """상품 상세 페이지에서 정보 추출"""
        try:
            logger.info(f"Selenium Fetching: {url}")
            self.driver.get(url)
            time.sleep(2)

            product_info = {
                'url': url,
                '브랜드': self._extract_brand(),
                '상품명': self._extract_product_name(),
                '별점': self._extract_rating(),
                '리뷰_갯수': self._extract_review_count(),
                '원가': self._extract_original_price(),
                '할인율': self._extract_discount_rate(),
                '판매가': self._extract_sale_price(),
                '상품이미지': self._extract_product_thumbnail_images(),
                '상품상세_이미지': self._extract_product_images(),
                '구매자_통계': self._extract_buyer_age_stats()
            }

            # 원가와 판매가 상호 보완
            original_price = product_info.get('원가')
            sale_price = product_info.get('판매가')

            if original_price is not None and sale_price is None:
                # 원가만 있는 경우 판매가에 원가 채우기
                product_info['판매가'] = original_price
                logger.debug(f"판매가 없음, 원가({original_price})로 채움")
            elif sale_price is not None and original_price is None:
                # 판매가만 있는 경우 원가에 판매가 채우기
                product_info['원가'] = sale_price
                logger.debug(f"원가 없음, 판매가({sale_price})로 채움")

            logger.info(f"상품 정보 추출 완료: {product_info.get('상품명', 'Unknown')}")
            return product_info

        except Exception as e:
            logger.error(f"상품 상세 정보 추출 중 오류: {e}")
            return {}

    def _extract_brand(self) -> str:
        """브랜드명 추출"""
        try:
            xpath = '//*[@id="__next"]/section/section[1]/section/div/div/div[1]/div[1]/div[2]/div[1]/div[2]/div[1]/a'
            element = self.driver.find_element(By.XPATH, xpath)
            return element.text.strip() if element else "N/A"
        except Exception as e:
            logger.debug(f"기본 브랜드 추출 실패, 대체 XPath 시도: {e}")
            try:
                xpath_alt = '//*[@id="__next"]/section/section[1]/section/div/div/div[1]/div[1]/div[2]/div[1]/div/div[1]/a'
                element = self.driver.find_element(By.XPATH, xpath_alt)
                return element.text.strip() if element else "N/A"
            except Exception as e:
                logger.debug(f"대체1 브랜드 추출 실패, 대체2 XPath 시도: {e}")
                try:
                    # 대체 레이아웃: div[2]/div[2]/div[2]//a
                    xpath_alt2 = '//*[@id="__next"]/section/section[1]/section/div/div/div[1]/div[1]/div[2]/div[2]/div[2]//a'
                    element = self.driver.find_element(By.XPATH, xpath_alt2)
                    return element.text.strip() if element else "N/A"
                except Exception as e:
                    logger.debug(f"대체2 브랜드 추출 실패, 대체3 XPath 시도: {e}")
                    try:
                        # 대체 레이아웃3: div[2]/div/div[1]/a
                        xpath_alt3 = '//*[@id="__next"]/section/section[1]/section/div/div/div[1]/div[1]/div[2]/div[2]/div/div[1]/a'
                        element = self.driver.find_element(By.XPATH, xpath_alt3)
                        return element.text.strip() if element else "N/A"
                    except Exception as e:
                        logger.debug(f"브랜드 추출 오류: {e}")
        return "N/A"

    def _extract_product_name(self) -> str:
        """상품명 추출"""
        try:
            xpath = '//*[@id="__next"]/section/section[1]/section/div/div/div[1]/div[1]/div[2]/div[1]/div[2]/div[2]/strong'
            element = self.driver.find_element(By.XPATH, xpath)
            return element.text.strip() if element else "N/A"
        except Exception as e:
            logger.debug(f"기본 상품명 추출 실패, 대체 XPath 시도: {e}")
            try:
                xpath_alt = '//*[@id="__next"]/section/section[1]/section/div/div/div[1]/div[1]/div[2]/div[1]/div/div[2]/strong'
                element = self.driver.find_element(By.XPATH, xpath_alt)
                return element.text.strip() if element else "N/A"
            except Exception as e:
                logger.debug(f"대체1 상품명 추출 실패, 대체2 XPath 시도: {e}")
                try:
                    # 대체 레이아웃: div[2]/div[2]/div[2]//strong
                    xpath_alt2 = '//*[@id="__next"]/section/section[1]/section/div/div/div[1]/div[1]/div[2]/div[2]/div[2]//strong'
                    element = self.driver.find_element(By.XPATH, xpath_alt2)
                    return element.text.strip() if element else "N/A"
                except Exception as e:
                    logger.debug(f"대체2 상품명 추출 실패, 대체3 XPath 시도: {e}")
                    try:
                        # 대체 레이아웃3: div[2]/div/div[2]/strong
                        xpath_alt3 = '//*[@id="__next"]/section/section[1]/section/div/div/div[1]/div[1]/div[2]/div[2]/div/div[2]/strong'
                        element = self.driver.find_element(By.XPATH, xpath_alt3)
                        return element.text.strip() if element else "N/A"
                    except Exception as e:
                        logger.debug(f"상품명 추출 오류: {e}")
        return "N/A"

    def _extract_rating(self):
        """별점 추출 (없으면 None, 있으면 float)"""
        try:
            xpath = '//*[@id="__next"]/section/section[1]/section/div/div/div[1]/div[1]/div[2]/div[2]/button[1]/span[1]/span'
            element = self.driver.find_element(By.XPATH, xpath)
            if element:
                rating_text = element.text.strip()
                return float(rating_text) if rating_text else None
        except Exception as e:
            logger.debug(f"기본 별점 추출 실패, 대체 XPath 시도: {e}")
            try:
                # 대체 레이아웃: div[3]/button[1]/span[1]/span
                xpath_alt = '//*[@id="__next"]/section/section[1]/section/div/div/div[1]/div[1]/div[2]/div[3]/button[1]/span[1]/span'
                element = self.driver.find_element(By.XPATH, xpath_alt)
                if element:
                    rating_text = element.text.strip()
                    return float(rating_text) if rating_text else None
            except Exception as e:
                logger.debug(f"별점 추출 오류: {e}")
        return None

    def _extract_review_count(self) -> int:
        """리뷰 갯수 추출 (없으면 0, 있으면 정수)"""
        try:
            xpath = '//*[@id="__next"]/section/section[1]/section/div/div/div[1]/div[1]/div[2]/div[2]/button[1]/span[3]'
            element = self.driver.find_element(By.XPATH, xpath)
            if element:
                review_text = element.text.strip()
                # '리뷰 ' 텍스트 제거
                review_text = review_text.replace('리뷰 ', '').replace('리뷰', '')
                # 쉼표 제거 후 숫자만 추출
                review_text = review_text.replace(',', '')
                numbers = re.findall(r'\d+', review_text)
                return int(numbers[0]) if numbers else 0
        except Exception as e:
            logger.debug(f"기본 리뷰 갯수 추출 실패, 대체 XPath 시도: {e}")
            try:
                # 대체 레이아웃: div[3]/button[1]/span[3]
                xpath_alt = '//*[@id="__next"]/section/section[1]/section/div/div/div[1]/div[1]/div[2]/div[3]/button[1]/span[3]'
                element = self.driver.find_element(By.XPATH, xpath_alt)
                if element:
                    review_text = element.text.strip()
                    # '리뷰 ' 텍스트 제거
                    review_text = review_text.replace('리뷰 ', '').replace('리뷰', '')
                    # 쉼표 제거 후 숫자만 추출
                    review_text = review_text.replace(',', '')
                    numbers = re.findall(r'\d+', review_text)
                    return int(numbers[0]) if numbers else 0
            except Exception as e:
                logger.debug(f"리뷰 갯수 추출 오류: {e}")
        return 0

    def _extract_original_price(self) -> int:
        """원가 추출 (정수형, 숫자만 추출)"""
        try:
            xpath = '//*[@id="__next"]/section/section[1]/section/div/div/div[1]/div[1]/div[2]/div[3]/div[1]/div[1]'
            element = self.driver.find_element(By.XPATH, xpath)
            if element:
                price_text = element.text.strip()
                # 숫자만 추출
                numbers = re.findall(r'\d+', price_text.replace(',', ''))
                return int(numbers[0]) if numbers else None
        except Exception as e:
            logger.debug(f"기본 원가 추출 실패, 대체 XPath 시도: {e}")
            try:
                # 대체 레이아웃: div[4]/div[1]/div[1]
                xpath_alt = '//*[@id="__next"]/section/section[1]/section/div/div/div[1]/div[1]/div[2]/div[4]/div[1]/div[1]'
                element = self.driver.find_element(By.XPATH, xpath_alt)
                if element:
                    price_text = element.text.strip()
                    # 숫자만 추출
                    numbers = re.findall(r'\d+', price_text.replace(',', ''))
                    return int(numbers[0]) if numbers else None
            except Exception as e:
                logger.debug(f"원가 추출 오류: {e}")
        return None

    def _extract_discount_rate(self) -> int:
        """할인율 추출 (없으면 0, 있으면 정수)"""
        try:
            xpath = '//*[@id="__next"]/section/section[1]/section/div/div/div[1]/div[1]/div[2]/div[3]/div[2]/em'
            element = self.driver.find_element(By.XPATH, xpath)
            if element:
                discount_text = element.text.strip()
                # 숫자만 추출
                numbers = re.findall(r'\d+', discount_text)
                return int(numbers[0]) if numbers else 0
        except Exception as e:
            logger.debug(f"기본 할인율 추출 실패, 대체 XPath 시도: {e}")
            try:
                # 대체 레이아웃: div[4]/div[2]/em
                xpath_alt = '//*[@id="__next"]/section/section[1]/section/div/div/div[1]/div[1]/div[2]/div[4]/div[2]/em'
                element = self.driver.find_element(By.XPATH, xpath_alt)
                if element:
                    discount_text = element.text.strip()
                    # 숫자만 추출
                    numbers = re.findall(r'\d+', discount_text)
                    return int(numbers[0]) if numbers else 0
            except Exception as e:
                logger.debug(f"할인율 추출 오류: {e}")
        return 0

    def _extract_sale_price(self) -> int:
        """판매가 추출 (정수형, 숫자만 추출)"""
        try:
            xpath = '//*[@id="__next"]/section/section[1]/section/div/div/div[1]/div[1]/div[2]/div[3]/div[2]/div[1]/strong'
            element = self.driver.find_element(By.XPATH, xpath)
            if element:
                price_text = element.text.strip()
                # 숫자만 추출
                numbers = re.findall(r'\d+', price_text.replace(',', ''))
                return int(numbers[0]) if numbers else None
        except Exception as e:
            logger.debug(f"기본 판매가 추출 실패, 대체1 XPath 시도: {e}")
            try:
                xpath_alt = '//*[@id="__next"]/section/section[1]/section/div/div/div[1]/div[1]/div[2]/div[2]/div/div[1]/strong'
                element = self.driver.find_element(By.XPATH, xpath_alt)
                if element:
                    price_text = element.text.strip()
                    # 숫자만 추출
                    numbers = re.findall(r'\d+', price_text.replace(',', ''))
                    return int(numbers[0]) if numbers else None
            except Exception as e:
                logger.debug(f"대체1 판매가 추출 실패, 대체2 XPath 시도: {e}")
                try:
                    # 대체 레이아웃: div[4]/div[2]/div[1]/strong
                    xpath_alt2 = '//*[@id="__next"]/section/section[1]/section/div/div/div[1]/div[1]/div[2]/div[4]/div[2]/div[1]/strong'
                    element = self.driver.find_element(By.XPATH, xpath_alt2)
                    if element:
                        price_text = element.text.strip()
                        # 숫자만 추출
                        numbers = re.findall(r'\d+', price_text.replace(',', ''))
                        return int(numbers[0]) if numbers else None
                except Exception as e:
                    logger.debug(f"판매가 추출 오류: {e}")
        return None

    def _extract_product_thumbnail_images(self) -> List[str]:
        """상품 썸네일 이미지 추출 (중복 제거)"""
        images = []
        seen_urls = set()
        try:
            # 부모 요소 내의 모든 div 자식 요소 찾기
            parent_xpath = '//*[@id="__next"]/section/section[1]/section/div/div/div[1]/div[1]/div[1]/div/div/div[1]'
            parent_element = self.driver.find_element(By.XPATH, parent_xpath)

            # 자식 div 요소들 찾기
            child_divs = parent_element.find_elements(By.XPATH, './div')

            for idx, child_div in enumerate(child_divs, 1):
                try:
                    # 각 div 내의 img 또는 picture/img 찾기
                    img_element = None
                    try:
                        img_element = child_div.find_element(By.XPATH, './/picture/img')
                    except:
                        img_element = child_div.find_element(By.XPATH, './/img')

                    if img_element:
                        img_url = img_element.get_attribute('src') or img_element.get_attribute('data-src')
                        if img_url and img_url not in seen_urls:
                            images.append(img_url)
                            seen_urls.add(img_url)
                            logger.debug(f"상품이미지 {idx} 추출: {img_url}")
                        elif img_url in seen_urls:
                            logger.debug(f"상품이미지 {idx} 중복 제거: {img_url}")
                except Exception as e:
                    logger.debug(f"상품이미지 {idx} 추출 실패: {e}")
                    continue
        except Exception as e:
            logger.debug(f"상품 썸네일 이미지 추출 오류: {e}")

        return images

    def _extract_product_images(self) -> List[str]:
        """상품 상세 이미지 추출 (버튼 클릭 후 나타나는 섹션 내부 이미지만 수집)"""
        logger.info("=== 상품 상세 이미지 추출 시작 ===")
        images = []

        try:
            # 1단계: 상세 이미지 버튼 클릭
            button_xpath = '//*[@id="productDesc"]/section/div/div[1]/div/button'
            try:
                logger.info("[1단계] 버튼 클릭...")
                button_element = self.driver.find_element(By.XPATH, button_xpath)
                self.driver.execute_script("arguments[0].click();", button_element)
                logger.info("✓ 버튼 클릭 완료")

                # 상세 이미지 영역이 DOM에 추가될 때까지 대기
                try:
                    wait = WebDriverWait(self.driver, 15)
                    # div[2]/div[2] 영역이 나타날 때까지 대기
                    detail_area = wait.until(
                        EC.presence_of_element_located((By.XPATH, '//*[@id="productDesc"]/section/div/div[1]/div[2]/div[2]'))
                    )
                    logger.info("✓ 상세 이미지 영역 (div[2]/div[2]) DOM에 존재")

                    # 영역이 완전히 렌더링될 때까지 충분히 대기
                    time.sleep(5)

                    # 스크롤하여 모든 이미지가 로드되도록 함
                    try:
                        self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", detail_area)
                        time.sleep(3)
                    except:
                        pass

                except Exception as e:
                    logger.warning(f"상세 이미지 영역 대기 실패: {e}")
                    time.sleep(5)

            except Exception as e:
                logger.warning(f"버튼 클릭 실패 (이미 열려있을 수 있음): {e}")
                time.sleep(2)

            # 2단계: 버튼 클릭 후 나타난 섹션 내부의 이미지만 수집
            logger.info("[2단계] 상세 이미지 섹션 내부 이미지 수집...")

            # 여러 경로 패턴을 순차적으로 시도
            possible_xpaths = [
                ('//*[@id="productDesc"]/section/div/div[1]/div[2]/div[2]', 'div[2]/div[2]'),  # 기존 경로
                ('//*[@id="productDesc"]/section/div/div[1]/div/div[2]/div[1]', 'div/div[2]/div[1]'),  # 새 경로
            ]

            parent_element = None
            found_path = None
            img_elements = []

            # 각 경로를 순차적으로 시도
            for xpath, path_desc in possible_xpaths:
                try:
                    logger.info(f"경로 시도: {path_desc}")
                    temp_element = self.driver.find_element(By.XPATH, xpath)

                    # 스크롤하여 lazy loading 이미지 로드
                    try:
                        self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'start'});", temp_element)
                        time.sleep(2)
                        # 스크롤을 아래로 천천히 내려서 모든 이미지 로드
                        self.driver.execute_script("""
                            var element = arguments[0];
                            var scrollHeight = element.scrollHeight;
                            element.scrollBy(0, scrollHeight / 2);
                        """, temp_element)
                        time.sleep(2)
                    except:
                        logger.debug("스크롤 실패, 계속 진행...")

                    # 하위의 모든 img 태그 찾기 (p 태그 안의 img도 포함)
                    temp_img_elements = temp_element.find_elements(By.XPATH, './/img')

                    if temp_img_elements:
                        parent_element = temp_element
                        img_elements = temp_img_elements
                        found_path = path_desc
                        logger.info(f"✓ 상세 이미지 영역 ({path_desc}) 발견")
                        logger.info(f"{path_desc} 영역에서 {len(img_elements)}개의 img 태그 발견")

                        # 디버깅: contenteditor-image 클래스도 확인
                        try:
                            contenteditor_divs = parent_element.find_elements(By.CLASS_NAME, 'contenteditor-image')
                            logger.info(f"  - contenteditor-image 클래스: {len(contenteditor_divs)}개 발견")
                        except:
                            pass

                        break  # 이미지를 찾았으므로 더 이상 시도하지 않음
                    else:
                        logger.debug(f"{path_desc} 경로에 img 없음, 다음 경로 시도...")

                except Exception as e:
                    logger.debug(f"{path_desc} 경로 실패: {e}, 다음 경로 시도...")
                    continue

            # 모든 경로에서 이미지를 찾지 못한 경우
            if not img_elements:
                logger.warning("모든 경로에서 img 태그를 찾지 못함")
            else:
                # 이미지 처리 시작
                for idx, img in enumerate(img_elements, 1):
                    try:
                        # 모든 가능한 속성에서 이미지 URL 찾기
                        possible_attrs = ['src', 'data-src', 'data-original', 'data-lazy-src',
                                        'data-img-src', 'srcset', 'data-srcset']

                        img_url = None
                        found_attr = None
                        all_attrs = {}  # 디버깅용: 모든 속성 저장

                        for attr in possible_attrs:
                            value = img.get_attribute(attr)
                            if value:
                                all_attrs[attr] = value[:100]  # 처음 100자만 저장
                                if not img_url:  # 첫 번째로 발견된 값만 사용
                                    # srcset인 경우 첫 번째 URL만 추출
                                    if 'srcset' in attr and ' ' in value:
                                        value = value.split(' ')[0].split(',')[0]

                                    img_url = value
                                    found_attr = attr

                        # 디버깅: 상세 정보 출력
                        logger.info(f"  === 이미지 {idx} ===")
                        logger.info(f"  found_attr: {found_attr}")
                        logger.info(f"  all_attrs: {all_attrs}")

                        # URL이 있으면 수집
                        if img_url and img_url.startswith('http'):
                            if img_url not in images:
                                images.append(img_url)
                                logger.info(f"  ✓✓✓ 수집 성공 [{idx}]: {img_url}")
                            else:
                                logger.debug(f"  - 중복 제거 [{idx}]: {img_url[:80]}...")
                        else:
                            logger.warning(f"  ✗✗✗ 유효한 URL 없음 [{idx}]: img_url={img_url}")
                            # 디버깅: outerHTML 일부 출력
                            outer_html = img.get_attribute('outerHTML')
                            if outer_html:
                                logger.warning(f"  outerHTML: {outer_html[:300]}...")

                    except Exception as e:
                        logger.warning(f"이미지 {idx} 처리 실패: {e}")

                if images:
                    logger.info(f"✓ 총 {len(images)}개의 상세 이미지 수집 완료 (경로: {found_path})")
                    return images
                else:
                    logger.warning("이미지 URL 수집 실패")

            # 3단계: 모든 경로 실패 시 폴백
            if not images:
                logger.warning("모든 경로에서 이미지 수집 실패. 폴백 방식으로 시도...")
                return self._extract_product_images_fallback()

        except Exception as e:
            logger.error(f"상품 상세이미지 추출 중 예외 발생: {e}")
            return self._extract_product_images_fallback()

        logger.info(f"=== 상품 상세 이미지 추출 완료: 총 {len(images)}개 ===")
        return images

    def _extract_product_images_fallback(self) -> List[str]:
        """상품 상세 이미지 추출 - 기존 방식 (폴백)"""
        images = []
        seen_urls = set()
        try:
            # 기본 XPath로 시도
            xpath = '//*[@id="swiper-wrapper-ae2a1cb102a3dbe18"]/div/div/picture/img'
            elements = self.driver.find_elements(By.XPATH, xpath)

            if elements:
                for element in elements:
                    img_url = element.get_attribute('src') or element.get_attribute('data-src')
                    if img_url and img_url not in seen_urls:
                        images.append(img_url)
                        seen_urls.add(img_url)
                        logger.debug(f"상세이미지(fallback) 추출: {img_url}")
            else:
                logger.debug(f"기본 상세이미지 위치에서 찾을 수 없음, 대체 XPath 시도")
                # 대체 XPath 1: 직접 img 태그
                try:
                    parent_xpath = '//*[@id="productDesc"]/section/div/div[1]/div/div[2]/div[1]/div/div'
                    parent_element = self.driver.find_element(By.XPATH, parent_xpath)

                    # 부모 내의 모든 img 태그 찾기
                    img_elements = parent_element.find_elements(By.XPATH, './/img')

                    if img_elements:
                        for idx, element in enumerate(img_elements, 1):
                            img_url = element.get_attribute('src') or element.get_attribute('data-src')
                            if img_url and img_url not in seen_urls:
                                images.append(img_url)
                                seen_urls.add(img_url)
                                logger.debug(f"상세이미지(fallback) {idx} 추출: {img_url}")
                            elif img_url in seen_urls:
                                logger.debug(f"상세이미지(fallback) {idx} 중복 제거: {img_url}")
                    else:
                        logger.debug(f"직접 img 태그에서 찾을 수 없음, 대체 XPath 2 시도")
                        # 대체 XPath 2: div 내부의 img 태그들
                        nested_parent_xpath = '//*[@id="productDesc"]/section/div/div[1]/div/div[2]/div[1]/div/div'
                        nested_parent_element = self.driver.find_element(By.XPATH, nested_parent_xpath)

                        # div 내의 모든 img 태그 찾기 (.//div//img)
                        nested_img_elements = nested_parent_element.find_elements(By.XPATH, './/div//img')

                        for idx, element in enumerate(nested_img_elements, 1):
                            img_url = element.get_attribute('src') or element.get_attribute('data-src')
                            if img_url and img_url not in seen_urls:
                                images.append(img_url)
                                seen_urls.add(img_url)
                                logger.debug(f"상세이미지(fallback-nested) {idx} 추출: {img_url}")
                            elif img_url in seen_urls:
                                logger.debug(f"상세이미지(fallback-nested) {idx} 중복 제거: {img_url}")
                except Exception as e:
                    logger.debug(f"대체 XPath 추출 오류: {e}")
        except Exception as e:
            logger.debug(f"폴백 방식 상품 상세이미지 추출 오류: {e}")

        return images

    def _extract_buyer_age_stats(self) -> Dict[str, Dict[str, int]]:
        """구매자 연령대 및 피부타입 통계 추출

        Returns:
            dict: {
                '연령대별': {'10대 이하': 0, '20대': 5, ...},
                '피부타입별': {'복합성': 34, '건성': 30, ...}
            }
            또는 탭이 없는 경우:
            dict: {'연령대별': {'10대 이하': 0, '20대': 5, ...}}
        """
        try:
            # div[2] 영역 전체
            div2_xpath = '//*[@id="productDesc"]/section/div/div[2]'
            div2_element = self.driver.find_element(By.XPATH, div2_xpath)

            # listHeader에서 탭 버튼 찾기
            try:
                header = div2_element.find_element(By.CLASS_NAME, 'listHeader')
                tabs = header.find_elements(By.CLASS_NAME, 'btnTab')

                if len(tabs) > 0:
                    # 탭이 있는 경우: 각 탭 클릭하고 데이터 수집
                    logger.debug(f"탭이 {len(tabs)}개 발견됨. 탭별 데이터 추출 시작")
                    all_data = {}

                    for tab in tabs:
                        tab_text = tab.text.strip()
                        logger.debug(f"'{tab_text}' 탭 클릭")

                        # 탭 클릭
                        self.driver.execute_script("arguments[0].click();", tab)
                        time.sleep(0.5)  # 데이터 로딩 대기

                        # 차트 데이터 추출
                        chart_wrap = div2_element.find_element(By.CLASS_NAME, 'chartWrap')
                        chart_text = chart_wrap.text
                        lines = [line.strip() for line in chart_text.split('\n') if line.strip()]

                        # 방법 1: "카테고리 XX%" 형식 파싱 (피부타입별 등)
                        pattern1 = {}
                        for line in lines:
                            match = re.match(r'(.+?)\s+(\d+%)$', line)
                            if match:
                                category = match.group(1).strip()
                                percentage = int(match.group(2).replace('%', ''))
                                pattern1[category] = percentage

                        if pattern1:
                            all_data[tab_text] = pattern1
                            logger.debug(f"'{tab_text}' 데이터 추출 완료: {pattern1}")
                        else:
                            # 방법 2: 퍼센티지와 카테고리 분리 (연령대별 등)
                            percentages = [line for line in lines if re.match(r'\d+%$', line)]
                            categories = [line for line in lines if not re.match(r'\d+%$', line) and line != tab_text]

                            if len(percentages) == len(categories):
                                pattern2 = {}
                                for i in range(len(categories)):
                                    pattern2[categories[i]] = int(percentages[i].replace('%', ''))
                                all_data[tab_text] = pattern2
                                logger.debug(f"'{tab_text}' 데이터 추출 완료: {pattern2}")
                            else:
                                logger.debug(f"'{tab_text}' 데이터 매칭 실패")

                    return all_data if all_data else None

            except Exception as e:
                logger.debug(f"탭 버튼 없음: {e}")

            # 탭이 없는 경우: 기존 방식으로 단일 차트 추출
            logger.debug("탭 없음. 기존 방식으로 차트 데이터 추출 시도")
            try:
                chart_xpath = '//*[@id="productDesc"]/section/div/div[2]/div[2]'
                chart_element = self.driver.find_element(By.XPATH, chart_xpath)

                chart_text = chart_element.text
                lines = [line.strip() for line in chart_text.split('\n') if line.strip()]

                # 퍼센티지와 연령대 분리
                percentages = []
                age_groups = []

                for line in lines:
                    if re.match(r'\d+%$', line):
                        percentages.append(line)
                    elif any(keyword in line for keyword in ['대', '미만', '이상', '이하']):
                        age_groups.append(line)

                # 딕셔너리로 매칭
                if len(percentages) == len(age_groups):
                    result = {}
                    for i in range(len(age_groups)):
                        result[age_groups[i]] = int(percentages[i].replace('%', ''))
                    logger.debug(f"연령대 통계 추출 완료: {result}")
                    return {'연령대별': result}
                else:
                    logger.debug(f"연령대 통계 매칭 실패: 퍼센티지 {len(percentages)}개, 연령대 {len(age_groups)}개")
                    return None

            except Exception as e:
                logger.debug(f"기존 방식 차트 추출 오류: {e}")
                return None

        except Exception as e:
            logger.debug(f"구매자 통계 추출 오류: {e}")
            return None

    def parse_content(self) -> List[Dict]:
        """상품 링크 추출 및 상세정보 크롤링"""
        products = []
        product_links = self.get_product_links()

        for idx, link in enumerate(product_links, 1):
            logger.info(f"상품 {idx}/{len(product_links)} 처리 중...")
            product_info = self.scrape_product_detail(link)
            if product_info:
                products.append(product_info)
            time.sleep(1)

        return products

    def crawl(self) -> List[Dict]:
        """메인 크롤링 함수 - 여러 URL 크롤링"""
        logger.info(f"크롤링 시작... (총 {len(self.urls)}개 URL)")

        if not self.init_driver():
            return []

        all_products = []

        try:
            for idx, url in enumerate(self.urls, 1):
                logger.info(f"URL {idx}/{len(self.urls)} 처리 중: {url}")
                try:
                    self.driver.get(url)
                    time.sleep(3)

                    products = self.parse_content()
                    all_products.extend(products)

                    logger.info(f"URL {idx} 크롤링 완료 ({len(products)}개 상품)")
                except Exception as e:
                    logger.error(f"URL {idx} 크롤링 중 오류: {e}")
                    continue

                time.sleep(2)  # URL 간 대기

            logger.info("전체 크롤링 완료")
            return all_products

        finally:
            if self.driver:
                self.driver.quit()

    def save_data(self, data: List[Dict], output_dir: str = None, filename: str = None):
        """데이터를 JSONL 형식으로 저장

        Args:
            data: 저장할 데이터 리스트
            output_dir: 출력 디렉토리 경로 (기본값: ../data/crawling_result)
            filename: 파일명 (기본값: product_crawling_YYMMDDHHMM.jsonl)
        """
        try:
            # 기본 출력 디렉토리 설정
            if output_dir is None:
                # 프로젝트 루트 기준으로 경로 설정
                project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                output_dir = os.path.join(project_root, 'data', 'crawling_result')

            # 디렉토리가 없으면 생성
            os.makedirs(output_dir, exist_ok=True)

            # 파일명 생성 (YYMMDDHHMM 형식)
            if filename is None:
                timestamp = datetime.now().strftime('%y%m%d%H%M')
                filename = f'product_crawling_{timestamp}.jsonl'

            # 전체 경로 생성
            filepath = os.path.join(output_dir, filename)

            # 데이터 저장
            with open(filepath, 'w', encoding='utf-8') as f:
                for item in data:
                    json.dump(item, f, ensure_ascii=False)
                    f.write('\n')

            logger.info(f"데이터가 저장되었습니다")
            logger.info(f"  - 파일 경로: {filepath}")
            logger.info(f"  - 상품 수: {len(data)}개")
            print(f"\n[SUCCESS] 저장 완료!")
            print(f"  파일 위치: {filepath}")
            print(f"  상품 수: {len(data)}개")

        except Exception as e:
            logger.error(f"데이터 저장 중 오류: {e}")
            print(f"\n[ERROR] 저장 실패: {e}")


def main():
    """메인 실행 함수"""
    # JSON 파일에서 URL 리스트 로드
    json_path = os.path.join(os.path.dirname(__file__), 'brand_home_url.json')

    try:
        logger.info(f"JSON 파일 로드 중: {json_path}")
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            urls = data.get('brand_home_urls', [])

        if not urls:
            print(f"경고: {json_path}에 brand_home_urls가 비어있거나 존재하지 않습니다.")
            logger.error("URL 리스트가 비어있음")
            return

        print("=== 브랜드 페이지 크롤러 ===")
        print(f"JSON 파일에서 {len(urls)}개의 URL을 로드했습니다.")
        print(f"파일 경로: {json_path}")
        print()

    except FileNotFoundError:
        print(f"오류: {json_path} 파일을 찾을 수 없습니다.")
        logger.error(f"JSON 파일을 찾을 수 없음: {json_path}")
        return
    except json.JSONDecodeError as e:
        print(f"오류: JSON 파일 파싱 실패: {e}")
        logger.error(f"JSON 파싱 오류: {e}")
        return
    except Exception as e:
        print(f"오류: URL 로드 중 예외 발생: {e}")
        logger.error(f"URL 로드 중 예외: {e}")
        return

    crawler = BrandPageCrawler(urls)
    products = crawler.crawl()

    if products:
        print(f"\n크롤링 완료: {len(products)}개 상품 정보 수집")
        print("\n첫 번째 상품:")
        print(json.dumps(products[0], ensure_ascii=False, indent=2))
        crawler.save_data(products)
    else:
        print("데이터를 가져올 수 없습니다")


if __name__ == "__main__":
    main()