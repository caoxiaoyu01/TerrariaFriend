<p align="center">
  <img src="./assets/terraria-banner.png" alt="TerrariaFriend Banner" width="100%">
</p>

# TerrariaFriend

TerrariaFriend 是一个面向 **Terraria** 的 AI 游戏伙伴模组

它不会替玩家自动操作游戏，而是根据实时游戏状态、游戏事件、玩家提问和历史经历，在合适的时机提供提示、解释与建议

由两部分组成：

- **C# / tModLoader 模组**：采集游戏状态、识别事件、接收玩家输入并展示回复
- **Python Agent**：负责决策、工具调用、知识查询、记忆检索与多轮推理

> 项目持更中~

## 主要功能

### 事件驱动交互

支持三类触发：

- 玩家主动提问
- 游戏事件触发
- 周期性检查

Decision Node 会根据当前 Trigger 和游戏上下文选择：

```text
IGNORE  → 不打扰玩家
RESPOND → 轻量直接回应
REASON  → 进入多步推理与工具调用
```

可识别 Boss、玩家死亡、场景变化、装备变化、世界事件等游戏状态变化。

### 实时游戏上下文

Agent 可以按需读取：

- Player：生命、魔力、防御、位置、手持物品、Buff 等
- Combat：战斗状态、Boss、附近敌人、近期受伤
- Inventory：快捷栏、装备、饰品、恢复物品、背包空间
- Progress：Boss 击败情况、世界阶段、重要区域探索
- Scene / World：群系、特殊区域、时间、天气和世界事件

当前状态始终以实时 GameSnapshot 为准。

### Terraria Wiki 查询

当问题涉及精确掉落、配方、获取方式、召唤条件、生成规则或具体机制时，Reasoner 可以按需调用 **Terraria Wiki MCP**，而不是只依赖模型自身知识。

### Memory

TerrariaFriend 将历史记忆分为两层：

- **L1 Recent Memory**：保存近期完整对话和游戏 Episode，并按 Trace 组织
- **L2 Long-term Memory**：借助 graphiti FalkerDB 同时存储图节点和语义信息，重要 Episode 中抽取值得长期保留的玩家经历与关系保存

例如：

```text
Player -- DEFEATED --> Queen Bee
Player -- VISITED --> Bee Hive
Player -- PREFERS --> Ranged Combat
```

Reasoner 可以通过统一的 Memory Retrieval 查询近期或长期记忆，用于恢复上下文和生成更贴合玩家经历的回答。

## **Workflow**

```text
                    Terraria / tModLoader
                           │
          ┌────────────────┼────────────────┐
          │                │                │
      User Query       Game Event        Periodic
          │                │                │
          └────────────────┴────────────────┘
                           │
                      GameSnapshot
                           │
                           ▼
                    ┌───────────────┐
                    │ Decision Node │
                    └───────┬───────┘
                            │
              ┌─────────────┼─────────────┐
              │             │             │
              ▼             ▼             ▼
           IGNORE        RESPOND        REASON
                            │             │
                            │             ▼
                            │       ┌────────────┐
                            │       │  Reasoner  │
                            │       └─────┬──────┘
                            │             │
                   ┌────────┘      ┌──────┼───────────────┐
                   │               │      │               │
                   ▼               ▼      ▼               ▼
            Game Context      Game Context Wiki MCP   Memory Retrieval
                Tools             Tools                   │
                                                          │
                                              ┌───────────┴───────────┐
                                              │                       │
                                              ▼                       ▼
                                       L1 Recent Memory        L2 Long-term Memory
                                       Episode / Trace         Graphiti / FalkorDB
                                              ▲                       ▲
                                              │                       │
                         Game Event / Query ──► Trace Runtime ──► Memory Formation
                                              │
                                              └───────────────────────┘

                            └──────────────┬──────────────┘
                                           ▼
                                    Final Response
                                           │
                                           ▼
                               Terraria In-game Message
```

不同信息由不同来源负责：

| 信息 | 来源 |
| --- | --- |
| 当前玩家 / 世界状态 | Game Context |
| 玩家过去的对话与经历 | Memory |
| Terraria 公共知识 | Terraria Wiki |
| 世界永久进度 | Progress |

## 技术与开发配置

| 部分 | 当前配置 |
| --- | --- |
| 游戏客户端 | C# / tModLoader |
| Agent 服务 | Python 3.12 / FastAPI / LangGraph |
| Python 环境管理 | uv |
| LLM | SiliconFlow / DeepSeek 兼容接口 |
| 当前主要模型 | DeepSeek V4 Flash |
| 长期记忆 | Graphiti + FalkorDB |
| Embedding / Reranker | Gemini |
| 游戏知识 | Terraria Wiki MCP |


## 本地启动

当前开发环境下，Agent 服务从 `agent` 目录启动：

```powershell
uv run agent
```

游戏内以 `@` 开头的聊天消息会发送给 TerrariaFriend，例如：

```text
@我现在适合挑战蜂王吗
```

普通聊天消息不会进入 Agent 流程

## 项目结构

```text
TerrariaFriend/
├── AgentCommunication/    # 游戏端与 Agent 通信
├── Common/                # 界面和聊天入口
├── Content/               # 模组命令与内容
├── GameState/             # GameSnapshot 与状态采集
├── Triggering/            # 游戏事件检测与触发
├── agent/
│   ├── src/agent/
│   │   ├── decision/      # IGNORE / RESPOND / REASON
│   │   ├── reasoning/     # Reasoner 与工具调用
│   │   ├── response/      # 轻量回复
│   │   ├── trace/         # Episode / Trace / L1
│   │   ├── memory/        # L2 Formation 与 Retrieval
│   │   └── mcp_servers/   # Terraria Wiki MCP
│   └── tests/
├── TerrariaFriend.csproj
└── README.md
```

## 当前状态

目前已经完成：

- [x] 游戏状态采集与事件触发
- [x] Decision / Response / Reasoning 主链路
- [x] Game Context Tools
- [x] Terraria Wiki MCP
- [x] Recent Memory（Episode / Trace）与 Long-term Memory（Graphiti / FalkorDB）Retrieval
- [x] Trace 持久化、恢复与异步 Episode 重排
- [x] 游戏内聊天入口与 Agent 回复展示

当前仍在继续优化真实游戏中的事件边界、Memory Retrieval 精度、响应延迟和整体交互体验。
