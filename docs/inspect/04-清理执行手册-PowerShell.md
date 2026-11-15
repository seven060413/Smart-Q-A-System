# 04 · 清理执行手册（Windows PowerShell）

> 目标：把敏感文件/无用产物从 GitHub 历史中彻底移除，**本地文件原地保留**，更新 `.gitignore`，最后强制推送清理后的历史。
>
> 本手册按阶段执行。每个阶段都有检查点。**不要跳步，不要一次性把所有命令粘进去执行。**
>
> 环境假设：Windows 11、PowerShell 5.1 或 7、Git 2.56、Python 3.11、仓库路径 `D:\IKGR-system-eands`、远程仓库 `seven060413/Smart-Q-A-System`。如路径不同请自行替换。
>
> **当前状态（2026-11-15）**：`main` 已通过 `reset` + 重新提交 + force push 完成清理；
> 旧提交缓存/Support 清理未执行。本文保留完整步骤作为参考，**不需要从头重做**。

---

## 风险标记

| 标记 | 含义 |
|---|---|
| 🟢 | 安全/可逆，可直接执行 |
| 🟡 | 需要确认；影响局部，通常可回滚 |
| 🔴 | **不可逆或高风险**；执行前必须备份并明确确认 |
| ⛔ | **禁止执行**；会破坏目标（尤其是本地文件保留） |

---

## 阶段 0 · 执行前检查

### 0.1 确认当前状态

```powershell
Set-Location "D:\IKGR-system-eands"

git status
git log --oneline -5
git remote -v
git rev-parse HEAD
git branch -vv
git worktree list
```

预期：

- `HEAD` 是你清理前的提交（用 `git rev-parse HEAD` 记录到私有位置；不要把真实 SHA 写进公开文档）。
- `main` 跟踪 `origin/main`，没有领先/落后的本地提交。
- 当前未提交修改只有 `.env.example`、`src/auth_service.py`（以实际为准）。
- 另一个 worktree 位于本机用户目录下的 `WorkBuddy\Worktrees\IKGR-system-eands\main-44e833c1`。

> 如果 `main` 有本地提交（`git log origin/main..HEAD` 有输出），**先停下来**。不要直接 reset；需要先备份并单独决定如何处理这些提交。

### 0.2 关闭可能占用文件的程序

- 关闭 VS Code / HBuilderX / 正在运行的 Git 图形工具。
- 关闭正在写数据库的后端服务（如果你在本机跑着）。
- 不要关闭 PowerShell 本身。

### 0.3 确认你接受以下事实

- 强制推送后，GitHub 上的旧提交会被新提交取代；旧提交可能短期仍可通过 SHA/缓存访问，需要联系 GitHub Support 清理。
- 本地敏感文件会保留，但会变成“未跟踪 + 被忽略”状态。
- 所有协作者（如果有）必须重新克隆；旧 clone 不能直接 pull。
- 旧历史备份 bundle 里仍然有敏感数据，必须安全保存，不能上传。

---

## 阶段 1 · 立即遏制（先做，不等清理）🔴 需确认

### 1.1 把 GitHub 仓库改为 Private（推荐立即做）

浏览器打开：

```text
https://github.com/seven060413/Smart-Q-A-System/settings
```

路径：**Settings → General → 页面底部 Danger Zone → Change repository visibility → Change to private**。

确认后，公开访问立即停止。这个操作本身可逆（以后可以再改回 public），但在清理完成前不建议改回。

### 1.2 重置受影响账号密码、吊销会话

审查确认泄露的是 2 个账号的密码哈希和聊天内容。**密码哈希不是明文，但应按已泄露处理。**

#### 方式 A：在服务器上执行（推荐）

先停服务，避免并发写入：

```bash
# 以下为服务器 Linux shell，不是 PowerShell
systemctl stop ikgr
cd /opt/ikgr
/opt/ikgr/.venv/bin/python - <<'PY'
import getpass
import sqlite3
from src.security import hash_password, now_utc

DB = "/opt/ikgr/data/app/ikgr.db"
username = input("username: ").strip()
new_password = getpass.getpass("new password: ")
now = now_utc()

con = sqlite3.connect(DB)
with con:
    cur = con.execute(
        "UPDATE users SET password_hash=?, updated_at=? WHERE username=?",
        (hash_password(new_password), now, username),
    )
    con.execute(
        "UPDATE auth_sessions SET revoked_at=? "
        "WHERE user_id=(SELECT id FROM users WHERE username=?) AND revoked_at IS NULL",
        (now, username),
    )
    print("users updated:", cur.rowcount)
con.close()
PY
systemctl start ikgr
```

