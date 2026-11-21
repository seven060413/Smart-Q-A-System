# data/ 数据说明

## 数据来源

| 项 | 内容 |
| -- | -- |
| 数据集 | K12-KGraph（北京大学 PKU-DCAI 团队，NeurIPS 2026） |
| HuggingFace | https://huggingface.co/datasets/lhpku20010120/K12-KGraph |
| 代码仓库 | https://github.com/haolpku/K12-Dataset |
| 论文 | arXiv:2605.09635 |
| 本目录文件 | `raw/math.json`（数学学科图谱，源路径 `K12-KGraph/subject_specific_KG/math.json`） |

## 版本

- 下载日期：2026-10-17
- 下载方式：HuggingFace `main` 分支直接下载（未作任何修改）
- 规模：节点 2711，边 5273

## 数据格式

**节点**字段：`id`、`label`（类型）、`name`、`properties`（类型相关属性）。

| 类型 label | 数量 | properties 主要字段 |
| -- | -- | -- |
| Book（教材册） | 23 | subject / grade / publisher |
| Chapter（章/单元） | 150 | （无） |
| Section（节） | 166 | （无） |
| Concept（概念/知识点） | 1470 | definition / importance / pages / examples / aliases / formula / unit |
| Skill（技能） | 428 | description |
| Exercise（习题） | 474 | stem / answer / difficulty / type / analysis |

**边**字段：`source`、`target`、`type`、`properties`；其中 `tests_concept` 与
`tests_skill` 的 target 为 `target_name_to_ids` 列表（一题可对应多个知识点/技能）。

关系类型（数学学科 8 种）：appears_in、prerequisites_for、tests_concept、
tests_skill、relates_to、is_part_of、is_a、leads_to。
（全学科共 9 种，`verifies` 仅出现在含实验的学科；数学无实验类节点，故不出现。）

## 授权

- 数据集授权：**CC BY-NC-SA 4.0**（署名-非商业-相同方式共享）
- 用途：仅作课程研究与教学演示，不用于商业用途；本项目为课程综合实践，符合约束。
- 合规：未批量爬取任何教材网站。

## 规模约束提示

数学全量图谱含 1470 个 Concept + 428 个 Skill = **1898 个知识点**，超出项目
「知识点 ≤ 200」约束；后续步骤将按年级（如 `math_7a_rjb_*`）或教材筛选出 ≤200 的子集。

## 新增数据集：pansgo 数学 K12（1–14 年级，2026-11-21）

| 项 | 内容 |
| -- | -- |
| 数据集 | cn-math-taxonomy（Aifeng / `xiaoyang111222`，站点 math.pansgo.com） |
| 仓库 | https://github.com/xiaoyang111222/cn-math-taxonomy |
| 锁定提交 | `f4721bb947d95823ee8a41b2507ad411ff66e5e0` |
| 授权 | **CC BY-NC 4.0**（署名—非商业性使用），仅限非商业用途 |
| 产物 | `processed/pansgo_math_k12.json`（870 节点 / 1,459 边）、`processed/pansgo_math_k12_questions.json`（3,627 题）、`processed/pansgo_math_k12_catalog.json`（年级/册/章目录） |

年级覆盖 1–9 年级加高中（高一、高二、选必一、选必二、选必三）。获取与构建见
[docs/pansgo-math-k12.md](../docs/pansgo-math-k12.md)。原始过滤数据在 `raw/pansgo_k12/`，
被 `.gitignore` 忽略，可随时重新生成。

题库导入数据库：

```bash
.venv/Scripts/python.exe scripts/migrate.py
.venv/Scripts/python.exe scripts/seed_pansgo_questions.py
```

**质量提示**：知识点与题目由该项目的 AI 生成流程产出，未经一线教师审核；仅适合
做薄弱点筛查，不能作为权威答案或正式测评依据。
