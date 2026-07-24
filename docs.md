你现在是一名资深 Python 架构师、网络自动化工程师和全栈开发工程师，请协助我从零开始实现一个名为 MiniNCE 的网络自动化配置平台。

# 一、项目定位

MiniNCE 是一个部署在内网环境中的轻量级网络自动化管理平台，主要用于连接和管理网络设备。

它不是简单的网络命令生成器，而是一个具备完整任务生命周期的网络自动化平台，需要支持：

1、用户提交网络配置需求。

2、系统将需求转换为结构化配置意图。

3、根据设备厂商和功能模板生成设备配置。

4、通过 SSH 自动连接网络设备。

5、在下发前进行风险检查和配置预览。

6、执行配置下发。

7、读取设备状态并验证执行结果。

8、记录任务、配置、日志和执行结果。

9、为未来配置备份、回滚、设备退役和 AI 运维预留扩展能力。

# 二、当前阶段目标

第一阶段只实现可运行、可扩展、可验证的基础版本，不要一次性堆积过多功能。

第一阶段需要支持：

1、华为 VRP 网络设备。

2、SSH 自动连接设备。

3、设备信息管理。

4、VLAN 创建、修改和删除。

5、接口基础配置。

6、接口加入 VLAN。

7、配置模板管理。

8、配置预览。

9、任务创建与执行。

10、任务执行日志。

11、执行结果验证。

12、SQLite 数据持久化。

13、基于 FastAPI 模板系统的 Web 管理界面。

# 三、技术架构要求

项目采用轻量级单体架构，不使用前后端分离。

建议技术栈如下：

- Python 3.12+
- FastAPI
- Jinja2 Templates
- HTMX，可选
- SQLAlchemy 2.x
- Alembic
- SQLite
- Pydantic 2.x
- Netmiko 或基于 Paramiko 封装的 SSH 连接层
- pytest
- structlog 或标准 logging
- cryptography，用于敏感字段加密
- uv 或 Poetry，用于依赖管理

项目主要部署在能够访问网络设备管理地址的内网服务器或个人计算机中。

不要为了所谓“微服务化”而拆分服务，也不要引入 Redis、Celery、Kafka、Kubernetes 等当前阶段不需要的组件。

但代码结构必须允许未来将任务执行器独立部署。

# 四、核心设计原则

所有实现必须遵循以下原则。

## 1、模块化

每个模块只负责明确的业务职责。

禁止将路由、数据库操作、设备连接、配置生成和业务判断全部写在同一个文件中。

## 2、高内聚、低耦合

领域逻辑不得直接依赖 FastAPI、Jinja2、Netmiko 或具体数据库实现。

外部技术组件必须通过接口或适配器接入。

## 3、可扩展性

必须考虑未来支持：

- 华为 VRP
- Cisco IOS
- H3C Comware
- Juniper Junos
- OSPF
- BGP
- ACL
- VPN
- 配置备份
- 精确回滚
- 设备优雅退役
- AI 辅助运维

禁止在核心业务代码中大量使用：

```python
if vendor == "huawei":
    ...
elif vendor == "cisco":
    ...
```

应使用驱动注册、策略模式、工厂模式或插件机制。

## 4、幂等性

同一个配置任务重复执行时，不应无意义地重复配置，也不应导致配置异常。

例如：

- VLAN 100 已存在时，不应重复创建。
- 接口已经加入目标 VLAN 时，不应重复修改。
- 当前配置已经满足目标状态时，应返回无需变更。

每个配置功能应尽可能实现：

- 当前状态读取。
- 期望状态描述。
- 差异计算。
- 配置命令生成。
- 执行后验证。

## 5、状态管理

系统不能只保存最终生成的命令。

必须保存：

- 用户原始输入。
- 结构化配置意图。
- 任务当前状态。
- 配置预览。
- 实际下发命令。
- 设备返回结果。
- 验证结果。
- 错误信息。
- 操作时间。
- 操作用户。

## 6、防误操作

所有修改设备配置的任务必须经过明确的执行流程。

建议流程：

```text
DRAFT
→ VALIDATING
→ READY
→ RUNNING
→ VERIFYING
→ SUCCEEDED / FAILED / PARTIAL
```

