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
