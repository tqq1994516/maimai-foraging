# 麦麦觅食（MaiMai Foraging）

> 基于麦当劳中国 MCP（`mcd-mcp`）的「门店 × 餐品 × 优惠券」交叉查询 Skill。
> 领了券，告诉你附近哪家店有售、能用；想吃某餐品，告诉你附近哪家店有售、有没有券可领。

麦当劳程序员节创意开发大赛参赛项目 · 基于 [麦当劳中国 MCP Server](https://github.com/M-China/mcd-mcp-server) 开发。

## 背景与痛点

麦当劳的「优惠券」和「门店供应」是两张独立的网，用户经常遇到两个麻烦：

1. **领了券不知道去哪家用**——卡包里躺着一堆券，走到店门口才发现这家店不卖这个套餐，或者券在这家用不了；
2. **想吃某餐品不知道哪家店有**——跨店找餐品全靠碰运气，也看不到有没有对应的券可以领。

「麦麦觅食」把 **券 × 餐品 × 门店** 三者交叉验证，用一句话给出可直接执行的到店结论。

## 功能特性：两条路径，清晰切换

| 路径 | 触发方式 | 流程 |
|---|---|---|
| **A · 领券后查询** | 用户提及已领/想领的优惠券 | （一键领券）→ 读已领券 → 提取券适用餐品 → 查附近门店 → **逐店核实餐品在售 + 门店券可用性** |
| **B · 指定餐品查询** | 用户输入餐品名称 | 查附近门店 → **逐店核实餐品在售** → 匹配可领取优惠券 → 标注已拥有的相关券 |

- Skill 入口自动判定路径：提到券走 A，只给餐品名走 B，同时给出时以券为主线，意图不明时一句话询问用户二选一；
- 结果固定为「结论一句话 + 门店表格 + 优惠券明细」三段式，价格与供应状态注明时效性；
- 只读查询 + 领券，不碰下单支付，尊重官方业务边界。

## 快速开始

### 方式一：作为 WorkBuddy Skill 使用（推荐）

1. **申请 MCP Token**：打开 https://open.mcd.cn/mcp ，手机号登录 → 右上角「控制台」→「激活」→ 一键复制 Token。
2. **配置连接器**：WorkBuddy 左侧边栏【专家·技能·连接器】→【连接器】→ 右上角【自定义连接器】→【配置 MCP】，填入：

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

   （把 `YOUR_MCP_TOKEN` 替换为实际 Token，保存后在【自定义连接器】中启用 `mcd-mcp`。）
3. **安装本 Skill**：将本仓库目录复制到用户级技能目录 `~/.workbuddy/skills/maimai-foraging/`（即 `SKILL.md` 位于该目录根部），重开会话生效。
4. **对话中使用**：
   - 「我刚领了麦辣鸡腿堡套餐的券，北京中关村附近哪家店能用的？」（路径 A）
   - 「我想吃巨无霸套餐，北京中关村附近哪家有？有没有券？」（路径 B）

### 方式二：命令行直接运行（无需 AI 宿主）

仅需 Python 3.8+，无第三方依赖：

```bash
export MCD_MCP_TOKEN="你的MCP_TOKEN"   # Windows PowerShell: $env:MCD_MCP_TOKEN="你的MCD_TOKEN"

# 查附近门店
python src/maimai_foraging.py nearby --city 北京 --keyword 中关村

# 路径 A：领券后查询（--auto-claim 先一键领券）
python src/maimai_foraging.py coupon-flow --city 北京 --keyword 中关村 --auto-claim

# 路径 B：指定餐品查询
python src/maimai_foraging.py meal-flow "巨无霸套餐" --city 北京 --keyword 中关村

# 无 Token 时用内置演示数据离线体验两条流程
python src/maimai_foraging.py --demo coupon-flow --city 北京 --keyword 中关村
python src/maimai_foraging.py --demo meal-flow "巨无霸套餐" --city 北京 --keyword 中关村
```

## 使用示例

**路径 A（对话）**：

> 用户：我刚领了麦辣鸡腿堡套餐的券，北京中关村附近哪家店能用的？
>
> 麦麦觅食：好的，走「领券后查询」——目标券「麦辣鸡腿堡套餐 立减10元」，查北京中关村附近门店。
>
> 结论：附近 3 家门店中 1 家有售「麦辣鸡腿堡套餐」，且该店门店券列表包含此券。
>
> | 门店名称 | 地址/距离 | 餐品在售（价格） | 门店券 |
> |---|---|---|---|
> | 麦当劳(中关村大街店) | 海淀区中关村大街1号 · 0.4km | 麦辣鸡腿堡套餐 ¥28.5 | 本店可用 |
> | 麦当劳(五道口店) | 海淀区成府路28号 · 1.2km | 未查询到在售 | 本店券列表未见该券 |
> | 麦当劳(西直门店) | 西城区西直门内大街 · 2.1km | 未查询到在售 | 本店券列表未见该券 |
>
> 价格与供应状态以麦当劳官方渠道实时结果为准。

**路径 B（对话）**：

> 用户：我想吃巨无霸套餐，北京中关村附近哪家有？有没有券？
>
> 麦麦觅食：好的，走「指定餐品查询」——目标餐品「巨无霸套餐」。
>
> 结论：附近 3 家门店中 2 家有售；当前可领「巨无霸套餐 第二份半价」，你的卡包里已有「巨无霸套餐 减5元」。

更完整的模拟对话见 [`examples/`](examples/) 目录。

## 目标用户

- **精打细算的麦门信徒**：卡包里一堆券，想知道附近哪家店真的能用；
- **目标明确干饭人**：突然想吃某个特定餐品/套餐，想快速找到附近有售的门店；
- **懒得比价的上班族**：希望一句话同时得到"哪家店有 + 有没有券 + 多少钱"的决策信息。

## 项目结构

```
maimai-foraging/
├── SKILL.md                  # Skill 主定义（WorkBuddy Skill 格式：路径判定 + 两条流程 + 匹配规则 + 输出格式）
├── README.md                 # 本文件：项目介绍、安装方法、使用示例、目标用户
├── CONTEST_DECLARATION.md    # 参赛声明（官方模板，内容未改动）
├── MCP_INTEGRATION.md        # 麦当劳 MCP 集成说明：Server/Tool/调用流程/业务价值
├── workbuddy.md              # WorkBuddy 开发上下文（WorkBuddy 专项奖励核验用）
├── src/
│   └── maimai_foraging.py    # 可运行源代码：MCP 客户端 + 两条流程 CLI（仅标准库，含 --demo）
├── examples/
│   ├── flow-a-coupon-first.md  # 路径 A 示例对话
│   └── flow-b-meal-first.md    # 路径 B 示例对话
├── LICENSE
└── .gitignore
```

## 工作原理（简版）

两条路径共享同一个起点——`query-nearby-stores` 拿附近门店，然后逐店调用 `query-meals` 核实餐品在售；差异在于"查什么"和"额外匹配什么"：

- **路径 A** 从 `query-my-coupons` 出发，先锁定券及其适用餐品，逐店验证"餐品在售 + 门店券可用"；
- **路径 B** 从餐品名出发，逐店验证在售，再用 `available-coupons` 匹配可领券、`query-my-coupons` 标注已拥有。

详细的 MCP Server/Tool/调用流程/错误处理见 [MCP_INTEGRATION.md](MCP_INTEGRATION.md)。

## 上传 GitHub 与报名（参赛步骤）

1. 本地 `git init` → `git add .` → `git commit` → push 到新建的 **Public** 仓库（仓库创建时间需在 2025-12-25 至 2026-10-25 之间）；
2. 在活动仓库 [M-China/mcd-developer-innovation-challenge](https://github.com/M-China/mcd-developer-innovation-challenge) 按标准格式发布报名 Issue：
   ```
   【参赛申请】
   项目名称：麦麦觅食（MaiMai Foraging）
   项目地址：https://github.com/<你的用户名>/<仓库名>
   项目简介：基于麦当劳中国 MCP 的「找店+找券」助手……
   ```
   注意：标题与正文之间、各字段之间不要使用换行符；项目地址不要用 Markdown 格式；
3. 报名成功后系统会在 Issue 下回复；排行榜按 **公开 Star 数** 排名（Star > 0 才入榜），活动 **2026-10-25 23:59** 截止；
4. 参加 WorkBuddy 专项奖励需提交 `workbuddy.md`（本仓库已包含开发上下文记录）。

## 免责声明

本项目为参赛作品，由参赛者独立开发，非麦当劳官方产品。餐品信息、价格及供应状态以麦当劳官方渠道实时结果为准；本项目不提供下单支付能力。麦当劳及相关商标归其权利人所有。
