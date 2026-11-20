import sqlite3
import glob

db_files = set(glob.glob('**/*.db', recursive=True) + glob.glob('**/*.sqlite', recursive=True) + glob.glob('*.db'))
print(f"🔍 找到 {len(db_files)} 个数据库文件，开始终极校验...\n")

for db in db_files:
    print(f"正在检查: {db}")
    try:
        conn = sqlite3.connect(db)
        cursor = conn.cursor()
        
        # 1. 修复 users 表
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(users)")
            cols = [row[1] for row in cursor.fetchall()]
            if 'avatar' not in cols:
                cursor.execute("ALTER TABLE users ADD COLUMN avatar TEXT")
                print("  ✅ users 表补充: avatar")
                
        # 2. 修复 attachments 表
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='attachments'")
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(attachments)")
            cols = [row[1] for row in cursor.fetchall()]
            att_needed = {
                'user_message_id': 'TEXT', 'assistant_message_id': 'TEXT',
                'user_id': 'TEXT', 'conversation_id': 'TEXT', 'message_id': 'TEXT',
                'original_name': 'TEXT', 'media_type': 'TEXT', 'byte_size': 'INTEGER',
                'ocr_status': 'TEXT', 'ocr_text': 'TEXT', 'question_text': 'TEXT',
                'error_code': 'TEXT', 'page_count': 'INTEGER', 'failed_pages': 'TEXT',
                'ocr_confidence': 'REAL', 'file_path': 'TEXT', 'created_at': 'TEXT',
                'deleted_at': 'TEXT'
            }
            for c, t in att_needed.items():
                if c not in cols:
                    cursor.execute(f"ALTER TABLE attachments ADD COLUMN {c} {t}")
                    print(f"  ✅ attachments 表补充: {c}")
                    
        # 3. 修复 messages 表
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='messages'")
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(messages)")
            cols = [row[1] for row in cursor.fetchall()]
            msg_needed = {
                'status': 'TEXT DEFAULT "completed"', 'refused': 'INTEGER DEFAULT 0',
                'knowledge_point': 'TEXT', 'source': 'TEXT', 'prerequisite_gaps': 'TEXT',
                'learning_path_json': 'TEXT', 'graph_version_id': 'TEXT',
                'context_graph_version_id': 'TEXT', 'reply_to_message_id': 'TEXT',
                'meta': 'TEXT', 'error_code': 'TEXT', 'error_message': 'TEXT',
                'latency_ms': 'INTEGER', 'deleted_at': 'TEXT'
            }
            for c, t in msg_needed.items():
                if c not in cols:
                    cursor.execute(f"ALTER TABLE messages ADD COLUMN {c} {t}")
                    print(f"  ✅ messages 表补充: {c}")

        conn.commit()
        conn.close()
        print(f"  🎉 {db} 修复完毕！\n")
        
    except Exception as e:
        print(f"  ❌ 修复 {db} 出错: {e}\n")

print("所有修复执行完毕，请重启后端服务！")