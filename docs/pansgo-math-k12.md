# pansgo 数学 K12 数据与学情诊断

## 来源与许可

| 项 | 内容 |
|---|---|
| 项目 | `cn-math-taxonomy`（Aifeng / `xiaoyang111222`） |
| 仓库 | https://github.com/xiaoyang111222/cn-math-taxonomy |
| 站点 | https://math.pansgo.com/ |
| 锁定提交 | `f4721bb947d95823ee8a41b2507ad411ff66e5e0` |
| 许可证 | **CC BY-NC 4.0**（署名—非商业性使用 4.0 国际） |
| 用途 | 仅限非商业使用。再分发或改编须署名原作者并注明修改 |

建议署名：

> 知识图谱与题库数据来自 Aifeng（xiaoyang111222）的 cn-math-taxonomy，采用 CC BY-NC 4.0 许可。

**质量边界**：知识点、先修边、题目与答案均由该项目的 AI 生成流程产出，未经一线教师审核。小学数学有独立程序复核、初中数学有盲解复核；高中题没有盲解。只适合做薄弱点筛查，不能当权威答案或正式测评。

## 覆盖范围与规模

| 学段 | 年级编码 | 知识点 | 题目 |
|---|---|---:|---:|
| 小学 | 1–6 | 284 | 1,136 |
| 初中 | 7–9 | 315 | 1,407 |
| 高中 | 10–14（高一、高二、选必一/二/三） | 271 | 1,084 |
| **合计** | 1–14 | **870** | **3,627** |

先修边 1,459 条（hard 1,219 / soft 240）。每个知识点 4–5 题，其中 452 个点 4 题、147 个点 5 题。

年级编码说明：10=高一（必修第一册）、11=高二（必修第二册）、12=选必一、13=选必二、14=选必三；页面不写“高三/高四”。

## 获取与构建

```bash
# 1. 下载并过滤（锁定提交，默认 1–14 年级）
.venv/Scripts/python.exe scripts/fetch_pansgo.py

# 2. 转成图谱 / 题库 / 目录
.venv/Scripts/python.exe scripts/build_pansgo_graph.py
```

产物：

| 文件 | 内容 |
|---|---|
| `data/raw/pansgo_k12/{topics,dependencies,questions}.json` | 过滤后的源数据（被 `.gitignore` 忽略） |
| `data/raw/pansgo_k12/manifest.json` | 来源、提交、计数、sha256 |
| `data/processed/pansgo_math_k12.json` | 图谱（870 节点 / 1,459 边） |
| `data/processed/pansgo_math_k12_questions.json` | 题库（3,627 题） |
| `data/processed/pansgo_math_k12_catalog.json` | 年级 → 册 → 章 → 知识点目录 |

构建是确定性的：排序固定、无时间戳，同一提交重复构建 sha256 一致。

## 字段映射

知识点：

```
topic                        → node
  id                         → id
  name                       → name
  （固定）                    → label = "Concept"
  grade/grade_label/stage
  semester/book/chapter/chapter_label
  domain/type/description
  mastery_criteria/standards
  diagnostic_question        → properties（诊断首题）
```

先修边（方向与项目一致：source 先学 → target 后学）：

```
dependency  topicId 依赖 prerequisiteId
  prerequisiteId → source
  topicId        → target
  type           → "prerequisites_for"
  strength/reason → properties
```

题目保留 `id/topicId/difficulty/type/prompt/choices/answer/explanation/verify/figure/hideChoiceText`。`type` 有 `numeric/choice/short/self`；`self` 是开放题，不参与自动诊断。

## 诊断规则

引擎在 [src/quiz_engine.py](../src/quiz_engine.py)，纯状态机，不依赖数据库：

1. 每个知识点按难度阶梯出题：基础 → 提高 → 拓展；
2. 连续答对 `mastery_streak` 题判「掌握」；题量不足时按实际题量判定（`min(N, 可用题数)`）；
3. 答错立即终止该点的掌握判定，追加 **1 道确认题**（同级或降一级）：
   - 确认题答对 → 「不稳」；
   - 确认题答错 → 「薄弱」，并回溯先修；
4. 总题量到上限后，未测完的点标「未测」；
5. 可用题目少于 2 道标「题量不足」。

三种模式：

| 模式 | 起点难度 | 题量范围 | 回溯层数 | 结果 |
|---|---|---|---|---|
| 单点诊断 | 基础 | 8–30（默认 16） | 3 | 该点结论 + 根因 |
| 章节诊断 | 基础 | 8–30（默认 16） | 3 | 逐点 + 章内汇总 |
| 整年级摸底 | 提高 | 20–60（默认 40） | 1 | 只出章节结论 |

默认掌握标准：单点/章节 3 题，整年级摸底 2 题。题量有限时，整年级 40 题覆盖 119 个七年级知识点，大部分点只能测 1 题，结果按章汇总，不承诺逐点掌握。

## 后端接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/diagnose/catalog` | 年级 / 册 / 章 / 知识点目录 |
| POST | `/api/diagnose/quiz` | `action=start / answer / abort` |

开始：

```json
{"action":"start","mode":"single","node_ids":["cnm_221"],
 "max_questions":16,"mastery_streak":3}
```

章节模式传 `node_ids`（可多章）；整年级传 `grade` 和 `semester`（`all/上/下`）。

作答：

```json
{"action":"answer","session_id":"qs_...","question_id":"cnm_221_q1",
 "answer":"C","client_request_id":"..."}
```

响应只含题干、选项、解析和下一步，**不返回正确答案**。`client_request_id` 重试返回首次结果。

游客可用（匿名会话，`user_id` 为 NULL）；登录用户的会话绑定用户，别人拿 session id 也无法作答。会话 24 小时过期。

数据结构（migration v8/v9）：

- `questions`：`(dataset_version, id)` 主键，答案只在服务端；
- `quiz_sessions`：模式、范围、参数、`state_json`、`result_json`；
- `quiz_attempts`：每题作答，`(session_id, question_id)` 唯一，`client_request_id` 幂等。

## 导入数据库

```bash
.venv/Scripts/python.exe scripts/migrate.py
.venv/Scripts/python.exe scripts/seed_pansgo_questions.py
```

pansgo 与 K12-KGraph 的节点 id、命名体系不同，**不要合并到同一张图**。图谱如需入库，单独建课程：

```bash
.venv/Scripts/python.exe scripts/import_graph.py \
    --json data/processed/pansgo_math_k12.json \
    --scope custom --book-id pansgo_math_k12 \
    --course-id pansgo_math --course-name "数学（pansgo K12）" \
    --dataset-name "cn-math-taxonomy math K12" --dataset-version f4721bb
```

## 前端入口

- 侧边栏「学情诊断」→ `pages/diagnosis/diagnosis`；
- 三个 Tab：单点诊断 / 章节诊断 / 整年级摸底；
- 设置项默认收起；选完范围点「开始诊断」直接进入第 1 题，没有中间确认页；
- 答题页即时反馈，结果页按模式展示逐点结论或章节汇总；
- 「只测薄弱点」会用薄弱知识点再开一次章节诊断。

## 已知边界

- 每点只有 4–5 题，N=5 时大部分点按 4 题判定；
- 整年级摸底是筛查，不是逐点掌握判定；
- 内联 SVG 配图在 H5 用 `data:image/svg+xml` 渲染，APK 端需要实机验证；
- pansgo 节点没有视频映射，诊断结果页暂不关联视频；
- 题目 AI 生成、未经教师审核，UI 和文档需保留标注。