对两个受影响账号各执行一次。如果这些账号不再需要，可以在确认后停用/删除，而不是重置。

#### 方式 B：在本机数据库执行（仅当你要重置本地库）

新建一个临时 Python 文件（不要放进仓库），把上面脚本里的 `DB` 改成 `D:\IKGR-system-eands\data\app\ikgr.db`，然后：

```powershell
Set-Location "D:\IKGR-system-eands"
.\.venv\Scripts\python.exe D:\temp\reset_ikgr_password.py
```

> 临时脚本不要放进仓库；用完删除。新密码不要写进命令历史、文档或 `.env`。

### 1.3 吊销所有旧会话（可选，但推荐）

如果你不确定哪些账号登录过，可以一次性吊销所有未撤销会话：

```sql
UPDATE auth_sessions
SET revoked_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
WHERE revoked_at IS NULL;
```

这会让所有用户重新登录，但能确保泄露期间签发的令牌失效。

### 1.4 通知受影响用户

如果这是课程/小范围系统，告知这 2 位用户：其聊天记录和密码哈希曾出现在公开仓库，建议更换密码；如果他们在其他地方复用了同一密码，也应更换。

---

## 阶段 2 · 完整备份 🟢（但备份含敏感数据，妥善保管）

### 2.1 复制整个工作目录（含 `.git`）

```powershell
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = "D:\IKGR-backup-$stamp"
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null

robocopy "D:\IKGR-system-eands" "$backupRoot\repo" /E `
  /XD ".venv" "node_modules" ".pytest_cache" "__pycache__" `
  /R:1 /W:1

# robocopy 的 0-7 都表示成功
if ($LASTEXITCODE -gt 7) { throw "robocopy failed: $LASTEXITCODE" }
Write-Host "Backup: $backupRoot"
```

说明：

- 包含 `.git` 和本地所有 SQL/压缩包。
- 排除 `.venv`、`node_modules`、缓存，节省空间；这些可以重建。
- 备份目录里会有敏感 SQL，**不要上传网盘/公开仓库**。

### 2.2 额外生成旧历史 bundle

```powershell
Set-Location "D:\IKGR-system-eands"
git bundle create "$backupRoot\repo-before-rewrite.bundle" --all
Get-FileHash "$backupRoot\repo-before-rewrite.bundle" -Algorithm SHA256
```

这个 bundle 是强制推送后恢复旧历史的最后手段。它同样含敏感数据，建议加密或放在离线介质。

### 2.3 校验关键本地文件仍在

```powershell
$files = @(
  "migration_data.sql",
  "migration_data_fixed.sql",
  "fix_user_id.sql",
  "h5-dist.zip",
  "deploy\migration-package.zip"
)
foreach ($f in $files) {
  $p = Join-Path "D:\IKGR-system-eands" $f
  "{0}  {1}" -f (Test-Path $p), $p
}
```

全部应为 `True`。

---

## 阶段 3 · 安装并验证 git-filter-repo 🟢

```powershell
python -m pip install --upgrade git-filter-repo
git filter-repo --version
```

预期输出版本号（审查时可安装到 `2.47.0`）。

如果 `git filter-repo` 提示不是 Git 命令：

```powershell
$pyScripts = python -c "import sysconfig; print(sysconfig.get_path('scripts'))"
Write-Host "Python Scripts: $pyScripts"
$env:Path = "$pyScripts;$env:Path"
git filter-repo --version
```

如果仍然找不到，直接用完整路径：

```powershell
& "$pyScripts\git-filter-repo.exe" --version
```

> 关闭并重新打开 PowerShell 后，PATH 才会永久生效。

---

## 阶段 4 · 修复 GitHub 认证 🟡

审查时 `ssh -T git@github.com` 返回 `Permission denied (publickey)`，说明当前机器没有可用的 GitHub SSH 身份。**不修好这一步，最后的 `git push --force` 一定失败。**

### 方案 A：改用 HTTPS + Git Credential Manager（推荐，简单）

```powershell
git config --global credential.helper manager
git config --global user.name "seven060413"
git config --global user.email "you@example.com"   # 替换为你的 GitHub 邮箱
```

如果提示 `credential helper 'manager' not found`，改用：

```powershell
git config --global credential.helper manager-core
```

或直接让 Git 在推送时弹窗输入 GitHub 用户名 + Personal Access Token。

读取测试（公开仓库不需要登录）：

```powershell
git ls-remote https://github.com/seven060413/Smart-Q-A-System.git
```

