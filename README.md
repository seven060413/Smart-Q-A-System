# 中小学教材知识图谱智能问答系统（选题 7）

面向中小学生的教材知识图谱问答系统。以**北京大学 K12-KGraph** 公开数据集为底座，
构建数学学科知识图谱，实现「**先补前置、再讲本体**」的可溯源问答：

- 答案必须标注教材章节出处；
- 知识库未覆盖时**明确拒答**，并给出最接近的知识点；
- 前置关系成环时报警并输出完整环序列，**拒绝生成学习路径**。

交付形态为 **Android APK**（uni-app 可同时编译 H5）。

---

## 一、技术栈

| 层次 | 技术 |
| --- | --- |
| 后端框架 | Python 3.11 + FastAPI |
| 图存储 / 检索 | NetworkX（MultiDiGraph） |
| 向量召回 | bge-m3（FlagEmbedding，本地 CPU） |
| 文本生成 | Qwen 在线接口（阿里云 DashScope，OpenAI 兼容协议） |
| 前端 | uni-app（Vue3 + Vite），`app/` 子项目，可编译 APK 与 H5 |
| 数据 | 北京大学 K12-KGraph（人教版数学，知识点 ≤ 200） |
| 部署 | 阿里云 ECS（systemd 托管 uvicorn） |

**当前演示环境**

| 项 | 地址 |
| --- | --- |
| 后端 API | `http://114.55.116.162:18080` |
| 接口文档 | `http://114.55.116.162:18080/docs` |

> 该地址为课程演示用临时部署，实际地址在 `app/src/config.js` 中配置。

---

## 二、目录结构

```
IKGR-system-eands/
├── README.md                  # 本文件
├── requirements.txt           # 本地完整依赖（含 bge-m3 / torch）
├── requirements-server.txt    # 服务端最小依赖（不含 torch，约 1 分钟装完）
├── .env.example               # 环境变量模板（复制为 .env）
├── .gitignore                 # 忽略 .env / 虚拟环境 / 缓存 / 原始数据
│
├── src/                       # 后端源码（FastAPI + NetworkX + 检索 + 生成）
│   ├── models.py              # 数据模型：Node / Edge / GraphSets（三个有限集合）
│   ├── loader.py              # 从 JSON 读取节点与边
│   ├── filter.py              # 按年级 + importance 筛选知识点（≤200）
│   ├── subgraph.py            # 抽取五年级下册知识子图
│   ├── graph.py               # NetworkX 建图、前置闭包、环检测、拓扑排序
│   ├── linking.py             # 实体链接（问句 → 知识点）
│   ├── retrieval.py           # 文本通道：bge-m3 向量 + 余弦 Top-K
│   ├── fusion.py              # 双通道融合（0.7 文本 + 0.3 图谱）
│   ├── diagnosis.py           # 前置诊断（量词查询：必需 / 建议）
│   ├── learning_path.py       # 三级学习路径（前置—本体—巩固）
│   ├── refusal.py             # 拒答判定
│   ├── generator.py           # Qwen 在线生成
│   ├── pipeline.py            # 问答流水线 + Prompt 组装
│   └── api.py                 # FastAPI 应用（POST /api/ask）
│
├── tests/                     # 测试（pytest）
│   ├── test_models.py         # 集合建模
│   ├── test_filter.py         # 年级 + importance 筛选
│   ├── test_subgraph.py       # 子图抽取
│   ├── test_graph.py          # 建图 / 传递闭包 / 环检测
│   ├── test_graph_channel.py  # 相邻子图 / 连通性 / 路径
│   ├── test_linking.py        # 实体链接
│   ├── test_retrieval.py      # 文本通道
│   ├── test_fusion.py         # 双通道融合
│   ├── test_diagnosis.py      # 前置诊断
│   ├── test_learning_path.py  # 学习路径
│   ├── test_refusal.py        # 拒答
│   ├── test_api.py            # API 接口
│   └── test_acceptance.py     # 三组验收用例
│
├── data/
│   ├── README.md              # 数据来源、版本、授权说明
│   ├── raw/
│   │   └── math.json          # K12-KGraph 数学图谱（2711 节点 / 5273 边）
│   └── processed/
│       └── math_5b_knowledge_graph.json  # 五年级下册子图（67 节点 / 92 边）
│
├── app/                       # 前端 uni-app（Vue3 + Vite）
│   ├── package.json
│   ├── src/
│   │   ├── config.js          # ★ 后端地址（改这里即可换服务器）
│   │   ├── api.js             # uni.request 封装
│   │   ├── store.js           # 跨页面共享数据
│   │   ├── pages.json         # 页面注册
│   │   ├── manifest.json      # App 配置（name / appid / 权限）
│   │   └── pages/
│   │       ├── index/index.vue  # 首页：聊天气泡问答 + 三层折叠 + 拒答卡
│   │       └── path/path.vue    # 学习路径：前置→本体→巩固 流程图
│   └── dist/                  # H5 构建产物（npm run build:h5）
│
├── scripts/
│   └── verify_dataset.py      # 数据集核验：下载并统计真实的节点/关系类型
│
└── docs/
    ├── 选题 7操作手册.md
    ├── 需求分析与方案策划报告1.docx
    ├── 数据集核验方法.md
    ├── 检索与融合设计.md
    ├── 真机调试与APK打包指南.md
    └── 阿里云后端部署指南.md
```

