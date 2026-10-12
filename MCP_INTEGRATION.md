# MCP_INTEGRATION.md — 麦当劳 MCP 集成说明

## 1. 使用的 MCP Server

| 项目 | 内容 |
|---|---|
| Server 名称 | `mcd-mcp`（麦当劳中国 MCP Server） |
| 接入地址 | `https://mcp.mcd.cn` |
| 传输协议 | Streamable HTTP |
| 认证方式 | 请求头 `Authorization: Bearer <MCP_TOKEN>` |
| Token 申请 | https://open.mcd.cn/mcp （手机号登录 → 控制台 → 激活 → 一键复制） |
| 官方仓库/文档 | https://github.com/M-China/mcd-mcp-server ｜ https://open.mcd.cn/mcp |
| 限流 | 600 次/分钟/Token |
| 错误码 | 401 = Token 无效/过期/未提供；429 = 触发限流 |
| 服务范围 | 中国大陆地区（不含港澳台） |

MCP Client 配置示例（WorkBuddy 自定义连接器 / 其他 MCP Client 通用）：

```json
{
  "mcpServers": {
    "mcd-mcp": {
      "type": "streamablehttp",
      "url": "https://mcp.mcd.cn",
      "headers": {
        "Authorization": "Bearer YOUR_MCP_TOKEN"
      }
    }
  }
}
```

## 2. 实际使用的 Tool 清单

| Tool | 在本项目中的用途 | 关键参数 |
|---|---|---|
| `query-nearby-stores` | 查询附近可用门店，两条路径的公共起点 | `searchType`(1收藏/2位置/3经纬度)、`beType`(1到店自取/5得来速)、`city`、`keyword`、`latitude`、`longitude` |
| `query-my-coupons` | 路径 A：读取已领券，提取券适用餐品；路径 B：标注"已拥有"的券 | 无入参 |
| `available-coupons` | 路径 B：查询当前可领取的麦麦省券列表 | 无入参 |
| `auto-bind-coupons` | 路径 A：用户要求领券时一键领取 | 无入参 |
| `query-meals` | 两条路径：逐店核实目标餐品是否在售 | `storeCode`、`beCode`、`orderType`(1到店/2外送)、`beType` |
| `query-store-coupons` | 路径 A：核实目标券是否在本店可用 | `storeCode`、`beCode`、`orderType`、`beType` |
| `query-meal-detail` | 可选：查看套餐组成/替换选项 | `storeCode`、`beCode`、`code` |
| `now-time-info` | 可选：获取服务器时间，辅助判断券有效期/营业状态 | 无入参 |

> `storeCode` / `beCode` 一律取自 `query-nearby-stores` 的返回值，严禁凭空生成。

## 3. 调用流程

### 路径 A · 领券后查询（coupon-first）

```
用户："我刚领了麦辣鸡腿堡套餐的券，附近哪家店能用的？"
  │
  ├─ [可选] auto-bind-coupons ───────────► 一键领取所有可领券
  ├─ query-my-coupons ──────────────────► 已领券列表 → 匹配目标券
  │                                        └─ 提取适用餐品（productCode / 券名解析）
  ├─ query-nearby-stores ───────────────► 附近门店列表（storeCode + beCode）
  └─ for each 门店（≤10 家，间隔 ≥0.2s）：
       ├─ query-meals ──────────────────► 该餐品是否在售 + 售价
       └─ query-store-coupons ──────────► 该券是否在本店可用
  │
  └─► 输出：有售门店表 + 券可用门店 + 结论
```

### 路径 B · 指定餐品查询（meal-first）

```
用户："我想吃巨无霸套餐，附近哪家有？有没有券？"
  │
  ├─ query-nearby-stores ───────────────► 附近门店列表
  ├─ for each 门店（≤10 家，间隔 ≥0.2s）：
  │    └─ query-meals ──────────────────► 名称模糊匹配 → 在售门店 + 价格
  ├─ available-coupons ─────────────────► 可领取券 → 匹配该餐品相关券
  ├─ query-my-coupons ──────────────────► 卡包中该餐品相关券（标注"已拥有"）
  └─► 输出：有售门店表 + 可领券 + 已拥有券 + 结论
```

## 4. 业务价值

- **解决真实痛点**：麦当劳的券包和门店供应是两张独立的网——用户经常"领了券却不知道去哪家店用"，或"想吃某餐品却不知道哪家店有售、有没有券"。本 Skill 把「券 × 餐品 × 门店」三者交叉验证，给出可直接执行的到店结论。
- **两条路径覆盖两类高频场景**：券驱动（领券后用券）与餐品驱动（想吃某东西再找券），并在入口处清晰切换，降低用户表达成本。
- **尊重官方边界**：只读查询 + 领券，不碰下单支付；全链路使用官方 MCP 实时数据，价格/供应状态有时效性说明。

## 5. 错误处理与降级

| 情况 | 处理 |
|---|---|
| 401 | 提示 Token 无效/过期，引导至 https://open.mcd.cn/mcp 重新申请 |
| 429 | 已触发限流：停止批量查询，告知稍后重试；日常控制间隔 ≥0.2s、门店 ≤10 家 |
| 单店 `query-meals` / `query-store-coupons` 失败 | 该店标注"未查询到"，继续查下一店，不中断整体流程 |
| 已领券为空（路径 A） | 提示先领券（auto-bind-coupons）或改用路径 B |
| 门店无售目标餐品 | 明确写入"未查询到在售"，不静默丢弃 |
| `query-meal-detail` 查不到促销商品 | 回退用 `query-meals` 返回的名称与价格 |
