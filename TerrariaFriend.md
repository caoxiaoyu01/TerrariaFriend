# Terraria Companion Agent 项目设计说明

## 1. 项目目标

我们希望做的不是一个“自动玩 Terraria 的游戏 Bot”，而是一个 **陪玩家一起玩的智能 Agent（Companion / Friend Agent）**。

玩家仍然自己操作游戏，Agent 主要负责：

- 感知当前游戏状态
- 记住玩家过去发生过的事情
- 判断现在是否值得主动说话
- 在需要时查询游戏知识
- 给出简短、有上下文的建议或陪伴式反馈

例如：

- 玩家连续三次死在同一个 Boss：Agent 可以提醒玩家调整装备或策略。
- 世界开始下雨：Agent 可以结合当前进度，判断是否有值得做的事情。
- 玩家击败重要 Boss：Agent 可以识别游戏阶段变化，并提示下一步可能的目标。
- 玩家重新来到以前经常死亡的区域：Agent 可以记住过去的经历，而不是把当前场景当成第一次发生。
- 玩家只是正常探索：Agent 应该保持安静，而不是不停打扰。

所以这个项目最核心的问题不是：

> “Agent 下一步应该帮玩家执行什么操作？”

而是：

> **“Agent 什么时候应该介入？介入时应该知道什么、查什么、说什么？”**

---

## 2. 项目定位

项目可以定位为：

**Context-Aware Proactive Game Companion Agent**

即：

> 一个能够持续理解游戏环境、记忆玩家经历，并在合适时机主动提供帮助的游戏陪伴 Agent。

它与普通 Chatbot 的区别在于：

普通 Chatbot：

```text
用户提问
→ LLM
→ 回答
```

我们的 Agent：

```text
游戏持续运行
→ Agent 持续接收状态和事件
→ 判断是否值得处理
→ 读取当前状态 / Memory / 游戏知识
→ 决定是否响应
→ 在游戏中显示简短信息
```

Agent 不一定需要用户主动提问。

**“保持沉默”本身也是一种合理的 Agent 行为。**

---

## 3. 从 SPIKE 借鉴什么

SPIKE 是一个在 Stardew Valley 中完成任务的自主游戏 Agent 框架。

它和我们的目标不同：

```text
SPIKE
玩家给任务
→ Agent 自己规划
→ Agent 操作游戏
→ 完成任务
```

而我们是：

```text
Terraria Companion
玩家自己玩
→ Agent 观察
→ Agent 理解上下文
→ 必要时提供帮助
```

因此我们不直接复现 SPIKE，而是借鉴其中几个重要思想。

### 3.1 Event Trigger

SPIKE 不会每一步都进行复杂推理，而是判断：

> 当前是不是到了值得重新思考的时候？

我们的项目可以把这个思想改造成：

> **当前事件是不是值得 Agent 介入？**

例如：

```text
捡到普通木头
→ 不处理

正常移动
→ 不处理

第一次普通死亡
→ 记录事件

连续多次死于同一 Boss
→ 高重要度事件
→ Agent 可以介入

击败 Wall of Flesh
→ 游戏阶段发生重大变化
→ Agent 可以主动提醒
```

这样可以避免 Agent 变成一个一直说话的“弹幕机器人”。

---

### 3.2 Selective Reasoning

不是所有事件都需要调用大模型。

可以分成：

```text
Game Event
    ↓
Event Trigger
    ↓
是否值得处理？
 ┌──┴──┐
 No   Yes
 ↓      ↓
忽略   是否需要复杂推理？
       ┌──┴──┐
       No    Yes
       ↓      ↓
     简单响应  Agent / LLM
```

例如：

“下雨了”可能只需要简单逻辑。

而：

“玩家连续三次挑战 Boss 失败，并且装备没有变化”

就值得进入更复杂的 Agent 推理。

---

### 3.3 Memory Filtering

SPIKE 不会把每一步游戏操作都永久保存。

我们也不应该记录：

```text
走了一步
跳了一次
掉了 3 HP
捡了一块普通木头
```

长期 Memory 更应该保存：

- Boss 尝试
- 死亡
- 游戏阶段变化
- 重要装备变化
- 重要 NPC 入住
- Agent 曾经给出的建议
- 玩家是否采纳建议
- 重复失败模式
- 重要成功经历

核心思想：

