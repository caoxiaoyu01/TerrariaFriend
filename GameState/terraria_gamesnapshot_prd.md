# Terraria Companion Agent — GameSnapshot PRD

**版本**：v0.1  
**模块**：Game State / GameSnapshot  
**目标阶段**：MVP  
**定位**：为 Companion Agent 提供稳定、轻量、可解释的游戏环境状态输入

## 1. 背景

Terraria Companion Agent 不负责自动操作玩家，而是持续理解玩家当前处境，并在合适的时候提供帮助、提醒或陪伴式反馈。

因此需要在 tModLoader 游戏端建立一层统一状态抽象，让 Agent 能稳定理解：

- 玩家现在是什么状态；
- 玩家拥有什么关键装备与资源；
- 当前位于什么环境；
- 世界正在发生什么；
- 世界推进到什么阶段；
- 当前是否处于战斗或危险；
- 附近有哪些重要 NPC、敌人或 Boss。

这层统一状态定义为 **GameSnapshot**。

GameSnapshot 不是 Terraria 全部内部状态的镜像，而是：

> 面向 Agent 的、经过筛选和语义化的当前游戏状态。

---

## 2. 产品目标

GameSnapshot MVP 需要让 Agent 能回答 7 个基本问题：

1. **WHO**：玩家现在是什么状态？
2. **HAVE**：玩家拥有什么关键装备与资源？
3. **WHERE**：玩家现在在哪里、处于什么环境？
4. **WORLD**：当前世界正在发生什么？
5. **PROGRESS**：这个世界推进到了什么阶段？
6. **DANGER**：玩家当前是否处于战斗或危险中？
7. **WHO ELSE**：当前有哪些重要 NPC、敌人或 Boss？

如果这 7 个问题能够稳定回答，GameSnapshot MVP 即成立。

### 非目标

MVP 不追求：

- 完整复制 Terraria 内部状态；
- 保存每一个 tick；
- 扫描整个世界地图；
- 精确重建所有 tile；
- 记录所有箱子内容；
- 完整分析所有房屋；
- 精确 DPS 分析；
- 直接暴露 Terraria 原始 Player / NPC / Item 对象；
- 在 GameSnapshot 中承担长期 Memory。

原则：

> **Agent-complete，而不是 Engine-complete。**

---

## 3. 核心数据边界

整个状态系统分成四类：

```text
GameSnapshot
= What is true now

EventBuffer
= What just happened

PersistentWorldState
= What has happened / been discovered in this world

Agent Memory
= What past experience is worth remembering
```

必须保持这四层边界清晰。

例如：

- 当前 HP → GameSnapshot
- 最近 5 秒受到多少伤害 → EventBuffer 聚合后进入 CombatSnapshot
- Jungle 是否曾探索 → PersistentWorldState
- 上次打 Skeletron 连死三次 → Agent Memory

---

## 4. GameSnapshot 产品结构

```text
GameSnapshot
├── Player
├── Inventory
├── World
├── Progress
│   ├── BossProgress
│   ├── WorldProgress
│   └── Exploration
├── Scene
├── Combat
└── NPC
```

---

## 5. Player

### 职责

描述玩家当前自身状态。

### MVP Scope

- HP / Max HP
- Mana / Max Mana
- 是否死亡
- Position
- Velocity
- Defense
- 当前手持物品
- 主要 Buff / Debuff

### 暂不包含

- 所有内部 cooldown
- 动画状态
- 完整 combat modifier
- 精细职业伤害参数

---

## 6. Inventory

### 职责

描述玩家当前拥有的、对决策有价值的资源。

主要支持：

- Boss 准备判断
- 装备建议
- 药水提醒
- 背包空间提醒
- progression 判断

### MVP Scope

- 当前武器
- Armor
- Accessories
- Hotbar
- Healing Potion 数量
- Free Slot 数量

### 产品原则

不把完整 Terraria Item 对象直接交给 Agent。

统一转换成轻量 Item Summary，只保留：

- TypeId
- Name
- Stack
- Damage / Defense（需要时）
- Consumable 等少量语义字段

---

## 7. World

### 职责

描述整个世界当前的全局环境。

### MVP Scope

- Day / Night
- Rain
- Hardmode
- Blood Moon
- Eclipse
- Invasion / Major Event

### 与 Scene 的区别

World 回答：

> 整个世界现在发生什么？

Scene 回答：

> 玩家身边现在是什么环境？

---

## 8. Progress

Progress 回答：

> 这个世界已经发展到哪里？

### 8.1 BossProgress

记录关键 Vanilla Boss 是否已经击败。

主要用于：

- 判断 progression
- 推荐下一目标
- 避免过时建议

### 8.2 WorldProgress

记录世界级关键阶段变化，例如：

- Hardmode
- Mechanical Boss 进度
- Plantera
- Temple
- Lunar progression

优先读取 Terraria 原生 world flags。

### 8.3 Exploration

记录：

> 玩家在这个世界历史上已经探索过哪些关键区域。

MVP 可覆盖：

- Jungle
- Dungeon
- Underworld
- Sky
- Ocean
- Temple
- Shimmer
- Snow
- Desert

Exploration 的 source of truth 属于 **PersistentWorldState**。

数据流：

```text
玩家第一次进入 Jungle
→ ExplorationTracker 检测
→ 标记 Jungle 已探索
→ 保存世界数据
→ ProgressSnapshot.Exploration 对外暴露
```

---

## 9. Scene

### 职责

描述玩家当前所在的局部环境。

### 数据来源

```text
Player.ZoneXXX
+
SceneMetrics
+
Player Position
```

统一转换成 SceneSnapshot。

### MVP Scope

- Primary Biome
- Active Biomes
- Surface / Underground / Cavern / Underworld
- Campfire Nearby
- Heart Lantern Nearby
- Graveyard
- Town NPC Count Nearby

