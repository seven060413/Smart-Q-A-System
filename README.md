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
| 数据持久化 | SQLite（`data/app/ikgr.db`，含用户/会话/消息/图谱） |
| 认证 | 用户名 + 密码；密码 scrypt 哈希，登录用随机不透明令牌（服务端只存 SHA-256） |
| 前端 | uni-app（Vue3 + Vite），`app/` 子项目，可编译 APK 与 H5 |
| 数据 | 北京大学 K12-KGraph（人教版数学，全量 + 五年级下册子图） |
| 部署 | 阿里云 ECS（systemd 托管 uvicorn） |

**当前演示环境**

| 项 | 地址 |
| --- | --- |
| 后端 API | `http://114.55.116.162:18080` |
| 接口文档 | `http://114.55.116.162:18080/docs` |

> 该地址为课程演示用临时部署，实际地址在 `app/src/config.js` 中配置。
> **注意**：公网这台当前跑的是较旧代码，不含注册/登录/聊天历史接口；体验学生端功能请先按
> 下方「快速开始」在本地启动，并把 `config.js` 指向 `http://127.0.0.1:18080`。

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
│   ├── pipeline.py            # 问答流水线 + Prompt 组装（含内部知识点元数据）
│   ├── api.py                 # FastAPI 应用（问答 + 认证 + 聊天历史路由）
│   │
│   ├── db.py                  # SQLite 连接工厂（PRAGMA / 路径解析 / 备份）
│   ├── schema.py              # 版本化迁移与 11 张表 DDL
│   ├── graph_import.py        # 图谱 JSON → SQLite 导入/删除逻辑
│   ├── security.py            # scrypt 密码哈希、令牌生成/SHA-256
│   ├── settings.py            # 认证相关环境变量读取
│   ├── rate_limit.py          # 进程内登录/注册限流
│   ├── errors.py              # 统一错误响应 + X-Request-ID
│   ├── auth_service.py        # 注册/登录/会话签发与撤销
│   ├── auth_deps.py           # Bearer 令牌解析与当前用户依赖
│   ├── auth_api.py            # /api/auth/* 路由
│   ├── chat_service.py        # 会话/消息持久化、分页、软删除
│   └── chat_api.py            # /api/conversations* 路由
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
│   ├── test_acceptance.py     # 三组验收用例
│   ├── test_db.py             # 数据库迁移
│   ├── test_graph_import.py   # 图谱导入
│   ├── test_auth.py           # 注册/登录/令牌安全
│   └── test_chat.py           # 会话/消息持久化/越权/分页
│
├── data/
│   ├── README.md              # 数据来源、版本、授权说明
│   ├── raw/
│   │   └── math.json          # K12-KGraph 数学图谱（2711 节点 / 5273 边）
│   ├── processed/
│   │   └── math_5b_knowledge_graph.json  # 五年级下册子图（67 节点 / 92 边）
│   └── app/
│       └── ikgr.db            # SQLite 运行时数据库（已 .gitignore，不入库）
│
├── app/                       # 前端 uni-app（Vue3 + Vite）
│   ├── package.json
│   ├── vite.config.js         # 开发服务器监听 0.0.0.0:5173
│   ├── src/
│   │   ├── config.js          # ★ 后端地址（改这里即可换服务器）
│   │   ├── api.js             # 统一请求封装（Bearer 头 / 错误解析 / 401 清理）
│   │   ├── auth.js            # 注册/登录/退出/启动恢复状态逻辑
│   │   ├── auth-storage.js    # 本地令牌/用户存储
│   │   ├── store.js           # 跨页面共享数据（含登录态、当前会话）
│   │   ├── pages.json         # 页面注册
│   │   ├── manifest.json      # App 配置（name / appid / 权限）
│   │   └── pages/
│   │       ├── index/index.vue   # 首页：问答 + 三层折叠 + 拒答卡 + 历史入口
│   │       ├── path/path.vue     # 学习路径：前置→本体→巩固 流程图
│   │       ├── auth/auth.vue     # 登录 / 注册 / 账号 / 退出
│   │       └── history/history.vue # 历史会话列表 / 打开 / 删除
│   └── dist/                  # H5 构建产物（npm run build:h5）
│
├── scripts/
│   ├── verify_dataset.py      # 数据集核验：下载并统计真实的节点/关系类型
│   ├── migrate.py             # 建库 / 应用迁移（--db 可选，status 查看状态）
│   └── import_graph.py        # 图谱导入 / 删除版本（--json / --scope / --force / --delete-version）
│
└── docs/
    ├── 选题 7操作手册.md
    ├── 需求分析与方案策划报告1.docx
    ├── 数据集核验方法.md
    ├── 检索与融合设计.md
    ├── 真机调试与APK打包指南.md
    ├── 阿里云后端部署指南.md
    ├── 网页版运行指南.md
    ├── 学生端数据与接口设计.md
    └── 学生端登录与聊天记录实施计划.md
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