执行前必须支持：

- 参数校验。
- 设备连通性检查。
- 配置命令预览。
- 风险提示。
- 用户确认。
- 高风险操作拦截。

删除 VLAN、关闭接口、清空配置等操作应被标记为高风险操作。

## 7、所有操作可追踪

每次任务都必须拥有唯一任务编号。

必须能够查询：

- 谁创建了任务。
- 对哪台设备执行。
- 执行了什么操作。
- 生成了什么命令。
- 设备返回了什么。
- 是否验证成功。
- 在什么时间执行。
- 失败在哪个步骤。

# 五、架构分层

建议采用接近整洁架构或六边形架构的分层方式，但不要过度设计。

建议目录结构：

```text
minince/
├── pyproject.toml
├── README.md
├── .env.example
├── alembic.ini
├── migrations/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
└── src/
    └── minince/
        ├── main.py
        ├── config.py
        ├── logging.py
        │
        ├── domain/
        │   ├── devices/
        │   ├── tasks/
        │   ├── templates/
        │   └── network/
        │
        ├── application/
        │   ├── services/
        │   ├── commands/
        │   ├── queries/
        │   └── dto/
        │
        ├── infrastructure/
        │   ├── database/
        │   ├── ssh/
        │   ├── vendors/
        │   │   └── huawei_vrp/
        │   ├── repositories/
        │   └── security/
        │
        ├── web/
        │   ├── routers/
        │   ├── schemas/
        │   ├── dependencies.py
        │   ├── templates/
        │   └── static/
        │
        └── shared/
            ├── exceptions.py
            ├── enums.py
            ├── result.py
            └── utils.py
```

可以根据实际实现调整目录，但必须说明调整理由。

# 六、核心领域模型

至少设计以下领域对象。

## 1、Device

字段建议：

- id
- name
- hostname
- management\_ip
- port
- username
- encrypted\_password
- vendor
- platform
- connection\_type
- status
- last\_connected\_at
- created\_at
- updated\_at

密码不得以明文保存。

设备对象不应直接负责数据库读写。

## 2、ConfigTask

字段建议：

- id
- task\_number
- task\_type
- device\_id
- status
- risk\_level
- original\_request
- structured\_intent
- generated\_commands
- execution\_output
- verification\_output
- error\_message
- created\_by
- created\_at
- started\_at
- completed\_at

## 3、TaskStep

用于记录任务每一个执行步骤，例如：

- 参数验证
- 连接设备
- 获取当前状态
- 计算差异
- 生成配置
- 下发配置
- 保存配置
- 状态验证

字段建议：

- id
- task\_id
- step\_name
- status
- input\_data
- output\_data
- error\_message
- started\_at
- completed\_at

## 4、ConfigTemplate

字段建议：

- id
- name
- vendor
- feature
- version
- template\_content
- variable\_schema
- enabled
- created\_at
- updated\_at

## 5、AuditLog

字段建议：

- id
- actor
- action
- resource\_type
- resource\_id
- details
- created\_at

# 七、网络配置意图模型

不要让 Web 表单参数直接传递到设备驱动。

必须定义厂商无关的配置意图对象。

例如 VLAN 意图：

```python
class VlanIntent(BaseModel):
    operation: Literal["create", "update", "delete"]
    vlan_id: int
    name: str | None = None
    description: str | None = None
```

接口配置意图：

```python
class InterfaceIntent(BaseModel):
    interface_name: str
    description: str | None = None
    admin_up: bool | None = None
    link_type: Literal["access", "trunk", "hybrid"] | None = None
    access_vlan: int | None = None
    trunk_allowed_vlans: list[int] | None = None
```

意图模型必须完成完整校验。

例如：

- VLAN ID 范围必须合法。
- access 接口不能同时配置 trunk VLAN。
- trunk 接口不能配置 access\_vlan。
- 删除操作不得携带无关字段。
- 接口名称必须经过格式校验。

# 八、厂商驱动设计

定义统一的设备驱动协议，例如：