> **Memory 不是日志仓库，而是有选择地保存“以后可能有用的经历”。**

---

### 3.4 Skill 抽象

SPIKE 有自己的 Skill Library，但它的 Skill 主要用于直接操作游戏，例如：

```text
move
use
interact
attack
```

我们的 Friend Agent 不负责代打，因此不需要 `move_player`、`attack` 这类控制技能。

我们的 Skill 更适合定义成：

> **Agent 可以调用的高层信息能力和辅助能力。**

例如：

```text
Game State Skills
├── get_player_state
├── get_world_state
└── get_progression

Memory Skills
├── search_memory
└── write_memory

Knowledge Skills
├── search_local_knowledge
└── search_wiki

Interaction Skill
└── send_message
```

因此，两者虽然都使用 Skill，但 Action Space 不同：

```text
SPIKE
→ 控制角色行动

Terraria Companion
→ 获取信息、检索知识、管理记忆、给玩家反馈
```

这是我们从 SPIKE 工程框架中可以直接借鉴、但需要重新定义的一部分。

---

## 4. 整体工程架构

项目采用 **双入口 + 统一 Agent** 的结构：

```text
                         Terraria
                             │
                   ┌─────────┴─────────┐
                   ↓                   ↓
              Game Event          User Query
                   │                   │
             Event Trigger             │
                   │                   │
                   └─────────┬─────────┘
                             ↓
                      State Aggregator
                             ↓
                      LangGraph Agent
                             ↓
                     Intent / Tool Router
                             ↓
          ┌──────────────────┼──────────────────┐
          ↓                  ↓                  ↓
     Current State         Memory          Game Knowledge
          │                  │                  │
      tModLoader           SQLite          Local RAG
                                                  │
                                           必要时 fallback
                                                  ↓
                                             MCP / Wiki
          └──────────────────┼──────────────────┘
                             ↓
                       Response Policy
                             ↓
                      send_message Skill
                             ↓
                    Terraria 游戏内 UI
```

两种入口共用同一套 State、Memory、Knowledge 和 Skill，不维护两套 Agent。

---

## 5. 两种交互模式：主动 + 用户提问

Friend Agent 最合适的形态不是二选一，而是：

> **Proactive Companion + On-demand Assistant**

### 5.1 主动模式

游戏持续产生事件：

```text
Game Event
→ Event Trigger
→ 是否值得介入？
→ 必要时调用 Agent
→ 游戏内弹幕 / 提示
```

这是项目最有辨识度的部分。

例如：

- 连续多次死于同一个 Boss
- 重大 progression 变化
- 当前状态与过去失败模式高度相似
- 某些特殊天气或事件与当前进度有关

### 5.2 用户 Query 模式

玩家也可以主动询问 Agent，例如通过快捷键打开一个轻量输入框：

```text
我现在应该干什么？
我这个装备能打骷髅王吗？
我刚才为什么一直死？
这个材料有什么用？
```

然后进入同一个 LangGraph Agent：

```text
User Query
→ 读取 Current State
→ 必要时查 Memory
→ 必要时查 Local RAG / Wiki
→ 回答
```

用户 Query 的意义在于：

- 不是所有需求都会由游戏事件自动触发；
- 更容易展示 Tool Routing 和 Agentic RAG；
- Agent 既能主动陪伴，也能在玩家需要时提供帮助。

但 UI 不做成大型 ChatGPT 侧边栏，而保持游戏内轻量交互，避免项目退化成“Terraria + Chatbot”。

---

## 6. tModLoader 负责什么

tModLoader 是 Agent 与 Terraria 世界之间的接口。

Mod 可以读取当前游戏中的真实状态，例如：

- 当前天气
- 白天 / 夜晚
- 玩家位置
- 当前 biome
- HP / Mana
- Inventory
- Armor
- 武器
- Boss 击败状态
- Hardmode 状态
- NPC 是否入住
- 重要世界事件

这些信息属于 **Current State**。

它们不需要 RAG，也不应该通过 LLM 猜测。

例如：

```json
{
  "weather": "rain",
  "biome": "Dungeon",
  "hardmode": false,
  "player": {
    "hp": 240,
    "weapon": "Demon Bow",
    "armor": "Gold Armor"
  },
  "progress": {
    "eye_of_cthulhu": true,
    "skeletron": false
  }
}
```

---

## 7. Agent State

Agent 不应该每次直接读取一大堆原始游戏变量。

