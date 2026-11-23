# 教学助手出图能力 · 实施计划（2026-11-20 待评审）

> 说明：按「图表（可视化）」理解，不是 emoji 图标。若你要的是给数据项配小图标，方案会简单很多（见文末 C 方案），告诉我即可切换。

## 1 目标

助手回答里的数据目前全是文字和数字卡片。目标是让同一份事实**同时有图和文字**：教师一眼看到到勤构成和趋势，学生一眼看到自己成绩分布和薄弱知识点。

非目标（本期不做）：
- 不做交互式图表（点柱子钻取、缩放、悬浮提示）
- 不引入图表库（ECharts / Chart.js），不增加打包体积
- 不做图片导出 / 分享卡片
- 不改任何统计口径：图里的数字必须和文字里的数字是同一份

## 2 现状（已核实）

`frontend/js/charts.js` 已有三个零依赖 SVG 函数：

| 函数 | 签名要点 | 已有使用方 |
|---|---|---|
| `donutChart(slices, {size, thickness, gap})` | 输入 `[{label,value,color}]`，返回 `{nodes,total,rows,empty}`；图例含 0 值项 | `analytics-view.js` 考勤环形图 |
| `barChart(series, {width,height,baseColor,fillColor})` | 输入 `[{label,expected,present}]`，画「底柱 + 前柱」双柱 | `analytics-view.js` 按周到勤柱状图 |
| `lineChart(points, {width,height,max,unit})` | 输入 `[{label,value}]`，**少于 2 点返回空态** | 目前无人使用 |

`analytics-view.js` 第 44—75 行有一个本地 `chartNode(node)`，负责把 `charts.js` 返回的节点数组渲染成 `h('line'|'path'|'rect'|'circle'|'text')`。这个函数要抽出来复用，否则助手视图会复制一份。

## 3 方案：后端只给数据，前端只画图

### 3.1 后端响应新增 `charts` 字段

```json
"charts": [
  {
    "id": "attendance-donut",
    "kind": "donut",
    "title": "到勤构成",
    "unit": "人次",
    "source": "010A",
    "note": "出勤含迟到",
    "slices": [
      { "label": "出勤", "value": 321, "colorKey": "present" },
      { "label": "迟到", "value": 15,  "colorKey": "late" },
      { "label": "请假", "value": 11,  "colorKey": "leave" },
      { "label": "缺勤", "value": 773, "colorKey": "absent" }
    ]
  },
  {
    "id": "mastery-bars",
    "kind": "bar",
    "title": "掌握度最低的 3 个知识点",
    "unit": "percent",
    "source": "010B",
    "bars": [
      { "label": "ALU 的运算选择", "value": 60, "total": 100 },
      { "label": "存储器组织与地址译码", "value": 60, "total": 100 }
    ]
  },
  {
    "id": "attendance-trend",
    "kind": "line",
    "title": "按周到勤率",
    "unit": "ratio",
    "max": 1,
    "source": "010A",
    "points": [
      { "label": "10-26", "value": 0.42 },
      { "label": "11-02", "value": 0.55 },
      { "label": "11-09", "value": 0.31 }
    ]
  }
]
```

约束：
- **颜色不落库**：后端只给 `colorKey`（present / late / leave / absent / accent / high / mid / low），前端从 `chartColors` 映射，保持与统计页同一套配色。
- **数字同源**：`charts` 与 `facts` 必须由同一次计算得到，不允许为画图再查一次库。
- **空就不给**：达不到最小数据量时直接不返回该图（环形 total=0、条形 0 项、折线 <2 点），不返回空图占位。
- **每答最多 2 张**：按优先级截断，避免回答变成仪表盘。

### 3.2 前端适配层

新增 `frontend/js/assistant-chart.js`（纯函数，可单测）：

```js
export function chartSpec(chart)      // 协议 → charts.js 入参
export function renderChart(chart, h) // 返回 <figure><svg>…</svg><figcaption></figcaption></figure>
```

- `donut` → `donutChart(slices.map(s => ({...s, color: chartColors[s.colorKey] ?? chartColors.ACCENT})))`
- `bar` → `barChart(bars.map(b => ({label: b.label, expected: b.total ?? 100, present: b.value})))`
- `line` → `lineChart(points, {unit: chart.unit, max: chart.max ?? 1})`

同时把 `analytics-view.js` 里的 `chartNode` 搬到 `charts.js` 导出（`renderChartNodes(svg, nodes, h)`），analytics 改成引用。这是唯一一处跨文件重构，影响面是统计页一张图，现有 261 项前端测试能兜住。

### 3.3 每个意图出什么图

| 角色 | 意图 | 图 1 | 图 2 | 不出图的条件 |
|---|---|---|---|---|
| 教师 | class_overview | 到勤构成环形 | 按周到勤率折线 | 应到 0 人次；周序列 <2 点 |
| 教师 | attendance | 到勤构成环形 | — | 应到 0 |
| 教师 | weak_knowledge | 掌握度条形（最多 5 项） | — | 无有效作答知识点 |
| 教师 | at_risk | 预警原因条形（规则/聚类各几 人） | — | 命中 0 人 |
| 教师 | advice | 最弱 2 个知识点掌握度条形 | — | 无样本 |
| 教师 | session_absence | 出勤/缺勤/请假环形 | — | 无已关闭任务 |
| 教师 | student_attendance | 该生出勤/迟到/请假/缺勤环形 | 最近 5 次状态条形（1=到，0=缺） | 应到 0 |
| 教师 | student_profile | 该生考勤环形 | 已评分成绩条形（百分比） | 无成绩则只出考勤图 |
| 学生 | my_attendance | 本人到勤构成环形 | — | 应到 0 |
| 学生 | my_progress | 本人最弱 3 个知识点条形 | — | 无作答 |
| 学生 | my_scores | 各次已评分成绩条形（百分比） | — | 无已评分 |
| 学生 | my_attempts | 对/错环形 | 错题知识点条形（最多 5） | 做题 0 |
| 学生 | next_practice | 最弱 3 个知识点条形 | — | 无低于 60% 的知识点 |

