# HTTPS 部署指南

> 目标：把 `seventeen17.com.cn` 通过 Nginx + Let's Encrypt 暴露为 HTTPS，并把后端
> `18080` 收紧为仅本机访问。
> 适用：阿里云 ECS + Ubuntu/Debian 或 CentOS/Alibaba Cloud Linux + Nginx。
> 本文不记录密码、私钥或真实密钥；证书由 Certbot 自动申请和续期。

| 项 | 当前值 |
|---|---|
| 域名 | `seventeen17.com.cn`、`www.seventeen17.com.cn` |
| 服务器公网 IP | `114.55.116.162`（阿里云 ECS） |
| 前端目录 | `/opt/ikgr/frontend` |
| 后端 | `127.0.0.1:18080`（由 Nginx 反代） |
| 仓库配置 | [`deploy/nginx-ikgr.conf`](../../deploy/nginx-ikgr.conf)、[`deploy/deploy-frontend.sh`](../../deploy/deploy-frontend.sh) |

---

## 1. 部署前检查

- [ ] 域名已完成 ICP 备案（阿里云要求）
- [ ] 后端已在服务器 `18080` 正常运行
- [ ] DNS A 记录已指向 `114.55.116.162`
- [ ] 安全组已放行 80/443
- [ ] 前端 `app/src/config.js` 的 `BASE_URL` 使用 HTTPS

---

## 2. DNS 解析与安全组

### 2.1 DNS 解析

入口：阿里云控制台 → **云解析 DNS** <https://dc.console.aliyun.com/>

在 `seventeen17.com.cn` 的“解析设置”中添加两条 A 记录：

| 记录类型 | 主机记录 | 记录值 | TTL |
|---|---|---|---|
| A | `@` | `114.55.116.162` | 10 分钟 |
| A | `www` | `114.55.116.162` | 10 分钟 |

验证（本地 PowerShell）：

```powershell
nslookup seventeen17.com.cn
```

应返回 `114.55.116.162`。DNS 通常 1–10 分钟生效。

### 2.2 安全组

入口：阿里云控制台 → **云服务器 ECS** <https://ecs.console.aliyun.com/> →
实例 → 安全组 → 入方向 → 手动添加：

| 协议 | 端口范围 | 授权对象 | 说明 |
|---|---|---|---|
| TCP | `80/80` | `0.0.0.0/0` | HTTP（Certbot 验证 + 跳转） |
| TCP | `443/443` | `0.0.0.0/0` | HTTPS |

`80/443` 对公网开放是标准做法；**真正敏感的是 18080**，配置完成后应收紧为仅本机。

验证端口：

```powershell
Test-NetConnection -ComputerName 114.55.116.162 -Port 80
Test-NetConnection -ComputerName 114.55.116.162 -Port 443
```

`TcpTestSucceeded : True` 即通。

---

## 3. 前端构建与上传

```powershell
cd D:\IKGR-system-eands\app
npm install
npm run build:h5
Compress-Archive -Path dist\build\h5\* -DestinationPath ..\h5-dist.zip -Force
scp ..\h5-dist.zip root@114.55.116.162:/root/
```

> `BASE_URL` 必须是 `https://seventeen17.com.cn`，否则浏览器会因混合内容拦截 API。

---

## 4. 服务器安装 Nginx

```bash
ssh root@114.55.116.162

# Ubuntu / Debian
apt update && apt install -y nginx certbot python3-certbot-nginx
# CentOS / RHEL
# dnf install -y nginx certbot python3-certbot-nginx

mkdir -p /opt/ikgr/frontend
unzip -o /root/h5-dist.zip -d /opt/ikgr/frontend
ls /opt/ikgr/frontend/   # 应看到 index.html、assets、static
```

仓库已提供完整的 [`deploy/nginx-ikgr.conf`](../../deploy/nginx-ikgr.conf)，直接作为
站点配置使用即可。核心内容：

```nginx
server {
    listen 80;
    server_name seventeen17.com.cn www.seventeen17.com.cn;
    root /opt/ikgr/frontend;
    index index.html;

    location / { try_files $uri $uri/ /index.html; }

    location /api/ {
        proxy_pass http://127.0.0.1:18080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }

    location ~ /\. { deny all; }
}
```

启用站点：

```bash
ln -sf /etc/nginx/sites-available/ikgr /etc/nginx/sites-enabled/ikgr
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl restart nginx
systemctl enable nginx
```

