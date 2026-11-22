@echo off
chcp 65001 >nul
cd /d "%~dp0"
where zsign >nul 2>&1
if errorlevel 1 (
  echo [!] 找不到 zsign。請先安裝並將 zsign.exe 放到 PATH，或設定 ZSIGN_PATH。
  echo     zsign: https://github.com/zhlynn/zsign
  pause
  exit /b 1
)
py -m pip install -r requirements.txt
if errorlevel 1 (
  echo [!] 套件安裝失敗，請先安裝 Python 3.11+
  pause
  exit /b 1
)
echo [OK] 網站位置: http://127.0.0.1:8000
start "" http://127.0.0.1:8000
py -m uvicorn app:app --host 127.0.0.1 --port 8000
pause