---

## 三、环境要求

| 依赖 | 版本 | 用途 |
| --- | --- | --- |
| Python | 3.11+ | 后端 |
| Node.js | 18+（本项目实测 24.20） | 前端构建 |
| HBuilderX | 4.41+ | 真机调试 / 云打包 APK |

---

## 四、快速开始

### 1. 后端

```bash
# 创建虚拟环境
python -m venv .venv

# 安装依赖（本地完整版，会拉取 torch 约 2GB）
.venv/Scripts/python.exe -m pip install -r requirements.txt

# 复制环境变量模板并填写 Qwen 密钥
cp .env.example .env
```

`.env` 内容：

```ini
QWEN_API_KEY=sk-你的密钥
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen-plus
BGE_MODEL=BAAI/bge-m3
DATA_DIR=data
```

**启动服务**（注意必须监听 `0.0.0.0` 才能被手机访问）：

```bash
.venv/Scripts/python.exe -m uvicorn src.api:app --host 0.0.0.0 --port 18080
```

> 本机 **8000 端口被系统占用**（实测绑定报 `Errno 13`），故统一使用 **18080**。

验证：

```bash
curl http://127.0.0.1:18080/
# {"service":"中小学教材知识图谱智能问答系统","docs":"/docs"}
```

### 2. 前端

```bash
cd app
npm install
npm run dev:h5          # H5 调试，浏览器打开终端提示的地址
npm run build:h5        # 构建 H5 产物到 app/dist/build/h5
```

**修改后端地址**：编辑 [app/src/config.js](app/src/config.js)

```js
export const BASE_URL = 'http://114.55.116.162:18080'
```

> 地址是**编译时写死**的，改完必须重新运行到真机或重新打包 APK。

### 3. 运行测试

```bash
.venv/Scripts/python.exe -m pytest tests/ -q
# 47 passed, 1 skipped
```

> 跳过的是真实 bge-m3 召回测试（需先构建向量索引）。

---

## 五、API 接口

### `POST /api/ask`

**请求**

```json
{ "question": "为什么异分母分数相加要先通分" }
```

**响应**

```json
{
  "answer": "……（Qwen 分层讲解）",
  "knowledge_point": "异分母分数加减法",
  "prerequisite_gaps": [
    { "name": "同分母分数加减法", "required": true },
    { "name": "通分方法", "required": true },
    { "name": "分数的基本认识", "required": false }
  ],
  "learning_path": {
    "prerequisites": ["分数的基本认识", "通分方法", "同分母分数加减法"],
    "body": "异分母分数加减法",
    "consolidation": ["分数混合运算"]
  },
  "source": "人教版五年级下册·分数的加法和减法",
  "refused": false
}
```

**库外问题**（如「什么是导数」）：

```json
{
  "answer": "当前知识库未覆盖该内容，最接近：倍数",
  "knowledge_point": "倍数",
  "learning_path": null,
  "source": null,
  "refused": true
}
```

其他接口：`GET /`（服务信息）、`GET /docs`（Swagger 文档）。

---

## 六、数据说明

| 项 | 内容 |
| --- | --- |
| 来源 | 北京大学 K12-KGraph（PKU-DCAI 团队，NeurIPS 2026 Evaluations & Datasets Track） |
| 地址 | HuggingFace `lhpku20010120/K12-KGraph`；GitHub `haolpku/K12-KGraph` |
| 论文 | arXiv:2605.09635 |
| 授权 | **CC BY-NC-SA 4.0**（仅课程研究，非商业） |
| 本项使用 | 数学单科；筛选至人教版五年级下册，59 个知识点（≤200） |
| 合规 | 未批量爬取任何教材网站 |

**实测数据规模**

