@echo off
chcp 65001 >nul
title PE Builder - 多架构构建脚本

echo ================================
echo  PE Builder - Multi-Arch Builder
echo ================================
echo.
echo 选择目标架构:
echo   [1] x64 (AMD64)  - 推荐, 大多数电脑
echo   [2] x86 (32-bit) - 旧电脑
echo   [3] ARM64        - ARM 设备 (需 ARM Windows)
echo.

set /p arch="请输入数字 (1/2/3): "

if "%arch%"=="1" set TARGET=x64
if "%arch%"=="2" set TARGET=x86
if "%arch%"=="3" set TARGET=arm64

if "%TARGET%"=="" (
    echo 无效选择
    pause
    exit /b 1
)

echo.
echo 目标架构: %TARGET%
echo 要求: Python 3.12+ (%TARGET% 位版本)
echo.

REM 清理旧构建
if exist dist-%TARGET% rmdir /s /q dist-%TARGET%
if exist build-%TARGET% rmdir /s /q build-%TARGET%

REM 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo 错误: 未找到 Python!
    pause
    exit /b 1
)

python -c "import struct; print(f'Python架构: x{struct.calcsize(\"P\")*8} bit')"

REM 安装依赖
echo.
echo 正在安装依赖...
pip install pywebview pyinstaller pycdlib --quiet

REM 构建主程序
echo.
echo 正在构建 PE-Builder (%TARGET%)...
set PYINSTALLER_ARGS=--onefile --windowed
set PYINSTALLER_ARGS=%PYINSTALLER_ARGS% --add-data "electron/index.html;."
set PYINSTALLER_ARGS=%PYINSTALLER_ARGS% --add-data "electron/iso_builder.py;."
set PYINSTALLER_ARGS=%PYINSTALLER_ARGS% --add-data "tools/PE-Browser-%TARGET%.exe;tools/"
set PYINSTALLER_ARGS=%PYINSTALLER_ARGS% --hidden-import pycdlib
set PYINSTALLER_ARGS=%PYINSTALLER_ARGS% --name "PE-Builder-%TARGET%"
set PYINSTALLER_ARGS=%PYINSTALLER_ARGS% --distpath "dist-%TARGET%"
set PYINSTALLER_ARGS=%PYINSTALLER_ARGS% --workpath "build-%TARGET%"
set PYINSTALLER_ARGS=%PYINSTALLER_ARGS% --noconfirm

pyinstaller %PYINSTALLER_ARGS% electron/main.py

if %errorlevel% equ 0 (
    echo.
    echo ✅ PE-Builder-%TARGET% 构建成功!
    echo    输出: dist-%TARGET%\PE-Builder-%TARGET%.exe
) else (
    echo.
    echo ❌ 构建失败
)

REM 清理
if exist build-%TARGET% rmdir /s /q build-%TARGET%

pause
