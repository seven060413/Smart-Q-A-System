#!/bin/bash
# ============================================
# IKGR 前端部署脚本
# 用途：在阿里云服务器上部署 H5 前端 + Nginx + HTTPS
# 使用方法：bash deploy-frontend.sh
# ============================================

set -e  # 遇到错误立即退出

echo "=========================================="
echo "  IKGR 知识图谱系统 - 前端部署脚本"
echo "  域名：seventeen17.com.cn"
echo "=========================================="

# 检查是否为 root 用户
if [ "$EUID" -ne 0 ]; then
    echo "❌ 请使用 root 用户运行此脚本"
    exit 1
fi

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_success() { echo -e "${GREEN}✅ $1${NC}"; }
print_error() { echo -e "${RED}❌ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
print_info() { echo -e "📋 $1"; }

# ============================================
# 第 1 步：安装 Nginx 和 Certbot
# ============================================
echo ""
echo ">>> [1/6] 安装 Nginx 和 Certbot..."

if command -v apt &> /dev/null; then
    apt update && apt install -y nginx certbot python3-certbot-nginx
elif command -v dnf &> /dev/null; then
    dnf install -y nginx certbot python3-certbot-nginx
else
    print_error "不支持的包管理器，请手动安装 Nginx 和 Certbot"
    exit 1
fi

print_success "Nginx 和 Certbot 安装完成"

# ============================================
# 第 2 步：部署前端文件
# ============================================
echo ""
echo ">>> [2/6] 部署前端文件..."

# 创建目录
mkdir -p /opt/ikgr/frontend

# 检查打包文件是否存在
if [ ! -f /root/h5-dist.zip ]; then
    print_error "未找到 /root/h5-dist.zip，请先上传前端打包文件"
    exit 1
fi

# 解压文件
unzip -o /root/h5-dist.zip -d /opt/ikgr/frontend

# 验证文件
if [ ! -f /opt/ikgr/frontend/index.html ]; then
    print_error "前端文件解压失败，未找到 index.html"
    exit 1
fi

print_success "前端文件部署完成"
print_info "文件位置：/opt/ikgr/frontend/"

# ============================================
# 第 3 步：配置 Nginx
# ============================================
echo ""
echo ">>> [3/6] 配置 Nginx..."

# 备份现有配置（如果存在）
if [ -f /etc/nginx/sites-available/ikgr ]; then
    cp /etc/nginx/sites-available/ikgr /etc/nginx/sites-available/ikgr.bak.$(date +%Y%m%d%H%M%S)
    print_info "已备份现有配置"
fi

# 写入 Nginx 配置
cat > /etc/nginx/sites-available/ikgr << 'NGINX_CONF'
server {
    listen 80;
    server_name seventeen17.com.cn www.seventeen17.com.cn;

    root /opt/ikgr/frontend;
    index index.html;

    access_log /var/log/nginx/ikgr_access.log;
    error_log /var/log/nginx/ikgr_error.log;

    # Gzip 压缩
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types
        text/plain
        text/css
        text/xml
        application/json
        application/javascript
        application/xml
        application/xml+rss
        text/javascript;

    # 前端路由支持
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API 反向代理
    location /api/ {
        proxy_pass http://127.0.0.1:18080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        proxy_connect_timeout 60s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;
    }

    # 静态资源缓存
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 30d;
        add_header Cache-Control "public, immutable";
        access_log off;
    }

    # 禁止访问隐藏文件
    location ~ /\. {
        deny all;
        access_log off;
        log_not_found off;
    }
}
NGINX_CONF

# 启用站点
ln -sf /etc/nginx/sites-available/ikgr /etc/nginx/sites-enabled/

# 删除默认站点
rm -f /etc/nginx/sites-enabled/default

# 测试配置
if nginx -t; then
    print_success "Nginx 配置通过验证"
else
    print_error "Nginx 配置有误，请检查"
    exit 1
fi

# 重启 Nginx
systemctl restart nginx
systemctl enable nginx

