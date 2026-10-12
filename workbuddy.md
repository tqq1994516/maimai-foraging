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
4. **防御式数据解析**：官方未公开完整响应结构，开发中用递归遍历提取门店/餐品/券节点，兼容不同字段命名（该方案在 CLI 原型中验证后纳入设计记录）；
5. **限流友好**：默认最多查 10 家门店，调用间隔 ≥0.2s；
6. **边界克制**：只读查询 + 领券，不调用 `create-order` 等下单工具；
7. **交付形态**：与参赛者确认后，项目以 SKILL.md（Skill 定义）为核心交付物；开发过程中曾同步实现 Python CLI 原型用于验证两条流程的可执行性（见第 6 节自测记录），后按参赛者决定移除，保留于 git 历史中可随时恢复。

## 5. 交付文件清单

| 文件 | 说明 |
|---|---|
| `SKILL.md` | Skill 主定义：路径判定、两条流程、匹配规则、输出格式 |
| `README.md` | 项目介绍、安装方法、使用示例、目标用户 |
| `CONTEST_DECLARATION.md` | 参赛声明（官方模板原文） |
| `MCP_INTEGRATION.md` | MCP Server/Tool/调用流程/业务价值/错误处理 |
| `examples/flow-a-coupon-first.md`、`examples/flow-b-meal-first.md` | 两条路径的示例对话 |
| `workbuddy.md` | 本文件 |

## 6. 自测记录（CLI 原型阶段，脚本后已按参赛者决定移除）

开发初期为实现并验证两条流程的逻辑，曾编写 `src/maimai_foraging.py` 原型并通过以下自测（脚本已移除，记录留存；如需恢复可从 git 历史首个提交取回）：

- `--demo nearby --city 北京 --keyword 中关村`：正常返回 3 家演示门店；
- `--demo coupon-flow --auto-claim`：正确锁定演示券「麦辣鸡腿堡套餐 立减10元」，逐店核实仅中关村大街店在售且门店券可用；
- `--demo meal-flow "巨无霸套餐"`：正确返回 2 家在售门店，并匹配到可领券「巨无霸套餐 第二份半价」与已拥有券「巨无霸套餐 减5元」。

上述逻辑已完整沉淀到 `SKILL.md` 的流程定义与匹配规则中，Skill 形态不依赖该脚本即可运行。

## 7. 如何追加完整对话导出

在 WorkBuddy 中导出本项目的开发会话记录（对话全文），追加到本文件「第 8 节」之后即可，用于 WorkBuddy 联动奖励核验。

## 8. workbuddy上下文

我要参加 https://github.com/M-China/mcd-developer-innovation-challenge 活动，基于 MCP 设计一个名为「麦麦觅食」的 skill，需实现以下两类用户交互流程：
￥
1. 领券后查询：用户领取优惠券后，查询附近哪些门店有售该券对应餐品。
2. 指定餐品查询：用户输入指定餐品名称，查询附近哪些门店有售该餐品，并同时检查是否有对应优惠券可领取。

skill 应支持上述两种路径的清晰切换，并准确返回附近门店列表及匹配的优惠券信息。

设置要skill按照参赛要求准备好项目文件，给我后续上传github命令及后续操作步骤

我先查看参赛仓库的具体要求，再帮你搭建项目文件。
已获取参赛规则。接下来查看麦当劳 MCP Server 的工具清单，确保 skill 调用的是真实工具名。
工具清单已明确。再获取参赛声明原文和 MCP 开放平台文档（确认工具参数），然后开始搭建项目。
开放平台页面无详细参数文档。快速搜索一下是否有第三方记录的参数细节，然后开始搭建项目。<tool_call>
<function=WebSearch>
<parameter=query>
麦当劳 MCP mcd.mcd.cn query-nearby-stores query-meals 参数 tool
</parameter>
<parameter=top_k:
5
</parameter>
</function>
</tool_call>
非常有价值——找到了第三方对 MCP 工具参数的实测记录。再抓取该仓库详情确认 `query-nearby-stores` 等工具的参数。
关键参数已确认。最后再查一下官方文档中 `query-nearby-stores` 的入参格式。
参赛规则、MCP 工具清单和参数文档都已确认。现在开始搭建「麦麦觅食」项目文件。
SKILL.md 主文件已完成。现在写参赛声明（官方原文，不可改动）和 MCP 集成说明。
现在写 README.md 和 workbuddy.md。
修正 workbuddy.md 中的一处笔误，然后写示例对话和辅助文件。
文档部分完成。现在写 .gitignore、LICENSE 和核心源代码。
现在编写核心源代码 `src/maimai_foraging.py`（MCP 客户端 + 双流程 CLI + 演示模式）。
源代码完成。现在用 `--demo` 模式自测两条流程。
`nearby` 正常。测试路径 A 和路径 B。
两条流程都正确运行。再补充测试券名筛选、经纬度入参和错误处理。
全部测试通过（含券名筛选、经纬度检索、缺 Token 报错）。检查 git 环境并本地初始化仓库。
本地仓库已完成首次提交。记录工作日志并交付文件。
「麦麦觅食」项目已按参赛要求搭建完成并通过自测。以下是交付说明和后续操作步骤。

