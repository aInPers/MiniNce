# MiniNCE - 轻量级网络自动化配置平台

MiniNCE 是一个部署在内网环境中的轻量级网络自动化管理平台，主要用于连接和管理网络设备，支持配置自动化下发。

## 功能特性

### 第一阶段已实现
- ✅ FastAPI Web 应用框架
- ✅ SQLite 数据库持久化
- ✅ SQLAlchemy ORM 模型
- ✅ Alembic 数据库迁移
- ✅ 设备管理 CRUD
- ✅ 任务管理 CRUD
- ✅ 任务步骤跟踪
- ✅ Fernet 密码加密存储
- ✅ 完整任务状态机 (DRAFT → VALIDATING → READY → RUNNING → VERIFYING → SUCCEEDED/FAILED/PARTIAL)
- ✅ 风险等级管理
- ✅ 结构化日志
- ✅ 健康检查接口
- ✅ 系统首页仪表盘
- ✅ RESTful API

### 待实现
- 🔄 SSH 设备连接
- 🔄 VLAN 配置管理
- 🔄 接口配置管理
- 🔄 配置模板引擎
- 🔄 任务执行器
- 🔄 配置预览
- 🔄 华为 VRP 驱动

## 技术栈

- Python 3.12+
- FastAPI 0.115+
- Jinja2 3.x
- SQLAlchemy 2.x
- Alembic 1.13+
- Pydantic 2.x
- cryptography 42+
- structlog 24+
- pytest 8+

## 快速开始

### 1. 克隆项目

```bash
cd MiniNce
```

### 2. 创建虚拟环境并安装依赖

```bash
py -3.12 -m venv venv

# Windows PowerShell
.\venv\Scripts\Activate.ps1

# 安装依赖
pip install -e ".[dev]"
```

### 3. 配置环境变量

```bash
# 复制示例配置
copy .env.example .env

# 编辑 .env 文件，修改必要配置
```

### 4. 初始化数据库

```bash
# 生成迁移
alembic revision --autogenerate -m "init"

# 执行迁移
alembic upgrade head
```

### 5. 启动应用

```bash
# 开发模式（带热重载）
minince
# 或
py -m minince.main
```

应用将在 `http://localhost:8000` 启动。

### 6. 访问应用

- 首页: http://localhost:8000/
- 健康检查: http://localhost:8000/health
- API 统计: http://localhost:8000/api/v1/stats
- API 文档: http://localhost:8000/docs

## 项目结构

```
src/minince/
├── main.py              # FastAPI 应用入口
├── config.py            # 配置管理
├── logging.py           # 日志配置
├── shared/              # 共享模块
│   ├── enums.py         # 枚举定义
│   ├── exceptions.py    # 异常定义
│   └── result.py        # 结果对象
├── domain/              # 领域层
│   ├── devices/         # 设备领域模型
│   ├── tasks/           # 任务领域模型
│   ├── templates/       # 模板领域模型
│   └── network/         # 网络配置意图
├── application/         # 应用层
│   ├── services/        # 业务服务
│   └── dto/             # 数据传输对象
├── infrastructure/      # 基础设施层
│   ├── database/        # 数据库配置和模型
│   ├── repositories/    # 仓储实现
│   └── security/        # 安全加密
└── web/                 # Web 层
    ├── routers/         # 路由定义
    ├── templates/       # Jinja2 模板
    ├── static/          # 静态文件
    └── dependencies.py  # 依赖注入
```

## 运行测试

```bash
# 运行所有测试
pytest

# 运行单元测试
pytest tests/unit/

# 运行集成测试
pytest tests/integration/

# 带覆盖率运行
pytest --cov=src/minince tests/
```

## 开发规范

### 代码风格
- 使用 type hints
- 遵循 PEP 8
- 使用 ruff 进行代码检查

### 提交规范
- 每个功能模块独立提交
- 提交信息遵循 Conventional Commits 规范

## 配置说明

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| APP_NAME | 应用名称 | MiniNCE |
| APP_VERSION | 应用版本 | 0.1.0 |
| DEBUG | 调试模式 | true |
| HOST | 监听地址 | 0.0.0.0 |
| PORT | 监听端口 | 8000 |
| DATABASE_URL | 数据库连接 | sqlite:///./minince.db |
| LOG_LEVEL | 日志级别 | INFO |
| ENCRYPTION_KEY | 加密密钥 | - |

### 生成加密密钥

```python
from cryptography.fernet import Fernet
key = Fernet.generate_key()
print(key.decode())
```

将生成的密钥配置到 `.env` 文件的 `ENCRYPTION_KEY` 中。

## 许可证

MIT License
