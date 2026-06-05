@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo ============================================
echo  Naver Band Session Refresh
echo ============================================
echo.
echo  1) A Chrome window will open shortly
echo  2) Log in to Band as usual in that window
echo  3) When login is done, return to this black
 echo     window and press Enter at the prompt
echo.
pause

python make_band_session.py
if errorlevel 1 (
    echo.
    echo [FAILED] Session creation failed.
    echo  - Check Python is installed and on PATH
    echo  - First-time setup, run these once in cmd:
    echo      python -m pip install -r requirements.txt
    echo      python -m playwright install chromium
    pause
    exit /b 1
)

if not exist band_storage_state.json (
    echo.
    echo [FAILED] band_storage_state.json was not created.
    pause
    exit /b 1
)

echo.
echo Copying new session to clipboard...
powershell -NoProfile -Command "Get-Content -LiteralPath '%~dp0band_storage_state.json' -Raw | Set-Clipboard"
if errorlevel 1 (
    echo [WARN] Clipboard copy failed. Opening Notepad for manual copy.
    notepad band_storage_state.json
) else (
    echo [OK] Copied to clipboard
)

echo.
echo Opening GitHub Secrets page in your browser...
start "" "https://github.com/dlalxp-droid/giseong/settings/secrets/actions"

echo.
echo ============================================
echo  Next steps on the opened GitHub page
echo ============================================
echo   1. Click  BAND_STORAGE_STATE_JSON
echo   2. Click  Update
echo   3. Select all (Ctrl+A) and delete the old value
echo   4. Paste (Ctrl+V)
echo   5. Click  Update secret
echo.
echo Close this window when done.
pause