需要在中间整理成比较稳定的 Agent State，例如：

```text
AgentState

├── player_state
│   ├── hp
│   ├── equipment
│   └── inventory
│
├── world_state
│   ├── weather
│   ├── time
│   └── biome
│
├── progress_state
│   ├── boss_progress
│   ├── hardmode
│   └── important_unlocks
│
├── recent_events
│
├── memory_context
│
└── current_agent_task
```

这样 LangGraph 中不同节点可以共享同一份状态。

---

## 8. Skill 设计

Skill 是 Agent 可以调用的能力集合。

第一版不需要很多 Skill，控制在 8～10 个即可。

### 8.1 Game State Skills

```text
get_player_state
get_world_state
get_progression
```

负责从 tModLoader / State Aggregator 获取真实游戏状态。

### 8.2 Memory Skills

```text
search_memory
write_memory
```

负责读取和写入玩家的重要历史经历。

### 8.3 Knowledge Skills

```text
search_local_knowledge
search_wiki
```

分别用于：

- 本地稳定知识检索
- 长尾、精确或可能需要最新版本的外部知识

### 8.4 Interaction Skill

```text
send_message
```

负责把最终消息显示回 Terraria。

### 8.5 Skill 的边界

Friend Agent 第一版明确 **没有角色控制 Skill**：

```text
不提供：
move_player
attack
use_item
auto_fight
```

这样可以保证项目定位清晰：

> Agent 负责观察、理解、记忆和建议；玩家始终保留游戏控制权。

---

## 9. 为什么使用 LangGraph

LangGraph 可以作为整个 Agent 的工作流骨架。

因为我们的流程不是固定的一条 Chain，而是存在：

- 状态
- 条件分支
- Tool Calling
- Memory
- 多步检索
- 循环
- 提前结束

例如：

```text
Event
 ↓
是否值得响应？
 ↓
需要什么信息？
 ├── Current State
 ├── Memory
 ├── Local RAG
 └── MCP / Wiki
 ↓
信息是否足够？
 ├── Yes → Response
 └── No  → 继续查询
```

因此 LangGraph 比简单的：

```text
Prompt → LLM → Output
```

更适合这个项目。

---

## 10. ReAct 怎么使用

项目不需要让所有事件都进入 ReAct。

ReAct 只负责比较开放、需要多步工具调用的问题。

例如：

> “按照我现在的装备，我适合去打 Skeletron 吗？”

Agent 可能需要：

```text
读取当前装备
→ 查询 Skeletron 攻略
→ 对比推荐装备
→ 发现某个关键装备缺失
→ 查询该装备获取方式
→ 给出建议
```

这种任务适合：

```text
Reason
→ Tool
→ Observation
→ Reason
→ Tool
→ Observation
→ Answer
```

但：

```text
玩家连续死亡次数 +1
```

这种确定性逻辑不需要 ReAct。

因此：

> **LangGraph 管理整个系统，ReAct 只作为复杂 Agent 节点中的一种决策方式。**

---

## 11. RAG 怎么设计

RAG 不应该成为所有问题的必经步骤。

它只是 Agent 获取外部游戏知识的一种工具。

### 9.1 本地知识库存什么

本地 Vector DB 主要保存适合语义检索的自然语言知识：

#### Progression

例如：

- Pre-Hardmode progression
- Pre-Skeletron progression
- Pre-Wall of Flesh progression
- Early Hardmode progression

#### Boss / Event Strategy

例如：

- Boss 准备
- 推荐装备
- 战斗策略
- 常见失败原因
- Arena 建议
- Boss 击败后的 progression

#### Build / Equipment Guidance

例如：

- Melee progression
- Ranged progression
- Mage progression
- Summoner progression

#### NPC / Biome / Mechanics

例如：

- NPC 入住条件说明
- Biome 特殊机制
- Weather Event
- 特殊游戏机制

---

### 9.2 什么不应该放 Vector DB

精确结构化数据不一定适合向量检索，例如：

```text
Item ID
Damage
Defense
Recipe
Drop Rate
Item Count
```

这些可以使用：

```text
SQLite / JSON / Wiki Tool
```

而：

```text
当前 HP
当前 Inventory
当前天气
Boss 是否击败
```

直接来自 tModLoader。

---

## 12. Agentic RAG

我们不希望做：

