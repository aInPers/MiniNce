<br />

建议下一阶段先实现 **OSPFv2 基础闭环**：

### 第一版实现范围

支持以下能力：

- 创建、修改、删除 OSPF 进程
- 配置 Router ID
- 创建 Area
- 发布 IPv4 网段
- 接口方式启用 OSPF
- 配置接口 Cost
- 配置接口 Network Type
- 配置静默接口
- OSPF 简单认证和 HMAC-MD5 密文认证
- 配置前预览
- 配置后状态验证
- 任务日志及风险等级
- 幂等生成
- 删除配置时的精确命令生成

暂时不要加入：

- Stub、NSSA
- 路由引入
- 路由聚合
- Filter-policy
- Virtual Link
- OSPFv3
- 多进程重分发

这些功能应在基础模型稳定后逐步增加。

## 推荐目录调整

```
src/minince/
├── domain/network/
│   ├── intents.py
│   ├── config_plan.py
│   └── ospf/
│       ├── __init__.py
│       ├── models.py
│       ├── intents.py
│       ├── validators.py
│       └── state.py
├── application/services/
│   ├── ospf_plan_service.py
│   └── ospf_verification_service.py
├── infrastructure/drivers/huawei_vrp/
│   ├── ospf_renderer.py
│   ├── ospf_parser.py
│   └── ospf_verifier.py
└── web/
    ├── api/
    │   └── ospf.py
    └── templates/
        └── ospf/

```

