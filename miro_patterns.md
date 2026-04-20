# Miro AVG Flowchart 数据规律分析

> 基于 board `uXjVGrwCCP4=` (name: `UntitledSpringDebris_Flowchart`)
> 数据源: `uXjVGrwCCP4_items.json` (266 items) + `uXjVGrwCCP4_connectors.json` (106 connectors)
> 此文档用于确定"把 Miro 数据转成场景化 JSON 集群"之前需要对齐的规则。

---

## 1. 总览

266 个 item + 106 个 connector。按 `type` 分:

| type          | 数量 | 角色 |
|---------------|----:|------|
| `shape`       | 110 | 主体 — 真正参与流程的图元 |
| `text`        | 96  | 旁注、描述、策划备注、Twine 路径说明 |
| `sticky_note` | 60  | 物品/状态标签卡(以及"开始/通关"这类锚点) |

`shape` 还要看 `data.shape` 子类型才能判断用途:

| data.shape               | 数量 | 用途 |
|--------------------------|----:|------|
| `rectangle`              | 63 | **不是场景** — 绝大多数是绘制"物品表格"的单元格;少数是大背景框用于分组 |
| `flow_chart_process`     | 26 | **候选场景** — 圆角/直角过程框,含场景名(游戏开始、床、门、窗、书架、烟囱…)、也有"获得大/获得小"这种奖励壳 |
| `flow_chart_decision`    | 10 | **分支节点** — 菱形,几乎全是"万花筒"(本作的穿越机关),代表需要做选择/带条件 |
| `flow_chart_terminator`  | 7  | **锚点/剧情段结束** — "NPC 对话,获取关键名词【床】…"、"确认当前文本某全局变量"、"游戏正式开始" |
| `rhombus`, `circle`, `flow_chart_preparation` | 4 | 零星,基本可忽略或按"未知图元"处理 |

---

## 2. 节点颜色的语义(高度推测,需用户确认)

`flow_chart_process` 的 `fillColor` 呈现出几组:

| 颜色       | 出现处 | 推测含义 |
|------------|-------|---------|
| `#ffffff`(白) | 游戏开始、【导入】 | 骨架锚点 |
| `#fff6b6`(浅黄) | 床、门、窗、书架、烟囱、尸骸 | **主线场景**(核心可探索位置) |
| `#dedaff`(浅紫) | "梦中床 [[直接跳转回【床】|床]]"、Passage 跳转 | **另一维度/梦境镜像**的同名场景 |
| `#adf0c7`(浅绿) | "记忆床 [[…|床]]" | **另一维度/记忆镜像** |
| `#c6dcff`(浅蓝) | "获得大"(两次) | **奖励节点**,代表这里产出大尺寸物品 |
| `#ffc6c6`(浅红) | "梦境集合结束 | 记忆集合"、"新章节(通过 CG)" | **剧情段落切换/过渡** |
| `#e7e7e7`(灰) | 床、记忆床、梦中床 | 可能是草稿/待定位置 |
| `#b0b0b0`(深灰) | "床" | 与 e7e7e7 区分,可能是"已弃用"变体 |

**关键:颜色 = 维度 + 语义**。同一个逻辑位置("床")在三个维度里各有一份,靠颜色区分。

---

## 3. 文本语法约定

### 3.1 零宽空格 U+200B
**每个中文字之间几乎都有 `\u200b`。** 处理前必须 `.replace('\u200b','')`。这是 Miro 前端为断行塞进去的,不是语义内容。

### 3.2 HTML 外壳
每个 `data.content` 都是 HTML,形如 `<p><span style="…">游戏</span>开始</p>`。剥 HTML 后才能比较文本。HTML 实体 `&#xff1a;`(即全角冒号`:`)、`&#xff08;`/`&#xff09;`(全角括号)会原样出现,剥 HTML 时要解码。

### 3.3 Twine Wiki 链接
节点文字里内嵌 `[[目标 | 显示文字]]` 或 `[[显示文字|目标]]`,语义是 **Twine passage 跳转**。例:

- `梦中床 [[直接跳转回【床】 | 床]]` — 这个节点的名字是"梦中床",并内嵌了一条"直接跳回【床】"的跳转
- `重来  [[重来 | C 开始]]`

这些内嵌跳转不是图上的连线 — 而是 **Twine 运行时的跳转**。导出时应该把它们作为 scene 的额外 `twine_links: [...]` 字段。

### 3.4 方括号【...】
用来圈"关键名词/关键状态"。高频模式:

- `【导入】` — 剧情标记
- `NPC 对话,获取关键名词【床】和关键状态【梦中】` — 声明玩家此处获得一个 name token 和 state token
- `【描述:】...`(text 节点) — 对最近那个 shape 的详细描述
- `【条件:】...`(text 节点) — 某条边的条件说明
- `注:...`(text 节点) — 策划备注,非数据

