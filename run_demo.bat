@echo off
rem 데모 실행 (Windows): 폴더 안의 python\python.exe(임베디드 Python), py 런처, python 순서로 Python 3.8 이상을 찾아 scripts\demo.py 를 실행한다.
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

if exist "python\python.exe" goto embedded
py -3 -c "import sys; sys.exit(0 if sys.version_info>=(3,8) else 1)" >nul 2>nul
if %errorlevel%==0 goto pylauncher
python -c "import sys; sys.exit(0 if sys.version_info>=(3,8) else 1)" >nul 2>nul
if %errorlevel%==0 goto plainpython

echo [안내] Python 3.8 이상이 필요합니다. 설치 후 다시 실행하세요 (외부 패키지는 필요 없습니다).
echo        설치가 어려우면 docs\대회제출\10_구동안내서_초안.md 의 'Python이 없는 경우'를 참고하세요.
exit /b 1

:embedded
"python\python.exe" scripts\demo.py %*
exit /b %errorlevel%

:pylauncher
py -3 scripts\demo.py %*
exit /b %errorlevel%

:plainpython
python scripts\demo.py %*
exit /b %errorlevel%