```text
所有问题
→ Vector DB
→ LLM
```

而是让 retrieval 成为 Agent 的一种 Action。

例如：

```text
问题 / Event
    ↓
Agent 判断信息是否足够
    ↓
┌──────────────┬──────────────┬──────────────┐
↓              ↓              ↓
Current State  Memory       Game Knowledge
                              ↓
                       Local RAG or MCP
```

例子：

### “现在下雨了吗？”

```text
Current State
→ 直接回答
```

不需要 RAG。

### “我以前在这里死过几次？”

```text
Memory
→ 回答
```

不需要 Wiki。

### “我现在的装备适合打 Skeletron 吗？”

```text
Current State
+
Local RAG
→ 比较后回答
```

### “最新版这个 Item 的掉率是多少？”

```text
需要精确信息 / 可能存在版本变化
→ MCP / Terraria Wiki
```

这就是我们希望实现的 **Agentic Retrieval**：

> Agent 自己判断是否检索、检索什么、使用哪个知识源。

---

## 13. MCP 的作用

MCP 第一版不是必需模块，可以作为后续增强。

它主要用于：

> Agent 需要访问本地知识库之外的外部知识。

例如：

```text
MCP
→ Terraria Wiki
```

Local RAG 和 MCP 可以形成：

```text
稳定、高频、可控知识
→ Local RAG

长尾、精确、可能需要最新版本的信息
→ MCP / Wiki
```

因此 MCP 不需要为了“展示 MCP”而强行加入所有流程。

---

## 14. Memory 设计

我们的 Memory 与 SPIKE 不同。

SPIKE 更关注：

```text
State
→ Action
→ Next State
```

因为 SPIKE 自己控制玩家。

我们的 Agent 更关注：

> **这个玩家以前经历过什么？**

可以分为：

### Short-term Context

保存最近几分钟的重要信息。

例如：

```text
进入 Dungeon
→ Boss 出现
→ 第一次死亡
→ 再次挑战
```

### Episodic Memory

保存重要经历：

- Boss attempts
- deaths
- major success
- progression milestones
- important equipment changes

### Player Profile

逐渐形成玩家偏好，例如：

- 常用职业
- 常用武器
- 喜欢探索还是推进
- 是否喜欢频繁提示
- 是否希望减少剧透

### Interaction Memory

记录 Agent 自己以前说过什么。

主要作用：

> 避免 Agent 重复给出完全相同的建议。

---

## 15. Friend Agent 最重要的能力：什么时候闭嘴

这个项目不是攻略机器人。

因此非常重要的一项能力是：

> **不要一直说话。**

可以设计一个 Intervention / Speak Policy。

例如：

```text
Event importance
+
Recent failure
+
Progress change
+
Previous reminder
+
Cooldown
+
Player preference
        ↓
 Should Speak?
```

可能输出：

```text
SILENCE
LIGHT_COMMENT
HELPFUL_HINT
DETAILED_GUIDANCE
```

例如：

第一次死亡：

```text
SILENCE / LIGHT_COMMENT
```

连续三次死亡：

```text
HELPFUL_HINT
```

连续失败并主动询问：

```text
DETAILED_GUIDANCE
```

这样 Agent 才更接近“朋友”，而不是提示框。

---

## 16. 项目评价方式

我们不评价：

> “Agent Terraria 玩得好不好？”

因为 Agent 根本不负责代打。

应该评价：

> **它是不是一个好的 Companion Agent？**

可以构造一批可复现 Scenario。

例如：

### Scenario 1

```text
玩家正常探索 10 分钟
没有重大事件
```

期望：

```text
Agent 保持沉默
```

### Scenario 2

```text
第一次死于 Skeletron
```

期望：

```text
记录 Memory
不过度干预
```

### Scenario 3

```text
连续第三次死于 Skeletron
装备没有明显变化
```

期望：

```text
Agent 主动介入
读取 Memory
必要时查询攻略
给出简短建议
```

### Scenario 4

```text
玩家换装备后再次挑战
```

期望：

```text
不要继续重复旧的“装备不足”建议
```

### Scenario 5

```text
击败 Wall of Flesh
```

期望：

```text
识别重大 progression change
主动给出 Hardmode 提示
```

---

## 17. Hardness 如何定义

Hardness 不按“感觉难不难”划分，而按照 Agent 需要的信息和决策复杂度划分。

### H1 — Reactive