推送时 Git Credential Manager 会弹窗让你登录 GitHub，或要求输入 Personal Access Token。**不要把 token 直接写进 remote URL、脚本或文档。**

### 方案 B：继续用 SSH

先检查是否有密钥：

```powershell
Get-ChildItem "$env:USERPROFILE\.ssh" -Force
```

如果已有 `id_ed25519`：

```powershell
Get-Service ssh-agent
Start-Service ssh-agent
ssh-add "$env:USERPROFILE\.ssh\id_ed25519"
ssh -T git@github.com
```

如果提示 `Could not open a connection to your authentication agent`，先以管理员身份启动服务：

```powershell
Set-Service ssh-agent -StartupType Automatic
Start-Service ssh-agent
```

如果没有密钥，生成一个：

```powershell
ssh-keygen -t ed25519 -C "you@example.com"   # 替换为你的邮箱
Get-Content "$env:USERPROFILE\.ssh\id_ed25519.pub" | Set-Clipboard
```

然后到 GitHub：**Settings → SSH and GPG keys → New SSH key → 粘贴 → Add SSH key**。

验证：

```powershell
ssh -T git@github.com
```

看到 `successfully authenticated` 即可（SSH 可能返回 exit code 1，这是正常现象）。

> 本手册后续默认使用 HTTPS。如果你用 SSH，把下面所有 `https://github.com/...` 换成 `git@github.com:...`。

---

## 阶段 5 · 镜像克隆到独立目录 🟢

**不要在工作目录里直接改写历史。** 先在独立目录操作，确认无误后再推送。

```powershell
$rewrite = "D:\ikgr-rewrite.git"

if (Test-Path $rewrite) {
  $old = "$rewrite.old-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
  Rename-Item $rewrite $old
  Write-Host "Existing mirror moved to: $old"
}

git clone --mirror https://github.com/seven060413/Smart-Q-A-System.git $rewrite
Set-Location $rewrite
git config core.quotepath false
git for-each-ref --format="%(refname)" refs/heads refs/tags
```

预期能看到：

```text
refs/heads/feature/captcha
refs/heads/feature/sidebar-nav
refs/heads/main
```

> 如果仓库已转 Private，克隆时会要求登录；这是正常的。

---

## 阶段 6 · 改写镜像历史 🟡（只影响镜像，不影响本地工作目录）

### 6.1 执行 filter-repo

```powershell
Set-Location "D:\ikgr-rewrite.git"

git filter-repo --invert-paths `
  --path "fix_user_id.sql" `
  --path "migration_data.sql" `
  --path "migration_data_fixed.sql" `
  --path "h5-dist.zip" `
  --path "junior_dryrun.log" `
  --path "deploy/migration-package.zip" `
  --path "docs/数据迁移快速开始.md" `
  --path "docs/数据迁移操作指南.md" `
  --path "node_modules/" `
  --path "app/node_modules/" `
  --path-glob "*node_modules*"
```

说明：

| 参数 | 作用 |
|---|---|
| `--invert-paths` | 删除后面列出的路径，而不是保留 |
| `--path` | 精确匹配文件或目录（目录建议带 `/`） |
| `--path-glob "*node_modules*"` | 兜底移除所有嵌套的 `node_modules` 路径 |
| `fix_user_id.sql` | 真实用户 UUID |
| `migration_data*.sql` | 真实用户/聊天数据 |
| `deploy/migration-package.zip` | 含上述 SQL 的迁移包 |
| `h5-dist.zip` | 前端构建产物 |
| `junior_dryrun.log` | 空日志 |
| `docs/数据迁移*.md` | 已过时的一次性迁移文档，含真实用户名/姓名/用户 ID |

> **关于两份迁移文档**：它们已过时，且含真实标识符，所以默认一并从历史移除。  
> 如果你要把它们作为课程材料保留：请先把本地副本复制到仓库外（例如 `D:\IKGR-private\docs\`），**从上面命令中删掉这两行**，并在阶段 10 前不要 `git add` 它们。  
> 不删这两行也不会丢本地文件；`git reset --mixed` 后它们会以未跟踪文件形式留在磁盘上。

如果 filter-repo 报“expected freshly cloned repository”：

```powershell
# 仅在确认这是刚克隆的镜像、且没有本地改动时使用
git filter-repo --force --invert-paths `
  --path "fix_user_id.sql" `
  --path "migration_data.sql" `
  --path "migration_data_fixed.sql" `
  --path "h5-dist.zip" `
  --path "junior_dryrun.log" `
  --path "deploy/migration-package.zip" `
  --path "docs/数据迁移快速开始.md" `
  --path "docs/数据迁移操作指南.md" `
  --path "node_modules/" `
  --path "app/node_modules/" `
  --path-glob "*node_modules*"
```

