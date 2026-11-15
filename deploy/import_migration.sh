#!/bin/bash
# ============================================
# IKGR 数据库迁移 - 服务器端一键导入脚本
# 用法: bash import_migration.sh [数据库路径]
# 示例: bash import_migration.sh /opt/ikgr/data/app/ikgr.db
# ============================================

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 默认数据库路径（可通过参数覆盖）
DB_PATH="${1:-/opt/ikgr/data/app/ikgr.db}"
SQL_FILE="/tmp/migration_data.sql"
BACKUP_SUFFIX=$(date +%Y%m%d_%H%M%S)

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  IKGR 数据库迁移工具 - 导入阶段${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""
echo -e "目标数据库: ${YELLOW}${DB_PATH}${NC}"
echo -e "SQL 文件:   ${YELLOW}${SQL_FILE}${NC}"
echo ""

# ==================== 步骤 1: 检查前置条件 ====================
echo -e "${BLUE}[步骤 1/6] 检查前置条件...${NC}"

# 检查 SQL 文件是否存在
if [ ! -f "$SQL_FILE" ]; then
    echo -e "${RED}❌ 错误: SQL 文件不存在: ${SQL_FILE}${NC}"
    echo -e "请先上传 migration_data.sql 到 /tmp/ 目录"
    exit 1
fi
echo -e "  ✅ SQL 文件存在 ($(ls -lh "$SQL_FILE" | awk '{print $5}'))"

# 检查数据库文件是否存在
if [ ! -f "$DB_PATH" ]; then
    echo -e "${YELLOW}⚠️  警告: 数据库文件不存在: ${DB_PATH}${NC}"
    echo -e "  将创建新的数据库文件..."
    mkdir -p "$(dirname "$DB_PATH")"
    touch "$DB_PATH"
else
    echo -e "  ✅ 数据库文件存在 ($(ls -lh "$DB_PATH" | awk '{print $5}'))"
fi

# 检查 sqlite3 是否安装
if ! command -v sqlite3 &> /dev/null; then
    echo -e "${YELLOW}⚠️  sqlite3 未安装，正在安装...${NC}"
    apt-get update -qq
    apt-get install -y -qq sqlite3
    echo -e "  ✅ sqlite3 安装完成"
else
    echo -e "  ✅ sqlite3 已安装 ($(sqlite3 --version | awk '{print $1}'))"
fi

echo ""

# ==================== 步骤 2: 备份数据库 ====================
echo -e "${BLUE}[步骤 2/6] 备份数据库...${NC}"

BACKUP_FILE="${DB_PATH}.backup.${BACKUP_SUFFIX}"
cp "$DB_PATH" "$BACKUP_FILE"
echo -e "  ✅ 备份完成: ${BACKUP_FILE}"
echo -e "  📦 备份大小: $(ls -lh "$BACKUP_FILE" | awk '{print $5}')"

echo ""

# ==================== 步骤 3: 停止后端服务 ====================
echo -e "${BLUE}[步骤 3/6] 停止后端服务...${NC}"

if systemctl is-active --quiet ikgr 2>/dev/null; then
    systemctl stop ikgr
    echo -e "  ✅ 服务已停止"
    sleep 2
else
    echo -e "  ℹ️  服务未运行或不存在，跳过停止"
fi

echo ""

# ==================== 步骤 4: 执行数据导入 ====================
echo -e "${BLUE}[步骤 4/6] 执行数据导入...${NC}"

# 记录导入前的表记录数
echo -e "  📊 导入前统计:"
sqlite3 "$DB_PATH" "
SELECT '  users' as tbl, COUNT(*) as cnt FROM users
UNION ALL SELECT 'conversations', COUNT(*) FROM conversations
UNION ALL SELECT 'messages', COUNT(*) FROM messages;
" 2>/dev/null || echo "  (表可能尚未创建)"

echo ""
echo -e "  🔄 正在导入数据..."

# 执行导入并捕获输出
IMPORT_OUTPUT=$(sqlite3 "$DB_PATH" < "$SQL_FILE" 2>&1) || {
    echo -e "${RED}❌ 导入失败!${NC}"
    echo -e "${RED}$IMPORT_OUTPUT${NC}"
    echo -e "\n${YELLOW}正在从备份恢复...${NC}"
    cp "$BACKUP_FILE" "$DB_PATH"
    echo -e "  ✅ 已恢复到备份状态"
    exit 1
}

# 检查是否有错误（忽略 UNIQUE constraint 警告）
ERROR_COUNT=$(echo "$IMPORT_OUTPUT" | grep -v "UNIQUE constraint" | grep -i "error" | wc -l)
if [ "$ERROR_COUNT" -gt 0 ]; then
    echo -e "${YELLOW}⚠️  导入时有 ${ERROR_COUNT} 个错误:${NC}"
    echo "$IMPORT_OUTPUT" | grep -v "UNIQUE constraint" | grep -i "error"
else
    echo -e "  ✅ 数据导入成功!"
fi

# 显示被跳过的记录数（如果有）
SKIPPED=$(echo "$IMPORT_OUTPUT" | grep -c "UNIQUE constraint" || true)
if [ "$SKIPPED" -gt 0 ]; then
    echo -e "  ℹ️  跳过 ${SKIPPED} 条已存在的记录（正常现象）"
fi

echo ""

# ==================== 步骤 5: 验证导入结果 ====================
echo -e "${BLUE}[步骤 5/6] 验证导入结果...${NC}"

echo -e "  📊 导入后统计:"
sqlite3 "$DB_PATH" "
SELECT '  users' as tbl, COUNT(*) as cnt FROM users
UNION ALL SELECT 'conversations', COUNT(*) FROM conversations
UNION ALL SELECT 'messages', COUNT(*) FROM messages
UNION ALL SELECT 'message_knowledge_points', COUNT(*) FROM message_knowledge_points
UNION ALL SELECT 'attachments', COUNT(*) FROM attachments;
"

echo ""
echo -e "  👥 用户列表:"
sqlite3 "$DB_PATH" "SELECT '    ' || username || ' (' || display_name || ')' FROM users;"

echo ""
echo -e "  💬 最近 5 个会话:"
sqlite3 "$DB_PATH" "SELECT '    ' || title || ' [' || substr(created_at, 1, 10) || ']' FROM conversations ORDER BY created_at DESC LIMIT 5;"

echo ""

# ==================== 步骤 6: 重启服务 ====================
echo -e "${BLUE}[步骤 6/6] 重启后端服务...${NC}"

if systemctl is-enabled --quiet ikgr 2>/dev/null; then
    systemctl start ikgr
    sleep 2
    
    if systemctl is-active --quiet ikgr; then
        echo -e "  ✅ 服务启动成功"
    else
        echo -e "${YELLOW}⚠️  服务启动异常，请手动检查:${NC}"
        echo -e "     systemctl status ikgr"
        echo -e "     journalctl -u ikgr -f"
    fi
else
    echo -e "  ℹ️  IKGR 服务未配置为 systemd 服务，跳过自动启动"
    echo -e "     请手动启动后端服务"
fi

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  ✅ 迁移完成！${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo -e "📋 后续操作:"
echo -e "   1. 打开浏览器访问: https://seventeen17.com.cn"
echo -e "   2. 使用原有账号登录"
echo -e "   3. 验证历史会话和消息是否完整"
echo ""
echo -e "🔧 如需回滚:"
echo -e "   systemctl stop ikgr"
echo -e "   cp ${BACKUP_FILE} ${DB_PATH}"
echo -e "   systemctl start ikgr"
echo ""
echo -e "📦 备份文件位置: ${BACKUP_FILE}"
echo ""
