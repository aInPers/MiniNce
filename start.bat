@echo off
chcp 65001 >nul
REM ============================================================
REM MiniNCE 安全启动脚本
REM ------------------------------------------------------------
REM 安全默认：
REM   - ENVIRONMENT=production（强制校验加密密钥、关闭 Debug、绑定 127.0.0.1）
REM   - 自动生成 Fernet 加密密钥（通过 Python 脚本以 UTF-8 写入 .env）
REM   - 自动应用 Alembic 数据库迁移
REM   - 不会自动接受 SSH 主机密钥（连接真实设备时需先发现并确认指纹）
REM ------------------------------------------------------------
REM 用法：
REM   start.bat              使用 production 环境启动（推荐）
REM   start.bat dev          使用 development 环境启动（开放 Debug）
REM ============================================================

setlocal EnableDelayedExpansion

set "APP_DIR=%~dp0"
cd /d "%APP_DIR%"

REM ---- 解析参数：dev/development 启用开发模式 ----
set "RUN_ENV=production"
if /i "%~1"=="dev" set "RUN_ENV=development"
if /i "%~1"=="development" set "RUN_ENV=development"

echo [1/5] MiniNCE 启动脚本 (environment=%RUN_ENV%)

REM ---- 检查 Python 3 ----
where py >nul 2>&1
if errorlevel 1 (
    echo [ERROR] 未找到 py 启动器，请安装 Python 3 并确保 py 命令可用。
    exit /b 1
)

py -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] 需要 Python 3.12 或更高版本。
    py --version
    exit /b 1
)

echo       Python:
py --version

REM ---- 设置环境变量（优先级低于已存在的 .env） ----
set "ENVIRONMENT=%RUN_ENV%"

if /i "%RUN_ENV%"=="development" (
    set "DEBUG=true"
    set "HOST=127.0.0.1"
) else (
    set "DEBUG=false"
    set "HOST=127.0.0.1"
)
set "PORT=8000"

REM ---- 确保 .env 存在并包含有效 ENCRYPTION_KEY ----
REM 通过 Python 脚本以 UTF-8 编码写入，避免 PowerShell/CMD 中文系统编码问题
if not exist ".env" (
    echo [2/5] 首次启动：生成 .env 配置文件
    for /f "delims=" %%L in ('py scripts\init_env.py %RUN_ENV% %DEBUG% %HOST% %PORT%') do (
        set "INIT_RESULT=%%L"
    )
    if "!INIT_RESULT:~0,14!"=="GENERATED_KEY=" (
        echo       已生成 .env 文件，ENCRYPTION_KEY 已自动配置
    ) else (
        echo [ERROR] .env 生成失败：!INIT_RESULT!
        exit /b 1
    )
) else (
    echo [2/5] 检测到 .env 配置文件，检查 ENCRYPTION_KEY
    for /f "delims=" %%L in ('py scripts\init_env.py --ensure-key') do (
        set "ENSURE_RESULT=%%L"
    )
    if "!ENSURE_RESULT:~0,13!"=="APPENDED_KEY=" (
        echo       已补充 ENCRYPTION_KEY 到 .env
    ) else if "!ENSURE_RESULT!"=="NO_CHANGE" (
        echo       .env 配置完整
    ) else (
        echo [WARN] .env 可能编码损坏或缺少密钥：!ENSURE_RESULT!
        echo        正在重新生成 .env
        for /f "delims=" %%L in ('py scripts\init_env.py %RUN_ENV% %DEBUG% %HOST% %PORT%') do (
            set "INIT_RESULT=%%L"
        )
        if "!INIT_RESULT:~0,14!"=="GENERATED_KEY=" (
            echo       已重新生成 .env 文件
        )
    )
)

REM ---- 加载 .env 到当前进程环境（仅覆盖未在系统环境变量中设置的项） ----
call :load_dotenv

REM ---- 同步 ENVIRONMENT 与命令行参数 ----
if /i "%RUN_ENV%"=="development" (
    set "ENVIRONMENT=development"
) else (
    set "ENVIRONMENT=production"
)

REM ---- 安装依赖（若未安装） ----
echo [3/5] 检查项目依赖
py -c "import minince" >nul 2>&1
if errorlevel 1 (
    echo       未检测到 minince 包，执行 pip install -e .
    py -m pip install -e . >nul
    if errorlevel 1 (
        echo [ERROR] 依赖安装失败。
        exit /b 1
    )
) else (
    echo       依赖已安装
)

REM ---- 应用数据库迁移 ----
echo [4/5] 应用 Alembic 数据库迁移
py -m alembic upgrade head
if errorlevel 1 (
    echo [ERROR] 数据库迁移失败，请检查 migrations/ 目录。
    exit /b 1
)

REM ---- 启动服务 ----
echo [5/5] 启动 MiniNCE 服务
echo       访问地址: http://%HOST%:%PORT%
echo       按 Ctrl+C 停止服务
echo.

py -m uvicorn minince.main:app --host %HOST% --port %PORT%
goto :eof


REM ============================================================
REM 子程序：加载 .env 文件到当前环境
REM 仅覆盖未在系统环境变量中设置的项
REM ============================================================
:load_dotenv
if not exist ".env" goto :eof
for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
    if not "%%A"=="" (
        if not defined %%A set "%%A=%%B"
    )
)
goto :eof
