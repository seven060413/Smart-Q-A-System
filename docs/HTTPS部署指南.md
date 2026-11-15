# 🌐 IKGR 知识图谱系统 - 公网 HTTPS 部署指南

> **域名**：`seventeen17.com.cn`  
> **服务器**：`114.55.116.162`（阿里云）  
> **后端端口**：`18080`（已运行）  
> **部署日期**：2026-11-15

---

## 📋 部署前检查清单

- [x] 域名 ICP 备案已完成
- [x] 后端服务已在 18080 端口运行
- [ ] DNS 解析已配置（A 记录指向服务器 IP）
- [ ] 安全组已放行 80/443 端口
- [ ] 前端代码已修改 BASE_URL 为 HTTPS 地址

---

## 🚀 部署步骤（按顺序执行）

### 第 1 步：本地修改前端配置并构建 H5

#### 1.1 修改 API 地址

编辑 `app/src/config.js`，将 `BASE_URL` 改为：

```javascript
export const BASE_URL = 'https://seventeen17.com.cn'
```

**⚠️ 重要**：必须使用 HTTPS，否则浏览器会因混合内容（Mixed Content）拦截 API 请求！

#### 1.2 安装依赖并构建

```powershell
cd D:\IKGR-system-eands\app

# 安装依赖（如果还没装）
npm install

# 构建 H5 版本
npm run build:h5
```

构建成功后，产物在 `app/dist/build/h5/` 目录下。

#### 1.3 打包构建产物

```powershell
cd D:\IKGR-system-eands\app
Compress-Archive -Path dist\build\h5\* -DestinationPath ..\h5-dist.zip -Force
```

打包后的文件：`D:\IKGR-system-eands\h5-dist.zip`

---

### 第 2 步：上传到服务器

```bash
# 在本地 PowerShell 执行（或用 WinSCP/FileZilla 上传）
scp D:\IKGR-system-eands\h5-dist.zip root@114.55.116.162:/root/
```

---

### 第 3 步：服务器安装配置 Nginx

#### 3.1 SSH 登录服务器

```bash
ssh root@114.55.116.162
```

#### 3.2 安装 Nginx

**Ubuntu/Debian 系统**：
```bash
apt update && apt install -y nginx certbot python3-certbot-nginx
```

**CentOS/RHEL 系统**：
```bash
dnf install -y nginx certbot python3-certbot-nginx
```

#### 3.3 部署前端文件

```bash
# 创建前端目录
mkdir -p /opt/ikgr/frontend

# 解压前端文件
unzip -o /root/h5-dist.zip -d /opt/ikgr/frontend

# 验证文件
ls /opt/ikgr/frontend/
# 应该看到 index.html, static/ 等文件
```

#### 3.4 创建 Nginx 配置文件

```bash
cat > /etc/nginx/sites-available/ikgr << 'EOF'
server {
    listen 80;
    server_name seventeen17.com.cn www.seventeen17.com.cn;

    # 前端静态文件
    root /opt/ikgr/frontend;
    index index.html;

    # Gzip 压缩
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;

    # 前端路由（Vue/uni-app history 模式）
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API 反向代理到后端
    location /api/ {
        proxy_pass http://127.0.0.1:18080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket 支持（如果后续需要）
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # 超时设置（问答可能较慢）
        proxy_connect_timeout 60s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;
    }

    # 静态资源缓存
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # 禁止访问隐藏文件
    location ~ /\. {
        deny all;
        access_log off;
        log_not_found off;
    }
}
EOF
```

#### 3.5 启用站点并测试配置

```bash
# 创建软链接启用站点
ln -sf /etc/nginx/sites-available/ikgr /etc/nginx/sites-enabled/

# 删除默认站点（避免冲突）
rm -f /etc/nginx/sites-enabled/default

# 测试 Nginx 配置
nginx -t

# 启动 Nginx 并设置开机自启
systemctl restart nginx
systemctl enable nginx
```

此时访问 `http://seventeen17.com.cn` 应该能看到前端页面（但 API 还不能用，因为还没配 HTTPS）。

---

### 第 4 步：DNS 解析配置

登录 **阿里云控制台** → **域名解析** → 找到 `seventeen17.com.cn` → **添加记录**：

| 记录类型 | 主机记录 | 记录值 | TTL |
|---------|---------|--------|-----|
| A | @ | 114.55.116.162 | 10分钟 |
| A | www | 114.55.116.162 | 10分钟 |

**验证 DNS 生效**（可能需要几分钟）：
```bash
# 在本地执行
nslookup seventeen17.com.cn
# 应该返回 114.55.116.162
```

---

### 第 5 步：申请 Let's Encrypt SSL 证书

**前提**：DNS 解析已生效，且 80 端口可从公网访问。

```bash
# 申请证书并自动配置 Nginx
certbot --nginx -d seventeen17.com.cn -d www.seventeen17.com.cn
```

**交互提示**：
1. 输入邮箱地址（用于证书过期提醒）
2. 同意服务条款（输入 `Y`）
3. 选择是否重定向 HTTP 到 HTTPS（**选择 2：强制 HTTPS 重定向**）

**验证 HTTPS**：
```bash
# 测试证书自动续期
certbot renew --dry-run
```

此时访问 `https://seventeen17.com.cn` 应该能看到完整功能！

---

### 第 6 步：安全组配置