### 3.5 前缀统计(仅 text 节点 96 个)
- `【描述:】` — 场景描述文本(与某 shape 空间相邻)
- `【条件:】` — 条件说明(与某条 edge/shape 相邻)
- `注:` — 策划/开发备注,应当忽略
- 裸文字(不带前缀) — 多为位置标签、章节标题(如"梦中床"重复出现是表格行/列标题)

---

## 4. 边(Connector)的语义

### 4.1 caption 统计
106 条连线里 **只有 4 条带 caption**:

- `我是【梦】`(2 次,其中 1 条是 dangling)
- `我是【床】`(dangling)
- `放下万花筒`(2 次)

**推断的 caption 语义**:
- `我是【X】` → 该边表示"产出物品/状态 X"(相当于 drawio 里的"获得:X")
- `放下万花筒` → 条件(需要玩家执行动作"放下万花筒"才能走这条边,相当于"需要:放下万花筒")

### 4.2 大多数边无 caption
**条件和奖励并不是全靠边 caption 表达。** 更常见的模式是:

- **奖励**:在 `flow_chart_terminator` 节点文字里写"获取关键名词【X】和关键状态【Y】";或在 `flow_chart_process` 文字里直接写"获得大"
- **条件**:通常没有明确声明;或放在边旁边的 `text` 节点(前缀"【条件:】"),靠空间邻近推断属于哪条边

→ **这是 Miro 版本比 drawio 版本难处理的主要差异**: 语义不在边上,而在相邻的注释节点里。

### 4.3 dangling edges(6 条)
- 4 条从 `rectangle` 或 `flow_chart_decision` 出发,`to=None`,无 caption
- 2 条从 `flow_chart_decision`(万花筒)出发,caption 是"我是【梦】"/"我是【床】"

→ **都是策划没画完的 TODO**,不是容器指向。转换时单独输出到 `_drafts` 字段,不丢弃。

---

## 5. 入口、孤儿、容器

### 5.1 10 个 entry(无入边、有出边)