```python
class NetworkDeviceDriver(Protocol):
    def test_connection(self) -> ConnectionResult:
        ...

    def get_facts(self) -> DeviceFacts:
        ...

    def get_current_state(self, intent: ConfigIntent) -> CurrentState:
        ...

    def build_plan(
        self,
        intent: ConfigIntent,
        current_state: CurrentState,
    ) -> ConfigPlan:
        ...

    def apply_plan(self, plan: ConfigPlan) -> ExecutionResult:
        ...

    def verify(
        self,
        intent: ConfigIntent,
    ) -> VerificationResult:
        ...
```

华为 VRP 驱动应位于独立模块。

驱动内部可以使用 Netmiko，但应用层不得直接依赖 Netmiko。

驱动应处理：

- 进入 system-view。
- 命令执行。
- 设备提示符。
- 超时。
- 登录失败。
- 配置失败。
- 保存配置。
- 状态查询。
- 输出解析。

命令生成和 SSH 执行应尽量分离，方便单元测试。

# 九、配置计划模型

配置任务不应直接返回字符串列表，应返回结构化配置计划。

例如：

```python
@dataclass
class ConfigPlan:
    device_id: int
    feature: str
    intent: dict
    current_state: dict
    commands: list[str]
    verify_commands: list[str]
    changed: bool
    risk_level: RiskLevel
    warnings: list[str]
```

当 `changed=False` 时，任务应被识别为已经满足目标状态，而不是继续执行配置。

# 十、任务执行器设计

实现统一任务执行器，负责：

1、加载任务。

2、检查任务状态。

3、加载设备信息。

4、测试设备连接。

5、读取当前状态。

6、计算配置差异。

7、生成配置计划。

8、记录配置预览。

9、执行配置。

10、读取执行结果。

11、执行状态验证。

12、更新任务状态。

13、记录每个任务步骤。

任务执行器不得包含具体华为命令。

具体命令应由厂商驱动负责。

需要处理异常状态：

- 连接失败。
- 认证失败。
- 获取状态失败。
- 配置命令失败。
- 部分命令成功。
- 验证失败。
- 数据库记录失败。
- 用户重复执行任务。

# 十一、Web 界面要求

使用 FastAPI、Jinja2 和少量 JavaScript 或 HTMX。

第一阶段页面至少包括：

1、首页仪表盘。

2、设备列表。

3、新建设备。

4、设备详情。

5、测试设备连接。

6、任务列表。

7、新建 VLAN 配置任务。

8、新建接口配置任务。

9、任务配置预览。

10、任务执行确认。

11、任务详情。

12、任务步骤和日志展示。

13、配置模板列表。

界面不追求复杂视觉设计，但必须：

- 清晰。
- 可操作。
- 有状态提示。
- 有错误提示。
- 高风险操作有明显警告。
- 不允许通过普通 GET 请求执行配置修改。

# 十二、数据库要求

使用 SQLAlchemy 2.x 和 Alembic。

要求：

- 使用声明式模型。
- Repository 层封装数据库访问。
- 应用层不得直接编写 SQLAlchemy 查询。
- 支持事务。
- 任务状态更新和步骤记录应尽量保持一致性。
- SQLite 启用合理的连接配置。
- 为未来迁移 PostgreSQL 保留兼容性。

不要使用只适用于 SQLite 的特殊字段设计。

结构化数据可暂时使用 JSON 字段，但要定义清晰的数据格式。

# 十三、安全要求

至少实现：

1、设备密码加密存储。

2、日志中禁止输出密码。

3、异常信息中禁止泄露敏感凭据。

4、Web 表单进行服务端校验。

5、所有设备修改操作使用 POST。

6、防止重复提交任务。

7、限制高风险命令。

8、禁止用户直接提交任意 CLI 命令。

9、模板变量必须经过白名单校验。

10、禁止通过模板注入执行任意代码。

不要实现“输入任意命令然后 SSH 下发”的功能。

# 十四、测试要求

必须同步编写测试，不允许所有功能完成后再补测试。

至少包含：

## 1、单元测试

- VLAN 意图参数校验。
- 接口意图参数校验。
- 华为 VLAN 命令生成。
- 华为接口命令生成。
- 幂等性判断。
- 风险等级判断。
- 任务状态流转。
- 配置计划生成。

## 2、集成测试

- Repository 数据读写。
- FastAPI 路由。
- 创建任务流程。
- 模拟设备驱动执行任务。
- 执行失败状态记录。
- 验证失败状态记录。