只需要当前单一事件。

```text
Boss 出现
天气变化
死亡
```

### H2 — Contextual

需要组合多个当前状态。

```text
“我现在适合打这个 Boss 吗？”
```

需要：

```text
Boss
+
HP
+
Equipment
+
Progression
```

### H3 — Knowledge / Multi-step

当前状态不足，需要外部知识或多步查询。

```text
Current State
→ 查询 Boss Strategy
→ 查询装备信息
→ 综合判断
```

### H4 — Temporal / Personalized

必须结合历史 Memory。

例如：

```text
连续死亡
→ Agent 给过建议
→ 玩家换装备
→ 再次挑战
```

Agent 必须理解：

> 当前情况已经和之前不同，旧建议不能继续机械重复。

---

## 18. MVP 范围

项目目标是两到三周做出一个可以稳定演示、可以在面试中讲清楚的版本。

第一版不追求：

- 自动操作角色
- 自动打 Boss
- 大规模强化学习
- GraphRAG
- 复杂多 Agent
- 大规模模型微调

第一版重点实现：

### 1. tModLoader 状态与事件接口

能够获取：

- Player State
- World State
- Progress State
- 重要 Event

### 2. 游戏内双入口

实现：

- Proactive Event Trigger
- 玩家快捷键 Query
- 游戏内轻量消息展示

### 3. 基础 Skill

至少实现：

```text
get_player_state
get_world_state
get_progression
search_memory
write_memory
search_local_knowledge
send_message
```

### 4. LangGraph Agent

实现：

```text
Event / Query
→ State
→ Trigger / Intent
→ Tool Routing
→ Memory / RAG
→ Response
```

### 5. Event Trigger

第一版只识别少量高价值事件：

- death
- Boss
- weather
- progression
- equipment change
- repeated failure

### 6. Local RAG

准备一个小而高质量的 Terraria 知识库。

不追求整个 Wiki。

### 7. Memory

至少实现：

- Boss attempt
- death history
- progression history
- previous Agent response

### 8. Agentic Routing

让 Agent 能区分：

```text
直接使用当前状态
查 Memory
查 Local RAG
必要时查外部 Wiki
```

### 9. ReAct

只为少量复杂 Query / 多步检索场景开启，并设置最大 Tool Step。

### 10. Scenario Evaluation

准备一组固定场景，验证：

- 应该说话时是否介入
- 不应该说话时是否保持沉默
- Tool 是否选对
- Memory 是否使用正确
- 是否出现重复提醒

---

## 19. 第一版技术栈

可以暂定：

```text
Game Side
├── Terraria
└── tModLoader / C#

Agent Backend
├── Python
├── FastAPI
├── LangGraph
└── LLM API

Storage
├── SQLite
└── FAISS / Qdrant

Optional
└── MCP → Terraria Wiki
```

---

## 20. 项目最终希望展示什么

这个项目最重要的不是展示：

> “我会调用一个 LLM。”

也不是：

> “我做了一个 Terraria Wiki Chatbot。”

真正希望展示的是一套完整的 Agent Engineering 思路：

```text
Observe
↓
理解当前环境

Remember
↓
保持长期上下文

Decide
↓
判断什么时候值得介入

Retrieve / Tool Use
↓
主动选择需要的信息来源

Respond
↓
给出简短、有价值的反馈
```

最终希望实现的体验是：

> Agent 不是一直在旁边教玩家怎么玩，而是像一个一直在看着玩家玩的朋友。

它知道现在发生了什么，也记得之前发生过什么。

平时它安静。

当真正值得说话的时候，它才出现。


---

## 21. 工程执行步骤

下面按照“先打通最短链路，再逐渐增加 Agent 能力”的顺序开发。

原则是：

> **每完成一个阶段，都应该有一个可以运行的小版本。**

不要一开始同时做 RAG、Memory、MCP、LangGraph 和复杂 UI。

### Phase 0：确定 MVP 边界与仓库结构

先固定第一版只做：

```text
Game State
+ Event
+ User Query
+ LangGraph
+ Memory
+ Local RAG
+ 游戏内回复
```

暂时不做：

- 自动操作玩家
- GraphRAG
- 多 Agent
- 模型微调
- 复杂视觉模型
- 大规模 Wiki 抓取

建议仓库结构：

