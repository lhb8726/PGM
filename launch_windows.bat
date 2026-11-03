@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto check_environment

py -3 -c "import sys; raise SystemExit(sys.version_info < (3, 10))" >nul 2>nul
if errorlevel 1 goto try_python
py -3 -m venv .venv
if errorlevel 1 goto failed
goto check_environment

:try_python
python -c "import sys; raise SystemExit(sys.version_info < (3, 10))" >nul 2>nul
if errorlevel 1 goto missing_python
python -m venv .venv
if errorlevel 1 goto failed

:check_environment
".venv\Scripts\python.exe" -c "import sys; raise SystemExit(sys.version_info < (3, 10))" >nul 2>nul
if errorlevel 1 goto old_environment
".venv\Scripts\python.exe" -c "import PySide6" >nul 2>nul
if errorlevel 1 goto install_dependencies
goto launch

:install_dependencies
echo PGM에 필요한 패키지를 설치합니다. 최초 설치에는 인터넷이 필요합니다.
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed

:launch
".venv\Scripts\python.exe" -m pgm %*
if errorlevel 1 goto failed
exit /b 0

:missing_python
echo Python 3.10 이상을 설치한 후 다시 실행해 주세요.
echo 권장 개발 환경: Python 3.12 / https://www.python.org/downloads/
goto failed

:old_environment
echo 기존 .venv의 Python이 3.10 미만입니다. 가상환경을 별도로 보관한 뒤 새로 생성해 주세요.

:failed
echo.
echo PGM 실행에 실패했습니다. 위 오류를 확인해 주세요.
pause
exit /b 1
