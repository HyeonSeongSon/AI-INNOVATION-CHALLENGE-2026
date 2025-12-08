import easyocr
import cv2
import numpy as np
from PIL import Image
import requests
from io import BytesIO
import os
from datetime import datetime

class URLImageOCR:
    """URL 이미지에서 OCR 수행"""
    
    def __init__(self, use_gpu=True):
        """
        초기화
        
        Args:
            use_gpu: GPU 사용 여부
        """
        print("EasyOCR 초기화 중...")
        self.reader = easyocr.Reader(
            ['ko', 'en'],  # 한글 + 영어
            gpu=use_gpu,
            verbose=False
        )
        print("✅ 초기화 완료!\n")
    
    def download_image(self, image_url):
        """
        URL에서 이미지 다운로드
        
        Args:
            image_url: 이미지 URL
        
        Returns:
            PIL Image 객체
        """
        try:
            print(f"이미지 다운로드 중: {image_url[:50]}...")
            
            # User-Agent 헤더 추가 (일부 사이트에서 필요)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(image_url, headers=headers, timeout=10)
            response.raise_for_status()
            
            # 이미지로 변환
            img = Image.open(BytesIO(response.content))
            
            print(f"✅ 다운로드 완료 (크기: {img.size})")
            
            return img
        
        except requests.exceptions.RequestException as e:
            print(f"❌ 다운로드 실패: {e}")
            return None
        except Exception as e:
            print(f"❌ 이미지 처리 실패: {e}")
            return None
    
    def preprocess_image(self, img):
        """
        이미지 전처리 (선택적)
        
        Args:
            img: PIL Image 또는 numpy array
        
        Returns:
            전처리된 numpy array
        """
        # PIL Image → numpy array
        if isinstance(img, Image.Image):
            img_array = np.array(img)
        else:
            img_array = img
        
        # RGB로 변환 (필요시)
        if len(img_array.shape) == 2:  # 그레이스케일
            img_array = cv2.cvtColor(img_array, cv2.COLOR_GRAY2RGB)
        elif img_array.shape[2] == 4:  # RGBA
            img_array = cv2.cvtColor(img_array, cv2.COLOR_RGBA2RGB)
        
        # 대비 향상 (CLAHE)
        lab = cv2.cvtColor(img_array, cv2.COLOR_RGB2LAB)
        l, a, b = cv2.split(lab)
        
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        l = clahe.apply(l)
        
        enhanced = cv2.merge([l, a, b])
        enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2RGB)
        
        return enhanced
    
    def extract_text(self, image_url, save_image=True, use_preprocess=True):
        """
        URL 이미지에서 텍스트 추출
        
        Args:
            image_url: 이미지 URL
            save_image: 이미지 로컬 저장 여부
            use_preprocess: 전처리 사용 여부
        
        Returns:
            추출된 텍스트 리스트
        """
        # 1. 이미지 다운로드
        img = self.download_image(image_url)
        
        if img is None:
            return None
        
        # 2. 이미지 저장 (선택)
        saved_path = None
        if save_image:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            saved_path = f"downloaded_{timestamp}.png"
            img.save(saved_path)
            print(f"💾 이미지 저장: {saved_path}")
        
        # 3. 전처리 (선택)
        img_array = np.array(img)
        
        if use_preprocess:
            print("🔧 이미지 전처리 중...")
            img_array = self.preprocess_image(img_array)
            
            if save_image:
                preprocessed_path = f"preprocessed_{timestamp}.png"
                Image.fromarray(img_array).save(preprocessed_path)
                print(f"💾 전처리 이미지 저장: {preprocessed_path}")
        
        # 4. OCR 실행
        print("🔍 OCR 수행 중...\n")
        
        results = self.reader.readtext(
            img_array,
            paragraph=False,
            detail=1
        )
        
        if not results:
            print("❌ 텍스트를 찾을 수 없습니다.")
            return []
        
        # 5. 결과 정리
        print(f"✅ {len(results)}개 텍스트 발견!\n")
        print("=" * 60)
        print("추출 결과")
        print("=" * 60)
        
        extracted_texts = []
        
        for i, detection in enumerate(results, 1):
            box = detection[0]
            text = detection[1]
            confidence = detection[2]
            
            extracted_texts.append({
                'text': text,
                'confidence': confidence,
                'box': box
            })
            
            print(f"{i}. {text}")
            print(f"   신뢰도: {confidence:.3f} ({confidence*100:.1f}%)")
            print(f"   위치: {box[0]} ~ {box[2]}")
            print()
        
        # 6. 텍스트 파일로 저장
        if save_image:
            txt_path = f"ocr_result_{timestamp}.txt"
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(f"OCR 추출 결과\n")
                f.write(f"이미지 URL: {image_url}\n")
                f.write(f"추출 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 60 + "\n\n")
                
                for i, item in enumerate(extracted_texts, 1):
                    f.write(f"{i}. {item['text']}\n")
                    f.write(f"   신뢰도: {item['confidence']:.3f}\n\n")
            
            print(f"💾 결과 저장: {txt_path}")
        
        return extracted_texts
    
    def batch_extract_from_urls(self, url_list, output_file='batch_ocr_results.txt'):
        """
        여러 URL에서 일괄 OCR 수행
        
        Args:
            url_list: 이미지 URL 리스트
            output_file: 결과 저장 파일
        """
        print(f"\n{'='*60}")
        print(f"배치 OCR 시작 (총 {len(url_list)}개)")
        print(f"{'='*60}\n")
        
        all_results = []
        
        for i, url in enumerate(url_list, 1):
            print(f"\n[{i}/{len(url_list)}] 처리 중...")
            print(f"URL: {url[:50]}...")
            print("-" * 60)
            
            texts = self.extract_text(url, save_image=True, use_preprocess=True)
            
            all_results.append({
                'url': url,
                'texts': texts if texts else []
            })
            
            print()
        
        # 전체 결과 저장
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("배치 OCR 추출 결과\n")
            f.write(f"처리 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 60 + "\n\n")
            
            for i, result in enumerate(all_results, 1):
                f.write(f"[{i}] {result['url']}\n")
                f.write("-" * 60 + "\n")
                
                if result['texts']:
                    for j, item in enumerate(result['texts'], 1):
                        f.write(f"{j}. {item['text']} (신뢰도: {item['confidence']:.3f})\n")
                else:
                    f.write("(텍스트 없음)\n")
                
                f.write("\n\n")
        
        print(f"\n{'='*60}")
        print(f"✅ 배치 처리 완료!")
        print(f"💾 전체 결과 저장: {output_file}")
        print(f"{'='*60}")
        
        # 통계
        success_count = sum(1 for r in all_results if r['texts'])
        total_texts = sum(len(r['texts']) for r in all_results)
        
        print(f"\n📊 통계:")
        print(f"  총 이미지: {len(all_results)}개")
        print(f"  성공: {success_count}개")
        print(f"  실패: {len(all_results) - success_count}개")
        print(f"  추출된 텍스트: 총 {total_texts}개")
        
        return all_results


def main():
    """메인 함수"""
    
    print("=" * 60)
    print("이미지 URL OCR 추출 프로그램")
    print("=" * 60)
    print()
    
    # OCR 객체 생성
    ocr = URLImageOCR(use_gpu=True)
    
    # 사용 방법 선택
    print("사용 방법을 선택하세요:")
    print("1. 단일 URL 입력")
    print("2. 여러 URL 입력 (배치)")
    print("3. 종료")
    print()
    
    choice = input("선택 (1/2/3): ").strip()
    
    if choice == '1':
        # 단일 URL
        print("\n" + "-" * 60)
        image_url = input("이미지 URL 입력: ").strip()
        
        if not image_url:
            print("❌ URL을 입력해주세요.")
            return
        
        print("-" * 60)
        print()
        
        # OCR 수행
        results = ocr.extract_text(
            image_url, 
            save_image=True, 
            use_preprocess=True
        )
        
        if results:
            print("\n✅ OCR 완료!")
            print(f"추출된 텍스트: {len(results)}개")
    
    elif choice == '2':
        # 배치 URL
        print("\n" + "-" * 60)
        print("이미지 URL을 한 줄씩 입력하세요 (빈 줄 입력 시 종료):")
        print("-" * 60)
        
        urls = []
        while True:
            url = input(f"URL {len(urls)+1}: ").strip()
            if not url:
                break
            urls.append(url)
        
        if not urls:
            print("❌ URL을 입력해주세요.")
            return
        
        print(f"\n총 {len(urls)}개 URL 입력됨")
        confirm = input("OCR을 시작하시겠습니까? (y/n): ").strip().lower()
        
        if confirm == 'y':
            ocr.batch_extract_from_urls(urls)
    
    elif choice == '3':
        print("프로그램을 종료합니다.")
        return
    
    else:
        print("❌ 잘못된 선택입니다.")


# 예시 코드 (직접 사용)
def example_usage():
    """예시 사용법"""
    
    # OCR 객체 생성
    ocr = URLImageOCR(use_gpu=True)
    
    # 예시 1: 단일 이미지 URL
    image_url = "https://example.com/cosmetic_ad.jpg"
    
    results = ocr.extract_text(
        image_url,
        save_image=True,      # 이미지 저장
        use_preprocess=True   # 전처리 사용
    )
    
    # 결과 활용
    if results:
        for item in results:
            print(f"텍스트: {item['text']}")
            print(f"신뢰도: {item['confidence']:.2f}")
    
    # 예시 2: 여러 URL 배치 처리
    urls = [
        "https://example.com/image1.jpg",
    ]
    
    all_results = ocr.batch_extract_from_urls(urls, 'results.txt')


if __name__ == "__main__":
    # 대화형 모드
    main()
    
    # 또는 직접 코드 작성
    # example_usage()