```text
terraria-companion/
├── mod/                # tModLoader C#
├── backend/            # Python Agent Server
│   ├── graph/
│   ├── skills/
│   ├── memory/
│   ├── rag/
│   └── api/
├── knowledge/          # 本地知识库原始文档
├── eval/               # Scenario benchmark
└── README.md
```

**完成标准：**

仓库建立，模块职责明确，可以开始独立开发 Mod 和 Python Backend。

---

### Phase 1：先打通 Terraria → Python 的最小通信链路

这是第一优先级。

先不要接 LLM。

tModLoader 只需要做到：

```text
读取 Player / World State
→ 序列化 JSON
→ HTTP / WebSocket
→ Python
```

先支持少量字段：

```text
hp
position
biome
weather
hardmode
inventory summary
boss progression
```

同时捕获几个事件：

```text
death
boss_spawn
boss_defeated
weather_change
equipment_change
```

Python Backend 收到以后直接打印。

**完成标准：**

玩家在 Terraria 中死亡，Python 控制台能够收到一条结构化 `player_death` Event。

---

### Phase 2：打通 Python → Terraria 消息链路

增加最简单的：

```text
send_message("...")
```

Python 发一句字符串，tModLoader 在游戏内显示出来。

同时增加一个快捷键 Query：

```text
按键
→ 输入一句话
→ 发给 Python
```

这一阶段仍然不需要复杂 Agent。

**完成标准：**

玩家可以在游戏里输入：

```text
hello
```

Python 返回：

```text
Companion online.
```

并显示在游戏里。

到这里已经形成完整闭环：

```text
Terraria
→ Python
→ Terraria
```

---

### Phase 3：建立统一 Agent State

不要直接把 tModLoader 的原始字段全部扔给 LLM。

建立：

```text
AgentState
├── player_state
├── world_state
├── progress_state
├── recent_events
├── user_query
├── retrieved_memory
├── retrieved_knowledge
└── response
```

同时增加 Event Logger，把关键事件记录到本地。

**完成标准：**

无论是 Game Event 还是 User Query，都能转换成统一 AgentState。

---

### Phase 4：接入 LangGraph，但先只做最简单 Workflow

第一版 Graph：

```text
Input
 ↓
Update State
 ↓
Query or Event?
 ├── Query → Response Node
 └── Event → Trigger Node
                  ↓
             Respond / Silence
```

暂时：

- 不做 RAG
- 不做 MCP
- 不做复杂 ReAct

LLM 只根据当前 Agent State 生成回复。

**完成标准：**

同一个 LangGraph 可以同时处理：

- 用户主动 Query
- 游戏主动 Event

---

### Phase 5：实现 Event Trigger / Speak Policy

这是 Companion Agent 的核心。

第一版可以先使用：

```text
规则
+
LLM 判断
```

规则负责筛掉明显不重要的事件。

例如：

```text
普通移动 → ignore
普通掉血 → ignore
第三次连续 Boss death → important
major progression → important
```

然后 Agent 输出：

```text
SILENCE
LIGHT_COMMENT
HELPFUL_HINT
DETAILED_GUIDANCE
```

加入：

- cooldown
- duplicate suppression
- recent reminder history

**完成标准：**

正常游戏几分钟 Agent 不会一直说话；连续失败等明显事件又能够主动出现。

---

### Phase 6：加入 Memory

第一版使用 SQLite 即可。

先保存结构化事件：

```text
death
boss_attempt
boss_success
progression
equipment_change
agent_intervention
```

然后实现：

```text
search_memory
write_memory
```

Memory Write Policy 只保存重要经历，不保存所有 tick。

第一版检索甚至可以先用 SQL + recent history。

之后再考虑 embedding episodic memory。

**完成标准：**

Agent 能正确说出：

> “这是你今天第三次死在这个 Boss。”

并且不会因为旧记录覆盖当前状态而产生明显错误。

---

### Phase 7：构建一个小型 Local RAG

此时再开始做 RAG。

不要先抓整个 Wiki。

先准备少量高质量知识：

```text
Progression
Boss strategy
Equipment guidance
NPC / biome mechanics
```

建议先覆盖最常用的 10～15 个核心场景。

流程：

```text
Document
→ heading-aware chunk
→ metadata
→ embedding
→ FAISS / Qdrant
```

实现：

```text
search_local_knowledge(query, metadata)
```

**完成标准：**

用户问：

