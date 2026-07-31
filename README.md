# MiniNCE - 轻量级网络自动化配置平台

MiniNCE 是一个部署在内网环境中的轻量级网络自动化管理平台，主要用于连接和管理网络设备，支持配置自动化下发、配置备份、拓扑可视化和任务生命周期管理。

平台采用领域驱动设计（DDD）的分层架构，以 FastAPI 为 Web 框架，通过 SSH 抽象层对接真实网络设备（华为 VRP），并提供 Mock 后端用于本地无设备开发与测试。

---

## 目录

- [功能特性](#功能特性)
- [技术栈](#技术栈)
- [系统架构](#系统架构)
- [项目结构](#项目结构)
- [核心模块说明](#核心模块说明)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [访问地址](#访问地址)
- [运行测试](#运行测试)
- [开发规范](#开发规范)
- [版本历史](#版本历史)
- [许可证](#许可证)

---

## 功能特性

### 第一阶段 - 基础架构 (v0.1.0)
- ✅ FastAPI Web 应用框架
- ✅ SQLite 数据库持久化
- ✅ SQLAlchemy 2.x ORM 模型
- ✅ Alembic 数据库迁移
- ✅ 设备管理 CRUD
- ✅ Fernet 密码加密存储
- ✅ 风险等级管理
- ✅ 结构化日志（structlog，支持 JSON / 文本格式）
- ✅ 健康检查接口
- ✅ 系统首页仪表盘
- ✅ RESTful API

### 第二阶段 - 核心业务 (v0.2.0)
- ✅ 华为 VRP 设备驱动
- ✅ VLAN 配置管理（创建、修改、删除）
- ✅ 接口基础配置（Access / Trunk / Hybrid）
- ✅ 接口加入 VLAN
- ✅ 配置模板管理 CRUD
- ✅ 配置预览与差异计算
- ✅ 任务执行器（完整生命周期）
- ✅ 任务执行日志记录
- ✅ 执行结果验证
- ✅ Web 管理界面（设备、任务、模板页面）

### 第三阶段 - 扩展功能 (v0.3.0)
- ✅ SSH 连接抽象层（`Protocol` 接口）
- ✅ Mock SSH 后端（用于无设备测试）
- ✅ Paramiko SSH 后端（生产环境）
- ✅ Netmiko SSH 后端（生产环境）
- ✅ 配置备份服务
- ✅ 配置恢复功能
- ✅ 模板变量渲染引擎
- ✅ 变量白名单安全校验
- ✅ 配置备份管理 Web UI
- ✅ OSPF 配置预览 / 下发 / 状态读取
- ✅ 设备拓扑画布（拖拽定位、设备类型区分）
- ✅ 真实 SSH 设备对接（Paramiko / Netmiko 后端 + 设备诊断脚本）
- ✅ 配置回滚流程（备份恢复 + SHA256 完整性校验 + 二次确认）

### 待实现功能
- 🔄 批量任务调度
- 🔄 更多厂商驱动（Cisco / H3C，目前仅注册华为 VRP）

---

## 技术栈

| 层级 | 技术 | 版本 |
|------|------|------|
| 语言 | Python | 3.12+ |
| Web 框架 | FastAPI | 0.115+ |
| ASGI 服务器 | Uvicorn | 0.32+ |
| 模板引擎 | Jinja2 | 3.1+ |
| ORM | SQLAlchemy | 2.0+ |
| 数据库迁移 | Alembic | 1.13+ |
| 数据校验 | Pydantic / pydantic-settings | 2.x |
| 数据库 | SQLite | 内置 |
| SSH | Paramiko / Netmiko | 2.12+ |
| 加密 | cryptography (Fernet) | 42+ |
| 日志 | structlog | 24+ |
| 测试 | pytest / pytest-asyncio / pytest-cov | 8+ |
| HTTP 测试 | httpx | 0.28+ |
| 代码检查 | ruff / mypy | 0.6+ / 1.13+ |

---

## 系统架构

MiniNCE 采用 **DDD 分层架构**（领域驱动设计），将业务逻辑、基础设施和 Web 表现层严格分离，确保各层可独立演进与测试。

### 分层架构图

```
┌─────────────────────────────────────────────────────────────┐
│                     Web 层 (web/)                           │
│   FastAPI Routers + Jinja2 Templates                        │
│   - 页面路由 (pages, devices, canvas, backups, ...)         │
│   - RESTful API (/api/v1/*)                                 │
│   - 依赖注入 (dependencies.py)                              │
└────────────────────────┬────────────────────────────────────┘
                         │ 调用
┌────────────────────────▼────────────────────────────────────┐
│                  应用层 (application/)                      │
│   业务服务编排 + DTO                                         │
│   - DeviceService（设备管理 / 连接测试 / 画布操作）          │
│   - BackupService（配置备份 / 恢复 / 完整性校验）            │
└────────────────────────┬────────────────────────────────────┘
                         │ 调用
┌────────────────────────▼────────────────────────────────────┐
│                   领域层 (domain/)                           │
│   纯业务模型，无框架依赖                                     │
│   - devices/    设备领域模型、设备信息、配置                 │
│   - network/    配置意图 (intents)、配置计划 (config_plan)   │
│   - network/ospf/  OSPF 模型、状态、校验器                  │
│   - tasks/      任务领域模型                                │
│   - templates/  模板领域模型                                │
└────────────────────────┬────────────────────────────────────┘
                         │ 由基础设施实现
┌────────────────────────▼────────────────────────────────────┐
│                基础设施层 (infrastructure/)                  │
│   - database/   SQLAlchemy 连接、ORM 模型                   │
│   - repositories/  仓储实现（Device / Backup / Audit）      │
│   - drivers/huawei_vrp/  华为 VRP 驱动                      │
│   - ssh/        SSH 抽象 (Protocol) + 三种后端实现          │
│   - security/   Fernet 加密                                 │
└─────────────────────────────────────────────────────────────┘
```

### 请求处理流程

以"下发 VLAN 配置到设备"为例：

```
浏览器 / API 客户端
    │  HTTP POST /api/v1/devices/{id}/vlan/deploy
    ▼
Web 层 (routers/vlan.py)
    │  解析参数、校验请求
    ▼
应用层 (application/services/)
    │  编排业务流程
    ▼
领域层 (domain/network/)
    │  将需求转换为配置意图 (Intent → ConfigPlan)
    ▼
基础设施层 (drivers/huawei_vrp/)
    │  生成厂商特定命令 (command_generator)
    ▼
基础设施层 (ssh/)
    │  通过 SSHConnection 下发命令到设备
    ▼
网络设备 (华为 VRP)
```

### 关键设计决策

1. **SSH 连接抽象**：通过 `typing.Protocol` 定义 `SSHConnection` 接口，运行时可切换 Mock / Paramiko / Netmiko 后端，便于本地无设备开发与单元测试。
2. **安全默认**：配置层（`config.py`）在 `production` 环境强制校验加密密钥、禁止 Debug、禁止绑定 `0.0.0.0`；SSH 默认拒绝未知主机密钥（`auto_add_host_key=False`）。
3. **密码加密**：设备密码使用 Fernet 对称加密后存储，密钥由 `ENCRYPTION_KEY` 环境变量提供。
4. **模板安全**：模板变量渲染引擎内置白名单校验，防止注入风险。
5. **风险分级**：所有配置操作标注风险等级（LOW / MEDIUM / HIGH / CRITICAL），HIGH 及以上需要二次确认。

---

## 项目结构

```
MiniNce/
├── src/minince/                    # 主源码包
│   ├── main.py                     # FastAPI 应用入口、路由注册、启动事件
│   ├── config.py                   # Pydantic Settings 配置（含安全校验）
│   ├── logging.py                  # structlog 日志配置
│   ├── __init__.py
│   │
│   ├── shared/                     # 共享内核层
│   │   ├── enums.py                # 枚举：RiskLevel / DeviceStatus / DeviceType / DeviceVendor / ConnectionType
│   │   ├── exceptions.py           # 自定义异常层次结构
│   │   └── result.py               # 统一结果对象 (Result pattern)
│   │
│   ├── domain/                     # 领域层（纯业务模型，无框架依赖）
│   │   ├── devices/                # 设备领域
│   │   │   ├── network_device.py   #   网络设备实体
│   │   │   ├── facts.py            #   设备事实信息 (facts)
│   │   │   └── config.py           #   设备配置快照
│   │   ├── network/                # 网络配置意图
│   │   │   ├── intents.py          #   配置意图定义 (VLAN / 接口 / OSPF)
│   │   │   ├── config_plan.py      #   配置计划（意图 → 命令的中间表达）
│   │   │   └── ospf/               #   OSPF 子域
│   │   │       ├── models.py       #     OSPF 模型
│   │   │       ├── state.py        #     OSPF 状态与差异
│   │   │       └── validators.py   #     OSPF 配置校验器
│   │   └── devices/                #   设备领域（实体 / facts / 配置快照）
│   │
│   ├── application/                # 应用层（业务编排）
│   │   ├── services/
│   │   │   ├── device_service.py   #   设备管理服务（CRUD / 连接测试 / 画布操作）
│   │   │   └── backup_service.py   #   配置备份 / 恢复服务（含完整性校验）
│   │   └── dto/
│   │       └── device.py           #   设备数据传输对象
│   │
│   ├── infrastructure/             # 基础设施层（技术实现）
│   │   ├── database/
│   │   │   ├── connection.py       #   SQLAlchemy engine / Base / get_db 依赖
│   │   │   └── models.py           #   ORM 模型：Device / ConfigBackup / AuditLog
│   │   ├── drivers/
│   │   │   └── huawei_vrp/         #   华为 VRP 驱动
│   │   │       ├── huawei_device.py        # 设备适配器
│   │   │       ├── command_generator.py    # 配置命令生成器
│   │   │       ├── parser.py               # 设备输出解析器
│   │   │       ├── ospf_parser.py          # OSPF 输出解析
│   │   │       └── ospf_renderer.py        # OSPF 配置渲染
│   │   ├── repositories/
│   │   │   ├── base.py             #   仓储基类
│   │   │   ├── device_repository.py#   设备仓储
│   │   │   ├── backup_repository.py#   备份仓储
│   │   │   └── audit_repository.py #   审计日志仓储
│   │   ├── security/
│   │   │   └── encryption.py       #   Fernet 加密 / 解密
│   │   └── ssh/                    #   SSH 连接层
│   │       ├── base.py             #     SSHConfig + SSHConnection (Protocol)
│   │       ├── mock_connection.py  #     Mock 实现（无设备测试）
│   │       ├── paramiko_connection.py #  Paramiko 实现
│   │       └── netmiko_connection.py  #  Netmiko 实现
│   │
│   └── web/                        # Web 表现层
│       ├── dependencies.py         #   FastAPI 依赖注入
│       ├── routers/                #   路由定义
│       │   ├── pages.py            #     首页 / 健康检查
│       │   ├── api.py              #     RESTful API (/api/v1/*)
│       │   ├── devices.py          #     设备管理页面
│       │   ├── canvas.py           #     拓扑画布页面 + 画布 API
│       │   ├── backups.py          #     配置备份管理页面
│       │   ├── manual_config.py    #     手动配置页面
│       │   ├── template_config.py  #     模板配置页面
│       │   ├── vlan.py             #     VLAN 配置 API
│       │   └── ospf.py             #     OSPF 配置 API
│       └── templates/              #   Jinja2 HTML 模板
│           ├── base.html           #     布局基模板
│           ├── index.html          #     首页仪表盘
│           ├── devices.html        #     设备列表
│           ├── device_detail.html  #     设备详情
│           ├── device_form.html    #     设备表单
│           ├── canvas.html         #     拓扑画布
│           ├── backups.html        #     备份管理
│           ├── manual_config.html  #     手动配置
│           └── template_config.html#     模板配置
│
├── migrations/                     # Alembic 数据库迁移
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       ├── 9d40975b6851_init.py                      # 初始化
│       ├── 7e0f82396e0d_add_task_concurrency_control_fields.py
│       └── a1b2c3d4e5f6_add_device_canvas_fields.py # 画布坐标字段
│
├── tests/                          # 测试套件
│   ├── conftest.py                 #   pytest 公共夹具
│   ├── unit/                       #   单元测试
│   │   ├── test_encryption.py
│   │   ├── test_enums.py
│   │   ├── test_exceptions.py
│   │   ├── test_result.py
│   │   ├── test_huawei_vrp_driver.py
│   │   ├── test_huawei_vrp_generator.py
│   │   ├── test_mock_ssh.py
│   │   └── test_paramiko_connection.py
│   ├── integration/                #   集成测试
│   │   ├── test_api_routes.py
│   │   └── test_device_repository.py
│   └── domain/                     #   领域测试
│       └── network/ospf/
│           ├── test_models.py
│           ├── test_state_diff.py
│           └── test_validators.py
│
├── scripts/
│   └── init_env.py                 # .env 初始化脚本（生成加密密钥）
│
├── .env.example                    # 环境变量示例
├── .gitignore
├── alembic.ini                     # Alembic 配置
├── pyproject.toml                  # 项目元数据、依赖、工具配置
├── conftest.py                     # 根级 pytest 配置
├── start.bat                       # Windows 一键启动脚本
├── docs.md                         # 项目设计文档
├── ospf.md                         # OSPF 功能说明
├── vlan.md                         # VLAN 功能说明
├── diagnose_device.py              # 设备诊断脚本
├── test_real_ssh.py                # 真实 SSH 连接测试脚本
└── README.md                       # 本文档
```

---

## 核心模块说明

### 1. 配置层 (`config.py`)

基于 `pydantic-settings` 的 `Settings` 类，从 `.env` 文件和环境变量加载配置，并通过 `model_validator` 实现环境感知的安全校验：

- **所有环境**：禁止使用内置的已弃用默认密钥。
- **production 环境**：必须配置 `ENCRYPTION_KEY`、禁止开启 `DEBUG`、禁止绑定 `0.0.0.0` / `::`。
- **development / testing 环境**：自动注入测试专用密钥，避免启动失败。

### 2. SSH 连接层 (`infrastructure/ssh/`)

通过 `typing.Protocol` 定义统一的 `SSHConnection` 接口，包含连接、断开、发送命令、发送配置集、保存配置等抽象方法。三种实现可互换：

| 后端 | 文件 | 用途 |
|------|------|------|
| Mock | `mock_connection.py` | 本地无设备开发与单元测试 |
| Paramiko | `paramiko_connection.py` | 生产环境，基于 Paramiko 原生 API |
| Netmiko | `netmiko_connection.py` | 生产环境，基于 Netmiko 厂商适配 |

`SSHConfig` 默认 `auto_add_host_key=False`，拒绝未知主机密钥以防范中间人攻击；首次连接设备需显式确认指纹或预先配置已知主机。

### 3. 设备驱动 (`infrastructure/drivers/huawei_vrp/`)

华为 VRP 平台驱动，负责：
- `command_generator.py`：将领域配置意图转换为 VRP 命令行。
- `parser.py` / `ospf_parser.py`：解析设备回显（接口、VLAN、OSPF 状态等）。
- `ospf_renderer.py`：渲染 OSPF 配置片段。
- `huawei_device.py`：设备适配器，整合命令生成、SSH 下发与结果解析。

### 4. 数据模型 (`infrastructure/database/models.py`)

| 模型 | 表名 | 说明 |
|------|------|------|
| `Device` | `devices` | 网络设备（含加密密码、厂商、画布坐标等） |
| `ConfigBackup` | `config_backups` | 配置备份记录（含内容、校验和、来源） |
| `AuditLog` | `audit_logs` | 审计日志（操作者、动作、资源、详情 JSON） |

所有 ORM 模型继承 `Base`，`TimestampMixin` 提供 `created_at` / `updated_at` 时间戳。

### 5. Web 层 (`web/`)

采用 FastAPI 路由 + Jinja2 模板的单体架构（非前后端分离）。路由分两类：

- **页面路由**：返回 HTML（`response_class=HTMLResponse`），供浏览器直接访问。
- **API 路由**：返回 JSON，供前端脚本或外部系统集成，统一前缀 `/api/v1`。

---

## 快速开始

### 方式一：Windows 一键启动（推荐）

项目提供 `start.bat` 脚本，自动完成环境检查、`.env` 生成、依赖安装、数据库迁移和服务启动：

```bat
REM 生产模式（默认，安全配置：关闭 Debug、绑定 127.0.0.1、强制加密密钥）
start.bat

REM 开发模式（开启 Debug、热重载）
start.bat dev
```

脚本执行流程：
1. 检查 Python 3.12+ 是否安装。
2. 设置 `ENVIRONMENT` 环境变量。
3. 若不存在 `.env`，调用 `scripts/init_env.py` 生成并自动填充 `ENCRYPTION_KEY`。
4. 加载 `.env` 到当前进程环境。
5. 检查并按需安装项目依赖（`pip install -e .`）。
6. 执行 `alembic upgrade head` 应用数据库迁移。
7. 启动 Uvicorn 服务。

### 方式二：手动启动（跨平台）

#### 1. 进入项目目录

```bash
cd MiniNce
```

#### 2. 创建虚拟环境并安装依赖

```bash
py -3.12 -m venv venv

# Windows PowerShell
.\venv\Scripts\Activate.ps1

# Linux / macOS
source venv/bin/activate

# 安装依赖（含开发依赖）
pip install -e ".[dev]"
```

#### 3. 配置环境变量

```bash
# 复制示例配置
copy .env.example .env      # Windows
cp .env.example .env        # Linux / macOS

# 生成 Fernet 加密密钥并填入 .env 的 ENCRYPTION_KEY
py -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

> ⚠️ **生产环境必须配置 `ENCRYPTION_KEY`**，否则启动时会因安全校验失败而报错。开发 / 测试环境会自动注入测试密钥。

#### 4. 初始化数据库

项目已内置迁移文件，直接应用即可：

```bash
# 执行迁移到最新版本
alembic upgrade head
```

如需基于当前模型重新生成迁移（开发阶段）：

```bash
alembic revision --autogenerate -m "your migration message"
```

#### 5. 启动应用

```bash
# 方式 A：使用注册的命令行入口
minince

# 方式 B：以模块方式运行
py -m minince.main

# 方式 C：直接通过 uvicorn 启动（支持热重载）
py -m uvicorn minince.main:app --host 127.0.0.1 --port 8000 --reload
```

应用将在 `http://127.0.0.1:8000` 启动。

> ℹ️ 应用启动时会自动执行 `Base.metadata.create_all(bind=engine)`，确保表结构存在。但**版本化迁移仍建议通过 `alembic upgrade head` 管理**。

---

## 配置说明

所有配置通过 `.env` 文件或环境变量提供，由 `pydantic-settings` 自动加载（大小写不敏感）。

### 环境变量

| 变量 | 说明 | 默认值 | 备注 |
|------|------|--------|------|
| `ENVIRONMENT` | 环境标识 | `production` | `development` / `testing` / `production`；production 启动强制校验安全配置 |
| `APP_NAME` | 应用名称 | `MiniNCE` | |
| `APP_VERSION` | 应用版本 | `0.1.0` | |
| `DEBUG` | 调试模式 | `false` | production 环境禁止为 `true`；为 `true` 时 Uvicorn 启用热重载 |
| `HOST` | 监听地址 | `127.0.0.1` | production 环境禁止 `0.0.0.0` / `::` |
| `PORT` | 监听端口 | `8000` | |
| `DATABASE_URL` | 数据库连接串 | `sqlite:///./minince.db` | |
| `LOG_LEVEL` | 日志级别 | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL` |
| `LOG_FORMAT` | 日志格式 | `json` | `json` / `text` |
| `LOG_FILE` | 日志文件路径 | `logs/minince.log` | |
| `ENCRYPTION_KEY` | Fernet 加密密钥 | （空） | **production 必填**，用于加密设备密码等敏感字段 |
| `SSH_TIMEOUT` | SSH 连接超时（秒） | `30` | |
| `SSH_PORT` | SSH 默认端口 | `22` | |

### 生成加密密钥

```python
from cryptography.fernet import Fernet
key = Fernet.generate_key()
print(key.decode())
```

将输出填入 `.env` 的 `ENCRYPTION_KEY`，或直接使用 `start.bat` / `scripts/init_env.py` 自动生成。

---

## 访问地址

启动后默认监听 `http://127.0.0.1:8000`。

### Web 管理页面

| 页面 | URL |
|------|-----|
| 首页仪表盘 | `/` |
| 设备管理 | `/devices` |
| 新增设备 | `/devices/new` |
| 设备详情 | `/devices/{device_id}` |
| 拓扑画布 | `/canvas` |
| 配置备份管理 | `/backups` |
| 手动配置 | `/manual-config` |
| 模板配置 | `/template-config` |

### RESTful API（前缀 `/api/v1`）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/api/v1/stats` | 系统统计信息 |
| GET | `/api/v1/devices` | 设备列表 |
| POST | `/api/v1/devices/{device_id}/backups` | 创建设备配置备份 |
| GET | `/api/v1/backups` | 备份列表（可按 `device_id` 过滤） |
| POST | `/api/v1/backups/{backup_id}/restore` | 恢复指定备份 |
| DELETE | `/api/v1/backups/{backup_id}` | 删除指定备份 |
| POST | `/api/v1/devices/{device_id}/vlan/preview` | VLAN 配置预览 |
| POST | `/api/v1/devices/{device_id}/vlan/deploy` | VLAN 配置下发 |
| GET | `/api/v1/devices/{device_id}/vlan/state/{vlan_id}` | 查询指定 VLAN 状态 |
| POST | `/api/v1/devices/{device_id}/ospf/preview` | OSPF 配置预览 |
| POST | `/api/v1/devices/{device_id}/ospf/deploy` | OSPF 配置下发 |
| GET | `/api/v1/devices/{device_id}/ospf/state` | 查询 OSPF 状态 |

### 拓扑画布 API（前缀 `/canvas/api`）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/canvas/api/devices` | 获取画布上的设备列表 |
| POST | `/canvas/api/devices/{device_id}/position` | 设置设备坐标 |
| PATCH | `/canvas/api/devices/{device_id}/position` | 更新设备坐标 |
| PATCH | `/canvas/api/devices/{device_id}/type` | 更新设备类型 |
| POST | `/canvas/api/devices/{device_id}/remove` | 从画布移除设备 |

### 开发者文档

- Swagger UI（交互式 API 文档）：`http://127.0.0.1:8000/docs`
- ReDoc（只读 API 文档）：`http://127.0.0.1:8000/redoc`

---

## 运行测试

```bash
# 运行所有测试
pytest

# 运行单元测试
pytest tests/unit/

# 运行集成测试
pytest tests/integration/

# 运行领域测试
pytest tests/domain/

# 带覆盖率运行（默认阈值 80%）
pytest --cov=src/minince tests/
```

测试配置见 `pyproject.toml` 的 `[tool.pytest.ini_options]`：

- `testpaths = ["tests"]`
- `asyncio_mode = "auto"`
- `pythonpath = ["src"]`

### 代码检查

```bash
# ruff 检查与格式化
ruff check src tests
ruff format src tests

# 类型检查
mypy src
```

---

## 开发规范

### 代码风格
- 使用 type hints（Python 3.12+ 语法，如 `str | None`）。
- 遵循 PEP 8，行宽上限 100（`ruff` 配置）。
- 使用 `ruff` 进行代码检查与格式化，`mypy` 进行类型检查。

### 提交规范
- 每个功能模块独立提交。
- 提交信息遵循 [Conventional Commits](https://www.conventionalcommits.org/) 规范，例如：
  - `feat: 新增 OSPF 配置预览功能`
  - `fix: 修复设备连接超时未释放资源的问题`
  - `docs: 更新 README 架构说明`
  - `refactor: 重构 SSH 连接抽象层`

### 分层约定
- **领域层**不允许依赖任何框架（无 SQLAlchemy / FastAPI 导入）。
- **基础设施层**实现领域层定义的接口，负责技术细节。
- **应用层**编排领域对象与基础设施，不直接处理 HTTP 细节。
- **Web 层**只负责请求解析、调用应用服务、返回响应。

---

## 版本历史

### v0.3.0（当前）
- 添加 SSH 连接抽象层（`Protocol` 接口）
- 实现 Mock / Paramiko / Netmiko 三种 SSH 后端
- 实现配置备份与恢复服务
- 实现模板变量渲染引擎（含白名单校验）
- 新增 OSPF 配置管理（预览 / 下发 / 状态读取）
- 新增设备拓扑画布（拖拽定位、设备类型区分）
- 新增手动配置页面与模板配置页面
- 强化安全配置校验（production 环境强制加密密钥、禁 Debug、禁 0.0.0.0）
- 新增 `start.bat` 一键启动脚本与 `.env` 自动初始化

### v0.2.0
- 实现华为 VRP 设备驱动
- 实现 VLAN 和接口配置管理
- 实现任务执行器和完整生命周期
- 添加 Web 管理界面

### v0.1.0
- 初始化项目骨架
- 配置 FastAPI、SQLAlchemy、Jinja2
- 实现基础 CRUD 和状态机
- 引入 Fernet 加密、结构化日志、风险分级

---

## 许可证

MIT License