| 范围 | 节点 | 边 | 节点类型 | 关系类型 |
| --- | --- | --- | --- | --- |
| 全局（4 学科） | 10,685 | 23,278 | 7 | 9 |
| 数学单科 | 2,711 | 5,273 | 6 | 8 |
| 五年级下册子图 | 67 | 92 | 3（Concept/Skill/Chapter） | 4 |

> 论文设计为 9 类节点、14 类关系（含 Figure / VisualElement 及 5 类视觉关系），
> 但**开源发布的图谱本体为 7 类节点、9 类关系**。核验方法与证据见
> [docs/数据集核验方法.md](docs/数据集核验方法.md)；可运行 `python scripts/verify_dataset.py` 复现。

---

## 七、部署

| 场景 | 文档 |
| --- | --- |
| 阿里云 ECS 部署（公网访问） | [docs/阿里云后端部署指南.md](docs/阿里云后端部署指南.md) |
| 真机调试 / APK 云打包 | [docs/真机调试与APK打包指南.md](docs/真机调试与APK打包指南.md) |
| 检索与融合规则依据 | [docs/检索与融合设计.md](docs/检索与融合设计.md) |

**服务端最小依赖**（不装 torch）：

```bash
pip install -r requirements-server.txt
```

---

## 八、核心设计说明

### 1. 三个有限集合（实验 1 集合）

| 集合 | 定义 | 基数 |
| --- | --- | --- |
| 实体集合 E | 全部节点 | 2711（数学） |
| 知识点集合 K | Concept + Skill | 1898 |
| 教材章节集合 C | Chapter + Section | 316 |

满足：`K ⊆ E`、`C ⊆ E`、`K ∩ C = ∅`。

### 2. 双通道融合规则（教师要求「融合规则要有依据」）

```
final = 0.7 × text_score + 0.3 × graph_score
```

- 语义相关性是第一证据（用户问的是内容）→ 权重 0.7；
- 图谱结构是第二证据（补全前置知识，不改变主答案）→ 权重 0.3；
- 两通道均归一化到 [0,1]，量纲一致才可直接加权。

### 3. 拒答阈值

实体链接分数 `< 0.2` 判定为知识库未覆盖：
库内问句最高分约 0.49+，仅靠单字偶然命中的库外问句约 0.15。

### 4. 环检测（杀手用例）

前置关系图存在环时，`build_learning_path` 抛出 `ValueError`，
并在错误信息中输出**完整闭环序列**（如 `[['B', 'A', 'B']]`），禁止生成学习路径。

---

## 九、小组分工

| 成员 | 分工 |
| --- | --- |
| （待填） | （待填） |

---

## 十、当前进度

- [x] 项目骨架（目录、README、依赖、环境变量模板）
- [x] 数据下载与结构核验（K12-KGraph 数学图谱）
- [x] 实验 1 集合建模（三个有限集合 + 单元测试）
- [x] 按年级 + importance 筛选（五年级下册 59 个知识点）
- [x] 子图抽取（`data/processed/`）
- [x] 实验 4 图谱构建（NetworkX、传递闭包、环检测）
- [x] 实体链接 + 双通道检索 + 融合
- [x] 实验 3 前置诊断、实验 8 学习路径、拒答
- [x] Qwen 生成 + FastAPI 接口（CORS）
- [x] 前端首页（聊天气泡 + 三层折叠 + 拒答卡）
- [x] 前端学习路径页（三级流程图）
- [x] 真机调试、云打包 APK
- [x] 阿里云后端部署
- [ ] bge-m3 向量索引构建（真实召回测试当前 skip）
- [ ] 评测模块（抽样自动评测 + 人工抽检）

---

## 附：常见问题

| 现象 | 排查 |
| --- | --- |
| `npm: 无法识别` | Node.js 未加入 PATH，或当前终端是安装前打开的（新开窗口） |
| `npm.ps1 无法加载` | PowerShell 执行策略限制：`Set-ExecutionPolicy -Scope LocalMachine RemoteSigned` |
| 手机连不上后端 | 后端需 `--host 0.0.0.0`；防火墙/安全组放行 18080；手机与电脑同一网络 |
| App 白屏 | 看 HBuilderX 控制台报错；确认 `pages.json` 路径与文件一致 |
| 改了 `config.js` 不生效 | APK 地址编译时写死，必须重新运行到真机或重新打包 |
| Qwen 调用 401 | 检查 `.env` 中 `QWEN_API_KEY` |
| Qwen 连接错误 | 网络问题，`dashscope.aliyuncs.com` 可能暂时不可达 |
