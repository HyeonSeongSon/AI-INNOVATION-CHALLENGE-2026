"""
아모레몰 상품의 색상 이미지와 색상명을 크롤링하는 스크립트
"""

import json
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException


def setup_driver():
    """Chrome WebDriver 설정"""
    options = webdriver.ChromeOptions()
    # 헤드리스 모드 비활성화 (디버깅용)
    # options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

    driver = webdriver.Chrome(options=options)
    return driver


def crawl_product_colors(url, driver=None):
    """
    상품 페이지에서 색상 정보를 크롤링

    Args:
        url (str): 아모레몰 상품 상세 페이지 URL
        driver (webdriver, optional): 재사용할 WebDriver. None이면 새로 생성

    Returns:
        dict: {
            "url": 상품 URL,
            "colors": [{color_name: ..., image_url: ...}, ...],
            "total_count": 색상 개수
        }
    """
    should_quit = False
    if driver is None:
        driver = setup_driver()
        should_quit = True

    color_data = []
    product_data = {
        "url": url,
        "colors": [],
        "total_count": 0
    }

    try:
        print(f"페이지 접속 중: {url}")
        driver.get(url)

        # 페이지 로딩 대기
        wait = WebDriverWait(driver, 15)

        # 구매하기 버튼 찾기 및 클릭
        print("구매하기 버튼 찾는 중...")
        try:
            # 여러 가능한 버튼 선택자 시도
            buy_button_selectors = [
                "//button[contains(text(), '구매하기')]",
                "//button[contains(@class, 'buy') or contains(@class, 'purchase')]",
                "//*[@id='__next']/section/section[1]/section/div/div/div[1]/div[1]/div[2]/div[6]/button[3]"
            ]

            buy_button = None
            for selector in buy_button_selectors:
                try:
                    buy_button = wait.until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                    print(f"구매하기 버튼 발견: {selector}")
                    break
                except TimeoutException:
                    continue

            if buy_button is None:
                print("구매하기 버튼을 찾을 수 없습니다. 페이지 구조 확인 필요.")
                if should_quit:
                    driver.quit()
                return product_data

            # 버튼 클릭
            driver.execute_script("arguments[0].scrollIntoView(true);", buy_button)
            time.sleep(1)
            driver.execute_script("arguments[0].click();", buy_button)
            print("구매하기 버튼 클릭 완료")

        except Exception as e:
            print(f"구매하기 버튼 클릭 실패: {e}")
            # 스크린샷 저장
            driver.save_screenshot("./error_buy_button.png")
            if should_quit:
                driver.quit()
            return product_data

        # 모달 팝업이 나타날 때까지 대기
        print("모달 팝업 대기 중...")
        time.sleep(2)

        # 색상 선택 영역 찾기
        print("색상 선택 영역 찾는 중...")
        try:
            # 제공된 XPath를 기반으로 ul 요소 찾기
            color_container_xpath = "//*[@id='__next']/section/section[1]/section/div/div/div[1]/div[1]/div[2]/div[6]/section[2]/div[2]/div/div/div[1]/div[1]/div/ul"

            # 더 유연한 선택자도 시도
            color_selectors = [
                color_container_xpath,
                "//ul[contains(@class, 'color') or contains(@class, 'option')]",
                "//div[contains(@class, 'modal') or contains(@class, 'popup')]//ul"
            ]

            color_list = None
            for selector in color_selectors:
                try:
                    color_list = wait.until(
                        EC.presence_of_element_located((By.XPATH, selector))
                    )
                    print(f"색상 목록 발견: {selector}")
                    break
                except TimeoutException:
                    continue

            if color_list is None:
                print("색상 목록을 찾을 수 없습니다.")
                driver.save_screenshot("./error_color_list.png")
                if should_quit:
                    driver.quit()
                return product_data

            # li 요소들 가져오기
            color_items = color_list.find_elements(By.TAG_NAME, "li")
            print(f"총 {len(color_items)}개의 색상 발견")

            # 각 li에서 색상명과 이미지 URL 추출
            for idx, item in enumerate(color_items, 1):
                try:
                    # 이미지 찾기
                    img_element = item.find_element(By.TAG_NAME, "img")
                    img_url = img_element.get_attribute("src")

                    # 색상명 찾기 (alt 속성, title 속성, 또는 텍스트)
                    color_name = (
                        img_element.get_attribute("alt") or
                        img_element.get_attribute("title") or
                        item.text.strip()
                    )

                    # data-* 속성에서도 시도
                    if not color_name:
                        for attr in item.get_property('attributes'):
                            if 'color' in attr.get('name', '').lower():
                                color_name = attr.get('value', '')
                                break

                    # 색상명이 없으면 기본값 사용
                    if not color_name:
                        color_name = f"Color_{idx}"

                    if img_url:
                        color_data.append({
                            "color_name": color_name,
                            "image_url": img_url
                        })
                        print(f"  - {color_name}: {img_url[:80]}...")

                except NoSuchElementException:
                    print(f"색상 항목 {idx}에서 데이터 추출 실패")
                    continue

        except Exception as e:
            print(f"색상 정보 추출 중 오류: {e}")
            driver.save_screenshot("./error_extraction.png")

    except Exception as e:
        print(f"크롤링 중 오류 발생: {e}")
        driver.save_screenshot("./error_general.png")

    finally:
        if should_quit:
            driver.quit()

    product_data["colors"] = color_data
    product_data["total_count"] = len(color_data)
    return product_data