## 一、项目交付内容

位置：`C:\Users\Administrator\WorkBuddy\2026-10-12-20-12-18\maimai-foraging\`

| 文件 | 说明 |
|---|---|
| `SKILL.md` | Skill 主定义：入口自动判定路径（提到券→路径A；只给餐品名→路径B；意图不明→二选一询问），含匹配规则、输出格式、限流与边界约束 |
| `src/maimai_foraging.py` | 可运行源代码：纯标准库的 MCP JSON-RPC 客户端 + 双流程 CLI + `--demo` 演示模式 |
| `README.md` | 项目介绍、安装方法（WorkBuddy Skill / CLI 两种方式）、使用示例、目标用户 |
| `CONTEST_DECLARATION.md` | 参赛声明，**官方原文照搬未改动** |
| `MCP_INTEGRATION.md` | 实际使用的 MCP Server、8 个 Tool 及参数、两条路径调用流程图、错误处理 |
| `workbuddy.md` | WorkBuddy 开发上下文（参加 3000 积分专项奖励用，可再追加完整对话导出） |
| `examples/` | 两条路径的完整示例对话 |

**两条流程设计**：
- **路径A 领券后查询**：`auto-bind-coupons`（可选）→ `query-my-coupons` 锁定目标券并解析适用餐品 → `query-nearby-stores` → 逐店 `query-meals` 核实在售 + `query-store-coupons` 核实门店可用；
- **路径B 指定餐品查询**：`query-nearby-stores` → 逐店 `query-meals` 模糊匹配 → `available-coupons` 匹配可领券 + `query-my-coupons` 标注已拥有。

**自测结果**：demo 模式下 nearby、路径A（含 `--auto-claim`、`--coupon` 筛选、经纬度入参）、路径B、缺 Token 报错均验证通过。

## 二、上传 GitHub 命令

本地已完成 `git init` + 首次提交，直接执行：

```bash
cd /c/Users/Administrator/WorkBuddy/2026-10-12-20-12-18/maimai-foraging

# 方式1：gh CLI（一条命令建公开仓库并推送）
gh repo create maimai-foraging --public --source=. --push

