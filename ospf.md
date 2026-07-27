## OSPF 的参数比 VLAN 更多，建议按“进程、区域、接口、路由发布、高级特性、验证”来分。
```
OSPF 配置
├── 1、OSPF 进程参数
│   ├── Process ID
│   │   └── 本地进程编号，只在本设备有效
│   ├── Router ID
│   │   └── OSPF 路由器唯一标识
│   ├── OSPF 版本
│   │   ├── OSPFv2：IPv4
│   │   └── OSPFv3：IPv6
│   ├── Preference
│   │   └── OSPF 路由优先级
│   ├── Default Cost
│   │   └── 默认路由开销
│   └── Description
│       └── 进程描述
│
├── 2、区域参数
│   ├── Area ID
│   │   ├── 十进制格式：0
│   │   └── 点分十进制：0.0.0.0
│   ├── 区域类型
│   │   ├── Backbone Area
│   │   ├── Normal Area
│   │   ├── Stub Area
│   │   ├── Totally Stub Area
│   │   ├── NSSA
│   │   └── Totally NSSA
│   ├── 区域认证
│   │   ├── Simple
│   │   ├── MD5
│   │   └── HMAC-SHA
│   ├── Stub 默认路由开销
│   ├── NSSA 默认路由
│   └── Virtual Link
│       ├── Transit Area
│       └── Peer Router ID
│
├── 3、网络宣告参数
│   ├── Network Address
│   ├── Wildcard Mask
│   ├── Area ID
│   ├── 精确宣告接口地址
│   └── 批量宣告网段
│
├── 4、接口参数
│   ├── OSPF Enable
│   │   └── 在接口上启用 OSPF
│   ├── Area ID
│   ├── Network Type
│   │   ├── Broadcast
│   │   ├── NBMA
│   │   ├── Point-to-Point
│   │   └── Point-to-Multipoint
│   ├── Cost
│   │   └── 接口开销
│   ├── Hello Interval
│   ├── Dead Interval
│   ├── Retransmit Interval
│   ├── Transmit Delay
│   ├── Priority
│   │   └── DR/BDR 选举优先级
│   ├── MTU
│   ├── Silent Interface
│   │   └── 不发送 Hello，但仍发布网段
│   ├── Authentication
│   │   ├── Simple Password
│   │   ├── MD5 Key ID
│   │   └── Cipher Password
│   └── BFD
│       ├── Enable
│       ├── Min TX
│       ├── Min RX
│       └── Detect Multiplier
│
├── 5、邻居参数
│   ├── Neighbor IP
│   ├── Poll Interval
│   ├── NBMA Peer
│   ├── Static Peer
│   └── Peer Cost
│
├── 6、路由引入参数
│   ├── Import Route
│   │   ├── Direct
│   │   ├── Static
│   │   ├── RIP
│   │   ├── IS-IS
│   │   ├── BGP
│   │   └── 其他 OSPF 进程
│   ├── External Type
│   │   ├── Type 1
│   │   └── Type 2
│   ├── Cost
│   ├── Tag
│   ├── Route Policy
│   └── Limit
│
├── 7、默认路由参数
│   ├── Default Route Advertise
│   ├── Always
│   ├── Cost
│   ├── Type
│   │   ├── Type 1
│   │   └── Type 2
│   └── Route Policy
│
├── 8、路由过滤参数
│   ├── Filter Policy Import
│   ├── Filter Policy Export
│   ├── ACL
│   ├── IP Prefix
│   ├── Route Policy
│   └── ABR Summary Filter
│
├── 9、路由聚合参数
│   ├── ABR Aggregation
│   ├── ASBR Aggregation
│   ├── Summary Network
│   ├── Advertise
│   ├── Not Advertise
│   └── Cost
│
├── 10、LSA 控制参数
│   ├── LSA Generation Interval
│   ├── LSA Arrival Interval
│   ├── SPF Calculation Interval
│   ├── Maximum LSA
│   ├── LSA Filter
│   └── LSA Type 控制
│
├── 11、DR/BDR 参数
│   ├── Interface Priority
│   ├── DR Election
│   ├── BDR Election
│   └── DR Other
│
├── 12、性能与收敛参数
│   ├── SPF Timer
│   ├── LSA Timer
│   ├── Fast Convergence
│   ├── BFD
│   ├── Incremental SPF
│   ├── Smart Discover
│   └── Neighbor Flapping Suppression
│
├── 13、可靠性参数
│   ├── Graceful Restart
│   │   ├── GR Enable
│   │   ├── Helper Mode
│   │   └── Restart Interval
│   ├── NSR
│   ├── Stub Router
│   ├── Max Metric Router LSA
│   └── Link Down Delay
│
├── 14、特殊功能
│   ├── Sham Link
│   ├── Virtual Link
│   ├── OSPF VPN Instance
│   ├── Multi-Area Adjacency
│   ├── OSPF-LDP Synchronization
│   ├── Segment Routing
│   └── SRv6
│
└── 15、查询与维护
    ├── 查看 OSPF 进程
    ├── 查看 OSPF 邻居
    ├── 查看 OSPF 接口
    ├── 查看 OSPF 路由
    ├── 查看 LSDB
    ├── 查看 Peer 状态
    ├── 查看错误信息
    └── 查看统计信息
```
## 不建议一开始就支持所有参数。最基础的 OSPF 数据结构可以先做成：
```
OSPF
├── process_id
├── router_id
├── areas
│   ├── area_id
│   ├── area_type
│   ├── authentication
│   └── networks
│       ├── network
│       ├── wildcard_mask
│       └── interface
├── interfaces
│   ├── interface_name
│   ├── area_id
│   ├── cost
│   ├── network_type
│   ├── hello_interval
│   ├── dead_interval
│   ├── priority
│   ├── silent
│   └── authentication
├── redistribution
│   ├── protocol
│   ├── cost
│   ├── type
│   └── route_policy
└── default_route
    ├── enabled
    ├── always
    ├── cost
    └── type
```