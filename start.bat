@echo off
REM ============================================================
REM MiniNCE 安全启动脚本
REM ------------------------------------------------------------
REM 安全默认：
REM   - ENVIRONMENT=production（强制校验加密密钥、关闭 Debug、绑定 127.0.0.1）
REM   - 自动生成 Fernet 加密密钥（首次启动且 .env 缺失时）
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

REM ---- 确保 .env 存在并包含 ENCRYPTION_KEY ----
if not exist ".env" (
    echo [2/5] 首次启动：生成 .env 配置文件
    call :generate_env
) else (
    echo [2/5] 检测到 .env 配置文件
    call :ensure_encryption_key
)

REM ---- 加载 .env 到当前进程环境（简单实现：逐行解析 KEY=VALUE） ----
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
REM 子程序：生成初始 .env 文件
REM ============================================================
:generate_env
REM 生成 Fernet 密钥
set "KEY_LINE="
for /f "delims=" %%K in ('py -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"') do (
    set "KEY_LINE=%%K"
)

if "%KEY_LINE%"=="" (
    echo [ERROR] 无法生成加密密钥，请确认 cryptography 已安装。
    exit /b 1
)

> ".env" (
    echo # MiniNCE 自动生成的环境配置
    echo # 生成时间: %DATE% %TIME%
    echo # 请妥善保管 ENCRYPTION_KEY，丢失后将无法解密已保存的设备密码
    echo.
    echo ENVIRONMENT=%RUN_ENV%
    echo DEBUG=%DEBUG%
    echo HOST=%HOST%
    echo PORT=8000
    echo.
    echo DATABASE_URL=sqlite:///./minince.db
    echo.
    echo LOG_LEVEL=INFO
    echo LOG_FORMAT=json
    echo LOG_FILE=logs/minince.log
    echo.
    echo ENCRYPTION_KEY=%KEY_LINE%
    echo.
    echo SSH_TIMEOUT=30
    echo SSH_PORT=22
)
echo       已生成 .env 文件，ENCRYPTION_KEY 已自动配置
goto :eof


REM ============================================================
REM 子程序：若 .env 缺少 ENCRYPTION_KEY 则补全
REM ============================================================
:ensure_encryption_key
findstr /b /c:"ENCRYPTION_KEY=" .env >nul
if not errorlevel 1 (
    REM 已存在 ENCRYPTION_KEY 行，但需检查是否为空或占位符
    for /f "tokens=2 delims==" %%V in ('findstr /b /c:"ENCRYPTION_KEY=" .env') do (
        set "EXISTING_KEY=%%V"
    )
    if "!EXISTING_KEY!"=="" goto :append_key
    if /i "!EXISTING_KEY!"=="your-encryption-key-here" goto :append_key
    goto :eof
)
:append_key
echo [WARN] .env 缺少有效的 ENCRYPTION_KEY，正在补充...
set "KEY_LINE="
for /f "delims=" %%K in ('py -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"') do (
    set "KEY_LINE=%%K"
)
>> ".env" echo ENCRYPTION_KEY=%KEY_LINE%
echo       已补充 ENCRYPTION_KEY 到 .env
goto :eof


REM ============================================================
REM 子程序：加载 .env 文件到当前环境
REM 仅覆盖未在系统环境变量中设置的项
REM ============================================================
:load_dotenv
for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
    if not "%%A"=="" (
        if not defined %%A set "%%A=%%B"
    )
)
goto :eof
