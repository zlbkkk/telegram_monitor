#!/usr/bin/env python
# -*- coding: utf-8 -*-

import pymysql
import logging
from datetime import datetime

# 获取logger
logger = logging.getLogger()

# 数据库连接配置
DB_CONFIG = {
    'host': '104.168.64.206',
    'user': 'root',
    'password': '123456',
    'port': 3306,
    'database': 'telegram_forwarder',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

def get_db_connection():
    """获取数据库连接"""
    try:
        connection = pymysql.connect(**DB_CONFIG)
        return connection
    except Exception as e:
        logger.error(f"MySQL数据库连接失败: {e}")
        return None

def save_message_to_mysql(original_msg_id, source_channel_id, source_channel_name, 
                         forwarded_msg_id, message_text, contact_username,
                         is_media_group=False, media_group_id=None):
    """将消息记录保存到MySQL数据库"""
    connection = None
    try:
        connection = get_db_connection()
        if not connection:
            return None
            
        cursor = connection.cursor()
        
        # 准备SQL语句
        sql = '''
        INSERT INTO forwarded_messages 
        (original_message_id, source_channel_id, source_channel_name, 
         forwarded_message_id, message_text, contact_username,
         is_media_group, media_group_id, forwarded_at, repeat_counter)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        '''
        
        # 执行SQL
        cursor.execute(sql, (
            original_msg_id, source_channel_id, source_channel_name,
            forwarded_msg_id, message_text, contact_username,
            1 if is_media_group else 0, media_group_id, 
            datetime.now(), 0  # repeat_counter初始为0
        ))
        
        connection.commit()
        last_id = cursor.lastrowid
        
        logger.info(f"已将消息记录保存到MySQL (ID: {last_id})")
        return last_id
    except Exception as e:
        logger.error(f"保存消息到MySQL失败: {e}")
        return None
    finally:
        if connection:
            connection.close()

def check_contact_exists(contact_username):
    """检查联系人是否已存在，并返回当前计数器值
    
    返回值：
    - 如果不存在，返回 (False, 0)
    - 如果存在，返回 (True, 当前计数器值)
    """
    if not contact_username:
        return False, 0
        
    connection = None
    try:
        connection = get_db_connection()
        if not connection:
            return False, 0
            
        cursor = connection.cursor()
        
        # 查询最新的记录
        sql = '''
        SELECT id, repeat_counter 
        FROM forwarded_messages 
        WHERE contact_username = %s 
        ORDER BY forwarded_at DESC 
        LIMIT 1
        '''
        
        cursor.execute(sql, (contact_username,))
        result = cursor.fetchone()
        
        if not result:
            return False, 0  # 不存在
            
        # 确保repeat_counter是整数值，如果为None则返回0
        counter = result['repeat_counter']
        if counter is None:
            counter = 0
        else:
            # 确保counter是整数类型
            counter = int(counter)
            
        return True, counter
    except Exception as e:
        logger.error(f"检查联系人存在状态失败: {e}")
        return False, 0
    finally:
        if connection:
            connection.close()

def update_repeat_counter(contact_username, new_counter_value):
    """更新联系人的重复计数器值"""
    if not contact_username:
        return False
        
    connection = None
    try:
        connection = get_db_connection()
        if not connection:
            return False
            
        cursor = connection.cursor()
        
        # 更新最新记录的计数器
        sql = '''
        UPDATE forwarded_messages
        SET repeat_counter = %s
        WHERE id = (
            SELECT id FROM (
                SELECT id 
                FROM forwarded_messages 
                WHERE contact_username = %s 
                ORDER BY forwarded_at DESC 
                LIMIT 1
            ) as tmp
        )
        '''
        
        cursor.execute(sql, (new_counter_value, contact_username))
        connection.commit()
        
        affected_rows = cursor.rowcount
        if affected_rows > 0:
            logger.info(f"已更新联系人 {contact_username} 的重复计数器为 {new_counter_value}")
            return True
        else:
            logger.warning(f"更新联系人 {contact_username} 的重复计数器失败，没有找到记录")
            return False
    except Exception as e:
        logger.error(f"更新重复计数器失败: {e}")
        return False
    finally:
        if connection:
            connection.close()

def get_message_by_contact(contact_username, limit=10):
    """根据联系人用户名查询消息记录"""
    connection = None
    try:
        connection = get_db_connection()
        if not connection:
            return []
            
        cursor = connection.cursor()
        
        sql = '''
        SELECT * FROM forwarded_messages 
        WHERE contact_username = %s 
        ORDER BY forwarded_at DESC 
        LIMIT %s
        '''
        
        cursor.execute(sql, (contact_username, limit))
        result = cursor.fetchall()
        
        return result
    except Exception as e:
        logger.error(f"查询联系人消息记录失败: {e}")
        return []
    finally:
        if connection:
            connection.close()

def get_message_stats():
    """获取消息统计信息"""
    connection = None
    try:
        connection = get_db_connection()
        if not connection:
            return {}
            
        cursor = connection.cursor()
        
        # 总消息数
        cursor.execute("SELECT COUNT(*) as total FROM forwarded_messages")
        total = cursor.fetchone()['total']
        
        # 不同联系人数量
        cursor.execute("SELECT COUNT(DISTINCT contact_username) as contacts FROM forwarded_messages WHERE contact_username IS NOT NULL")
        contacts = cursor.fetchone()['contacts']
        
        # 媒体组数量
        cursor.execute("SELECT COUNT(*) as media_groups FROM forwarded_messages WHERE is_media_group = 1")
        media_groups = cursor.fetchone()['media_groups']
        
        # 今日消息数
        cursor.execute("SELECT COUNT(*) as today FROM forwarded_messages WHERE DATE(forwarded_at) = CURDATE()")
        today = cursor.fetchone()['today']
        
        return {
            'total_messages': total,
            'unique_contacts': contacts,
            'media_groups': media_groups,
            'today_messages': today
        }
    except Exception as e:
        logger.error(f"获取消息统计信息失败: {e}")
        return {}
    finally:
        if connection:
            connection.close() 