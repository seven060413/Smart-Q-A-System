# 中小学教材知识图谱智能问答系统（选题 7）

面向中小学生的教材知识图谱问答系统。以北京大学 K12-KGraph 公开数据集为底座，
构建数学学科知识图谱（知识点 ≤ 200），实现「先补前置、再讲本体」的可溯源问答：
答案标注教材章节出处，知识库未覆盖时明确拒答。交付形态为 Android APK（同时支持 H5）。

## 技术栈

| 层次 | 技术 |
| ---- | ---- |
| 后端框架 | Python + FastAPI |
| 图存储 / 检索 | NetworkX |
| 向量召回 | bge-m3（本地 CPU 加载） |
| 文本生成 | Qwen 在线接口（DashScope，OpenAI 兼容） |
| 前端 | uni-app（Vue3 语法），位于 `app/`，可编译 APK 与 H5 |
| 数据 | 北京大学 K12-KGraph（人教版数学，知识点 ≤ 200） |

## 目录结构

```
.
├── README.md            # 本文件
├── requirements.txt     # 后端 Python 依赖
├── .env.example         # 环境变量模板（复制为 .env 后填写）
├── .gitignore           # 忽略 .env / 虚拟环境 / 缓存 / 原始数据
├── data/
│   ├── raw/             # K12-KGraph 原始数据（下载后放置）
│   └── processed/       # 处理后的图谱数据（JSON，检索时加载）
├── src/                 # 后端源码（FastAPI + NetworkX + 检索）
├── tests/               # 测试用例（pytest）
└── app/                 # 前端 uni-app（Vue3），后续初始化
```

## 环境要求

- Python 3.11+
- Node.js 18+（前端，后续步骤）

## 快速开始

> 业务代码尚未实现，以下为环境准备步骤；运行方式待对应步骤完成后补充。

### 1. 创建虚拟环境并安装依赖

```bash
python -m venv .venv
# Windows（Git Bash）
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

> 首次安装会拉取 torch（bge-m3 的依赖），约 2GB，耗时较长，属正常现象。

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 QWEN_API_KEY 等
```

### 3. 准备数据

将北京大学 K12-KGraph 数据集放入 `data/raw/`，后续处理脚本会生成
`data/processed/` 下的图谱文件。

## 数据说明

| 项 | 说明 |
| -- | -- |
| 来源 | 北京大学 K12-KGraph（PKU-DCAI 团队；HuggingFace: `lhpku20010120/K12-KGraph`，GitHub: `haolpku/K12-Dataset`） |
| 内容 | 人教版小初高数理化教材抽取的图谱与配套题库；本项目仅使用数学、知识点 ≤ 200 |
| 授权 | 仅作课程研究用途，使用前需确认授权范围 |
| 隐私 | 不涉及个人隐私数据 |
| 合规 | 不批量爬取教材网站 |

## 小组分工

| 成员 | 分工 |
| ---- | ---- |
| （待填） | （待填） |

## 当前进度

- [x] 项目骨架（目录、README、依赖、环境变量模板）
- [ ] 数据下载与预处理
- [ ] 图谱构建（NetworkX）
- [ ] 向量召回（bge-m3）
- [ ] 双通道检索与融合
- [ ] 前置知识诊断与学习路径生成
- [ ] Qwen 生成与溯源 / 拒答
- [ ] 前端 uni-app（`app/`）
