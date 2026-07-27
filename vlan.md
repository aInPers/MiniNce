下面按 **华为 VRP / eNSP 常见配置**整理。VLAN 本身的配置可以分为“VLAN 属性、端口成员、三层网关、协议与高级功能”几部分。

```
VLAN 配置
├── 1、VLAN 基础属性
│   ├── VLAN ID
│   │   └── 取值：1～4094
│   │
│   ├── VLAN 名称
│   │   └── name
│   │
│   ├── VLAN 描述
│   │   └── description
│   │
│   └── VLAN 状态
│       ├── 创建 VLAN
│       └── 删除 VLAN
│
├── 2、接口 VLAN 属性
│   ├── 接口链路类型
│   │   ├── Access
│   │   ├── Trunk
│   │   ├── Hybrid
│   │   └── QinQ
│   │
│   ├── PVID
│   │   ├── Access 默认 VLAN
│   │   ├── Trunk PVID
│   │   └── Hybrid PVID
│   │
│   ├── VLAN 成员关系
│   │   ├── 单个接口加入 VLAN
│   │   ├── 多个接口加入 VLAN
│   │   └── Eth-Trunk 加入 VLAN
│   │
│   ├── VLAN 放行范围
│   │   ├── 放行单个 VLAN
│   │   ├── 放行多个 VLAN
│   │   ├── 放行 VLAN 范围
│   │   └── 放行全部 VLAN
│   │
│   └── 报文标签处理
│       ├── Tagged
│       ├── Untagged
│       ├── 接收带标签报文
│       └── 接收不带标签报文
│
├── 3、VLAN 三层接口
│   ├── VLANIF 接口
│   │   └── interface Vlanif
│   │
│   ├── IPv4 地址
│   │   ├── 主 IP 地址
│   │   └── 从 IP 地址
│   │
│   ├── IPv6 地址
│   │
│   ├── 接口描述
│   │
│   ├── MTU
│   │
│   ├── DHCP
│   │   ├── DHCP Server
│   │   ├── DHCP Relay
│   │   └── DHCP Select
│   │
│   ├── VRRP
│   │   ├── VRID
│   │   ├── 虚拟 IP
│   │   ├── 优先级
│   │   └── 抢占
│   │
│   └── 路由协议
│       ├── OSPF
│       ├── IS-IS
│       ├── RIP
│       └── BGP
│
├── 4、VLAN 批量配置
│   ├── 创建单个 VLAN
│   ├── 批量创建 VLAN
│   ├── 创建连续 VLAN 范围
│   └── 批量删除 VLAN
│
├── 5、VLAN 业务类型
│   ├── 普通 VLAN
│   ├── 管理 VLAN
│   ├── Voice VLAN
│   ├── Guest VLAN
│   ├── Auth-Fail VLAN
│   ├── Super VLAN
│   ├── Sub VLAN
│   └── MUX VLAN
│
├── 6、VLAN 划分方式
│   ├── 基于接口划分
│   ├── 基于 MAC 地址划分
│   ├── 基于 IP 子网划分
│   ├── 基于协议划分
│   └── 基于策略划分
│
├── 7、VLAN 映射与转换
│   ├── VLAN Mapping
│   │   ├── 1 对 1 映射
│   │   ├── 多对 1 映射
│   │   └── 2 层 VLAN 映射
│   │
│   ├── QinQ
│   │   ├── 基本 QinQ
│   │   ├── 灵活 QinQ
│   │   ├── 外层 VLAN
│   │   └── 内层 VLAN
│   │
│   └── VLAN Stacking
│
├── 8、VLAN 安全功能
│   ├── VLAN 内端口隔离
│   ├── DHCP Snooping
│   ├── IP Source Guard
│   ├── Dynamic ARP Inspection
│   ├── ARP 防攻击
│   ├── MAC 地址学习限制
│   ├── MAC 地址静态绑定
│   └── 广播、组播、未知单播抑制
│
├── 9、VLAN 与生成树
│   ├── STP
│   ├── RSTP
│   ├── MSTP
│   │   ├── VLAN 映射到 MST 实例
│   │   ├── Region Name
│   │   ├── Revision Level
│   │   └── Instance
│   └── VBST
│       └── 每 VLAN 生成树
│
├── 10、VLAN 与组播
│   ├── IGMP Snooping
│   ├── IGMP Querier
│   ├── 组播 VLAN
│   ├── Router Port
│   └── 静态组播成员
│
├── 11、VLAN 与 QoS
│   ├── VLAN 优先级
│   ├── 802.1p 优先级
│   ├── DSCP 映射
│   ├── 流量策略
│   ├── 流量监管
│   └── 流量整形
│
└── 12、VLAN 查询与维护
    ├── 查看 VLAN
    ├── 查看 VLAN 简要信息
    ├── 查看 VLAN 中的接口
    ├── 查看接口 VLAN 配置
    ├── 查看 VLANIF
    ├── 查看 MAC 地址表
    └── 查看 VLAN 统计信息
```

## 最常用的参数

对 MiniNCE 第一阶段来说，真正需要优先支持的可以简化成：

```
VLAN
├── vlan_id
├── name
├── description
├── device_id
├── interfaces
│   ├── interface_name
│   ├── link_type
│   ├── pvid
│   ├── allowed_vlans
│   ├── tagged_vlans
│   └── untagged_vlans
├── gateway
│   ├── vlanif_id
│   ├── ip_address
│   ├── subnet_mask
│   └── description
└── advanced
    ├── dhcp_mode
    ├── vrrp
    ├── mstp_instance
    ├── igmp_snooping
    └── port_isolation
```