> `--force` 会跳过安全检查，只在镜像目录里用，**不要**在主工作目录用。
>
> 补充：`git filter-repo` 通常可以直接在 `git clone --mirror` 的 bare 仓库中运行。如果你的版本报错说找不到工作区/不是普通仓库，可以改用普通克隆：
>
> ```powershell
> git clone --no-checkout https://github.com/seven060413/Smart-Q-A-System.git D:\ikgr-rewrite-work
> Set-Location D:\ikgr-rewrite-work
> # 为所有远程分支建立本地分支后再运行 filter-repo
> git branch -a
> ```
>
> 无论用哪种方式，执行前都要确认当前目录不是 `D:\IKGR-system-eands`。

### 6.2 filter-repo 的副作用

- 它会**删除 `origin` remote**（防止你误推），这是正常行为。
- 它会重写所有分支/标签的提交哈希。
- 只影响 `D:\ikgr-rewrite.git`，**不影响** `D:\IKGR-system-eands`。

### 6.3 重新添加 remote

```powershell
git remote add origin https://github.com/seven060413/Smart-Q-A-System.git
git remote -v
```

---

## 阶段 7 · 验证镜像中已无敏感路径 🔴 推送前必须通过

逐条执行，确认输出为空或符合预期。

### 7.1 路径已从所有历史中消失

```powershell
Set-Location "D:\ikgr-rewrite.git"

git log --all --oneline -- `
  fix_user_id.sql `
  migration_data.sql `
  migration_data_fixed.sql `
  h5-dist.zip `
  junior_dryrun.log `
  deploy/migration-package.zip
# 预期：没有任何输出

git log --all --oneline -- node_modules
# 预期：没有任何输出

git rev-list --objects --all | Select-String -Pattern `
  "migration_data|fix_user_id|h5-dist|migration-package|junior_dryrun|node_modules"
# 预期：没有任何输出
```

### 7.2 当前 HEAD 树中也没有

```powershell
git ls-tree -r --name-only HEAD | Select-String -Pattern `
  "migration_data|fix_user_id|h5-dist|migration-package|junior_dryrun|node_modules"
# 预期：没有任何输出
```

### 7.3 确认其他重要文件仍在

```powershell
git ls-tree -r --name-only HEAD | Select-String -Pattern `
  "^README.md$|^src/api.py$|^app/src/pages.json$|^deploy/nginx-ikgr.conf$|^docs/"
# 预期：能看到这些文件
```

### 7.4 查看分支和提交

```powershell
git for-each-ref --format="%(refname:short) %(objectname:short)" refs/heads
git log --oneline -5
git count-objects -vH
```

预期：

- `main`、`feature/captcha`、`feature/sidebar-nav` 都在。
- 最新提交是原 HEAD 的内容，但哈希已变（因为历史改写）。
- 仓库对象数/体积比改写前小。

### 7.5 检查是否还有 `.env`、DB、私钥

```powershell
git rev-list --objects --all | Select-String -Pattern `
  "\.env$|\.env\.|\.db$|\.sqlite|\.pem$|\.key$|id_rsa"
# 预期：最多只有 .env.example
```

> 只有当 7.1–7.2 全部为空时，才进入阶段 8。否则停下来检查路径拼写。

---

## 阶段 8 · 强制推送清理后的历史 🔴 **不可逆，需明确确认**

### 8.1 推送前最后确认

- [ ] 阶段 2 的备份和 bundle 已生成，且能打开/校验。
- [ ] 阶段 7 的所有敏感路径查询为空。
- [ ] 你接受所有提交哈希变化、协作者必须重新克隆。
- [ ] 你知道旧提交可能仍被 GitHub 缓存，需要后续联系 Support。
- [ ] 你当前在 `D:\ikgr-rewrite.git`，不是 `D:\IKGR-system-eands`。

```powershell
Get-Location
# 预期：D:\ikgr-rewrite.git
```

### 8.2 执行强制推送

```powershell
git push --force origin --all
git push --force origin --tags
```

如果 GitHub 提示分支保护（`protected branch hook declined` / `GH006`）：

1. 打开 GitHub：**Settings → Branches → Branch protection rules**。
2. 临时允许 force push / 关闭 `main` 的保护。
3. 重新执行推送。
4. 推送成功后立刻恢复保护规则。

> `--force` 会覆盖远程历史。旧提交在分支上不可见，但可能短期仍能通过 SHA 访问。恢复旧历史的唯一简单方式是阶段 2 的 bundle。