> “我现在准备打 Skeletron，这套装备有什么明显问题？”

Agent 可以：

```text
Current State
+
Local RAG
→ 给出有依据的建议
```

---

### Phase 8：实现 Agentic Routing

这时才让 Agent 自己决定查什么。

目标不是所有 Query 都 RAG。

Router 可以选择：

```text
DIRECT
STATE
MEMORY
LOCAL_RAG
EXTERNAL_WIKI
```

例如：

```text
“现在下雨了吗？”
→ STATE

“我在这里死过几次？”
→ MEMORY

“我的装备适合打这个 Boss 吗？”
→ STATE + LOCAL_RAG

“最新版这个物品掉率是多少？”
→ EXTERNAL_WIKI
```

**完成标准：**

不同 Query 可以走不同信息路径，并避免明显的无意义检索。

---

### Phase 9：再加入 MCP / 外部 Wiki

MCP 放在 Local RAG 已经工作以后。

它主要负责：

```text
长尾知识
精确事实
可能随版本变化的信息
Local RAG 没有命中的知识
```

不要让 MCP 成为所有问题的默认入口。

**完成标准：**

Local RAG 无法可靠回答时，Agent 可以 fallback 到外部 Wiki，并把结果继续交给 LangGraph。

如果时间不够，MCP 可以留作 Plus，而不影响 MVP 完整性。

---

### Phase 10：加入有限 ReAct

只有复杂任务进入 ReAct。

例如：

```text
“按照我现在的情况，下一步最适合干什么？”
```

可能需要：

```text
get_progression
→ search_memory
→ search_local_knowledge
→ 发现信息不足
→ 再调用 Tool
→ Answer
```

必须限制：

```text
max_steps
tool budget
duplicate tool-call detection
timeout
fallback
```

**完成标准：**

复杂 Query 可以完成 2～4 步动态 Tool Calling，而简单 Query 不进入 ReAct。

---

### Phase 11：建立 Scenario Benchmark

不要等整个项目做完才开始评价。

准备约 30～50 个 Scenario，覆盖：

```text
H1 Reactive
H2 Contextual
H3 Knowledge / Multi-step
H4 Temporal / Personalized
```

重点指标：

```text
Trigger Precision
Important Event Recall
Unnecessary Interruption Rate
Tool Routing Accuracy
Memory Correctness
Duplicate Reminder Rate
Response Latency
LLM / Tool Calls
```

尤其比较：

```text
Always Respond
vs
Rule Only
vs
Event-driven Agent
```

以及：

```text
Never RAG
vs
Always RAG
vs
Selective Retrieval
```

目的是回答真实工程问题，而不是为了证明“模块越多越好”。

---

### Phase 12：最后做 Demo 和项目包装

最后再整理：

- README
- 架构图
- Demo 视频
- Scenario Evaluation 表格
- 典型失败案例
- 技术选型说明

Demo 最好展示一条完整链路：

```text
玩家挑战 Boss
→ 连续失败
→ Agent 读取历史
→ 判断值得介入
→ 检索攻略
→ 给简短建议
→ 玩家继续游戏
```

再展示一次用户主动 Query：

```text
玩家提问
→ Agent 自动选择 State / Memory / RAG
→ 回答
```

这样可以同时证明：

- Proactive Agent
- LangGraph
- Skill / Tool Calling
- Memory
- Agentic RAG
- 游戏环境交互

---

## 22. 推荐的实际开发优先级

如果只有两到三周，优先级可以压缩为：

```text
P0
tModLoader ↔ Python 双向通信
↓
P0
Game State + Event
↓
P0
游戏内 Query + Message
↓
P0
LangGraph 基础 Workflow
↓
P0
Event Trigger / Speak Policy
↓
P1
Memory
↓
P1
Local RAG
↓
P1
Agentic Routing
↓
P2
MCP / Wiki
↓
P2
ReAct Multi-step
↓
P0
Scenario Evaluation + Demo
```

其中最不能砍掉的是：

> **游戏环境交互、主动 Trigger、Memory、双入口、基础 Agentic Routing。**

如果时间紧，最先可以砍掉的是：

> **MCP、复杂 ReAct、GraphRAG、复杂向量 Memory。**

项目是否成立，关键不在技术名词数量，而在于下面这条链路能不能稳定跑通：

```text
Observe
→ Remember
→ Decide
→ Retrieve when needed
→ Respond
```
