# IKGR 仓库审查与清理报告

- **审查日期**：2026-11-15
- **仓库**：`seven060413/Smart-Q-A-System`（GitHub）
- **审查时仓库可见性**：**Public（公开）**
- **当前 HEAD**：清理前的提交（具体 SHA 不写入公开报告；执行前用 `git rev-parse HEAD` 自行记录）
- **审查范围**：Git 跟踪文件、全部历史路径、未跟踪产物、`docs/`、`src/`、`scripts/`、`deploy/`、`app/`
- **本报告状态**：只做审查与方案，**未执行任何删除、Git 历史改写或推送**

---

## 一、结论摘要

### 1. 最严重：真实用户数据已进入公开仓库

清理前的最新提交中包含：

| 文件 | 内容 | 风险 |
|---|---|---|
| `migration_data.sql`（569,145 字节） | 2 个真实用户、scrypt 密码哈希、23 条会话、120 条消息、163 条知识点关联、23 条附件记录；含真实用户名与姓名 | 🔴 极高 |
| `migration_data_fixed.sql`（281,903 字节） | 同上，但不含 attachments | 🔴 极高 |
| `deploy/migration-package.zip`（81,187 字节） | 打包了 `migration_data.sql` + 导入脚本 + 迁移指南 | 🔴 极高 |
| `fix_user_id.sql`（746 字节） | 本地/服务器两套真实用户 UUID、真实姓名 | 🟠 高 |

这些文件必须从 Git 历史中彻底移除，但**本地文件要保留**。

另外，`docs/数据迁移快速开始.md`、`docs/数据迁移操作指南.md` 这两份已过时的一次性迁移文档也含真实用户名/姓名/用户 ID；默认清理命令会把它们一并从历史移除，本地可以留副本到仓库外。

### 2. 仓库历史里还有大量 `node_modules`

早期提交曾把整个 `node_modules/` 提交进去，后来删除了，但对象仍留在历史中。清理时应一并移除，仓库会明显变小。

### 3. 前端构建产物、日志、临时部署包混入仓库

- `h5-dist.zip`、`junior_dryrun.log` 已被 Git 跟踪。
- 三个 `ikgr-*.tar.gz` 和空文件 `tar` 目前**未跟踪**，尚未进入 GitHub，但应加入 `.gitignore` 防止误提交。

### 4. 没有发现 API Key / 私钥泄露

- `.env` **从未进入 Git 历史**（`git log --all -- .env` 为空）。
- 对当前文件和历史提交做了 `sk-*`、私钥、阿里云 AK 等模式扫描，**未发现真实密钥**。
- 这不改变“用户聊天记录和密码哈希已泄露”的结论，但至少 API 密钥不需要因为这次事件轮换（仍建议按常规安全习惯定期轮换）。

### 5. B 站/视频功能不是废弃实验，不要整组删除

`src/video_api.py` 已注册到 `src/api.py`，前端首页和路径页会调用 `/api/videos`，数据库有 `videos` 等表。`scripts/collect_videos.py`、`review_videos.py`、`seed_approved_videos.py` 仍在视频数据流程中使用。真正孤立的是 `src/retrieval.py` 和 `src/fusion.py`（只有测试引用），详见 `02-代码与文档清理建议.md`。

### 6. 两个执行层面的前置问题

1. 当前机器 **GitHub SSH 认证失败**：`git@github.com: Permission denied (publickey)`。最终强制推送前必须先修好 SSH，或改用 HTTPS + Git Credential Manager。
2. 本机还有另一个 worktree（位于本机用户目录下的 `WorkBuddy\Worktrees\IKGR-system-eands\main-44e833c1`）和本地分支 `backup-before-squash`。它们不在 GitHub 上，但会保留旧历史对象，清理后需要决定是否删除，避免以后误推回旧数据。

---

## 二、文件索引

| 文件 | 内容 |
|---|---|
| [01-问题文件清单.md](01-问题文件清单.md) | 逐个文件说明用途、大小、是否含敏感数据、风险等级、处理建议 |
| [02-代码与文档清理建议.md](02-代码与文档清理建议.md) | 废弃/孤立代码、过时文档、重复文档、前端无用项，含证据与不确定项 |
| [03-gitignore-proposed.txt](03-gitignore-proposed.txt) | 建议的完整 `.gitignore`（复制到仓库根目录使用） |
| [04-清理执行手册-PowerShell.md](04-清理执行手册-PowerShell.md) | 从备份、安装工具、改写历史到强制推送、本地同步、验证的完整 PowerShell 步骤 |
| [05-泄露处置与善后.md](05-泄露处置与善后.md) | 仓库转私有、密码/会话重置、GitHub 缓存清理、通知与长期预防 |

---

## 三、执行前必读（红线）

1. **先备份，再动手。** 备份要包含 `.git` 和本地所有敏感 SQL/压缩包。
2. **不要执行 `git reset --hard`。** 清理后本地 `main` 指向的新历史里没有 `migration_data.sql` 等文件，`reset --hard` 会把它们从磁盘上删除。必须使用 `git reset --mixed`（默认模式）。
3. **不要执行 `git clean -fdx`。** 它会删除所有未跟踪文件，包括你要保留的 SQL、压缩包和本地配置。
4. **不要直接删除本地敏感文件。** 本次目标是“从 GitHub 撤下、本地保留”，不是销毁本地数据。确认不再需要后，再单独处理。
5. **强制推送是不可逆操作。** 推送前必须确认镜像仓库中已无敏感路径，并保留旧历史 bundle。GitHub 上的旧提交即使从分支消失，也可能在缓存中短期可访问，需联系 GitHub Support 清理。
6. **`.gitignore` 只对未跟踪文件生效。** 已跟踪文件必须先 `git rm --cached`（保留本地文件）或通过 `git filter-repo` 从历史移除。
7. **本手册不会替你执行任何命令。** 所有标 🔴 的步骤都需要你确认后再逐条执行。
8. **本报告已做脱敏**：不包含真实用户名、姓名、用户 ID、密码哈希、聊天正文、服务器 IP 或旧提交 SHA。建议在完成 Git 历史清理、本地同步后，再提交 `docs/inspect/`，不要把它和敏感文件放在同一个提交里。

---

## 四、建议的处理顺序（高层）

1. **立即遏制**：仓库转 Private；重置受影响账号密码、吊销会话；告知受影响用户。
2. **备份**：整个工作目录 + `git bundle` 旧历史。
3. **修认证**：SSH 或 HTTPS，确保能推送。
4. **镜像克隆**：`git clone --mirror` 到独立目录，不在工作目录里改写历史。
5. **改写历史**：`git filter-repo` 移除敏感文件、构建产物、日志、`node_modules`。
6. **验证镜像**：确认所有目标路径在全部 refs 中都不存在。
7. **强制推送**：`git push --force origin --all` / `--tags`。
8. **本地同步**：`git fetch` + `git reset --mixed origin/main`，本地文件原地保留。
9. **落地 `.gitignore`**：复制 `03-gitignore-proposed.txt` 为根目录 `.gitignore`，提交并推送。
10. **善后**：联系 GitHub Support 清理缓存；检查 fork/Pages/Actions；长期加 pre-commit 防线。

详细命令见 `04-清理执行手册-PowerShell.md`。