把仓库里的配置上传到服务器（在本地 PowerShell 执行）：

```powershell
scp deploy\nginx-ikgr.conf root@114.55.116.162:/etc/nginx/sites-available/ikgr
```

如果使用 `deploy/deploy-frontend.sh`，脚本会完成安装 Nginx、解包前端、写配置和申请证书；
执行前先阅读脚本，确认路径和域名与你的服务器一致。

---

## 5. 申请 Let's Encrypt 证书

前提：DNS 已生效，80 端口可从公网访问。

```bash
certbot --nginx -d seventeen17.com.cn -d www.seventeen17.com.cn
```

交互提示：

1. 输入邮箱（证书过期提醒）；
2. 同意条款输入 `Y`；
3. 选择 **强制 HTTP → HTTPS 重定向**。

验证：

```bash
certbot renew --dry-run
curl -I https://seventeen17.com.cn
```

---

## 6. 收紧后端与安全组

生产环境不要让 18080 直接暴露公网：

1. 修改 systemd 的 `ExecStart`：

```ini
ExecStart=/opt/ikgr/.venv/bin/uvicorn src.api:app --host 127.0.0.1 --port 18080
```

```bash
systemctl daemon-reload
systemctl restart ikgr
```

2. 安全组删除/收紧 `18080` 规则，只保留 80/443；
3. 确认外部不能直接访问 `http://114.55.116.162:18080/`，但
   `https://seventeen17.com.cn/api/...` 正常。

---

## 7. 功能验证

| 检查项 | 方法 | 期望 |
|---|---|---|
| 首页 | 浏览器打开 `https://seventeen17.com.cn` | 正常加载，无混合内容警告 |
| API | `curl -I https://seventeen17.com.cn/api/health` | 200/404/405 均可，说明反代通 |
| 问答 | 输入一个数学问题 | 正常返回 |
| 手机 4G | 关闭 Wi-Fi，用移动数据访问域名 | 正常 |
| 语音 | HTTPS 页面点麦克风 | 可授权并识别 |
| 证书 | 浏览器锁图标 / `certbot certificates` | 有效，自动续期已配置 |

后端日志：

```bash
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log
journalctl -u ikgr -f
```

---

## 8. 证书自动续期

Let's Encrypt 证书有效期 90 天。Certbot 通常已自动安装续期任务；确认：

```bash
systemctl list-timers | grep certbot
certbot renew --dry-run
```

如需 cron：

```bash
crontab -e
0 3 * * * certbot renew --quiet --post-hook "systemctl reload nginx"
```

---

## 9. 后续更新

### 9.1 只更新前端

```powershell
cd D:\IKGR-system-eands\app
npm run build:h5
Compress-Archive -Path dist\build\h5\* -DestinationPath ..\h5-dist.zip -Force
scp ..\h5-dist.zip root@114.55.116.162:/root/
```

```bash
unzip -o /root/h5-dist.zip -d /opt/ikgr/frontend
systemctl reload nginx
```

### 9.2 更新后端

见 [后端部署与更新手册.md](后端部署与更新手册.md)。

---

## 10. 常见问题

| 现象 | 原因与处理 |
|---|---|
| 502 Bad Gateway | 后端没运行/没监听 18080：`systemctl status ikgr`、`ss -tlnp \| grep 18080`、看 Nginx error.log |
| 混合内容被拦截 | `BASE_URL` 还是 HTTP；改 HTTPS 后重新构建 H5 |
| CSS/JS 404 | `/opt/ikgr/frontend` 路径不对或文件没解压完整 |
| 刷新页面 404 | Nginx 缺少 `try_files $uri $uri/ /index.html;` |
| certbot 失败 | DNS 未生效、80 端口不通、防火墙/安全组未放行 |
| 域名打不开但 IP 能开 | DNS 未生效或解析到了别的 IP；`nslookup` 检查 |
| 18080 仍可从公网访问 | 安全组未收紧；systemd 仍监听 `0.0.0.0` |

---

## 11. 完成清单

- [ ] `https://seventeen17.com.cn` 可访问
- [ ] HTTP 自动跳转 HTTPS
- [ ] 问答、登录、历史、语音正常
- [ ] 手机 4G 可访问
- [ ] 证书自动续期已配置
- [ ] 18080 仅本机可访问
- [ ] 安全组只保留 80/443（和必要的 SSH 来源）
- [ ] 前端无混合内容/控制台报错