### 8.3 可选：删除不再需要的远程功能分支

如果 `feature/captcha`、`feature/sidebar-nav` 已经合并/不再使用：

```powershell
git push origin --delete feature/captcha
git push origin --delete feature/sidebar-nav
```

🟡 需确认；删除后远程分支不可恢复（本地镜像里还有）。

---

## 阶段 9 · 本地同步：保留文件，只移动分支指针 🔴 **绝不能 reset --hard**

### 9.1 切换本地 remote 到 HTTPS（如果你用 HTTPS）

```powershell
Set-Location "D:\IKGR-system-eands"
git remote set-url origin https://github.com/seven060413/Smart-Q-A-System.git
git remote -v
```

如果你继续用 SSH，跳过这一步。

### 9.2 拉取重写后的远程引用

```powershell
git fetch --force --prune origin
git branch -r
git log --oneline -3 origin/main
```

`--force` 允许远程跟踪分支做非快进更新（因为历史已重写）。

### 9.3 记录当前本地 HEAD

```powershell
git rev-parse HEAD
# 记下输出，与你清理前的 HEAD 对比
```

### 9.4 移动本地 main 到新历史（保留工作区）

```powershell
git reset --mixed origin/main
```

**这条命令做什么：**

- 把当前分支指针移动到 `origin/main`（重写后的历史）。
- 重置暂存区到新 HEAD。
- **不修改工作区文件。** `migration_data.sql`、`migration_data_fixed.sql`、`h5-dist.zip` 等仍然在磁盘上。

**为什么必须是 `--mixed`：**

- `git reset --hard origin/main` 会把“旧 HEAD 有、新 HEAD 没有”的文件从磁盘删除，**正好会删掉你要保留的 SQL/压缩包**。
- 所以本手册 **禁止** `git reset --hard`。

### 9.5 验证本地文件仍在

```powershell
Test-Path ".\migration_data.sql"
Test-Path ".\migration_data_fixed.sql"
Test-Path ".\fix_user_id.sql"
Test-Path ".\h5-dist.zip"
Test-Path ".\deploy\migration-package.zip"
Test-Path ".\ikgr-deploy.tar.gz"
```

全部应为 `True`。

### 9.6 此时 `git status` 会看到什么

```powershell
git status --short
```

预期：

- `.env.example`、`src/auth_service.py` 仍是 `M`（你原有的未提交修改）。
- 敏感文件可能显示为 `??`（未跟踪），因为新历史里没有它们，而旧 `.gitignore` 还没覆盖。
- 如果默认清理命令移除了两份迁移文档，它们也可能显示为 `?? docs/数据迁移...`；这是正常的。建议把本地副本移到 `D:\IKGR-private\docs\`，或让阶段 10 的新 `.gitignore` 忽略它们。
- **这是正常的。先不要 `git add -A`。** 先执行阶段 10。

> 如果你在这里误执行了 `git add -A`，敏感文件会重新进入暂存区。不要 commit；执行 `git reset` 取消暂存，然后继续阶段 10。

---

## 阶段 10 · 应用新 `.gitignore` 并提交 🟢

### 10.1 覆盖 `.gitignore`

```powershell
Set-Location "D:\IKGR-system-eands"
Copy-Item "docs\inspect\03-gitignore-proposed.txt" ".gitignore" -Force
```

### 10.2 确认敏感文件已被忽略

```powershell
git check-ignore -v migration_data.sql
git check-ignore -v migration_data_fixed.sql
git check-ignore -v fix_user_id.sql
git check-ignore -v h5-dist.zip
git check-ignore -v junior_dryrun.log
git check-ignore -v deploy/migration-package.zip
git check-ignore -v "docs/数据迁移快速开始.md"
git check-ignore -v "docs/数据迁移操作指南.md"
git check-ignore -v ikgr-full-deploy.tar.gz
git check-ignore -v tar
```

每条都应输出命中的 `.gitignore` 规则（例如 `*.sql`、`*.zip`、`*.log`、`docs/数据迁移*.md`、`*.tar.gz`、`/tar`）。

再看状态：

```powershell
git status --short
```

预期只剩：

```text
 M .env.example
 M .gitignore
 M src/auth_service.py
```

敏感文件不再出现。**不要**把 `.env.example` 和 `src/auth_service.py` 一起提交，除非你确认要提交它们。

### 10.3 只提交 `.gitignore`

```powershell
git add .gitignore
git status --short
git commit -m "chore: 完善 .gitignore，阻止迁移数据/构建产物/日志入库"
git push origin main
```

🟡 这是普通提交，可用 `git revert` 回滚。

### 10.4 可选：停止跟踪本地配置/误产物（保留本地文件）

```powershell
# 只取消跟踪，不删除本地文件
git rm --cached package-lock.json
git rm --cached .claude/settings.local.json
git rm --cached app/.hbuilderx/launch.json