`.env` 内容（**密钥用你自己的值，不要提交真实密钥**）：

```ini
QWEN_API_KEY=sk-你的密钥
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen-plus
BGE_MODEL=BAAI/bge-m3
DATA_DIR=data

# 学生端认证（可选，有默认值）
AUTH_TOKEN_TTL_DAYS=30
AUTH_RATE_LIMIT_ENABLED=true
```

**建库并导入图谱**（首次运行必做）：

```bash
# 1) 建库/迁移：创建 data/app/ikgr.db 和 11 张表
.venv/Scripts/python.exe scripts/migrate.py

# 2) 导入全量数学图谱 + 五年级下册子图
.venv/Scripts/python.exe scripts/import_graph.py --json data/raw/math.json --scope subject_full
.venv/Scripts/python.exe scripts/import_graph.py --json data/processed/math_5b_knowledge_graph.json --scope book --book-id math_5b_rjb
```

> 导入可重复执行，内容未变会自动跳过；`--force` 可强制重导，`--delete-version <id>` 可删除某版本。原始 JSON 只读，不会删除或覆盖。

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
npm run dev:h5          # H5 调试，浏览器打开 http://127.0.0.1:5173/
npm run build:h5        # 构建 H5 产物到 app/dist/build/h5
```

> 开发服务器已固定监听 `0.0.0.0:5173`；手机在同一 Wi-Fi 下可用
> `http://<电脑局域网 IP>:5173/` 访问。

**修改后端地址**：编辑 [app/src/config.js](app/src/config.js)

```js
export const BASE_URL = 'http://127.0.0.1:18080'   // 本地后端
// export const BASE_URL = 'http://114.55.116.162:18080'   // 云服务器
```

> 地址是**编译时写死**的，改完必须重新运行到真机或重新打包 APK。

### 3. 运行测试

```bash
.venv/Scripts/python.exe -m pytest tests/ -q
# 95 passed, 1 skipped
```

> 跳过的是真实 bge-m3 召回测试（需先构建向量索引）。

---

## 五、API 接口

### 认证接口（`/api/auth/*`）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/auth/register` | 学生注册并自动登录（固定创建 `student` 角色） |
| POST | `/api/auth/login` | 登录，返回 Bearer 令牌 |
| GET | `/api/auth/me` | 查询当前登录用户 |
| POST | `/api/auth/logout` | 退出当前设备，撤销令牌 |

注册/登录请求：

```json
{ "username": "xiaoming", "password": "用户密码", "display_name": "小明" }
```

成功响应（令牌只在这次返回）：

```json
{
  "token": "ikgr_<随机令牌>",
  "token_type": "bearer",
  "expires_at": "2026-11-27T08:30:00.000Z",
  "user": { "id": "<uuid>", "username": "xiaoming", "display_name": "小明", "role": "student" }
}
```

受保护接口需要请求头 `Authorization: Bearer <token>`。密码只存 scrypt 哈希，
令牌服务端只存 SHA-256；令牌默认 30 天过期、可撤销、支持多设备。

### 聊天历史接口（`/api/conversations*`，需登录）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/conversations?limit=20&cursor=...` | 当前学生的会话列表 |
| POST | `/api/conversations` | 创建空会话 |
| GET | `/api/conversations/{id}` | 会话详情 |
| GET | `/api/conversations/{id}/messages?limit=50&cursor=...` | 消息分页（按时间正序） |
| DELETE | `/api/conversations/{id}` | 软删除会话 |

### `POST /api/ask`

**游客请求**（不落库）：

```json
{ "question": "为什么异分母分数相加要先通分" }
```

**登录请求**（可选带会话/幂等 id，`Authorization` 头携带令牌）：

