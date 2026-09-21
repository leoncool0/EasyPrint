@echo off
cd /d "%~dp0"

echo ========================================
echo   EasyPrint Client - Build EXE
echo ========================================

echo.
echo [1/5] Checking Python...
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.8+
    echo Download: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)
python --version
echo.

echo.
echo [2/5] Checking PySide6 version...
for /f "tokens=2" %%i in ('python -c "import PySide6; print(PySide6.__version__)" 2^>nul') do set PYSIDE_VER=%%i
echo PySide6 version: !PYSIDE_VER!
python -c "import PySide6; assert tuple(map(int, PySide6.__version__.split('.')[:2])) < (6,5), 'PySide6 >= 6.5 not supported on Windows 7'; print('PySide6 version OK')" 2>nul || echo [WARNING] PySide6 >= 6.5 detected — Windows 7 not supported!
echo.

echo.
echo [3/5] Checking PyInstaller...
python -c "import PyInstaller" >nul 2>nul
if %errorlevel% neq 0 (
    echo Installing PyInstaller...
    pip install pyinstaller
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install PyInstaller
        pause
        exit /b 1
    )
)
echo PyInstaller OK
echo.

echo.
echo [4/5] Building EXE...
echo.

echo Killing running EasyPrint Client...
taskkill /f /im "EasyPrint Client.exe" >nul 2>nul
taskkill /f /im "EasyPrintClient.exe" >nul 2>nul
timeout /t 3 /nobreak >nul

echo Cleaning old output...
if exist "dist\EasyPrint Client.exe" (
    del /f /q "dist\EasyPrint Client.exe"
    timeout /t 1 /nobreak >nul
)
if exist "dist" rmdir /s /q "dist" 2>nul
if exist "build" rmdir /s /q "build" 2>nul
if exist "EasyPrint Client.spec" del /q "EasyPrint Client.spec" 2>nul

timeout /t 2 /nobreak >nul

pyinstaller --clean --noconfirm -F -w --name "EasyPrint Client" --icon "assets\app.ico" --add-data "src;src" --add-data "config;config" --add-data "assets;assets" --exclude-module=PyQt5 --exclude-module=PyQt6 --exclude-module=PySide2 --hidden-import=qasync --hidden-import=PySide6.QtGui --hidden-import=PySide6.QtWidgets --hidden-import=PySide6.QtCore --hidden-import=win32print --hidden-import=win32api --hidden-import=win32con --hidden-import=win32gui --hidden-import=win32event --hidden-import=win32process --hidden-import=asyncio --hidden-import=logging --hidden-import=json --hidden-import=struct --hidden-import=zlib --hidden-import=platform --hidden-import=subprocess --hidden-import=uuid --hidden-import=datetime --hidden-import=pathlib --hidden-import=typing --hidden-import=sqlite3 --noupx main.py

if %errorlevel% equ 0 (
    echo.
    echo ========================================
    echo [SUCCESS] Build completed!
    echo ========================================
    echo.
    echo Output: dist\EasyPrint Client.exe
    echo.
) else (
    echo.
    echo ========================================
    echo [ERROR] Build failed!
    echo ========================================
    echo.
    pause
    exit /b 1
)

echo.
echo [5/5] Cleaning up...
if exist "__pycache__" rmdir /s /q "__pycache__"
if exist "src\__pycache__" rmdir /s /q "src\__pycache__"
if exist "build" rmdir /s /q "build"
if exist "EasyPrint Client.spec" del /q "EasyPrint Client.spec"
echo Cleanup done.
echo.

echo ========================================
echo Build finished!
echo ========================================
echo.
pause