- **真入口**: `游戏开始`(flow_chart_process, #ffffff) — 唯一的剧情总起点
- **各维度的独立起点**: `门`、`窗`、`书架`、`记忆床`、`梦中床` — 这些本应从"床"走过来,但画图时可能用 Twine 跳转(`[[...]]`)代替了实线连接
- **烟囱相关的 decision 入口**: 两个 `flow_chart_decision` "万花筒..."没画入边,是图的残缺
- **两个 sticky_note "开始"**: 命名锚点,对应 Twine passage,不是真图节点

→ 入口判定不能只看图拓扑,**还要结合 Twine `[[...]]` 反向边**。

### 5.2 171 个 isolated(无任何边)

大头是 text 注释 + 物品表格。具体:

- **物品名称便签**(sticky_note 60 + 大量小 rectangle 63) — 场地×物品二维表格的单元格: 行 = 场地名(墙/床/窗),列 = 物品(毛线/书架/尸骸/万花筒/卡片/怀表/明信片/原稿/心)。这不是"流程",是"物品清单矩阵"。
- **【描述:】 text 块** — 靠空间邻近挂到最近的场景 shape
- **注: text 块** — 纯备注,忽略

→ 孤儿 ≠ 垃圾。需要二次处理:
1. 用位置(`position.x/y` + `geometry.width/height`)做空间聚类,把注释归到最近的场景
2. 把"物品矩阵"单独识别并输出成 `items_matrix.json`

### 5.3 大背景 rectangle(容器)
- 1 个 `rectangle` w=534 h=1143 — 大概是整个梦境区的背景框
- 1 个 w=512 h=334,文字 "这里是穿越过来后的安全 passage 区域" — 是分区容器

→ 按包含关系判断每个场景属于哪个"分区",输出成 `region` 字段。

---

## 6. 提议的场景判定规则

参考 drawio 版本的"rounded=1 → scene"思路,Miro 版本的**候选场景判定**:

```
is_scene(node) =
    node.type == "shape"
    AND node.data.shape in {
        "flow_chart_process",
        "flow_chart_decision",
        "flow_chart_terminator"
    }
    AND node.content_text 去 ZWS/HTML 后非空
    AND 不全是 Twine 跳转占位(例如不只剩 "[[...|...]]" 而已)
```

**三类 shape 的角色分工**(建议):
- `flow_chart_process` → `type: "scene"` 场景
- `flow_chart_decision` → `type: "choice"` 分支(条件转场)
- `flow_chart_terminator` → `type: "anchor"` 剧情锚(NPC 对话、段落切换、关键物品获得)

sticky_note 和 text **不是 scene**,但作为附属元数据挂靠:
- sticky_note 附近若有"获得 X"类说明 → 物品
- text 前缀 `【描述:】` → 挂到最近场景的 `description`
- text 前缀 `【条件:】` → 挂到最近边的 `condition`

---

## 7. 提议的输出结构(供讨论)

沿用 drawio 脚本的 `index.json` + `scene_X.json` 集群形式,扩展:

```jsonc
// index.json
{
  "source": "miro://uXjVGrwCCP4=",
  "generated_at": "...",
  "schema": { /* 字段说明,给下游 AI agent 看 */ },
  "scenes":  [ {"id":"scene_床_主线", "name":"床", "region":"梦境区", "file":"scene_床_主线.json"} ],
  "items":   ["床","门","钥匙","万花筒","怀表",...],
  "states":  ["梦中","记忆中",...],
  "dimensions": ["主线","梦中","记忆中"],   // 从颜色推出
  "drafts":  [ /* dangling edges 和未画完的分支 */ ]
}

// scene_床_主线.json
{
  "id": "scene_床_主线",
  "name": "床",
  "shape_type": "flow_chart_process",
  "dimension": "主线",              // 由颜色 #fff6b6 推出
  "region": "梦境区",                // 由容器矩形包含关系推出
  "description": "【描述:】一张床……",  // 从空间邻近的 text 抽出
  "exits": [
    {
      "to": "scene_门_主线",
      "conditions": [],
      "mechanism": "connector"       // 或 "twine_link"(来自 [[...]])
    }
  ],
  "rewards": ["床(关键名词)", "梦中(关键状态)"],  // 从终结节点/边 caption 抽出
  "incoming": [...],
  "twine_links": [ {"label":"直接跳转回【床】","target":"床"} ],
  "source_item_ids": ["3458764665303867882"],
  "notes": ["注: ...", ...]          // 非关键策划备注原样保留
}
```

---

## 8. 与 drawio 版的差异(写转换器前要知道)

| 方面 | drawio | Miro |
|------|--------|------|
| 场景形状 | `rounded=1` 单一类型 | shape 子类型有 3 种语义角色 |
| 物品 | 文本框 + "获得:" 前缀 | sticky_note / 终结节点 / 内嵌 `【X】` / 边 caption `我是【X】` 四选一 |
| 条件 | edgeLabel + "需要:" 前缀 | 边 caption(极少) + 相邻 `【条件:】` text(多数) |
| 跳转 | 只有图边 | 图边 **加** 内嵌 Twine `[[...]]` |
| 维度 | 无 | 颜色编码三个维度(主线/梦中/记忆中) |
| 分区 | 无 | 大背景 rectangle 做视觉容器 |
| 容错 | 孤儿节点基本没有 | 171 个孤儿要空间聚类回收 |

---

## 9. 待用户确认的问题

1. **颜色语义**我是靠观察猜的,尤其三个维度(主线/梦中/记忆中)和"浅蓝=奖励"。对吗?
2. 物品表格(171 孤儿里的小 rectangle 方阵)**是否需要**提取成 `items_matrix.json`?还是完全忽略?
3. `flow_chart_terminator` 这些 "NPC 对话,获取关键名词【X】和关键状态【Y】" 节点,应该当成一个 **独立的 anchor scene**,还是 **合并成其前驱场景的 rewards**?
4. Twine 内嵌跳转 `[[A|B]]` 要和图连线**合并为同一个 exits 列表**,还是分开存到 `twine_links`?
5. `注:` 开头的 text 节点(纯策划备注),要不要彻底丢弃,还是保留到 `notes` 里?
6. 六条 dangling edge 属于 TODO,直接放 `drafts` 数组,不触发报错 — 对吗?

---

## 10. 关键数据回顾(用于后续对齐)

**全部 26 个 `flow_chart_process`**(候选主场景):
游戏开始 / 【导入】 / 床 / 门 / 窗 / 书架 / 梦中床(×2) / 记忆床(×2) / 尸骸 / 重来 / 获得大(×2) / 记忆结束 | 梦境结束 / 新章节(通过 CG) / 床 / Passage 梦中床 / 床(灰) / 记忆床(灰) / 梦中床(灰)

**全部 10 个 `flow_chart_decision`**: 全部都叫"万花筒"(或带说明的万花筒),是本作的传送机制

**全部 7 个 `flow_chart_terminator`**:
1. NPC 对话,获取关键名词【床】和关键状态【梦中】
2. NPC 对话(参考草稿 P7 & 草稿 P5)
3. NPC 对话,获取关键名词【钥匙】
4. NPC 对话,获取关键名词【 】游戏正式开始
5. NPC 对话,获取关键名词【 】(钥匙?)
6. 烟囱所需 passage
7. 确认当前文本某全局变量

**带 caption 的 4 条边**: `我是【梦】`、`我是【床】`、`放下万花筒` ×2
