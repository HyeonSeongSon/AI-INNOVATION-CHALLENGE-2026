## File Path Rules (Workaround for Claude Code v1.0.111 Bug)

Claude Code has a known bug where file edits fail with "File has been unexpectedly modified" error.
To work around this issue, follow these path rules strictly:

### Path Usage Rules
- When reading or editing a file, **ALWAYS use relative paths.**
- **NEVER use absolute paths.**

### Examples

✅ **CORRECT - Relative Paths:**
```
./src/main.py
./components/Header.tsx
./utils/helpers.js
../config/settings.json
```

❌ **WRONG - Absolute Paths:**
```
C:/Users/username/project/src/main.py
/home/username/project/components/Header.tsx
D:/workspace/myapp/utils/helpers.js
```

### Why This Works
This is a workaround for a known bug in Claude Code v1.0.111 where the Edit tool fails 
when using absolute paths due to file state tracking issues.

**Reference:** https://github.com/anthropics/claude-code/issues/10882
```

### 4단계: 파일 저장

- VS Code: `Ctrl+S` (Windows/Linux) 또는 `Cmd+S` (Mac)
- 또는 메뉴에서 File → Save

### 5단계: Claude Code 재시작

설정을 적용하기 위해 Claude Code를 재시작하세요:

**VS Code 확장 프로그램으로 사용하는 경우:**
1. `Ctrl+Shift+P` (Windows/Linux) 또는 `Cmd+Shift+P` (Mac) - 명령 팔레트 열기
2. "Developer: Reload Window" 입력 후 실행

**CLI로 사용하는 경우:**
1. 현재 실행 중인 Claude Code 세션 종료 (`Ctrl+C`)
2. 다시 시작: `claude`

### 6단계: 동작 확인

Claude Code를 다시 시작한 후, 간단한 파일 편집을 요청해보세요:
```
"./test.txt 파일을 만들고 'Hello World'를 추가해줘"
```

정상적으로 작동하면 설정이 성공적으로 적용된 것입니다.

## 추가 팁

### CLAUDE.md 파일의 역할
- Claude Code는 프로젝트 루트의 `CLAUDE.md` 파일을 자동으로 읽습니다
- 이 파일에 작성된 규칙을 Claude가 따르도록 지시할 수 있습니다
- 프로젝트별 커스텀 지침을 설정하는 용도로도 사용 가능합니다

### 여러 프로젝트가 있는 경우
각 프로젝트의 루트 디렉토리마다 개별적으로 `CLAUDE.md` 파일을 생성해야 합니다.

### 파일 위치 예시
```
my-project/
├── CLAUDE.md          ← 여기에 생성
├── src/
│   └── main.py
├── package.json
└── README.md