print_success "Nginx 启动成功"

# ============================================
# 第 4 步：申请 SSL 证书
# ============================================
echo ""
echo ">>> [4/6] 申请 Let's Encrypt SSL 证书..."
print_info "将使用 certbot 自动申请并配置 HTTPS"

# 检查 DNS 是否解析到本机
SERVER_IP=$(curl -s ifconfig.me)
DNS_IP=$(dig +short seventeen17.com.cn | head -n1)

if [ "$SERVER_IP" != "$DNS_IP" ]; then
    print_warning "DNS 解析 IP ($DNS_IP) 与服务器 IP ($SERVER_IP) 不一致"
    print_warning "请确保已添加 A 记录指向 $SERVER_IP"
    read -p "是否继续？(y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "部署中止，请先配置 DNS 解析"
        exit 1
    fi
fi

# 申请证书
certbot --nginx -d seventeen17.com.cn -d www.seventeen17.com.cn

if [ $? -eq 0 ]; then
    print_success "SSL 证书申请成功"
else
    print_error "SSL 证书申请失败，请检查 DNS 解析和 80 端口访问"
    exit 1
fi

# ============================================
# 第 5 步：配置证书自动续期
# ============================================
echo ""
echo ">>> [5/6] 配置证书自动续期..."

# 添加 crontab 任务
(crontab -l 2>/dev/null | grep -v "certbot renew"; echo "0 3 * * * certbot renew --quiet --post-hook \"systemctl reload nginx\"") | crontab -

print_success "证书自动续期已配置（每天凌晨 3 点检查）"

# ============================================
# 第 6 步：验证部署
# ============================================
echo ""
echo ">>> [6/6] 验证部署..."

# 测试 HTTP 到 HTTPS 重定向
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://seventeen17.com.cn)
if [ "$HTTP_CODE" = "301" ] || [ "$HTTP_CODE" = "302" ]; then
    print_success "HTTP 到 HTTPS 重定向正常 ($HTTP_CODE)"
else
    print_warning "HTTP 重定向状态码：$HTTP_CODE（预期 301/302）"
fi

# 测试 HTTPS 访问
HTTPS_CODE=$(curl -s -o /dev/null -w "%{http_code}" https://seventeen17.com.cn)
if [ "$HTTPS_CODE" = "200" ]; then
    print_success "HTTPS 访问正常 (200)"
else
    print_warning "HTTPS 状态码：$HTTPS_CODE（预期 200）"
fi

# 测试 API 代理
API_CODE=$(curl -s -o /dev/null -w "%{http_code}" https://seventeen17.com.cn/api/health)
if [ "$API_CODE" = "200" ] || [ "$API_CODE" = "404" ] || [ "$API_CODE" = "405" ]; then
    print_success "API 反向代理正常 ($API_CODE)"
else
    print_warning "API 代理状态码：$API_CODE"
fi

# ============================================
# 部署完成
# ============================================
echo ""
echo "=========================================="
print_success "🎉 部署完成！"
echo "=========================================="
echo ""
echo "访问地址："
echo "  🌐 主域名：https://seventeen17.com.cn"
echo "  🌐 www：  https://www.seventeen17.com.cn"
echo ""
echo "后续操作："
echo "  1. 在浏览器访问上述地址测试功能"
echo "  2. 用手机 4G 网络测试公网访问"
echo "  3. 配置安全组放行 80/443 端口（如未配置）"
echo "  4. （可选）将后端 18080 端口改为仅允许本地访问"
echo ""
echo "常用命令："
echo "  查看 Nginx 日志：tail -f /var/log/nginx/ikgr_access.log"
echo "  查看错误日志：tail -f /var/log/nginx/ikgr_error.log"
echo "  重启 Nginx：   systemctl restart nginx"
echo "  查看后端日志：journalctl -u ikgr -f"
echo "  手动续期证书：certbot renew --force-renewal"
echo ""
echo "=========================================="