# .vscode/settings.json 是否取消跟踪由你决定；
# 如果取消，记得同时从 .gitignore 删除 "!.vscode/settings.json" 这行，
# 否则它会以未跟踪文件的形式一直出现在 git status 里。
# git rm --cached .vscode/settings.json

git status --short
git commit -m "chore: 停止跟踪本地 IDE 配置与误产物"
git push origin main
```

🟢 `git rm --cached` 不会删除本地文件。`package-lock.json` 这个 96 字节空 lockfile 可以在确认后直接删除本地文件：

```powershell
# 可选；备份已完成后再做
Remove-Item ".\package-lock.json" -Force
```

### 10.5 可选：提交 `docs/inspect` 报告

`docs/inspect/` 已做脱敏，可以在清理完成后单独提交：

```powershell
git add docs/inspect
git commit -m "docs: 添加仓库审查与清理报告"
git push origin main
```

> 建议在阶段 11 验证通过后再提交，避免报告和旧历史混在一起。

---

## 阶段 11 · 最终验证 🟢

### 11.1 本地仓库

```powershell
Set-Location "D:\IKGR-system-eands"

git status
git log --oneline -5
git ls-files | Select-String -Pattern `
  "migration_data|fix_user_id|h5-dist|migration-package|junior_dryrun"
# 预期：无输出

git log --all --oneline -- migration_data.sql
# 预期：无输出

git check-ignore -v migration_data.sql
# 预期：命中 *.sql
```

### 11.2 本地文件仍在

```powershell
Get-ChildItem ".\migration_data*.sql", ".\fix_user_id.sql", ".\h5-dist.zip", `
  ".\deploy\migration-package.zip" | Select-Object Name, Length
```

### 11.3 远程仓库

```powershell
git ls-remote origin
git log --oneline -3 origin/main
```

浏览器打开：

```text
https://github.com/seven060413/Smart-Q-A-System
```

检查：

- 最新提交是新的哈希，提交信息仍是“头像持久化 - 后端加avatar字段+前端同步保存”。
- 仓库文件列表中不再有 `migration_data.sql`、`migration_data_fixed.sql`、`fix_user_id.sql`、`h5-dist.zip`、`junior_dryrun.log`、`deploy/migration-package.zip`。
- 分支列表仍符合预期。

### 11.4 旧提交 SHA 检查（重要）

浏览器尝试打开旧提交：

```text
https://github.com/seven060413/Smart-Q-A-System/commit/<旧HEAD>
```

> 把 `<旧HEAD>` 替换为你在本地记录的旧提交 SHA。**不要把真实旧 SHA 写进公开文档**；它可能指向仍被 GitHub 缓存的敏感提交。

可能出现三种结果：

1. **404**：说明 GitHub 已不再提供该对象，最好。
2. **仍能打开**：GitHub 缓存尚未清理，继续阶段 12。
3. **提示需要登录**：仓库已转 Private，普通访问被阻断，但缓存可能仍在。

> 即使页面 404，也不能 100% 证明 GitHub 内部已删除；敏感数据仍应按“已泄露”处理。

---

## 阶段 12 · GitHub 缓存与旧提交清理 🔴 需确认

### 12.1 联系 GitHub Support

强制推送只删除分支上的可达性，不保证立即清除 GitHub 的缓存视图、搜索索引和旧对象。按 GitHub 官方建议，需要联系 Support 请求清除缓存视图。

打开：

```text
https://support.github.com/contact
```

选择与 **Sensitive data removal / Remove data** 相关的主题，提供：

- 仓库：`https://github.com/seven060413/Smart-Q-A-System`
- 旧提交 SHA：`<你在本地记录的旧 HEAD>`
- 已移除的路径：
  - `migration_data.sql`
  - `migration_data_fixed.sql`
  - `deploy/migration-package.zip`
  - `fix_user_id.sql`
  - `h5-dist.zip`
  - `junior_dryrun.log`
  - `docs/数据迁移快速开始.md`
  - `docs/数据迁移操作指南.md`
- 说明：已用 `git filter-repo` 重写历史并 force push，请求清理缓存视图/旧对象。

参考文档：

```text
https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository
```

### 12.2 检查 fork

审查时 fork 数为 **0**。如果清理后发现 fork：