登录 **阿里云控制台** → **ECS 实例** → **安全组** → **添加规则**：

| 方向 | 协议 | 端口范围 | 授权对象 | 说明 |
|------|------|---------|----------|------|
| 入方向 | TCP | 80 | 0.0.0.0/0 | HTTP |
| 入方向 | TCP | 443 | 0.0.0.0/0 | HTTPS |

**🔒 安全加固**（可选但推荐）：

修改后端安全组规则，将 18080 端口的授权对象从 `0.0.0.0/0` 改为 `127.0.0.1`，这样外部无法直接访问后端，只能通过 Nginx 反向代理访问。

---

### 第 7 步：功能验证

#### 7.1 浏览器访问测试

1. 打开浏览器访问：`https://seventeen17.com.cn`
2. 检查页面正常加载（无混合内容警告）
3. 测试问答功能（输入一个数学问题）
4. 检查控制台无报错（F12 → Console）

#### 7.2 手机测试

1. 手机浏览器（Safari/Chrome）访问同一地址
2. 关闭 Wi-Fi，仅用 4G/5G 访问（确保公网可达）
3. 测试语音输入功能（需要 HTTPS）

#### 7.3 API 直接测试

```bash
# 在服务器上测试后端是否正常运行
curl http://127.0.0.1:18080/api/health
# 或
curl https://seventeen17.com.cn/api/health
```

---

### 第 8 步：设置证书自动续期

Let's Encrypt 证书有效期为 90 天，需自动续期：

```bash
# 编辑 crontab
crontab -e

# 添加以下行（每天凌晨 3 点检查并续期）
0 3 * * * certbot renew --quiet --post-hook "systemctl reload nginx"
```

**验证定时任务**：
```bash
crontab -l
# 应该看到刚添加的任务
```

---

## 🔧 常见问题排查

### 问题 1：访问域名显示 502 Bad Gateway

**原因**：Nginx 无法连接到后端服务

**解决**：
```bash
# 检查后端是否运行
systemctl status ikgr

# 检查端口监听
ss -tlnp | grep 18080

# 查看 Nginx 错误日志
tail -f /var/log/nginx/error.log
```

### 问题 2：浏览器提示"混合内容"被拦截

**原因**：前端请求的 API 是 HTTP 而不是 HTTPS

**解决**：
1. 检查 `app/src/config.js` 中 `BASE_URL` 是否为 `https://...`
2. 重新构建并上传：`npm run build:h5`
3. 清除浏览器缓存后刷新

### 问题 3：CSS/JS 文件 404

**原因**：Nginx 的 `root` 路径配置错误或文件未上传完整

**解决**：
```bash
# 检查文件是否存在
ls -la /opt/ikgr/frontend/index.html
ls -la /opt/ikgr/frontend/static/

# 检查 Nginx 配置中的 root 路径
grep "root" /etc/nginx/sites-available/ikgr
```

### 问题 4：certbot 申请证书失败

**原因**：DNS 未生效或 80 端口不通

**解决**：
```bash
# 检查 DNS 解析
dig +short seventeen17.com.cn

# 从本地测试 80 端口
telnet seventeen17.com.cn 80

# 检查防火墙
ufw status  # Ubuntu
firewall-cmd --list-all  # CentOS
```

### 问题 5：页面刷新后 404

**原因**：Vue/uni-app 使用了 history 模式，但 Nginx 未配置 `try_files`

**解决**：确保 Nginx 配置中有：
```nginx
location / {
    try_files $uri $uri/ /index.html;
}
```

---

## 📁 部署后的目录结构

```
/opt/ikgr/
├── src/                    # 后端源码
├── data/
│   └── app/
│       └── ikgr.db         # SQLite 数据库
├── frontend/               # ★ 前端静态文件（新增）
│   ├── index.html
│   └── static/
│       ├── js/
│       ├── css/
│       └── assets/
├── .env                    # 环境变量
└── requirements-server.txt
```

---

## 🔄 后续更新流程

当需要更新前端时：

1. 本地修改代码
2. 修改 `BASE_URL`（如需）
3. 重新构建：`npm run build:h5`
4. 打包上传：
   ```powershell
   Compress-Archive -Path dist\build\h5\* -DestinationPath ..\h5-dist.zip -Force
   scp ..\h5-dist.zip root@114.55.116.162:/root/
   ```
5. 服务器解压：
   ```bash
   unzip -o /root/h5-dist.zip -d /opt/ikgr/frontend
   ```

当需要更新后端时：

参考 `docs/阿里云后端部署指南.md` 重新打包并重启服务。

---

## ✅ 部署完成确认

- [ ] `https://seventeen17.com.cn` 可访问
- [ ] 问答功能正常
- [ ] 手机 4G 网络可访问
- [ ] 语音输入功能正常（HTTPS 下）
- [ ] 无浏览器控制台报错
- [ ] 证书自动续期已配置
- [ ] 安全组已加固（18080 仅允许本地访问）

---

## 📞 技术支持

如有问题，检查以下日志：

```bash
# Nginx 日志
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log

# 后端日志
journalctl -u ikgr -f

# 系统日志
journalctl -xe
```

---

**部署日期**：2026-11-15  
**文档版本**：v1.0  
**适用环境**：阿里云 ECS + Ubuntu/CentOS + Nginx + Let's Encrypt