折线图只有教师「学情概览」用得上，因为只有 010A 提供周序列；其余保持环形/条形，不用时间轴硬凑。

### 3.4 展示形态

- 图放在回答卡片正文下方、数字卡片的**前面**（先图后数，符合课堂看板习惯），最多两张并排，窄屏自动单列。
- 每张图下方固定一行 `figcaption`：`图名 · 数据来源 010A · 最近 28 天`，与 facts 的出处一致。
- `facts` 文本**保留**，图表是增强不是替代：截图、朗读、色盲用户仍然能读到全部数字。
- `svg` 加 `role="img"` 和 `aria-label="到勤构成：出勤 321、迟到 15、请假 11、缺勤 773"`，由后端 `title` + 数据拼成，前端不另写。

## 4 验收与测试

| 层 | 用例 | 判据 |
|---|---|---|
| 后端 | 教师 class_overview | `charts` 含 donut 与 line；donut 各值之和 = 应到人次 = facts 里的分母 |
| 后端 | 空数据课程 | `charts == []`，不返回空图；文字仍说明「算不出来」 |
| 后端 | 学生 my_scores | 条形数量 = 已评分次数，数值与 answer 里的平均分一致 |
| 后端 | 图表与文字同源 | 同一响应内 donut 出勤数 == facts「出勤/迟到/请假/缺勤」的第一段 |
| 前端 | `chartSpec` 三种 kind | 纯函数映射正确；未知 kind 返回 null（跳过） |
| 前端 | 单点折线 | 不渲染 svg，不出空图占位 |
| 前端 | 无 `charts` 字段 | 老响应照常渲染，只是没图（向后兼容） |
| 浏览器 | 教师/学生各 3 个问题 | 无头 Edge 截图，检查图不溢出、窄屏单列、`aria-label` 存在 |

现有回归：后端 `tests.test_assistant`（12 项）+ 前端 261 项必须全绿；`check_docs.py` 与 ruff 不回归。

## 5 工期与顺序

| 顺序 | 工作 | 产出 | 预估 |
|---|---|---|---|
| 1 | 后端 `charts` 协议 + 各意图组装 | `assistant.py` 改动 + 4 条测试 | 半天 |
| 2 | 抽出 `renderChartNodes`，analytics 改引用 | `charts.js` / `analytics-view.js` | 半天 |
| 3 | `assistant-chart.js` + 视图接入 | 图渲染 + 4 条前端测试 | 半天 |
| 4 | 无头 Edge 截图 + 文档（APIC 16.4 图表协议、演示脚本加图） | 截图 4 张 + 文档 | 半天 |

演示前 2 天可完成，留半天缓冲专治「图在真实数据下比例难看」。

## 6 风险与处理

| 风险 | 处理 |
|---|---|
| 回答变成长图，课堂投屏要滚很久 | 每答最多 2 图；图高固定 160—200px；facts 折叠到「查看明细」（可选，本期先不折） |
| 图里的数字和文字对不上 | 强制同源：charts 由 facts 的中间计算结果直接生成，禁止二次查询 |
| 真实数据比例太极端（如 159/160 缺勤，环形几乎全红） | 环形的 0 值项仍保留图例；演示脚本里解释这是真实签到结果，不美化 |
| 折线只有 1 个周桶 | 少于 2 点不画，卡片只留环形图 |
| 小屏/投屏分辨率 | `viewBox` 等比缩放，宽 100%；图例在窄屏换行 |
| 色盲用户 | 图例带文字与数值，不依赖颜色区分；aria-label 给完整读数 |

## 7 需要你拍板的三点

1. **图的密度**：每答最多 2 张（推荐），还是 3 张、或只出 1 张？
2. **图与数字的顺序**：先图后数（推荐，适合投屏）、先数后图、还是图可折叠？
3. **「图标」如果真是 icon**：那不做图表，只在 facts 每项前加一个语义小图标（出勤/成绩/预警各一个），半天就能完事——告诉我按哪个做。

## 8 备选：C 方案（如果只要图标）

- 在 `assistant.css` 加 8 个内联 SVG 图标（出勤、迟到、请假、缺勤、成绩、练习、预警、进度）。
- 后端 facts 加 `iconKey`，前端按 key 渲染 16×16 SVG，放在 label 前。
- 不涉及图表协议、不动 charts.js，半天完成；但信息密度和「一眼看懂」效果远不如图表。

## 9 实施结果（2026-11-20 已完成）

按本计划 A 方案落地，三点默认取「每答最多 2 张 / 图在结论句后、明细数字前 / 是图表不是小图标」。

- 协议、配色、空态、每答张数都按 §3 实现；额外把 `chartNode` 从 `analytics-view.js` 抽到 `charts.js` 共用，新增 `rankChart`（横向条形，中文标签放得下）。
- 与计划的一处偏差：原本打算复用竖排 `barChart`，实际它画的是「应到/到勤」双柱，用来画掌握度会误解成两组数，因此新写了单值横向条。
- 真实库实测结果与计划预期一致：教师 3 类问题 9/9、学生 3 类问题 9/9（无头 Edge），图元与后端数字一一对应。
- 测试：后端 16 项、前端 294 项。