def load_jsonl(input_file):
    """
    JSONL 파일을 읽어서 리스트로 반환

    Args:
        input_file (str): 입력 파일 경로

    Returns:
        list: JSON 객체 리스트
    """
    data = []
    with open(input_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data


def save_jsonl(data_list, output_file):
    """
    리스트를 JSONL 파일로 저장

    Args:
        data_list (list): 저장할 데이터 리스트
        output_file (str): 출력 파일 경로
    """
    with open(output_file, 'w', encoding='utf-8') as f:
        for data in data_list:
            json_line = json.dumps(data, ensure_ascii=False)
            f.write(json_line + '\n')


def crawl_and_merge_from_jsonl(input_file, output_file):
    """
    JSONL 파일에서 URL을 읽어 크롤링하고 결과를 기존 데이터에 병합

    Args:
        input_file (str): 입력 JSONL 파일 경로 (URL이 포함된)
        output_file (str): 출력 JSONL 파일 경로

    Returns:
        list: 병합된 데이터 리스트
    """
    # JSONL 파일 읽기
    print(f"파일 읽는 중: {input_file}")
    products = load_jsonl(input_file)
    print(f"총 {len(products)}개의 상품 발견\n")

    driver = setup_driver()
    updated_products = []

    try:
        for idx, product in enumerate(products, 1):
            print(f"\n{'='*60}")
            print(f"[{idx}/{len(products)}] 상품 크롤링 시작")
            print(f"{'='*60}")

            url = product.get('url')
            if not url:
                print("⚠ URL이 없습니다. 건너뜁니다.")
                updated_products.append(product)
                continue

            # 색상 정보 크롤링
            color_data = crawl_product_colors(url, driver)

            # 기존 데이터에 색상 정보 추가
            product['color_info'] = {
                'colors': color_data['colors'],
                'total_count': color_data['total_count']
            }

            updated_products.append(product)

            print(f"✓ 브랜드: {product.get('브랜드', 'N/A')}")
            print(f"✓ 상품명: {product.get('상품명', 'N/A')}")
            print(f"✓ 색상 개수: {color_data['total_count']}개")

            # 다음 페이지로 이동하기 전 대기
            if idx < len(products):
                time.sleep(2)

    finally:
        driver.quit()

    # 결과를 JSONL 파일로 저장
    print(f"\n결과 저장 중: {output_file}")
    save_jsonl(updated_products, output_file)

    return updated_products


def main():
    """메인 실행 함수"""
    # 입력/출력 파일 경로
    input_file = r"C:\Users\user\Documents\GitHub\AI-INNOVATION-CHALLENGE-2026\data\product_document\product_documents_v2_included_tags.jsonl"
    output_file = "./data/product_document/product_documents_v2_included_tags_with_color_251219.jsonl"

    print("=" * 60)
    print("아모레몰 상품 색상 크롤링 시작")
    print("=" * 60)

    # JSONL 파일에서 URL을 읽어 크롤링하고 병합
    results = crawl_and_merge_from_jsonl(input_file, output_file)

    # 최종 결과 출력
    print("\n" + "=" * 60)
    print("크롤링 완료!")
    print("=" * 60)
    print(f"✓ 저장 위치: {output_file}")
    print(f"✓ 총 상품 수: {len(results)}개")

    # 색상 정보가 있는 상품 통계
    products_with_colors = [r for r in results if r.get('color_info', {}).get('total_count', 0) > 0]
    total_colors = sum(r.get('color_info', {}).get('total_count', 0) for r in results)

    print(f"✓ 색상 정보가 있는 상품: {len(products_with_colors)}개")
    print(f"✓ 총 색상 수: {total_colors}개")

    # 색상 정보가 있는 상품 예시
    if products_with_colors:
        print("\n=== 색상 정보가 있는 상품 예시 (최대 3개) ===")
        for idx, product in enumerate(products_with_colors[:3], 1):
            print(f"{idx}. {product.get('상품명', 'N/A')}")
            print(f"   브랜드: {product.get('브랜드', 'N/A')}")
            print(f"   색상: {product['color_info']['total_count']}개")
            if product['color_info']['colors']:
                print(f"   예시: {product['color_info']['colors'][0]['color_name']}")
            print()


if __name__ == "__main__":
    main()