不要把 OSPF 的所有逻辑继续堆进 `intents.py` 或华为主驱动文件。当前仓库已经把领域层、应用层和驱动层分开，OSPF 也应保持相同分层。([GitHub](https://github.com/aInPers/MiniNce/tree/master/src/minince "MiniNce/src/minince at master · aInPers/MiniNce · GitHub"))

## 核心领域模型

建议使用设备无关模型：

```
from enum import StrEnum
from ipaddress import IPv4Address, IPv4Network
from pydantic import BaseModel, Field, field_validator


class OspfOperation(StrEnum):
    ENSURE_PRESENT = "ensure_present"
    ENSURE_ABSENT = "ensure_absent"


class OspfNetworkType(StrEnum):
    BROADCAST = "broadcast"
    P2P = "p2p"
    NBMA = "nbma"
    P2MP = "p2mp"


class OspfAuthType(StrEnum):
    NONE = "none"
    SIMPLE = "simple"
    HMAC_MD5 = "hmac_md5"


class OspfNetworkIntent(BaseModel):
    network: IPv4Network
    area_id: IPv4Address


class OspfInterfaceIntent(BaseModel):
    interface_name: str
    area_id: IPv4Address
    cost: int | None = Field(default=None, ge=1, le=65535)
    network_type: OspfNetworkType | None = None
    silent: bool = False
    auth_type: OspfAuthType = OspfAuthType.NONE
    auth_key_id: int | None = Field(default=None, ge=1, le=255)
    auth_secret: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        repr=False,
    )


class OspfProcessIntent(BaseModel):
    operation: OspfOperation = OspfOperation.ENSURE_PRESENT
    process_id: int = Field(ge=1, le=65535)
    router_id: IPv4Address | None = None
    networks: list[OspfNetworkIntent] = Field(default_factory=list)
    interfaces: list[OspfInterfaceIntent] = Field(default_factory=list)

    @field_validator("interfaces")
    @classmethod
    def reject_duplicate_interfaces(
        cls,
        interfaces: list[OspfInterfaceIntent],
    ) -> list[OspfInterfaceIntent]:
        names = [item.interface_name.casefold() for item in interfaces]
        if len(names) != len(set(names)):
            raise ValueError("OSPF interface names must be unique")
        return interfaces

```

认证密码不能写入普通任务日志、配置差异文本或异常信息。任务记录中只保存类似：

```
{
  "auth_type": "hmac_md5",
  "auth_key_id": 1,
  "auth_secret_configured": true
}

```

## 华为 VRP 命令映射

进程与网段模式：

```
system-view
ospf 1 router-id 10.0.0.1
area 0.0.0.0
network 10.0.0.0 0.0.0.255
quit
quit

```

接口方式：

```
system-view
interface GigabitEthernet0/0/1
ospf enable 1 area 0.0.0.0
ospf cost 10
ospf network-type p2p
quit

```

静默接口：

```
ospf 1
silent-interface GigabitEthernet0/0/2

```

删除时必须根据意图精确生成，例如：

```
ospf 1
area 0.0.0.0
undo network 10.0.0.0 0.0.0.255

```

或者：

```
interface GigabitEthernet0/0/1
undo ospf enable
undo ospf cost
undo ospf network-type

```

不能默认通过 `undo ospf 1` 删除整个进程，除非用户明确请求删除进程并通过高风险确认。

## 幂等流程

执行器不应该直接渲染目标配置，而应执行：

```
用户意图
  ↓
读取设备当前 OSPF 状态
  ↓
标准化当前状态
  ↓
比较期望状态与当前状态
  ↓
生成 ConfigPlan
  ↓
风险检查
  ↓
命令预览
  ↓
执行
  ↓
重新读取状态
  ↓
验证

```

建议配置计划保存：

```
class OspfConfigPlan(BaseModel):
    process_id: int
    commands: list[str]
    verification_commands: list[str]
    changed_fields: list[str]
    risk_level: str
    requires_confirmation: bool
    expected_state: dict
    rollback_commands: list[str]

```

注意，第一版的 `rollback_commands` 只能用于本次明确新增或修改的配置，不要声称它已经实现完整精确回滚。

## 状态读取与验证

至少执行：

```
display ospf brief
display ospf peer
display ospf interface
display current-configuration configuration ospf

```

验证分为三层：

1. 配置存在性：进程、Area、网段和接口命令是否存在。
2. 运行状态：进程是否启动、接口是否进入预期 Area。
3. 邻居状态：仅当用户要求验证邻居时，检查邻居是否达到 Full；没有配置对端时，不应把“无邻居”直接判为失败。

验证结果建议：

```
class OspfVerificationResult(BaseModel):
    configuration_valid: bool
    process_running: bool
    interfaces_valid: bool
    neighbors_expected: bool
    neighbors_full: bool | None
    warnings: list[str]
    evidence: dict[str, str]

```

## 风险控制

风险等级建议：

- 新增 OSPF 进程：中风险
- 新增 Network 或接口启用：中风险
- 修改 Cost、Network Type：中风险
- 修改认证：高风险
- 删除 Network：高风险
- 删除进程：高风险
- Router ID 变更：高风险，提示可能导致 OSPF 进程重启或邻接变化

以下情况必须阻止执行：

- Area ID 非法
- 网段重叠且归属不同 Area
- 同一接口重复配置不同 Area
- 认证类型与必要参数不匹配
- 用户输入原始换行符或命令分隔符
- 接口名称不符合允许格式
- 删除整个进程但未明确确认

## API 设计

```
POST /api/v1/devices/{device_id}/ospf/preview
POST /api/v1/devices/{device_id}/ospf/tasks
GET  /api/v1/devices/{device_id}/ospf/state
GET  /api/v1/tasks/{task_id}/ospf/verification

```

示例请求：

```
{
  "process_id": 1,
  "router_id": "10.255.0.1",
  "networks": [
    {
      "network": "10.10.10.0/24",
      "area_id": "0.0.0.0"
    }
  ],
  "interfaces": [
    {
      "interface_name": "GigabitEthernet0/0/1",
      "area_id": "0.0.0.0",
      "cost": 10,
      "network_type": "p2p",
      "silent": false,
      "auth_type": "none"
    }
  ]
}

```

## 必须添加的测试

```
tests/domain/network/ospf/
├── test_models.py
├── test_validators.py
└── test_state_diff.py

tests/infrastructure/drivers/huawei_vrp/
├── test_ospf_renderer.py
├── test_ospf_parser.py
└── test_ospf_verifier.py

tests/application/
├── test_ospf_plan_service.py
└── test_ospf_task_execution.py

```

重点覆盖：

- 相同状态不生成命令
- 新增网段只生成新增命令
- 删除单个网段不删除进程
- Router ID 变更标记高风险
- 明文认证密码不出现在日志
- 密文认证缺少 Key ID 时拒绝
- 相同接口配置不同 Area 时拒绝
- 无邻居预期时不会误判失败
- 命令执行失败后任务状态正确
- Mock SSH 下完整生命周期可运行

当前最合理的开发顺序是：**领域模型 → 华为命令渲染 → 状态解析 → 差异计划 → 验证器 → API → Web 页面**。仓库 README 显示已有配置预览、差异计算、任务生命周期、结果验证和 Mock SSH，因此 OSPF 应复用这些机制，而不是重新实现一套执行系统。([GitHub](https://github.com/aInPers/MiniNce "GitHub - aInPers/MiniNce · GitHub"))

要让我直接修改并交付可运行代码，需要把仓库 ZIP 上传到当前对话，或提供可写的 GitHub/Codex 工作区；当前公开链接本身不授予代码写入能力。