- fork 会保留旧历史，force push 不会影响 fork。
- 需要联系 fork 所有者删除/更新，或通过 GitHub Support 处理。
- 在 fork 存在期间，不能认为数据已完全从 GitHub 消失。

检查：

```text
https://github.com/seven060413/Smart-Q-A-System/forks
```

### 12.3 检查 Releases / Actions / Pages

- **Releases**：审查时为空；如果后来有 release，删除对应 tag/release。
- **Actions**：审查时没有工作流；如果后来添加，删除包含敏感日志的 run/artifact。
- **Pages**：如果启用了 GitHub Pages，旧构建可能仍可访问；到 **Settings → Pages** 检查并禁用/重建。

### 12.4 检查 Issue / PR

仓库有 1 个 open issue。检查 issue/PR 正文、评论、附件中是否贴过 SQL、日志、服务器信息；如果有，编辑/删除。旧提交链接可能仍指向已重写的 SHA。

### 12.5 搜索索引/第三方镜像

GitHub 之外的搜索引擎缓存、代码搜索镜像、爬虫副本无法由你直接清除。若数据敏感，按“已泄露”处理，不要依赖删除来消除风险。

---

## 阶段 13 · 回滚方案 🟡

### 13.1 还没 force push，想放弃

```powershell
# 直接删除/重命名镜像目录即可；本地工作目录从未被改写
Remove-Item "D:\ikgr-rewrite.git" -Recurse -Force
```

### 13.2 已经 force push，想恢复旧历史

用阶段 2 的 bundle：

```powershell
$restore = "D:\ikgr-restore"
git clone "$backupRoot\repo-before-rewrite.bundle" $restore
Set-Location $restore
git remote add origin https://github.com/seven060413/Smart-Q-A-System.git
git push --force origin --all
git push --force origin --tags
```

🔴 这会把敏感文件重新推回 GitHub；只在万不得已、且你接受重新暴露时使用。

### 13.3 本地 reset 后想找回旧提交

```powershell
git reflog
# 找到 reset 前的 HEAD（用 git reflog 查看）
$oldHead = "在这里粘贴你记录的旧提交 SHA"
git reset --mixed $oldHead
```

注意：旧提交对象可能已被 `git gc` 清理；如果之前执行过阶段 14 的清理，只能用备份恢复。

---

## 阶段 14 · 可选：清理本地旧对象与旧分支 🔴 **不可逆**

> 这一步**不影响 GitHub**，只影响本机 `.git` 和历史可恢复性。不做也完全可以。  
> 做之前必须确认阶段 2 的备份/bundle 可用。

### 14.1 处理本地旧分支/worktree

先确认另一个 worktree 没有未提交修改：

```powershell
Set-Location "D:\IKGR-system-eands"
git -C "$env:USERPROFILE\WorkBuddy\Worktrees\IKGR-system-eands\main-44e833c1" status
```

如果确认不再需要：

```powershell
git worktree remove "$env:USERPROFILE\WorkBuddy\Worktrees\IKGR-system-eands\main-44e833c1"
git branch -D "workbuddy/main-44e833c1"
git branch -D "backup-before-squash"
```

🔴 删除后没有备份就无法恢复。`worktree remove` 如果提示 dirty，先备份，不要直接 `--force`。

### 14.2 过期 reflog 并 GC

```powershell
git reflog expire --expire=now --all
git gc --prune=now --aggressive
```

🔴 这会永久删除本机不可达对象，包括旧提交里的敏感 SQL。执行后无法通过 reflog 恢复。  
如果还想保留旧历史以便回滚，**跳过这一步**。

### 14.3 检查残留

```powershell
git count-objects -vH
git fsck --unreachable
```

---

## 附录 A · 命令速查（按顺序）

```powershell
# 0) 检查
Set-Location "D:\IKGR-system-eands"
git status
git log --oneline -5
git rev-parse HEAD
git worktree list

# 1) 备份
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = "D:\IKGR-backup-$stamp"
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
robocopy "D:\IKGR-system-eands" "$backupRoot\repo" /E `
  /XD ".venv" "node_modules" ".pytest_cache" "__pycache__" /R:1 /W:1
git bundle create "$backupRoot\repo-before-rewrite.bundle" --all

# 2) 安装工具
python -m pip install --upgrade git-filter-repo
git filter-repo --version

# 3) 镜像克隆
$rewrite = "D:\ikgr-rewrite.git"
git clone --mirror https://github.com/seven060413/Smart-Q-A-System.git $rewrite
Set-Location $rewrite
git config core.quotepath false

