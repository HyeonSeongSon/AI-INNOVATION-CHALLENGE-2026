# Project Guidelines

## Python 파일 실행 규칙

- Windows에서 Python 스크립트를 실행할 때 stdout을 파일로 리다이렉션하는 경우
  반드시 `PYTHONIOENCODING=utf-8` 환경변수를 설정할 것
  ```bash
  PYTHONIOENCODING=utf-8 python script.py > output.txt
  ```
- 스크립트 내부에서 stdout을 파일로 리다이렉션하거나 한글 출력이 있는 경우
  스크립트 상단(`import sys` 직후)에 추가:
  ```python
  sys.stdout.reconfigure(encoding='utf-8')
  ```
- 파일을 열어 쓸 때는 항상 `encoding="utf-8"` 명시:
  ```python
  open(path, "w", encoding="utf-8")
  ```

## 환경 정보

- Python 3.11: `C:\Users\user\AppData\Local\Programs\Python\Python311\python.exe`
- pip 설치 시 `python -m pip` 사용 (conda 환경 충돌 방지)
- Windows에서 `cd` 사용 시 경로를 항상 따옴표로 감쌀 것: `cd "c:\path\to\dir"`