```json
{
  "question": "为什么异分母分数相加要先通分",
  "conversation_id": "<可选>",
  "client_request_id": "<可选，用于网络重试去重>"
}
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
  "refused": false,
  "persisted": true,
  "conversation_id": "<uuid>",
  "user_message_id": "<uuid>",
  "assistant_message_id": "<uuid>"
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

统一错误结构：

```json
{ "error": { "code": "INVALID_CREDENTIALS", "message": "用户名或密码错误", "details": null, "request_id": "<id>" } }
```

> 游客问答不保存任何历史；登录后才持久化。所有会话/消息只能由令牌对应的用户访问。

---

## 六、数据说明

| 项 | 内容 |
| --- | --- |
| 来源 | 北京大学 K12-KGraph（PKU-DCAI 团队，NeurIPS 2026 Evaluations & Datasets Track） |
| 地址 | HuggingFace `lhpku20010120/K12-KGraph`；GitHub `haolpku/K12-KGraph` |
| 论文 | arXiv:2605.09635 |
| 授权 | **CC BY-NC-SA 4.0**（仅课程研究，非商业） |
| 本项使用 | 数学单科；导入全量数学图谱（`subject_full`）+ 五年级下册子图（`book`）到 SQLite |
| 合规 | 未批量爬取任何教材网站 |

**实测数据规模**

| 范围 | 节点 | 边 | 节点类型 | 关系类型 |
| --- | --- | --- | --- | --- |
| 全局（4 学科） | 10,685 | 23,278 | 7 | 9 |
| 数学单科（全量，已导入 SQLite） | 2,711 | 5,273 | 6 | 8 |
| 五年级下册子图（已导入 SQLite） | 67 | 92 | 3（Concept/Skill/Chapter） | 4 |

> 全量数学图谱的 5273 条边中，`tests_concept` / `tests_skill` 共 635 条是“一条边指向多个目标”
> 的特殊边，导入时统一展开到 `graph_edge_targets`，不会漏数据。

> 论文设计为 9 类节点、14 类关系（含 Figure / VisualElement 及 5 类视觉关系），
> 但**开源发布的图谱本体为 7 类节点、9 类关系**。核验方法与证据见
> [docs/数据集核验方法.md](docs/数据集核验方法.md)；可运行 `python scripts/verify_dataset.py` 复现。

---

## 七、部署

| 场景 | 文档 |
| --- | --- |
| **其他人克隆后如何查看网页版** | [docs/网页版运行指南.md](docs/网页版运行指南.md) |
| 阿里云 ECS 部署（公网访问） | [docs/阿里云后端部署指南.md](docs/阿里云后端部署指南.md) |
| **每次后端更新如何发布（打包/备份/部署/回滚）** | [docs/后端更新与部署操作手册.md](docs/后端更新与部署操作手册.md) |
| 真机调试 / APK 云打包 | [docs/真机调试与APK打包指南.md](docs/真机调试与APK打包指南.md) |
| 检索与融合规则依据 | [docs/检索与融合设计.md](docs/检索与融合设计.md) |
| **学生端数据与接口设计** | [docs/学生端数据与接口设计.md](docs/学生端数据与接口设计.md) |
| **学生端登录与聊天记录实施计划** | [docs/学生端登录与聊天记录实施计划.md](docs/学生端登录与聊天记录实施计划.md) |

**服务端最小依赖**（不装 torch）：

```bash
pip install -r requirements-server.txt
```

> 认证依赖使用 Python 标准库 `hashlib.scrypt`，**不需要额外安装**。
> 数据库文件 `data/app/ikgr.db` 不随 Git 提交；新环境需先 `scripts/migrate.py` 建库，
> 再 `scripts/import_graph.py` 导入图谱。

> ⚠️ HTTPS 尚未完成（域名 `seventeen17.com.cn` 已解析、ICP 备案进行中）。
> 当前公网仍是 HTTP，**不要把真实学生密码放到公网 HTTP 上测试**。

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
- [x] SQLite 数据库与图谱导入（`scripts/migrate.py` + `scripts/import_graph.py`，全量数学 + 5b 子图）
- [x] 后端学生注册 / 登录 / 当前用户 / 退出（scrypt 密码哈希 + 随机令牌）
- [x] 前端登录 / 注册页、登录状态、令牌存取与 401 处理
- [x] 聊天会话与消息持久化（会话列表 / 消息分页 / 软删除 / 失败记录 / 幂等重试）
- [x] 前端历史会话列表与打开历史会话
- [ ] HTTPS / ICP 备案（域名 `seventeen17.com.cn` 已解析，备案完成后做反向代理 + 证书）
- [ ] 学生端端到端检查与文档收尾
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
| 注册/登录返回 404 | 请求打到了**旧版后端**：确认 `config.js` 指向本地 `127.0.0.1:18080` 或已部署新代码的服务器；重启 dev server 后强刷页面 |
| 提问报「没有 users / conversations 表」 | 没建库：先 `scripts/migrate.py` |
| 聊天历史为空或报课程不存在 | 未导入图谱版本：运行 `scripts/import_graph.py` 导入全量与 5b 子图 |
| `localhost:5173` 打不开 | 开发服务器监听 IPv6；用 `http://127.0.0.1:5173/`，或手机用 `http://<电脑局域网 IP>:5173/` |
| Qwen 调用 401 | 检查 `.env` 中 `QWEN_API_KEY` |
| Qwen 连接错误 | 网络问题，`dashscope.aliyuncs.com` 可能暂时不可达 |
| 公网仍是 HTTP 明文 | HTTPS 尚未完成（ICP 备案进行中）；不要把真实学生密码放到公网 HTTP 上 |