# 4) 改写历史
git filter-repo --invert-paths `
  --path "fix_user_id.sql" `
  --path "migration_data.sql" `
  --path "migration_data_fixed.sql" `
  --path "h5-dist.zip" `
  --path "junior_dryrun.log" `
  --path "deploy/migration-package.zip" `
  --path "docs/数据迁移快速开始.md" `
  --path "docs/数据迁移操作指南.md" `
  --path "node_modules/" `
  --path "app/node_modules/" `
  --path-glob "*node_modules*"

# 5) 验证（必须全部为空）
git log --all --oneline -- migration_data.sql
git log --all --oneline -- node_modules
git rev-list --objects --all | Select-String `
  "migration_data|fix_user_id|h5-dist|migration-package|junior_dryrun|node_modules"

# 6) 强制推送 🔴
git remote add origin https://github.com/seven060413/Smart-Q-A-System.git
git push --force origin --all
git push --force origin --tags

# 7) 本地同步（注意：--mixed，不是 --hard）
Set-Location "D:\IKGR-system-eands"
git remote set-url origin https://github.com/seven060413/Smart-Q-A-System.git
git fetch --force --prune origin
git reset --mixed origin/main

# 8) 应用 .gitignore
Copy-Item "docs\inspect\03-gitignore-proposed.txt" ".gitignore" -Force
git check-ignore -v migration_data.sql
git add .gitignore
git commit -m "chore: 完善 .gitignore，阻止迁移数据/构建产物/日志入库"
git push origin main
```

---

## 附录 B · 绝对不能执行的命令

| 命令 | 后果 |
|---|---|
| `git reset --hard origin/main` | 会从磁盘删除旧 HEAD 有、新 HEAD 没有的敏感文件；**直接违背“本地保留”目标** |
| `git clean -fdx` | 删除所有未跟踪文件，包括要保留的 SQL、压缩包、`.env` |
| `git checkout -- .` | 丢弃工作区修改；可能覆盖你未提交的 `.env.example` / `auth_service.py` |
| `git add -A`（在阶段 10 之前） | 会把刚变成未跟踪的敏感文件重新加入暂存区 |
| 在 `D:\IKGR-system-eands` 里直接 `git filter-repo` | 会在主工作目录改写历史，风险高；本手册用独立镜像 |
| `git push --mirror`（未经确认） | 会强制同步所有 refs，可能删除远程分支；本手册用 `--all --tags` |
| 把 `repo-before-rewrite.bundle` 上传网盘/GitHub | 会再次泄露旧数据 |

---

## 附录 C · 本次从历史移除的路径

```text
fix_user_id.sql
migration_data.sql
migration_data_fixed.sql
h5-dist.zip
junior_dryrun.log
deploy/migration-package.zip
docs/数据迁移快速开始.md
docs/数据迁移操作指南.md
node_modules/
app/node_modules/
*/node_modules/**（通过 --path-glob "*node_modules*" 兜底）
```

**保留在本地、但不进入 Git：**

```text
migration_data.sql
migration_data_fixed.sql
fix_user_id.sql
h5-dist.zip
deploy/migration-package.zip
docs/数据迁移快速开始.md
docs/数据迁移操作指南.md
ikgr-deploy.tar.gz
ikgr-fix.tar.gz
ikgr-full-deploy.tar.gz
tar
```

**可选从历史移除（需你确认，默认不执行）：**

```text
docs/voice/语音识别实现原理.md   # 需先确认个人标识符上下文
package-lock.json                # 96 字节空 lockfile
```

---

## 附录 D · 执行记录表（建议你边做边填）

| 阶段 | 命令/操作 | 已执行 | 结果/备注 |
|---|---|---|---|
| 0 | 检查状态 | ☐ | |
| 1 | 仓库转 Private | ☐ | |
| 1 | 重置密码/吊销会话 | ☐ | |
| 2 | 目录备份 | ☐ | 备份路径： |
| 2 | 历史 bundle | ☐ | SHA256： |
| 3 | 安装 filter-repo | ☐ | 版本： |
| 4 | 修 GitHub 认证 | ☐ | HTTPS / SSH |
| 5 | 镜像克隆 | ☐ | |
| 6 | filter-repo | ☐ | |
| 7 | 验证无敏感路径 | ☐ | |
| 8 | 强制推送 | ☐ | 时间： |
| 9 | 本地 reset --mixed | ☐ | |
| 10 | 应用 .gitignore | ☐ | |
| 10 | 提交/推送 | ☐ | |
| 11 | 最终验证 | ☐ | |
| 12 | 联系 GitHub Support | ☐ | 工单号： |
| 14 | 可选 GC | ☐ | 是否跳过： |
