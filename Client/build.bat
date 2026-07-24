@echo off
cd /d "%~dp0"

echo ========================================
echo   EasyPrint Client - Build EXE
echo ========================================
echo.

echo [1/4] Checking Python...
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

echo [2/4] Checking PyInstaller...
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

echo [3/4] Building EXE...
echo.

echo Killing running EasyPrint Client...
taskkill /f /im "EasyPrint Client.exe" >nul 2>nul
taskkill /f /im "EasyPrintClient.exe" >nul 2>nul
taskkill /f /im "python.exe" /fi "WINDOWTITLE eq EasyPrint Client" >nul 2>nul
timeout /t 2 /nobreak >nul

echo Cleaning old output...
if exist "dist\EasyPrint Client.exe" del /f /q "dist\EasyPrint Client.exe"
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"
if exist "EasyPrint Client.spec" del /q "EasyPrint Client.spec"

pyinstaller ^
    --clean ^
    --noconfirm ^
    -F ^
    -w ^
    --name "EasyPrint Client" ^
    --add-data "src;src" ^
    --add-data "config;config" ^
    --exclude-module=PyQt5 ^
    --exclude-module=PyQt6 ^
    --exclude-module=PySide2 ^
    --hidden-import=qasync ^
    --hidden-import=PySide6.QtGui ^
    --hidden-import=PySide6.QtWidgets ^
    --hidden-import=PySide6.QtCore ^
    --hidden-import=win32print ^
    --hidden-import=win32api ^
    --hidden-import=win32con ^
    --hidden-import=win32gui ^
    --hidden-import=win32event ^
    --hidden-import=win32process ^
    --hidden-import=asyncio ^
    --hidden-import=logging ^
    --hidden-import=json ^
    --hidden-import=struct ^
    --hidden-import=zlib ^
    --hidden-import=platform ^
    --hidden-import=subprocess ^
    --hidden-import=uuid ^
    --hidden-import=datetime ^
    --hidden-import=pathlib ^
    --hidden-import=typing ^
    --hidden-import=sqlite3 ^
    main.py

if %errorlevel% equ 0 (
    echo.
    echo ========================================
    echo [SUCCESS] Build completed!
    echo ========================================
    echo.
    echo Output: dist\EasyPrint Client.exe
    echo.
    echo To distribute: Copy the entire 'dist' folder
    echo or just 'EasyPrint Client.exe' (standalone)
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

echo [4/4] Cleaning up...
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