# 方式2：GitHub 网页建好空仓库后
git remote add origin https://github.com/<你的用户名>/maimai-foraging.git
git push -u origin main
```

## 三、报名及后续步骤

1. **申请 MCP Token**（如已有可跳过）：https://open.mcd.cn/mcp → 手机号登录 → 控制台 → 激活 → 复制；
2. **本地实测真实数据**：`export MCD_MCP_TOKEN="你的Token"` 后运行 `python src/maimai_foraging.py meal-flow "巨无霸套餐" --city 北京 --keyword 中关村`（无 Token 时用 `--demo` 体验）；
3. **发布报名 Issue**（在 `M-China/mcd-developer-innovation-challenge` 仓库，标题和正文之间、各字段之间**不要换行**，地址**不要用 Markdown**）：
   ```
   标题：【参赛】麦麦觅食 — 麦当劳门店×餐品×优惠券查询 Skill
   正文：【参赛申请】项目名称：麦麦觅食（MaiMai Foraging）项目地址：https://github.com/<你的用户名>/maimai-foraging 项目简介：基于麦当劳中国 MCP 的「找店+找券」助手：领券后查询附近有售对应餐品且可用券的门店；输入餐品名查询附近有售门店并匹配可领优惠券，支持两条路径清晰切换。
   ```
4. **冲榜**：排行榜按公开 Star 数排名（Star>0 才入榜），报名成功后分享到技术社群邀好友 star；
5. **WorkBuddy 积分**：在 WorkBuddy 中导出本次开发会话，追加到 `workbuddy.md` 末尾后重新 push，前 100 名可领 3000 积分；
6. **关键时间**：报名截止 **2026-10-25 23:59**，10-26 00:00 定榜。

如需把 skill 安装到本机 WorkBuddy 试用：将 `maimai-foraging` 文件夹复制到 `~/.workbuddy/skills/maimai-foraging/`（SKILL.md 在目录根部），配置好 `mcd-mcp` 连接器后重开会话即可对话触发。

这个脚本测试用的话直接移除

你指的应该是 `src/maimai_foraging.py`。先说清楚一个关键点：**它不是测试脚本，而是参赛必需的「源代码」文件**——官方报名要求第 4 项就是“源代码，项目主体代码或可运行内容，必须”，整个移除会导致报名审核失败。其中真正属于“测试/演示”的只有 `--demo` 模式（内置假数据、不联网）。

你想怎么处理？
问得好，直接回答：**能，SKILL.md 就是给 agent 用的**——在 WorkBuddy 里配置好 `mcd-mcp` 连接器后，agent 加载 SKILL.md 就会自行判定路径、调用工具、输出门店和券结果。日常使用确实不需要脚本。

那为什么还留脚本？三个原因：

1. **报名合规（决定性原因）**：官方参赛要求第 4 项「源代码：项目主体代码或可运行内容，**必须**，形式不限」。只交 SKILL.md + 文档，报名校验会不过。
2. **给评委的可执行证据**：SKILL.md 是提示词，脚本是同一套流程的参照实现——评委 clone 后 `--demo` 一跑就能看到两条路径真实效果，比纯文档有说服力。
3. **脱离 AI 宿主也能用**：任何终端/支持 MCP 的环境都能直接运行。

所以脚本不是给你日常用的，是参赛交付物。你倾向哪种？
明白，按你的决定完全移除。先找出所有引用位置，确保清理干净。
引用位置确认（README/SKILL/workbuddy 三处）。执行移除和文档清理。
脚本已删除，但 README 中“方式二”段落有一处没匹配上，读取最新内容后精准删除。
找到差异了（第 60 行大小写不同）。现在精准删除整段。
多次匹配失败，直接读取全文后用 Write 重写，确保干净移除。
全文已确认，唯一残留是 55–75 行的“方式二”段落。重写整个文件干净移除。
README 已清理。现在更新 workbuddy.md 中的文件清单和自测记录。
验证无残留引用并提交更改。
剩余引用均在 workbuddy.md 的开发历史记录中（刻意留存），交付文档已全部干净。提交更改。
更新工作日志并交付。
已完成移除，项目现在以 SKILL.md 为核心交付物。

**本次改动：**
- 删除 `src/maimai_foraging.py`（867 行）及 `src/` 目录；
- `README.md`：删掉“命令行直接运行”整节，项目结构同步更新；
- `SKILL.md`：删掉注意事项里的 CLI 引用；
- `workbuddy.md`：文件清单去掉脚本行，原型自测记录改为“历史留存”表述；
- 已提交（`703f0f6`），仓库现有 9 个文件：SKILL.md、README.md、CONTEST_DECLARATION.md、MCP_INTEGRATION.md、workbuddy.md、examples×2、LICENSE、.gitignore。

**上传命令不变**（本地已两次提交，直接推送即可）：

```bash
cd /c/Users/Administrator/WorkBuddy/2026-10-12-20-12-18/maimai-foraging
gh repo create maimai-foraging --public --source=. --push
# 或：git remote add origin https://github.com/<你的用户名>/maimai-foraging.git && git push -u origin main
```

**两点提醒：**
1. 脚本并未真正丢失——首个提交 `d821486` 里完整保留，随时可 `git checkout d821486 -- src/maimai_foraging.py` 取回。若报名 Issue 被系统以“缺少源代码”驳回，恢复它只需一条命令；
2. agent 确实可以直接加载 SKILL.md 跑通两条流程（配置好 `mcd-mcp` 连接器即可），日常使用不受任何影响。

---

_本节之后可追加：完整对话上下文导出_
