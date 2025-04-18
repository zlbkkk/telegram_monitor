#!/usr/bin/env python
# -*- coding: utf-8 -*-

import pymysql
import sys

# 数据库连接配置
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '123456',
    'port': 3306,
    'charset': 'utf8mb4'
}

DB_NAME = 'telegram_forwarder'

def create_database_and_table():
    """创建数据库和表结构"""
    connection = None
    try:
        print("正在连接MySQL服务器...")
        # 先连接MySQL服务器，不指定数据库
        connection = pymysql.connect(
            host=DB_CONFIG['host'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password'],
            port=DB_CONFIG['port'],
            charset=DB_CONFIG['charset']
        )
        
        with connection.cursor() as cursor:
            # 创建数据库(如果不存在)
            print(f"正在创建数据库 {DB_NAME}...")
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME} DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            
            # 使用新创建的数据库
            print(f"切换到数据库 {DB_NAME}...")
            cursor.execute(f"USE {DB_NAME}")
            
            # 创建消息记录表
            print("正在创建forwarded_messages表...")
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS forwarded_messages (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                original_message_id BIGINT NOT NULL COMMENT '原始消息ID',
                source_channel_id VARCHAR(100) NOT NULL COMMENT '来源频道ID',
                source_channel_name VARCHAR(255) COMMENT '来源频道名称',
                forwarded_message_id BIGINT NOT NULL COMMENT '转发后的消息ID',
                message_text TEXT COMMENT '提取的消息文本内容',
                contact_username VARCHAR(255) COMMENT '提取的联系人用户名(如@xxxx)',
                is_media_group TINYINT(1) DEFAULT 0 COMMENT '是否为媒体组消息',
                media_group_id VARCHAR(100) DEFAULT NULL COMMENT '媒体组ID(如果是媒体组)',
                forwarded_at DATETIME NOT NULL COMMENT '转发时间',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
                repeat_counter INT DEFAULT 0 COMMENT '重复消息计数器',
                
                INDEX idx_original_msg (original_message_id, source_channel_id),
                INDEX idx_forwarded_msg (forwarded_message_id),
                INDEX idx_contact (contact_username),
                INDEX idx_media_group (media_group_id),
                INDEX idx_forwarded_at (forwarded_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            ''')
            
            # 如果表已存在，添加repeat_counter字段（如果不存在）
            print("检查并添加repeat_counter字段...")
            try:
                cursor.execute('''
                ALTER TABLE forwarded_messages 
                ADD COLUMN IF NOT EXISTS repeat_counter INT DEFAULT 0 COMMENT '重复消息计数器'
                ''')
            except pymysql.err.OperationalError as e:
                # 某些MySQL版本不支持IF NOT EXISTS语法，尝试备用方案
                if "Duplicate column name" not in str(e):
                    # 先检查字段是否存在
                    cursor.execute("SHOW COLUMNS FROM forwarded_messages LIKE 'repeat_counter'")
                    if not cursor.fetchone():
                        cursor.execute('''
                        ALTER TABLE forwarded_messages 
                        ADD COLUMN repeat_counter INT DEFAULT 0 COMMENT '重复消息计数器'
                        ''')
                        print("已添加repeat_counter字段")
                    else:
                        print("repeat_counter字段已存在")
                
            connection.commit()
            print("数据库和表创建成功！")
            print(f"数据库名称: {DB_NAME}")
            print("表名: forwarded_messages")
            
    except Exception as e:
        print(f"错误: {e}")
        return False
    finally:
        if connection:
            connection.close()
            print("数据库连接已关闭")
    
    return True

if __name__ == "__main__":
    print("开始创建Telegram转发消息存储数据库...")
    if create_database_and_table():
        print("数据库和表创建成功，可以开始使用了！")
    else:
        print("数据库和表创建失败，请检查错误信息。")
        sys.exit(1) 