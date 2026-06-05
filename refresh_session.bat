@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo ============================================
echo  네이버 밴드 세션 자동 갱신
echo ============================================
echo.
echo  1) 잠시 후 크롬 창이 뜨고 밴드 로그인 화면이 나옵니다
echo  2) 평소처럼 밴드(네이버)에 다시 로그인하세요
echo  3) 로그인이 끝나면 이 검은 창으로 돌아와서
echo     [로그인 완료 후 Enter] 표시에 Enter를 누르세요
echo.
pause

python make_band_session.py
if errorlevel 1 (
    echo.
    echo [실패] 세션 생성이 되지 않았습니다.
    echo  - Python이 설치되어 있는지 확인
    echo  - 처음 설치 시: python -m pip install -r requirements.txt
    pause
    exit /b 1
)

if not exist band_storage_state.json (
    echo.
    echo [실패] band_storage_state.json 파일이 만들어지지 않았습니다.
    pause
    exit /b 1
)

echo.
echo 새 세션을 클립보드에 복사하는 중...
powershell -NoProfile -Command "Get-Content -LiteralPath '%~dp0band_storage_state.json' -Raw | Set-Clipboard"
if errorlevel 1 (
    echo [경고] 클립보드 복사 실패. 메모장을 엽니다 - 수동 복사(Ctrl+A, Ctrl+C) 하세요.
    notepad band_storage_state.json
) else (
    echo ✓ 클립보드 복사 완료
)

echo.
echo GitHub Secrets 페이지를 엽니다...
start "" "https://github.com/dlalxp-droid/giseong/settings/secrets/actions"

echo.
echo ============================================
echo  다음 단계 (방금 열린 GitHub 페이지에서)
echo ============================================
echo   1. BAND_STORAGE_STATE_JSON 항목 클릭
 echo   2. 연필 모양(Update) 버튼 클릭
echo   3. 기존 값 전체선택(Ctrl+A) 후 삭제
echo   4. 붙여넣기 (Ctrl+V)
echo   5. [Update secret] 버튼 클릭
echo.
echo 모두 끝나면 이 창을 닫으세요.
pause