### 设计说明

已有 SceneMetrics 仍然需要 SceneSnapshot。

因为：

- SceneMetrics 是 Terraria 内部数据源；
- SceneSnapshot 是我们稳定暴露给 Agent 的语义接口。

Python Agent 不应该直接依赖 tModLoader 内部字段。

---

## 10. Combat

### 职责

描述玩家当前是否正在战斗，以及危险程度。

Combat 不等于 Boss Fight。

```text
普通战斗：
InCombat = true
BossActive = false

Boss 战：
InCombat = true
BossActive = true

正常探索：
InCombat = false
```

### MVP Scope

- InCombat
- BossActive
- ActiveBoss
- NearbyEnemyCount
- HP Ratio
- 最近 5 秒受到的伤害
- Last Damage Source

### 数据来源

Combat 由两类数据组成：

```text
Current State
+
Recent Events
```

因此需要独立 CombatTracker / EventBuffer。

---

## 11. NPC

### 职责

让 Agent 知道：

- 当前世界有哪些重要 Town NPC；
- 玩家附近有哪些重要 NPC；
- 当前是否存在 Boss。

### MVP Scope

- 已存在的 Town NPC
- Nearby Hostile Count
- Active Boss
- Nearby Important NPC

### 暂不包含

- 全世界 NPC 精确位置地图
- 完整 Housing Validation
- 自动统计全部合法空房间

---

## 12. 系统架构

```text
Terraria Runtime API
        │
        ├── Player
        ├── Main
        ├── NPC
        └── SceneMetrics
        │
        ↓
Snapshot Collectors
        │
        │
Hooks / Events ───→ EventBuffer
        │                 │
        │                 ↓
        │           CombatTracker
        │
Persistent Data ──→ ExplorationTracker
        │
        └─────────────┬─────────────
                      ↓
               GameStateCollector
                      ↓
                 GameSnapshot
                      ↓
                Python Agent
```

---

## 13. 工程组织

```text
GameState/
├── Snapshots/
│   ├── GameSnapshot.cs
│   ├── PlayerSnapshot.cs
│   ├── InventorySnapshot.cs
│   ├── WorldSnapshot.cs
│   ├── ProgressSnapshot.cs
│   ├── SceneSnapshot.cs
│   ├── CombatSnapshot.cs
│   └── NpcSnapshot.cs
│
├── Collectors/
│   ├── PlayerCollector.cs
│   ├── InventoryCollector.cs
│   ├── WorldCollector.cs
│   ├── ProgressCollector.cs
│   ├── SceneCollector.cs
│   ├── CombatCollector.cs
│   └── NpcCollector.cs
│
├── Tracking/
│   ├── CombatTracker.cs
│   ├── ExplorationTracker.cs
│   └── EventBuffer.cs
│
├── Persistence/
│   └── CompanionWorldState.cs
│
└── GameStateCollector.cs
```

---

## 14. 数据结构原则

### Snapshot

使用只读 DTO：

- `record`
- 或 `sealed class + init`

Snapshot 表示某一时刻已经发生的事实，创建后不再修改。

### Terraria 类型隔离

禁止直接向 Python 暴露：

- Player
- NPC
- Item
- SceneMetrics

统一转换为：

```text
Terraria Runtime Object
→ Collector
→ Snapshot / Summary
→ JSON
```

### 集合优先

对于可扩展对象，不建议不断增加 bool。

例如 Exploration：

```text
VisitedRegions = {
    Jungle,
    Dungeon,
    Sky
}
```

优于：

```text
VisitedJungle
VisitedDungeon
VisitedSky
...
```

BossProgress 同理。

---

## 18. 验收标准

### Case 1：普通探索

玩家在 Jungle 地表正常探索。

系统应正确识别：

- Jungle
- Surface
- 非战斗
- 当前 HP
- 当前装备
- Jungle 已标记 visited

### Case 2：普通战斗

玩家被多个普通怪物攻击。

应正确识别：

- InCombat = true
- BossActive = false
- NearbyEnemyCount > 0
- RecentDamage > 0

### Case 3：Boss 战

Skeletron 出现。

应正确识别：

- InCombat = true
- BossActive = true
- ActiveBoss = Skeletron
- Player / Inventory / Progress 同时可读取

### Case 4：Progression

玩家击败关键 Boss。

下一次 Snapshot 应正确更新：

- BossProgress
- 对应 WorldProgress

### Case 5：探索持久化

玩家访问 Jungle 后退出并重新进入世界。

仍应：

```text
VisitedJungle = true
```

---

## 19. 开发顺序

### Step 1

完成：

```text
GameSnapshot
PlayerSnapshot
PlayerCollector
```

目标：成功读取 Player State 并输出 JSON。

### Step 2

增加：

```text
World
Scene
```

目标：Agent 能理解玩家在哪里、世界当前环境如何。

### Step 3

增加：

```text
Inventory
Progress
```

目标：Agent 能理解玩家拥有什么、世界发展到哪里。

### Step 4

增加：

```text
ExplorationTracker
PersistentWorldState
```

目标：保存“这个世界探索过哪里”。

### Step 5

增加：

```text
CombatTracker
EventBuffer
```

目标：理解普通战斗和 Boss 战。

### Step 6

增加：

```text
NPC
```

完成 GameSnapshot MVP。

---


---

## 21. 最终原则

GameSnapshot 的职责不是：

> 把 Terraria 全部数据交给 Agent。

而是：

> **把复杂的 Terraria Runtime 压缩成一份稳定、清晰、对 Agent 决策有意义的世界描述。**

设计是否成功，不看字段数量，而看：

> Agent 是否能够基于这份 Snapshot 正确理解“现在发生了什么”。