不得要求测试环境必须连接真实网络设备。

SSH 和设备驱动必须可替换为 Fake 或 Mock。

# 十五、代码质量要求

所有代码必须：

- 提供类型注解。
- 避免超大函数。
- 避免万能 Service 类。
- 避免循环依赖。
- 避免全局可变状态。
- 避免在路由中编写业务逻辑。
- 避免在 ORM 模型中堆积复杂业务逻辑。
- 避免重复代码。
- 使用明确的领域异常。
- 对外部异常进行转换。
- 使用统一结果对象或异常处理机制。
- 使用统一日志结构。
- 关键代码添加必要注释，但不要写无意义注释。

建议配置：

- ruff
- mypy
- pytest
- pytest-cov
- pre-commit

# 十六、开发方式

不要直接一次性生成整个项目的所有代码。

请严格采用分阶段实现方式。

每个阶段开始前，先输出：

1、本阶段目标。

2、准备新增或修改的文件。

3、核心设计决策。

4、可能的风险。

然后开始生成代码。

每个阶段完成后，输出：

1、本阶段完成内容。

2、项目当前可运行能力。

3、测试方式。

4、尚未完成内容。

5、下一阶段建议。

每次只实现一个可验证的小阶段，确保代码始终处于可以运行或可以测试的状态。

# 十七、Grill Me 需求澄清机制

在实现存在重大不确定性的功能前，必须启动 Grill Me 机制。

Grill Me 的目标是主动发现需求漏洞，而不是简单询问“是否继续”。

当以下信息不明确时，应向用户提出集中、具体的问题：

- 业务目标不清晰。
- 数据模型存在多种合理方案。
- 操作是否需要人工确认不明确。
- 幂等性判断方式不明确。
- 回滚策略不明确。
- 风险边界不明确。
- 页面流程不明确。
- 网络设备行为可能因版本而异。
- 需要引入新的技术依赖。
- 设计会影响未来扩展。
- 用户要求可能破坏现有架构。

提问应满足：

1、每个问题只聚焦一个决策。

2、说明该决策会影响什么。

3、尽量提供推荐选项。

4、不要询问可以通过现有上下文直接推断的问题。

5、不要因小问题阻塞开发，可以采用合理默认值并明确记录。

示例：

```text
Grill Me 1：
任务在生成配置预览后，是否必须由用户再次点击确认才能执行？

A、必须人工确认，安全性更高，推荐。
B、普通任务自动执行，高风险任务人工确认。
C、全部自动执行。

该选择会影响任务状态机和后续批量任务设计。
```

# 十八、第一轮任务

现在先不要实现全部功能。

第一轮只完成“项目基础骨架与架构落地”，包括：

1、初始化 Python 项目。

2、创建推荐目录结构。

3、配置 FastAPI 应用。

4、配置 Jinja2 模板。

5、配置 SQLAlchemy 和 SQLite。

6、配置 Alembic。

7、配置统一设置管理。

8、配置统一日志。

9、定义基础异常。

10、定义任务状态和风险等级枚举。

11、实现健康检查接口。

12、实现简单首页。

13、编写对应测试。

14、编写 README 启动说明。

第一轮暂时不要实现：

- 真实 SSH。
- VLAN 配置。
- 接口配置。
- AI 功能。
- 用户权限系统。
- 后台任务队列。
- 配置回滚。

# 十九、第一轮输出要求

请先输出以下内容，不要马上生成全部代码：

1、你对 MiniNCE 项目的理解。

2、建议的第一阶段项目目录。

3、各层职责说明。

4、关键依赖选择和原因。

5、第一轮实施步骤。

6、需要我确认的 Grill Me 问题。

在需求确认完成后，再开始逐文件生成代码。

生成代码时，每个文件使用以下格式：

````text
文件路径：
src/minince/main.py

文件作用：
FastAPI 应用入口。

完整代码：
```python
# code
````

```

不得只输出代码片段，必须输出该阶段涉及文件的完整内容。

不得省略 import，不得使用“其他代码保持不变”等表达。

所有生成的代码必须能够相互对应，避免文件名、导入路径、类名和配置项不一致。
```

