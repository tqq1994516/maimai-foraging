# workbuddy.md — WorkBuddy 开发上下文（导出）

> 本文件用于麦当劳程序员节创意开发大赛「WorkBuddy 专项奖励」的联动核验，记录本项目使用 WorkBuddy 开发的关键上下文。参赛者可在此文件基础上追加自行导出的完整对话记录。

## 1. 开发环境

- 开发工具：WorkBuddy（Windows 客户端）
- 开发日期：2026-10-12
- 关联连接器：`mcd-mcp`（麦当劳中国 MCP Server，Streamable HTTP，https://mcp.mcd.cn）

## 2. 需求确认（来自用户）

参赛项目「麦麦觅食」需实现两类用户交互流程：

1. **领券后查询**：用户领取优惠券后，查询附近哪些门店有售该券对应餐品；
2. **指定餐品查询**：用户输入指定餐品名称，查询附近哪些门店有售该餐品，并同时检查是否有对应优惠券可领取；
3. Skill 需支持两条路径的**清晰切换**，并准确返回附近门店列表及匹配的优惠券信息；
4. 按参赛要求准备项目文件，并给出 GitHub 上传命令与后续操作步骤。

## 3. 调研结论（开发中核实）

- 参赛必需文件：`README.md`、`CONTEST_DECLARATION.md`（官方原文不可改）、`MCP_INTEGRATION.md`、源代码；`workbuddy.md` 为 WorkBuddy 专项奖励必需。
- 麦当劳 MCP 工具清单与参数（来自官方 README 与 open.mcd.cn 文档）：
  - `query-nearby-stores`：`searchType`(1收藏/2位置/3经纬度)、`beType`(1到店自取/5得来速)、`city`、`keyword`、`latitude`、`longitude`
  - `query-meals` / `query-store-coupons`：`storeCode`、`beCode`、`orderType`(1到店/2外送)、`beType`
  - `query-my-coupons` / `available-coupons` / `auto-bind-coupons`：无入参
- 限流 600 次/分钟；401 = Token 问题，429 = 限流。

## 4. 关键设计决策

1. **路径判定前置**：Skill 入口先根据用户输入（是否提及券）判定 A/B 路径，意图不明时一句话二选一，避免误走流程；
2. **逐店核实**：附近门店列表只回答"哪家近"，不回答"哪家有售"——必须对每家店调 `query-meals` 交叉验证，这是本 Skill 的核心价值；
3. **券 → 餐品解析**：优先取券的适用商品字段；无结构化字段时从券名剥离"立减 X 元/券/第 N 份半价"等噪声词；
4. **防御式数据解析**：官方未公开完整响应结构，代码用递归遍历提取门店/餐品/券节点，兼容不同字段命名；
5. **限流友好**：默认最多查 10 家门店，调用间隔 ≥0.2s；
6. **边界克制**：只读查询 + 领券，不调用 `create-order` 等下单工具；
7. **双形态交付**：同一套流程既有 AI Skill（SKILL.md）又有可独立运行的 Python CLI（`--demo` 可无 Token 演示）。

## 5. 交付文件清单

| 文件 | 说明 |
|---|---|
| `SKILL.md` | Skill 主定义：路径判定、两条流程、匹配规则、输出格式 |
| `README.md` | 项目介绍、安装方法、使用示例、目标用户 |
| `CONTEST_DECLARATION.md` | 参赛声明（官方模板原文） |
| `MCP_INTEGRATION.md` | MCP Server/Tool/调用流程/业务价值/错误处理 |
| `src/maimai_foraging.py` | 可运行源代码（MCP JSON-RPC 客户端 + 双流程 CLI + 演示数据） |
| `examples/flow-a-coupon-first.md`、`examples/flow-b-meal-first.md` | 两条路径的示例对话 |
| `workbuddy.md` | 本文件 |

## 6. 自测记录

- `python src/maimai_foraging.py --demo nearby --city 北京 --keyword 中关村`：正常返回 3 家演示门店；
- `--demo coupon-flow --auto-claim`：正确锁定演示券「麦辣鸡腿堡套餐 立减10元」，逐店核实仅中关村大街店在售且门店券可用；
- `--demo meal-flow "巨无霸套餐"`：正确返回 2 家在售门店，并匹配到可领券「巨无霸套餐 第二份半价」与已拥有券「巨无霸套餐 减5元」。

## 7. 如何追加完整对话导出

在 WorkBuddy 中导出本项目的开发会话记录（对话全文），追加到本文件「第 8 节」之后即可，用于 WorkBuddy 联动奖励核验。

---

_本节之后可追加：完整对话上下文导出_
