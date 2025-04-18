#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import logging
import asyncio
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telethon import TelegramClient, events, functions, utils
from telethon.sessions import StringSession
from telethon.tl.types import MessageEntityTextUrl, MessageEntityUrl, MessageMediaPhoto, MessageMediaDocument, PeerChannel, InputPeerChannel
from telethon.tl.types import InputMediaPhoto, InputMediaDocument, InputMediaUploadedPhoto, InputMediaUploadedDocument
from telethon.utils import get_peer_id
import tempfile
from telethon.tl.types import DocumentAttributeFilename
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest, ReadHistoryRequest
import random
# 导入人类行为模拟模块
from human_simulator import simulate_join_behavior, simulate_human_browsing
import logging.handlers
import json
import time
from logging.handlers import TimedRotatingFileHandler
import random
import mimetypes
# 导入MySQL功能
from mysql_functions import save_message_to_mysql, get_message_by_contact, get_message_stats, check_contact_exists, update_repeat_counter

# 每日消息限额设置 (新增)
MAX_DAILY_MESSAGES = 300  # 每天最多转发50条消息
daily_message_count = 0  # 当前日期已转发消息计数
last_count_reset_date = datetime.now().date()  # 上次重置计数的日期

# 消息转发冷却时间设置（新增）
COOLDOWN_MINUTES = random.randint(1, 10)  # 转发后冷却5~20分钟
last_forward_time = None  # 上次转发消息的时间
processing_message = False  # 初始化处理中标志为 False

# 检查是否可以发送更多消息 (新增)
def can_send_more_messages():
    """检查是否已达到每日消息限额，如需要则重置计数器"""
    global daily_message_count, last_count_reset_date, last_forward_time, processing_message
    
    # 检查日期是否变更，如果是新的一天则重置计数
    today = datetime.now().date()
    if today > last_count_reset_date:
        logger.info(f"新的一天开始，重置消息计数。上一天共发送 {daily_message_count} 条消息")
        daily_message_count = 0
        last_count_reset_date = today
        
        # 重置处理中标志，解决新的一天后消息处理被阻塞的问题
        processing_message = False
        logger.info("检测到新的一天，重置消息处理状态为空闲")
    
    # 检查是否超过每日限额
    if daily_message_count >= MAX_DAILY_MESSAGES:
        logger.warning(f"已达到每日消息限额 ({MAX_DAILY_MESSAGES})，今天不再转发更多消息")
        return False
    
    # 检查是否在冷却时间内（新增）
    if last_forward_time is not None:
        cooldown_seconds = COOLDOWN_MINUTES * 60
        elapsed_seconds = (datetime.now() - last_forward_time).total_seconds()
        
        if elapsed_seconds < cooldown_seconds:
            remaining_minutes = (cooldown_seconds - elapsed_seconds) / 60
            logger.info(f"正在冷却中，距离下次可转发还有 {remaining_minutes:.1f} 分钟")
            return False
        else:
            logger.info(f"冷却时间已过，可以继续转发消息")
    else:
        # 添加日志以确认没有初始冷却时间
        logger.info("初次启动，无冷却时间限制")
    
    return True

# 增加消息计数 (新增)
def increment_message_count():
    """增加已发送消息计数并记录日志"""
    global daily_message_count, last_forward_time, COOLDOWN_MINUTES
    daily_message_count += 1
    last_forward_time = datetime.now()  # 更新最后转发时间
    
    # 每次调用时重新生成随机的冷却时间
    COOLDOWN_MINUTES = random.randint(5, 20)
    
    remaining = MAX_DAILY_MESSAGES - daily_message_count
    logger.info(f"今日已转发 {daily_message_count}/{MAX_DAILY_MESSAGES} 条消息，剩余配额: {remaining} 条")
    logger.info(f"已启动 {COOLDOWN_MINUTES} 分钟冷却时间，下次可转发时间: {(last_forward_time + timedelta(minutes=COOLDOWN_MINUTES)).strftime('%H:%M:%S')}")
    
    # 如果达到限额，发送通知
    if daily_message_count == MAX_DAILY_MESSAGES:
        logger.warning(f"已达到今日转发限额 ({MAX_DAILY_MESSAGES} 条)，等待明天继续")
    
    # 保存消息计数
    save_message_count_data()

# 保存消息计数数据
def save_message_count_data():
    """保存当前消息计数和日期到文件"""
    data_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'message_count.json')
    try:
        data = {
            'count': daily_message_count,
            'date': last_count_reset_date.isoformat()
        }
        with open(data_file, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        logger.debug(f"已保存消息计数数据: {daily_message_count} 条 (日期: {last_count_reset_date})")
    except Exception as e:
        logger.error(f"保存消息计数数据失败: {e}")

# 加载消息计数数据
def load_message_count_data():
    """从文件加载消息计数和日期数据"""
    global daily_message_count, last_count_reset_date
    data_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'message_count.json')
    
    # 每次重启后重置消息计数
    daily_message_count = 0
    last_count_reset_date = datetime.now().date()
    logger.info(f"程序重启后重置今日消息计数: {daily_message_count}/{MAX_DAILY_MESSAGES}")
    
    # 如果希望完全禁用持久化可以删除下面这段代码
    # 但保留文件写入功能用于记录历史，即使我们不再读取它
    if os.path.exists(data_file):
        try:
            # 仅用于日志记录历史计数
            with open(data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            saved_date = datetime.fromisoformat(data['date']).date()
            saved_count = data['count']
            logger.info(f"上次运行的消息计数为: {saved_count} (日期: {saved_date})，已忽略并重置为0")
        except Exception as e:
            logger.debug(f"读取历史计数文件失败: {e}")
    else:
        logger.info("未找到消息计数数据文件，使用初始值0")

# 创建logs目录（如果不存在）
logs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(logs_dir, exist_ok=True)

# 创建一个倒序写入日志的处理器
class ReverseFileHandler(logging.FileHandler):
    """倒序写入日志的文件处理器，最新的日志会出现在文件的顶部"""
    
    def __init__(self, filename, mode='a', encoding=None, delay=False, max_cache_records=100):
        """
        初始化处理器
        filename: 日志文件路径
        max_cache_records: 内存中缓存的最大日志记录数，达到此数量会刷新到文件
        """
        super().__init__(filename, mode, encoding, delay)
        self.max_cache_records = max_cache_records
        self.log_records = []  # 用于缓存日志记录
        
        # 如果文件已存在，先读取现有内容
        self.existing_logs = []
        if os.path.exists(filename) and os.path.getsize(filename) > 0:
            try:
                with open(filename, 'r', encoding=encoding or 'utf-8') as f:
                    self.existing_logs = f.readlines()
            except Exception:
                self.existing_logs = []
    
    def emit(self, record):
        """重写emit方法，将日志记录缓存起来"""
        try:
            msg = self.format(record)
            self.log_records.append(msg + self.terminator)
            
            # 当缓存的记录达到最大数量时，写入文件
            if len(self.log_records) >= self.max_cache_records:
                self.flush()
        except Exception:
            self.handleError(record)
    
    def flush(self):
        """将缓存的日志写入文件，新日志在前面"""
        if self.log_records:
            try:
                # 在文件模式为'w'的情况下，先将新日志写入文件
                with open(self.baseFilename, 'w', encoding=self.encoding) as f:
                    # 写入新的日志记录（倒序）
                    for record in reversed(self.log_records):
                        f.write(record)
                    # 写入旧的日志记录
                    for line in self.existing_logs:
                        f.write(line)
                
                # 将新日志添加到现有日志的前面
                self.existing_logs = self.log_records + self.existing_logs
                self.log_records = []
            except Exception as e:
                # 如果出错，退回到标准写入方式
                print(f"倒序写入日志失败: {e}，使用标准方式写入")
                with open(self.baseFilename, 'a', encoding=self.encoding) as f:
                    for record in self.log_records:
                        f.write(record)
                self.log_records = []
    
    def close(self):
        """关闭处理器时刷新所有日志"""
        self.flush()
        super().close()

# 配置日志
# 创建一个日志记录器
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# 清除已有的处理器
for handler in logger.handlers[:]:
    logger.removeHandler(handler)

# 创建一个命令行处理器
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_format)
logger.addHandler(console_handler)

# 创建一个按天命名的倒序日志文件处理器
today_date = datetime.now().strftime("%Y-%m-%d")
log_file_path = os.path.join(logs_dir, f'telegram_forwarder_{today_date}.log')
file_handler = ReverseFileHandler(
    filename=log_file_path,
    encoding='utf-8'
)
file_handler.setLevel(logging.INFO)
file_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_format)
logger.addHandler(file_handler)

# 记录程序启动消息
logger.info("=" * 50)
logger.info("高级转发机器人启动 - %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
logger.info("=" * 50)

# 加载环境变量
load_dotenv()

# Telegram API凭证
API_ID = int(os.getenv('API_ID'))
API_HASH = os.getenv('API_HASH')

# 用户会话（首次运行后会生成，需保存）
SESSION = os.getenv('USER_SESSION', '')

# 频道信息
SOURCE_CHANNELS = os.getenv('SOURCE_CHANNELS', '').split(',')
DESTINATION_CHANNEL = os.getenv('DESTINATION_CHANNEL')

# 消息格式选项
INCLUDE_SOURCE = os.environ.get('INCLUDE_SOURCE', 'True').lower() in ['true', '1', 'yes', 'y']
ADD_FOOTER = os.environ.get('ADD_FOOTER', 'True').lower() in ['true', '1', 'yes', 'y']
FOOTER_TEXT = os.environ.get('FOOTER_TEXT', '').strip()
FORMAT_AS_HTML = os.environ.get('FORMAT_AS_HTML', 'False').lower() in ['true', '1', 'yes', 'y']

# 标题过滤设置
TITLE_FILTER = os.getenv('TITLE_FILTER', '')  # 标题过滤关键词，多个用逗号分隔，为空则不过滤
# 将TITLE_KEYWORDS设置为提供的关键词列表
TITLE_KEYWORDS = [
    "https://t.me/", 
    "私聊", 
    "频道", 
    "地址", 
    "价格", 
    "标签", 
    "位置", 
    "名字", 
    "双向机器人", 
    "电报", 
    "艺名"
]

# 存储媒体组的字典，键为媒体组ID，值为该组的消息列表
media_groups = {}

# 存储消息映射关系的字典，用于跟踪转发的消息
# 键为 "原频道ID_原消息ID"，值为目标频道中的消息ID
messages_map = {}

# 转发行为设置
FORWARD_MEDIA_GROUPS = os.environ.get('FORWARD_MEDIA_GROUPS', 'True').lower() in ['true', '1', 'yes', 'y']
EDIT_FORWARDED_MESSAGES = os.environ.get('EDIT_FORWARDED_MESSAGES', 'True').lower() in ['true', '1', 'yes', 'y']

class HumanLikeSettings:
    # 模拟人类操作的间隔时间范围（秒）
    JOIN_DELAY_MIN = 30  # 加入频道最小延迟
    JOIN_DELAY_MAX = 60  # 加入频道最大延迟，增加延迟上限更接近人类
    
    # 有时人类会暂停很长时间，模拟上厕所、接电话等
    LONG_BREAK_CHANCE = 0.25  # 25%的几率会有一个长时间暂停
    LONG_BREAK_MIN = 60  # 长暂停最小时间（秒）
    LONG_BREAK_MAX = 60  # 长暂停最大时间（秒）
    
    # 模拟人类活跃和非活跃时间段
    ACTIVE_HOURS_START = 7  # 活跃时间开始（24小时制）
    ACTIVE_HOURS_END = 23   # 活跃时间结束（24小时制）
    NIGHT_SLOWDOWN_FACTOR = 2.5  # 非活跃时段延迟倍率
    
    # 不同类型消息的阅读时间，根据内容长度调整
    TEXT_READ_SPEED = 0.03  # 每个字符的阅读时间（秒）
    TEXT_READ_BASE = 1.5    # 基础阅读时间（秒）
    IMAGE_VIEW_MIN = 3.0    # 查看图片的最小时间（秒）
    IMAGE_VIEW_MAX = 8.0    # 查看图片的最大时间（秒）
    VIDEO_VIEW_FACTOR = 0.3 # 视频持续时间的观看比例（看一个30秒视频可能会花10秒）
    
    # 消息转发的延迟
    FORWARD_DELAY_MIN = 3   # 消息转发最小延迟
    FORWARD_DELAY_MAX = 15  # 消息转发最大延迟
    
    # 人类偶尔会中断操作或改变注意力
    ATTENTION_SHIFT_CHANCE = 0.15  # 15%的几率会暂时分心
    ATTENTION_SHIFT_MIN = 10  # 分心的最小时间（秒）
    ATTENTION_SHIFT_MAX = 40  # 分心的最大时间（秒）
    
    # 输入和交互的速度变化
    TYPING_SPEED_MIN = 0.05  # 最快打字速度（每字符秒数）
    TYPING_SPEED_MAX = 0.15  # 最慢打字速度（每字符秒数）
    
    # 不再跳过任何消息，确保全部转发
    SKIP_MESSAGE_CHANCE = 0.0  # 设置为0，禁用随机跳过功能
    
    # 在转发大量媒体时设置随机间隔
    MEDIA_BATCH_DELAY_MIN = 0.5
    MEDIA_BATCH_DELAY_MAX = 5.0
    
    # 周期性活跃度变化（模拟工作日/周末模式）
    WEEKEND_ACTIVITY_BOOST = 1.3  # 周末活跃度提升
    MONDAY_ACTIVITY_DROP = 0.7    # 周一活跃度下降
    
    @staticmethod
    def calculate_reading_time(message_length, has_media=False, media_type=None):
        """根据消息长度和媒体类型计算真实的阅读时间"""
        # 基础阅读时间
        base_time = HumanLikeSettings.TEXT_READ_BASE
        
        # 文字阅读时间（随内容长度增加）
        if message_length > 0:
            text_time = message_length * HumanLikeSettings.TEXT_READ_SPEED
            base_time += text_time
        
        # 媒体查看时间
        if has_media:
            if media_type == 'photo':
                base_time += random.uniform(HumanLikeSettings.IMAGE_VIEW_MIN, HumanLikeSettings.IMAGE_VIEW_MAX)
            elif media_type == 'video':
                # 假设视频长度，根据大小或实际长度调整
                video_duration = random.randint(10, 60)  # 假设10-60秒的视频
                base_time += video_duration * HumanLikeSettings.VIDEO_VIEW_FACTOR
            else:
                base_time += random.uniform(2.0, 6.0)  # 其他媒体类型
        
        # 加入一点随机变化
        randomness = random.uniform(0.8, 1.2)
        return base_time * randomness
    
    @staticmethod
    def should_take_break():
        """判断是否应该模拟休息"""
        return random.random() < HumanLikeSettings.LONG_BREAK_CHANCE
    
    @staticmethod
    def get_break_time():
        """获取休息时间长度"""
        return random.uniform(HumanLikeSettings.LONG_BREAK_MIN, HumanLikeSettings.LONG_BREAK_MAX)
    
    @staticmethod
    def adjust_delay_for_time_of_day():
        """根据一天中的时间调整延迟"""
        current_hour = datetime.now().hour
        
        # 检查是否在活跃时间范围内
        if HumanLikeSettings.ACTIVE_HOURS_START <= current_hour < HumanLikeSettings.ACTIVE_HOURS_END:
            return 1.0  # 活跃时间，正常延迟
        else:
            # 非活跃时间，增加延迟
            return HumanLikeSettings.NIGHT_SLOWDOWN_FACTOR
    
    @staticmethod
    def adjust_delay_for_day_of_week():
        """根据星期几调整活跃度"""
        day_of_week = datetime.now().weekday()  # 0=周一，6=周日
        
        if day_of_week == 0:  # 周一
            return HumanLikeSettings.MONDAY_ACTIVITY_DROP
        elif day_of_week >= 5:  # 周末
            return HumanLikeSettings.WEEKEND_ACTIVITY_BOOST
        else:  # 普通工作日
            return 1.0

# 辅助函数：从链接中提取邀请哈希
def extract_invite_hash(link):
    """从Telegram邀请链接中提取哈希值"""
    logger.info(f"正在提取邀请哈希，链接: {link}")
    
    # 处理t.me/+XXXX格式的链接
    if '/+' in link:
        hash_value = link.split('/+', 1)[1].strip()
        logger.info(f"从/+格式链接提取哈希值: {hash_value}")
        return hash_value
    
    # 处理t.me/joinchat/XXXX格式的链接
    if '/joinchat/' in link:
        hash_value = link.split('/joinchat/', 1)[1].strip()
        logger.info(f"从/joinchat/格式链接提取哈希值: {hash_value}")
        return hash_value
        
    # 处理https://t.me/c/XXXX格式（私有频道直接链接）
    if '/c/' in link:
        try:
            parts = link.split('/c/', 1)[1].strip().split('/')
            if parts and parts[0].isdigit():
                channel_id = int(parts[0])
                logger.info(f"从/c/格式链接提取频道ID: {channel_id}")
                return channel_id
        except Exception as e:
            logger.error(f"提取/c/格式链接ID失败: {e}")
            pass
    
    logger.warning(f"无法从链接中提取邀请哈希: {link}")        
    return None

# 辅助函数：从链接中提取频道用户名
def extract_username(link):
    """从Telegram链接中提取频道用户名"""
    # 移除协议部分
    link = link.replace('https://', '').replace('http://', '')
    
    # 处理t.me/username格式
    if 't.me/' in link and '/+' not in link and '/joinchat/' not in link and '/c/' not in link:
        username = link.split('t.me/', 1)[1].strip()
        # 移除额外的路径部分
        if '/' in username:
            username = username.split('/', 1)[0]
        return username
    
    return None

# 存储已加入频道的记录文件
def save_joined_channels(channel_links):
    """保存已加入的频道链接到文件"""
    channels_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'joined_channels.json')
    try:
        # 确保所有链接都是字符串，并移除可能的空项
        channel_links = [ch for ch in channel_links if ch]
        
        # 标准化处理链接
        normalized_links = []
        for ch in channel_links:
            if isinstance(ch, str):
                normalized_links.append(ch.strip())
            else:
                # 如果不是字符串，转换为字符串
                normalized_links.append(str(ch))
        
        # 移除重复项
        normalized_links = list(set(normalized_links))
        
        with open(channels_file, 'w', encoding='utf-8') as f:
            json.dump(normalized_links, f, ensure_ascii=False, indent=2)
        logger.info(f"已保存 {len(normalized_links)} 个已加入频道的记录")
        return True
    except Exception as e:
        logger.error(f"保存已加入频道记录失败: {e}")
        return False

def load_joined_channels():
    """从文件加载已加入的频道链接"""
    channels_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'joined_channels.json')
    if not os.path.exists(channels_file):
        logger.info("未找到已加入频道的记录文件，将创建新记录")
        return []
    
    try:
        with open(channels_file, 'r', encoding='utf-8') as f:
            joined_channels = json.load(f)
        
        # 标准化链接格式
        joined_channels = [ch.strip() for ch in joined_channels if ch and isinstance(ch, str)]
        
        # 移除重复项
        joined_channels = list(set(joined_channels))
        
        logger.info(f"已加载 {len(joined_channels)} 个已加入频道的记录")
        return joined_channels
    except Exception as e:
        logger.error(f"加载已加入频道记录失败: {e}")
        return []

# 检查消息内容是否包含关键词
def contains_keywords(text):
    """检查文本是否包含关键词列表中的任何一个关键词，包括特殊格式如'关键词：值'的匹配"""
    if not text:
        return False
    
    # 首先进行直接匹配
    for keyword in TITLE_KEYWORDS:
        if keyword in text:
            logger.info(f"找到关键词匹配: '{keyword}'")
            return True
    
    # 然后检查特殊格式，如"名字：xxx"、"位置：xxx"等
    special_formats = ["名字", "位置", "价格", "标签", "频道", "私聊", "艺名"]
    for format_word in special_formats:
        # 使用正则表达式匹配"关键词：值"或"关键词:"格式
        pattern = f"{format_word}[：:].+"
        if re.search(pattern, text):
            logger.info(f"找到特殊格式匹配: '{format_word}：'")
            return True
    
    return False

def extract_contact_username(text):
    """从消息文本中提取私聊联系人用户名，排除频道、朋友圈和机器人相关的信息"""
    if not text:
        return None
    
    # 将文本按行分割，便于分析每一行
    lines = text.split('\n')
    username = None
    
    # 处理每一行文本
    for line in lines:
        line = line.strip()
        
        # 跳过空行
        if not line:
            continue
            
        # 检查特定关键词：排除频道、朋友圈和机器人相关的行
        if any(keyword in line.lower() for keyword in ['频道', '朋友圈', '机器人']):
            continue
        
        # 匹配私聊或联系后面的用户名
        if '私聊' in line or '联系' in line:
            # 尝试匹配"私聊:"或"联系:"后面的@用户名
            username_pattern = r'(私聊|联系)[:\s：]\s*(@\w+)'
            matches = re.findall(username_pattern, line)
            if matches:
                username = matches[0][1]  # 取匹配结果的第二个分组，即@xxx部分
                break
        
    # 如果没有匹配到标准格式，尝试其他常见格式
    if not username:
        for line in lines:
            line = line.strip()
            
            # 跳过排除关键词
            if any(keyword in line.lower() for keyword in ['频道', '朋友圈', '机器人']):
                continue
                
            # 如果行中包含联系人相关关键词，提取其中的@用户名
            if any(keyword in line.lower() for keyword in ['私聊', '联系', 'tg']):
                alt_pattern = r'@\w+'
                alt_matches = re.findall(alt_pattern, line)
                if alt_matches:
                    username = alt_matches[0]
                    break
    
    # 如果仍未找到，查找任何行中的@用户名
    if not username:
        for line in lines:
            line = line.strip()
            
            # 继续排除关键词
            if any(keyword in line.lower() for keyword in ['频道', '朋友圈', '机器人']):
                continue
                
            # 提取任何@开头的用户名
            alt_pattern = r'@\w+'
            alt_matches = re.findall(alt_pattern, line)
            if alt_matches:
                username = alt_matches[0]
                break
    
    return username

def remove_duplicated_text(text):
    """检测并移除重复的文本块"""
    if not text:
        return text
    
    # 按行分割文本
    lines = text.split('\n')
    if len(lines) <= 5:  # 如果行数很少，不太可能有重复
        return text
    
    # 尝试检测重复模式
    # 首先，查找可能的分隔点
    potential_blocks = []
    block_start = 0
    
    # 寻找可能的分隔点（空行或特定格式开头的行）
    for i, line in enumerate(lines):
        # 空行或者新内容块开始的标志
        if (not line.strip()) or any(line.strip().startswith(keyword) for keyword in ['位置', '名字', '艺名', '价格']):
            if i > block_start:
                potential_blocks.append((block_start, i-1))
                block_start = i
    
    # 添加最后一个块
    if block_start < len(lines) - 1:
        potential_blocks.append((block_start, len(lines) - 1))
    
    # 如果没有找到明显的块，返回原文本
    if len(potential_blocks) <= 1:
        return text
    
    # 提取第一个块的内容
    first_block_start, first_block_end = potential_blocks[0]
    first_block = '\n'.join(lines[first_block_start:first_block_end+1])
    
    # 如果第一个块的内容足够（包含关键信息），直接返回
    if '@' in first_block and any(keyword in first_block for keyword in ['私聊', '联系', 'tg', '频道']):
        return first_block
    
    # 尝试比较不同块是否相似
    unique_blocks = []
    for start, end in potential_blocks:
        block = '\n'.join(lines[start:end+1])
        # 只保留不重复的块
        if block not in unique_blocks:
            unique_blocks.append(block)
    
    # 如果有多个不同的块，可能是不同内容，保留全部
    if len(unique_blocks) > 1:
        return '\n\n'.join(unique_blocks)
    
    # 如果只有一个不重复的块，返回它
    return unique_blocks[0]

# 获取消息的完整文本内容（包括文本、标题和实体）
def get_full_message_text(message):
    """获取消息的所有可能包含文本的内容"""
    all_text = []
    
    # 添加主文本
    if message.text:
        all_text.append(message.text)
    
    # 添加消息标题（caption）
    if hasattr(message, 'caption') and message.caption:
        all_text.append(message.caption)
    
    # 如果消息有实体（如按钮、链接等），也提取其中的文本
    if hasattr(message, 'entities') and message.entities:
        for entity in message.entities:
            if hasattr(entity, 'text') and entity.text:
                all_text.append(entity.text)
    
    # 检查消息的其他可能属性
    for attr in ['message', 'raw_text', 'content']:
        if hasattr(message, attr) and getattr(message, attr):
            content = getattr(message, attr)
            if isinstance(content, str):
                all_text.append(content)
    
    # 将所有文本合并为一个字符串
    return "\n".join(all_text)

async def main():
    # 创建用户客户端
    # 安全处理SESSION字符串
    try:
        if SESSION and SESSION.strip():
            # 尝试使用已有会话
            client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
            logger.info("使用已有会话登录...")
        else:
            # 创建新会话
            client = TelegramClient(StringSession(), API_ID, API_HASH)
            logger.info("首次运行，需要验证登录...")
            logger.info("请按提示输入手机号（包含国家代码，如：+86xxxxxxxxxx）和验证码")
            logger.info("如果您的账户开启了两步验证，还需要输入您的密码")
    except ValueError:
        # SESSION字符串无效
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        logger.info("会话字符串无效，创建新会话...")
    
    # 确保启动时没有任何冷却限制
    global last_forward_time, processing_message
    last_forward_time = None
    processing_message = False  # 明确重置处理标志
    logger.info(f"初始化转发时间为 None，确保启动时无冷却限制")
    
    # 尝试加载消息计数数据
    load_message_count_data()
    
    try:
        # 启动客户端，显式指定手机号输入方式
        await client.start(phone=lambda: input('请输入手机号 (格式: +86xxxxxxxxxx): '))
        logger.info("登录成功!")
        
        # 生成会话字符串
        session_string = client.session.save()
        
        # 如果是新会话或会话已更改，保存到.env文件
        if not SESSION or session_string != SESSION:
            logger.info("生成新的会话字符串...")
            
            # 更新.env文件
            try:
                # 读取当前.env文件内容
                env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
                with open(env_path, 'r', encoding='utf-8') as file:
                    lines = file.readlines()
                
                # 更新USER_SESSION行
                updated = False
                for i, line in enumerate(lines):
                    if line.strip().startswith('USER_SESSION='):
                        lines[i] = f'USER_SESSION={session_string}\n'
                        updated = True
                        break
                
                # 如果没有找到USER_SESSION行，添加一行
                if not updated:
                    lines.append(f'USER_SESSION={session_string}\n')
                
                # 写回.env文件
                with open(env_path, 'w', encoding='utf-8') as file:
                    file.writelines(lines)
                
                logger.info("SESSION已保存到.env文件")
            except Exception as e:
                logger.error(f"保存SESSION到.env文件失败: {e}")
                logger.info("请手动将以下SESSION字符串添加到.env文件中的USER_SESSION变量：")
                logger.info(session_string)
    except Exception as e:
        logger.error(f"登录过程出错: {e}")
        return
    
    # 加载已加入的频道记录
    joined_channel_links = load_joined_channels()
    
    # 尝试自动加入源频道
    logger.info("尝试自动加入配置的源频道...")
    join_results = []
    raw_source_channels = []  # 存储源频道的ID或实体
    
    # 准备所有需要加入的频道列表
    channels_to_join = []
    for ch_id in SOURCE_CHANNELS:
        ch_id = ch_id.strip()
        if not ch_id:
            continue
        
        # 标准化处理频道链接进行比较
        if 't.me/' in ch_id.lower() or 'telegram.me/' in ch_id.lower():
            # 确保链接以https://开头
            if not ch_id.startswith('http'):
                if ch_id.startswith('t.me/'):
                    ch_id = 'https://' + ch_id
                elif ch_id.startswith('telegram.me/'):
                    ch_id = 'https://' + ch_id
        
        # 检查是否已有记录 - 使用部分匹配而不是完全匹配
        is_in_joined_list = False
        for joined_ch in joined_channel_links:
            # 1. 直接匹配
            if ch_id == joined_ch:
                is_in_joined_list = True
                break
                
            # 2. 如果都是链接，但格式略有不同
            if ('t.me/' in ch_id.lower() and 't.me/' in joined_ch.lower()):
                # 提取t.me/后面的部分进行比较
                ch_suffix = ch_id.lower().split('t.me/', 1)[1]
                joined_suffix = joined_ch.lower().split('t.me/', 1)[1]
                if ch_suffix == joined_suffix:
                    is_in_joined_list = True
                    ch_id = joined_ch  # 使用已记录的格式
                    break
        
        # 根据是否已加入决定下一步
        if is_in_joined_list:
            logger.info(f"跳过已记录加入的频道: {ch_id}")
            # 尝试直接获取实体
            try:
                # 获取频道实体
                entity = await client.get_entity(ch_id)
                raw_source_channels.append(entity.id)
                logger.info(f"已从记录中恢复频道: 「{entity.title}」")
                join_results.append(f"✅ 已从记录中恢复: {entity.title}")
                continue
            except Exception as e:
                logger.warning(f"无法从记录恢复频道 {ch_id}: {e}")
                # 如果无法恢复，则添加到待加入列表
                
        channels_to_join.append(ch_id)
    
    # 显示准备加入的频道总数
    logger.info(f"准备加入 {len(channels_to_join)} 个频道，将模拟人类操作速度...")
    
    # 处理每个频道，添加随机延迟
    channels_processed = 0
    newly_joined_channel_links = []  # 新加入的频道链接
    
    for ch_id in channels_to_join:
        channels_processed += 1
        
        # 模拟人类行为：在加入每个频道前增加随机延迟
        human_delay = random.uniform(HumanLikeSettings.JOIN_DELAY_MIN, HumanLikeSettings.JOIN_DELAY_MAX)
        logger.info(f"[{channels_processed}/{len(channels_to_join)}] 等待 {human_delay:.1f} 秒后尝试加入下一个频道...")
        await asyncio.sleep(human_delay)
        
        # 随机添加长时间暂停，模拟人类可能会暂时离开
        if random.random() < HumanLikeSettings.LONG_BREAK_CHANCE and channels_processed < len(channels_to_join):
            long_break = random.uniform(HumanLikeSettings.LONG_BREAK_MIN, HumanLikeSettings.LONG_BREAK_MAX)
            logger.info(f"模拟人类暂时离开，休息 {long_break:.1f} 秒...")
            await asyncio.sleep(long_break)
        
        # 检查是否是链接格式
        is_link = ('t.me/' in ch_id.lower() or 'telegram.me/' in ch_id.lower())
        
        try:
            # 首先检查是否已加入此频道，无论链接格式如何
            # 对于链接形式，尝试直接获取实体
            try:
                test_entity = await client.get_entity(ch_id)
                if test_entity:
                    logger.info(f"检测到已经是频道成员，无需重复加入: {test_entity.title if hasattr(test_entity, 'title') else ch_id}")
                    join_results.append(f"✅ 已是频道成员: {test_entity.title if hasattr(test_entity, 'title') else ch_id}")
                    raw_source_channels.append(test_entity.id if hasattr(test_entity, 'id') else test_entity)
                    newly_joined_channel_links.append(ch_id)
                    
                    # 对已加入的频道进行轻度浏览模拟
                    logger.info("对已加入频道进行简单浏览...")
                    await simulate_human_browsing(client, test_entity, 'light')
                    continue  # 已加入，跳过后续加入流程
            except Exception as e:
                # 获取实体失败，可能是未加入或其他原因，继续尝试加入
                logger.info(f"频道 {ch_id} 可能尚未加入，将尝试加入: {e}")
            
            if is_link:
                logger.info(f"检测到频道链接: {ch_id}")
                # 根据链接类型处理
                invite_hash = extract_invite_hash(ch_id)
                username = extract_username(ch_id)
                
                if invite_hash and not isinstance(invite_hash, int):
                    # 通过邀请链接加入
                    logger.info(f"尝试通过邀请链接加入: {ch_id}")
                    try:
                        # 模拟人类行为：先浏览邀请页面，再加入
                        await asyncio.sleep(random.uniform(1.5, 4.0))
                        
                        # 增加更多调试日志，显示发送给API的精确参数
                        logger.info(f"向Telegram API发送ImportChatInviteRequest，哈希值: '{invite_hash}'")
                        
                        # 对于+开头的链接，尝试两种方式
                        success = False
                        channel_entity = None
                        
                        # 方式一：直接使用提取的哈希值
                        try:
                            result = await client(functions.messages.ImportChatInviteRequest(
                                hash=invite_hash
                            ))
                            if result and result.chats:
                                success = True
                                channel_id = result.chats[0].id
                                channel_entity = result.chats[0]
                                logger.info(f"成功通过邀请链接加入: 「{result.chats[0].title}」")
                                join_results.append(f"✅ 已通过邀请链接加入: {result.chats[0].title}")
                                # 记录新加入的频道链接
                                newly_joined_channel_links.append(ch_id)
                        except Exception as e1:
                            error_str = str(e1).lower()
                            logger.error(f"第一种方式加入失败: {e1}")
                            
                            # 检查是否是已经是成员的错误
                            if "already a participant" in error_str:
                                logger.info("用户已是频道成员，无需重复加入")
                                success = True
                                # 直接通过链接获取频道实体
                                try:
                                    channel_entity = await client.get_entity(ch_id)
                                    channel_id = channel_entity.id
                                    logger.info(f"成功获取已加入频道的实体: 「{channel_entity.title}」")
                                    join_results.append(f"✅ 已是频道成员: {channel_entity.title}")
                                    # 记录频道链接
                                    newly_joined_channel_links.append(ch_id)
                                except Exception as e_entity:
                                    logger.error(f"获取已加入频道实体失败: {e_entity}")
                            # 处理已成功申请加入但需要管理员批准的情况
                            elif "successfully requested to join" in error_str:
                                logger.info(f"已成功申请加入频道，等待管理员批准: {ch_id}")
                                join_results.append(f"⏳ 已申请加入，等待批准: {ch_id}")
                                # 尝试获取频道的基本信息（即使未正式加入）
                                try:
                                    # 使用getFullChat API尝试获取基本信息
                                    await asyncio.sleep(random.uniform(1.0, 2.0))
                                    # 在这里不将此频道添加到source_channels，因为尚未正式加入
                                    # 但我们记录这个链接，以便将来可能重试
                                    newly_joined_channel_links.append(ch_id)
                                    logger.info(f"已记录待批准的频道链接: {ch_id}")
                                except Exception as e_info:
                                    logger.debug(f"无法获取待批准频道的信息: {e_info}")
                                
                                # 在这种情况下我们认为"成功"发送了请求，但不认为已成功加入
                                success = False
                            # 如果链接格式是+开头且尚未成功，尝试第二种方式
                            elif not success and '/+' in ch_id:
                                try:
                                    # 方式二：直接使用原始链接
                                    logger.info(f"尝试使用第二种方式加入: 使用完整链接直接获取实体")
                                    channel_entity = await client.get_entity(ch_id)
                                    if channel_entity:
                                        success = True
                                        channel_id = channel_entity.id
                                        logger.info(f"通过第二种方式成功获取频道实体: 「{channel_entity.title}」")
                                        join_results.append(f"✅ 已通过第二种方式加入: {channel_entity.title}")
                                        # 记录频道链接
                                        newly_joined_channel_links.append(ch_id)
                                except Exception as e2:
                                    logger.error(f"第二种方式也失败了: {e2}")
                                    
                                    # 检查是否是因为已经发送了加入请求
                                    if "successfully requested to join" in str(e2).lower():
                                        logger.info(f"第二种方式确认已申请加入频道，等待批准: {ch_id}")
                                        if not any(f"⏳ 已申请加入，等待批准: {ch_id}" in r for r in join_results):
                                            join_results.append(f"⏳ 已申请加入，等待批准: {ch_id}")
                                        newly_joined_channel_links.append(ch_id)
                        
                        # 如果成功获取到频道实体，添加到源频道列表并模拟浏览行为
                        if success and channel_entity:
                            raw_source_channels.append(channel_id)
                            # 使用更真实的人类浏览行为
                            logger.info("开始模拟人类浏览行为...")
                            await simulate_join_behavior(client, channel_entity)
                        elif not success:
                            logger.warning(f"加入频道失败，所有尝试方式均未成功: {ch_id}")
                            join_results.append(f"❌ 加入失败，请手动加入: {ch_id}")
                    except Exception as e:
                        logger.error(f"通过邀请链接加入失败: {ch_id}, 错误: {e}")
                        join_results.append(f"❌ 通过邀请链接加入失败: {ch_id}")
                elif isinstance(invite_hash, int):
                    # 这是/c/格式的私有频道ID
                    try:
                        # 尝试获取实体
                        channel_entity = await client.get_entity(invite_hash)
                        logger.info(f"找到私有频道: {channel_entity.title if hasattr(channel_entity, 'title') else invite_hash}")
                        join_results.append(f"✅ 已加入私有频道: {channel_entity.title if hasattr(channel_entity, 'title') else invite_hash}")
                        raw_source_channels.append(invite_hash)
                        # 记录频道链接
                        newly_joined_channel_links.append(ch_id)
                    except Exception as e:
                        logger.error(f"无法访问私有频道ID: {invite_hash}, 错误: {e}")
                        join_results.append(f"❌ 无法访问私有频道: {ch_id}")
                elif username:
                    # 通过用户名加入公开频道
                    logger.info(f"尝试加入公开频道: @{username}")
                    try:
                        # 首先尝试获取实体
                        channel_entity = await client.get_entity(username)
                        
                        # 检查是否已是成员
                        try:
                            # 尝试获取最近消息，如果能获取则说明已是成员
                            test_message = await client.get_messages(channel_entity, limit=1)
                            if test_message:
                                logger.info(f"检测到已是频道 @{username} 成员，无需重复加入")
                                join_results.append(f"✅ 已是频道成员: {channel_entity.title}")
                                raw_source_channels.append(channel_entity.id)
                                newly_joined_channel_links.append(ch_id)
                                
                                # 对已加入的频道进行轻度浏览模拟
                                logger.info("对已加入频道进行简单浏览...")
                                await simulate_human_browsing(client, channel_entity, 'light')
                                continue  # 跳过加入步骤
                        except Exception as e_test:
                            logger.info(f"可能还未加入频道 @{username}: {e_test}")
                        
                        # 模拟人类行为：先查看频道信息，再加入
                        await asyncio.sleep(random.uniform(2.0, 5.0))
                        
                        # 然后尝试加入
                        result = await client(functions.channels.JoinChannelRequest(
                            channel=channel_entity
                        ))
                        if result and result.chats:
                            channel_id = result.chats[0].id
                            logger.info(f"成功加入公开频道: {result.chats[0].title} (ID: {channel_id})")
                            join_results.append(f"✅ 已加入公开频道: {result.chats[0].title}")
                            raw_source_channels.append(channel_id)
                            # 记录频道链接
                            newly_joined_channel_links.append(ch_id)
                            
                            # 使用更真实的人类浏览行为代替简单延迟
                            logger.info("开始模拟人类浏览行为...")
                            await simulate_join_behavior(client, channel_entity)
                        else:
                            logger.warning(f"加入频道失败，返回结果中没有频道信息: {username}")
                            join_results.append(f"❌ 加入失败，无法获取频道信息: {username}")
                    except Exception as e:
                        # 检查错误信息是否表明已是成员
                        if "ALREADY_PARTICIPANT" in str(e) or "already in the channel" in str(e).lower():
                            logger.info(f"用户已是频道 @{username} 成员，无需重复加入")
                            join_results.append(f"✅ 已是频道成员: @{username}")
                            try:
                                # 直接获取实体
                                channel_entity = await client.get_entity(username)
                                raw_source_channels.append(channel_entity.id)
                                newly_joined_channel_links.append(ch_id)
                                
                                # 对已加入的频道进行轻度浏览模拟
                                logger.info("对已加入频道进行简单浏览...")
                                await simulate_human_browsing(client, channel_entity, 'light')
                            except Exception as e_get:
                                logger.error(f"获取已加入频道实体失败: {e_get}")
                        else:
                            logger.error(f"通过用户名加入频道失败: @{username}, 错误: {e}")
                            join_results.append(f"❌ 通过用户名加入频道失败: @{username}")
                else:
                    logger.warning(f"无法解析频道链接: {ch_id}")
                    join_results.append(f"❌ 无法解析频道链接: {ch_id}")
            else:
                # 尝试将频道ID转换为整数
                channel_id = int(ch_id)
                
                try:
                    # 尝试获取频道实体，如果已加入则能成功获取
                    channel_entity = await client.get_entity(channel_id)
                    logger.info(f"已经加入频道: {channel_entity.title if hasattr(channel_entity, 'title') else channel_id}")
                    join_results.append(f"✅ 已加入: {channel_entity.title if hasattr(channel_entity, 'title') else channel_id}")
                    raw_source_channels.append(channel_id)
                    # 记录频道链接/ID
                    newly_joined_channel_links.append(ch_id)
                    
                    # 对已加入的频道进行轻度浏览模拟
                    logger.info("对已加入频道进行简单浏览...")
                    await simulate_human_browsing(client, channel_entity, 'light')
                except:
                    # 如果获取实体失败，尝试直接加入
                    try:
                        # 模拟人类行为：尝试几次才找到正确频道
                        await asyncio.sleep(random.uniform(1.5, 3.0))
                        
                        # 方法1: 尝试直接使用ID加入
                        result = await client(functions.channels.JoinChannelRequest(
                            channel=channel_id
                        ))
                        if result and result.chats:
                            logger.info(f"成功加入频道: {result.chats[0].title} (ID: {channel_id})")
                            join_results.append(f"✅ 已加入: {result.chats[0].title}")
                            raw_source_channels.append(channel_id)
                            # 记录频道链接/ID
                            newly_joined_channel_links.append(ch_id)
                            
                            # 使用更真实的人类浏览行为
                            logger.info("开始模拟人类浏览行为...")
                            await simulate_join_behavior(client, result.chats[0])
                        else:
                            logger.warning(f"加入频道失败，返回结果中没有频道信息: {channel_id}")
                            join_results.append(f"❌ 加入频道 {channel_id} 失败: 无法获取频道信息")
                    except Exception as e:
                        logger.error(f"通过ID直接加入频道失败 {channel_id}: {e}")
                        join_results.append(f"❌ 无法加入频道 {channel_id}: {str(e)}")
        except ValueError:
            logger.error(f"无效的频道ID格式: {ch_id}")
            join_results.append(f"❌ 无效的频道ID格式: {ch_id}")
            # 即使格式错误，也添加一些延迟，更像人类输入错误后的思考
            await asyncio.sleep(random.uniform(1.0, 2.0))
        except Exception as e:
            logger.error(f"处理频道时出错 {ch_id}: {e}")
            join_results.append(f"❌ 处理频道出错 {ch_id}: {str(e)}")
            # 处理错误后添加延迟
            await asyncio.sleep(random.uniform(1.0, 2.0))
    
    # 更新并保存已加入频道的记录
    if newly_joined_channel_links:
        # 合并旧记录和新加入的频道，使用集合去重
        updated_channel_links = list(set(joined_channel_links + newly_joined_channel_links))
        # 保存更新后的记录
        save_joined_channels(updated_channel_links)
        logger.info(f"已更新频道记录文件，共 {len(updated_channel_links)} 个频道链接")

    # 输出加入结果摘要
    logger.info("频道加入结果摘要:")
    for result in join_results:
        logger.info(result)
    
    # 如果有无法自动加入的频道，提示用户手动加入
    if any("❌" in r for r in join_results):
        logger.warning("有些频道无法自动加入，请手动加入这些频道后再运行程序")
        logger.warning("手动加入方法: 在Telegram客户端中使用搜索功能或邀请链接加入这些频道")
    
    # 处理源频道ID列表，并确保获取到对应实体
    processed_source_channels = []
    logger.info(f"原始SOURCE_CHANNELS长度: {len(raw_source_channels)}")
    
    for ch_id in raw_source_channels:
        try:
            # 检查ID格式是否需要修正
            if isinstance(ch_id, int) and str(ch_id).isdigit() and len(str(ch_id)) > 6 and not str(ch_id).startswith('-100'):
                # 可能是缺少了 -100 前缀的频道ID
                corrected_id = int(f"-100{ch_id}")
                logger.info(f"尝试修正频道ID格式: {ch_id} -> {corrected_id}")
                try:
                    channel_entity = await client.get_entity(corrected_id)
                    channel_peer = get_peer_id(channel_entity)
                    processed_source_channels.append(channel_entity)
                    logger.info(f"使用修正后的ID格式成功连接频道: 「{channel_entity.title}」")
                    continue
                except Exception as e:
                    # 修正格式后仍然失败，继续尝试原始ID
                    logger.info(f"使用修正后的ID格式仍然失败: {e}")
            
            # 尝试获取频道实体
            channel_entity = await client.get_entity(ch_id)
            channel_peer = get_peer_id(channel_entity)
            processed_source_channels.append(channel_entity)
            logger.info(f"成功解析频道: 「{channel_entity.title}」")
        except ValueError:
            logger.warning(f"无效的频道ID格式: {ch_id} - 将尝试作为原始ID使用")
            processed_source_channels.append(ch_id)
            logger.info(f"将使用原始ID: {ch_id}，但可能无法接收消息")
        except Exception as e:
            # 减少冗长的错误消息，使用更简洁的提示
            logger.warning(f"无法获取频道 {ch_id} 的详细信息: {e}")
            logger.info(f"将使用原始ID: {ch_id} 继续尝试，若无法接收消息请检查ID格式或频道权限")
            
            # 尽管出错，仍然尝试添加原始ID
            processed_source_channels.append(ch_id)
    
    if not processed_source_channels:
        logger.error("没有可用的源频道，程序将退出")
        return
    
    # 获取目标频道实体
    try:
        # 直接使用配置的频道ID
        dest_id = int(DESTINATION_CHANNEL)
        logger.info(f"尝试连接目标频道: {dest_id}")
        destination_channel = await client.get_entity(dest_id)
        logger.info(f"已连接到目标频道: 「{destination_channel.title if hasattr(destination_channel, 'title') else destination_channel.id}」")
        
        # 发送测试消息以验证连接
        try:
            test_msg = await client.send_message(destination_channel, "✅ 转发机器人已启动，正在监控源频道...")
            logger.info("已发送测试消息到目标频道，连接正常")
        except Exception as e:
            logger.error(f"发送测试消息失败，可能没有发送消息权限: {e}")
    except Exception as e:
        logger.error(f"无法获取目标频道: {e}")
        logger.error("请确保:")
        logger.error("1. 您已经使用当前账号加入了该频道")
        logger.error("2. 频道ID正确")
        logger.error("3. 您有权限在该频道发送消息")
        return

    # 显示监控的频道列表
    logger.info("=== 开始监控以下频道 ===")
    channel_count = 0
    for channel in processed_source_channels:
        channel_count += 1
        try:
            if hasattr(channel, 'title'):
                logger.info(f"{channel_count}. 「{channel.title}」")
            else:
                logger.info(f"{channel_count}. ID: {channel}")
        except:
            logger.info(f"{channel_count}. 未知频道")
    logger.info("========================")
    
    # 添加一个处理中的标志变量
    processing_message = False

    # 注册消息处理器
    @client.on(events.NewMessage(chats=processed_source_channels))
    async def forward_messages(event):
        try:
            global processing_message, last_forward_time
            
            # 打印调试信息，看看 processing_message 的值
            logger.info(f"处理新消息，当前处理状态: {'正在处理中' if processing_message else '空闲'}")
            
            # 如果已经在处理消息，则跳过当前消息
            if processing_message:
                logger.info(f"已有消息正在处理中，跳过此消息 (ID: {event.message.id})")
                return
                
            # 标记为正在处理消息
            processing_message = True
                
            # 获取频道名称而非仅显示ID
            source_chat = await event.get_chat()
            chat_name = getattr(source_chat, 'title', f'未知频道 {event.chat_id}')
            
            # 增加更详细的日志，显示频道名称
            logger.info(f"收到来自频道「{chat_name}」的新消息: {event.message.id}")
            
            # 获取消息内容
            message = event.message
            
            # 确定消息类型，用于计算更真实的阅读时间
            message_type = None
            has_media = False
            
            if isinstance(message.media, MessageMediaPhoto):
                message_type = 'photo'
                has_media = True
            elif isinstance(message.media, MessageMediaDocument):
                if hasattr(message.media.document, 'mime_type'):
                    if 'video' in message.media.document.mime_type:
                        message_type = 'video'
                    elif 'audio' in message.media.document.mime_type:
                        message_type = 'audio'
                    else:
                        message_type = 'document'
                has_media = True
            
            # 跳过纯文本消息
            if not has_media:
                logger.info(f"跳过纯文本消息 (ID: {message.id}) - 根据设置只转发包含媒体的消息")
                processing_message = False
                return
            
            # 获取完整的消息文本内容
            full_message_text = get_full_message_text(message)
            logger.info(f"消息 (ID: {message.id}) 完整文本内容: {full_message_text}")
            
            # 提取联系人用户名
            contact_username = extract_contact_username(full_message_text) if 'extract_contact_username' in globals() else None
            
            # 如果存在联系人用户名，检查是否为重复消息
            if contact_username:
                # 设置重复消息的计数器阈值
                REPEAT_THRESHOLD = 5
                
                # 检查联系人是否已存在并获取当前计数器值
                exists, current_counter = check_contact_exists(contact_username)
                
                if exists:
                    logger.info(f"检测到重复联系人: {contact_username}，当前计数器值: {current_counter}")
                    
                    # 如果计数器未达到阈值，增加计数器并跳过此消息
                    if current_counter < REPEAT_THRESHOLD - 1:  # -1是因为之后会加1
                        new_counter = current_counter + 1
                        update_repeat_counter(contact_username, new_counter)
                        logger.info(f"跳过重复消息，联系人: {contact_username}，计数器已更新为: {new_counter}")
                        processing_message = False
                        return
                    else:
                        # 计数器达到阈值，重置为0并继续处理消息
                        update_repeat_counter(contact_username, 0)
                        logger.info(f"重复消息计数达到阈值 ({REPEAT_THRESHOLD})，将允许转发并重置计数器")
            
            # 检查消息文本是否包含关键词
            if not contains_keywords(full_message_text):
                logger.info(f"跳过消息 (ID: {message.id}) - 不包含任何指定关键词，关键词列表: {TITLE_KEYWORDS}")
                processing_message = False
                return
            
            # 检查每日消息限额
            global daily_message_count
            if daily_message_count >= MAX_DAILY_MESSAGES:
                logger.info(f"跳过消息 (ID: {message.id}) - 已达到每日转发限额 ({MAX_DAILY_MESSAGES})")
                processing_message = False
                return
                
            logger.info(f"消息 (ID: {message.id}) 包含媒体且文本包含关键词，将进行转发")
            
            # 检查冷却时间 - 避免初次启动时也有冷却
            if last_forward_time:
                current_time = datetime.now()
                time_since_last_forward = (current_time - last_forward_time).total_seconds() / 60
                if time_since_last_forward < COOLDOWN_MINUTES:
                    remaining_minutes = COOLDOWN_MINUTES - time_since_last_forward
                    logger.info(f"冷却时间未到，还需等待 {remaining_minutes:.1f} 分钟后才能转发此消息")
                    logger.info(f"消息 (ID: {message.id}) 将在 {remaining_minutes:.1f} 分钟后尝试转发")
                    await asyncio.sleep(remaining_minutes * 60)  # 等待剩余冷却时间
                    
                    # 再次检查是否可以发送消息（可能在等待期间达到了每日限额）
                    if daily_message_count >= MAX_DAILY_MESSAGES:
                        logger.info(f"等待冷却时间后检查：跳过消息 (ID: {message.id}) - 已达到每日转发限额 ({MAX_DAILY_MESSAGES})")
                        processing_message = False
                        return
            else:
                logger.info("首次转发消息，无需等待冷却时间")
            
            # 计算真实的阅读延迟（基于消息长度和类型）
            text_length = len(message.text) if message.text else 0
            reading_time = HumanLikeSettings.calculate_reading_time(text_length, has_media, message_type)
            
            # 应用时间段和星期因素调整
            time_factor = HumanLikeSettings.adjust_delay_for_time_of_day()
            day_factor = HumanLikeSettings.adjust_delay_for_day_of_week()
            
            # 最终阅读时间，结合一天中的时间和星期几
            final_reading_time = reading_time * time_factor * day_factor
            
            # 随机决定是否添加"分心"延迟
            if random.random() < HumanLikeSettings.ATTENTION_SHIFT_CHANCE:
                distraction_time = random.uniform(HumanLikeSettings.ATTENTION_SHIFT_MIN, HumanLikeSettings.ATTENTION_SHIFT_MAX)
                logger.info(f"模拟人类分心行为，暂停 {distraction_time:.1f} 秒")
                final_reading_time += distraction_time
            
            logger.info(f"根据消息类型和长度，模拟真实阅读延迟: {final_reading_time:.1f}秒")
            await asyncio.sleep(final_reading_time)
            
            # 模拟"打字"和处理时间 - 对于较长消息，添加额外处理时间
            if text_length > 50 and has_media:
                typing_time = random.uniform(1.5, 4.0)
                logger.info(f"模拟转发前的思考/处理时间: {typing_time:.1f}秒")
                await asyncio.sleep(typing_time)
            
            # 记录消息，可能需要用于后续编辑更新
            message_key = f"{event.chat_id}_{event.message.id}"
            
            # 获取来源信息
            source_info = f"\n\n来源: {source_chat.title}" if INCLUDE_SOURCE and hasattr(source_chat, 'title') else ""
            
            # 获取页脚
            footer = f"\n\n{FOOTER_TEXT}" if ADD_FOOTER else ""
            
            # 不再使用直接转发方式，因为会显示"Forwarded from"标记
            # 改为根据消息类型重新创建消息
            
            # 检查是否为媒体组的一部分
            if message.grouped_id:
                logger.info(f"检测到媒体组消息，组ID: {message.grouped_id}")
                await handle_media_group(client, message, source_info, footer, destination_channel)
            else:
                # 处理媒体消息
                logger.info(f"处理来自「{chat_name}」的媒体消息")
                caption = message.text if message.text else ""
                caption = caption + source_info + footer
                
                # 模拟上传准备时间
                upload_prep_time = random.uniform(0.5, 2.0)
                logger.info(f"模拟媒体上传准备时间: {upload_prep_time:.1f}秒")
                await asyncio.sleep(upload_prep_time)
                
                # 重新发送媒体（不是转发）
                try:
                    sent_message = await client.send_file(
                        destination_channel,
                        message.media,
                        caption=caption,
                        parse_mode='html' if FORMAT_AS_HTML else None
                    )
                    logger.info(f"已转发媒体消息 (ID: {message.id}) 到目标频道，新消息ID: {sent_message.id}")
                    
                    # 记录消息映射
                    messages_map[message_key] = sent_message.id
                    
                    # 增加消息计数并更新最后转发时间
                    last_forward_time = datetime.now()  # 更新最后转发时间
                    increment_message_count()
                    
                    # 计算下次可转发时间
                    next_forward_time = last_forward_time + timedelta(minutes=COOLDOWN_MINUTES)
                    logger.info(f"下次可转发时间: {next_forward_time.strftime('%H:%M:%S')}")
                    
                    # 去除重复内容
                    clean_text = remove_duplicated_text(full_message_text)
                    logger.info(f"处理后的消息文本长度: 原始{len(full_message_text)}字符 -> 处理后{len(clean_text)}字符")
                    
                    try:
                        save_message_to_mysql(
                            message.id,                      # 原始消息ID
                            str(event.chat_id),              # 源频道ID
                            chat_name,                       # 源频道名称
                            sent_message.id,                 # 转发后的消息ID
                            clean_text,                      # 去重后的消息文本
                            contact_username,                # 联系人用户名
                            False,                           # 不是媒体组
                            None                             # 无媒体组ID
                        )
                        logger.info(f"消息记录已保存到MySQL数据库，联系人: {contact_username}")
                    except Exception as db_error:
                        logger.error(f"保存消息记录到MySQL失败: {db_error}")
                except Exception as e:
                    logger.error(f"转发媒体消息 {message.id} 失败: {e}")
            # 转发成功后添加小延迟，模拟人类行为
            delay_after_send = random.uniform(0.8, 2.5)
            logger.info(f"转发后短暂暂停 {delay_after_send:.1f} 秒")
            await asyncio.sleep(delay_after_send)
        except Exception as e:
            logger.error(f"处理消息时出错: {e}")
        finally:
            # 解锁处理标志
            processing_message = False
    
    # 注册编辑消息处理器
    @client.on(events.MessageEdited(chats=processed_source_channels))
    async def forward_edited_messages(event):
        global processing_message, last_forward_time
        
        try:
            # 如果已经在处理消息，则跳过当前消息
            if processing_message:
                logger.info(f"已有消息正在处理中，跳过此编辑消息 (ID: {event.message.id})")
                return
                
            # 标记为正在处理消息
            processing_message = True
            
            # 获取消息ID
            message = event.message
            message_key = f"{event.chat_id}_{message.id}"
            
            # 获取频道名称
            source_chat = await event.get_chat()
            chat_name = getattr(source_chat, 'title', f'未知频道 {event.chat_id}')
            
            # 检查消息是否包含媒体
            has_media = False
            if message.media:
                if isinstance(message.media, MessageMediaPhoto):
                    has_media = True
                    message_type = 'photo'
                elif isinstance(message.media, MessageMediaDocument):
                    has_media = True
                    if hasattr(message.media.document, 'mime_type'):
                        if 'video' in message.media.document.mime_type:
                            message_type = 'video'
                        elif 'audio' in message.media.document.mime_type:
                            message_type = 'audio'
                        else:
                            message_type = 'document'
            
            # 跳过纯文本消息
            if not has_media:
                logger.info(f"跳过编辑的纯文本消息 (ID: {message.id}) - 根据设置只转发包含媒体的消息")
                processing_message = False
                return
            
            # 获取完整的消息文本内容
            full_message_text = get_full_message_text(message)
            logger.info(f"编辑消息 (ID: {message.id}) 完整文本内容: {full_message_text[:100]}...")
            
            # 提取联系人用户名
            contact_username = extract_contact_username(full_message_text) if 'extract_contact_username' in globals() else None
            
            # 如果存在联系人用户名，检查是否为重复消息
            if contact_username:
                # 设置重复消息的计数器阈值
                REPEAT_THRESHOLD = 5
                
                # 检查联系人是否已存在并获取当前计数器值
                exists, current_counter = check_contact_exists(contact_username)
                
                if exists:
                    logger.info(f"检测到重复联系人: {contact_username}，当前计数器值: {current_counter}")
                    
                    # 如果计数器未达到阈值，增加计数器并跳过此消息
                    if current_counter < REPEAT_THRESHOLD - 1:  # -1是因为之后会加1
                        new_counter = current_counter + 1
                        update_repeat_counter(contact_username, new_counter)
                        logger.info(f"跳过重复编辑消息，联系人: {contact_username}，计数器已更新为: {new_counter}")
                        processing_message = False
                        return
                    else:
                        # 计数器达到阈值，重置为0并继续处理消息
                        update_repeat_counter(contact_username, 0)
                        logger.info(f"重复编辑消息计数达到阈值 ({REPEAT_THRESHOLD})，将允许转发并重置计数器")
            
            # 检查消息文本是否包含关键词
            if not contains_keywords(full_message_text):
                logger.info(f"跳过编辑的消息 (ID: {message.id}) - 不包含任何指定关键词")
                processing_message = False
                return
            
            # 检查每日消息限额 (新增)
            if not can_send_more_messages():
                logger.info(f"跳过编辑的消息 (ID: {message.id}) - 已达到每日转发限额 ({MAX_DAILY_MESSAGES})")
                processing_message = False
                return
                
            logger.info(f"编辑的消息 (ID: {message.id}) 包含媒体且文本包含关键词，将进行转发")
            
            # 检查是否之前已转发
            if message_key not in messages_map:
                logger.info(f"从「{chat_name}」接收到编辑的消息，但未找到原始转发记录，将作为新消息处理")
                # 转发为新消息
                await forward_messages(event)
                return
                
            # 找到对应的目标消息ID
            dest_message_id = messages_map[message_key]
            logger.info(f"从「{chat_name}」接收到编辑的消息 (ID: {message.id})，对应目标消息ID: {dest_message_id}")
            
            # 获取来源信息
            source_info = f"\n\n来源: {source_chat.title}" if INCLUDE_SOURCE and hasattr(source_chat, 'title') else ""
            
            # 获取页脚
            footer = f"\n\n{FOOTER_TEXT}" if ADD_FOOTER else ""
            
            # 获取消息内容
            message_content = message.text if message.text else ""
            
            # 创建新消息
            new_message = message_content + source_info + footer
            
            # 发送包含原始媒体的编辑消息
            try:
                sent_message = await client.send_file(
                    destination_channel,
                    message.media,
                    caption=new_message,
                    parse_mode='html' if FORMAT_AS_HTML else None
                )
                logger.info(f"已转发编辑的媒体消息 (ID: {message.id}) 到目标频道")
                
                # 增加消息计数 (新增)
                increment_message_count()
                
                # 保存消息记录到MySQL数据库
                clean_text = remove_duplicated_text(full_message_text)
                try:
                    save_message_to_mysql(
                        message.id,                      # 原始消息ID
                        str(event.chat_id),              # 源频道ID
                        chat_name,                       # 源频道名称
                        sent_message.id,                 # 转发后的消息ID
                        clean_text,                      # 去重后的消息文本
                        contact_username,                # 联系人用户名
                        False,                           # 不是媒体组
                        None                             # 无媒体组ID
                    )
                    logger.info(f"编辑消息记录已保存到MySQL数据库，联系人: {contact_username}")
                except Exception as db_error:
                    logger.error(f"保存编辑消息记录到MySQL失败: {db_error}")
            except Exception as e:
                logger.error(f"转发编辑的媒体消息失败: {e}")
                
                # 尝试发送文本说明
                try:
                    await client.send_message(
                        destination_channel,
                        f"⚠️ 消息已更新，但媒体无法转发:\n\n{new_message}",
                        parse_mode='html' if FORMAT_AS_HTML else None
                    )
                    logger.info(f"已发送消息编辑通知")
                except Exception as e2:
                    logger.error(f"发送编辑通知也失败: {e2}")
        except Exception as e:
            logger.error(f"处理编辑消息时出错: {e}")
        finally:
            # 确保处理完后重置标志
            processing_message = False
    
    # 启动通知
    logger.info("高级转发机器人已启动，正在监控频道...")
    logger.info(f"监控的频道: {processed_source_channels}")
    logger.info(f"目标频道: {DESTINATION_CHANNEL}")
    logger.info(f"每日消息配额: {MAX_DAILY_MESSAGES}条，今日已发送: {daily_message_count}条，剩余: {MAX_DAILY_MESSAGES - daily_message_count}条")
    
    try:
        # 保持机器人运行
        await client.run_until_disconnected()
    finally:
        # 确保在退出时保存消息计数和哈希值
        logger.info("保存消息计数数据并退出...")
        save_message_count_data()

async def handle_media_group(client, message, source_info, footer, destination_channel):
    """处理媒体组消息（多张图片/视频）"""
    global media_groups
    
    group_id = str(message.grouped_id)
    message_key = f"{message.chat_id}_{message.id}"
    
    # 获取频道名称
    chat = await client.get_entity(message.chat_id)
    chat_name = getattr(chat, 'title', f'未知频道 {message.chat_id}')
    
    # 日志记录检测到的媒体组
    logger.info(f"检测到来自「{chat_name}」的媒体组消息，组ID: {group_id}")
    
    # 为每个媒体组ID创建一个列表
    if group_id not in media_groups:
        media_groups[group_id] = {
            'messages': [],
            'source_info': source_info,
            'footer': footer,
            'destination': destination_channel,
            'processing': False,
            'last_update': time.time(),
            'chat_name': chat_name
        }
    
    # 更新最后活动时间
    media_groups[group_id]['last_update'] = time.time()
    
    # 将当前消息添加到组中，避免重复添加
    if not any(m.id == message.id for m in media_groups[group_id]['messages']):
        media_groups[group_id]['messages'].append(message)
        logger.info(f"媒体组 {group_id} 添加一条新消息，目前收集了 {len(media_groups[group_id]['messages'])} 条")
    
    # 如果该组已经在处理中，直接返回，避免重复处理
    if media_groups[group_id]['processing']:
        logger.info(f"媒体组 {group_id} 已经在处理中，跳过")
        return
    
    # 标记为处理中，避免重复启动处理任务
    media_groups[group_id]['processing'] = True
    
    # 创建一个处理任务，会自动等待足够的时间
    asyncio.create_task(process_media_group_with_timeout(client, group_id))

async def process_media_group_with_timeout(client, group_id):
    """处理媒体组，使用自适应等待时间确保收集完整"""
    try:
        # 初始等待时间，单位：秒
        wait_time = 5
        
        # 连续几次消息数量相同的计数
        stable_count = 0
        last_count = 0
        max_stable_count = 3  # 需要达到的稳定次数
        
        # 最多等待次数
        max_wait_cycles = 10
        wait_cycles = 0
        
        while wait_cycles < max_wait_cycles:
            # 检查组是否依然存在
            if group_id not in media_groups:
                logger.warning(f"等待过程中媒体组 {group_id} 消失，可能已被处理")
                return
            
            # 记录当前状态
            group_data = media_groups[group_id]
            current_count = len(group_data['messages'])
            chat_name = group_data['chat_name']
            
            # 判断是否稳定（没有新消息进来）
            if current_count == last_count:
                stable_count += 1
                logger.info(f"媒体组 {group_id} 从「{chat_name}」收集了 {current_count} 条消息，保持稳定 ({stable_count}/{max_stable_count})")
            else:
                # 收到新消息，重置稳定计数
                stable_count = 0
                logger.info(f"媒体组 {group_id} 从「{chat_name}」收集了 {current_count} 条消息（有新消息）")
            
            # 记录当前数量用于下次比较
            last_count = current_count
            
            # 如果一段时间内消息数量稳定，则认为所有消息已收集完成
            if stable_count >= max_stable_count:
                logger.info(f"媒体组 {group_id} 的消息数量已稳定在 {current_count} 条，开始处理")
                break
            
            # 检查自上次消息后经过的时间，如果超过15秒无新消息，也视为完成
            elapsed = time.time() - group_data['last_update']
            if elapsed > 15:
                logger.info(f"媒体组 {group_id} 已超过15秒无新消息，视为收集完成")
                break
            
            # 等待一段时间
            logger.info(f"等待更多可能的媒体组消息，{wait_time}秒...")
            await asyncio.sleep(wait_time)
            wait_cycles += 1
            
            # 动态调整等待时间（逐渐减少）
            wait_time = max(1, wait_time - 1)
        
        # 最终处理媒体组
        await process_media_group_final(client, group_id)
    except Exception as e:
        logger.error(f"处理媒体组 {group_id} 时出错: {e}")
        if group_id in media_groups:
            # 出错时也清理，避免内存泄漏
            del media_groups[group_id]

async def process_media_group_final(client, group_id):
    """最终处理媒体组并转发"""
    try:
        global processing_message, last_forward_time, daily_message_count
        
        # 如果已经在处理消息，则跳过当前媒体组
        if processing_message:
            logger.info(f"已有消息正在处理中，跳过媒体组 {group_id}")
            return
            
        # 标记为正在处理消息
        processing_message = True
            
        # 检查组是否存在
        if group_id not in media_groups:
            logger.warning(f"处理前媒体组 {group_id} 消失，可能已被处理")
            processing_message = False
            return
            
        # 获取组数据并从跟踪字典中移除
        group_data = media_groups.pop(group_id)
        group_messages = group_data['messages']
        source_info = group_data['source_info']
        footer = group_data['footer']
        destination_channel = group_data['destination']
        chat_name = group_data['chat_name']
        
        # 如果没有消息，直接返回
        if not group_messages:
            logger.warning(f"媒体组 {group_id} 没有消息可处理")
            processing_message = False
            return
            
        # 按照ID排序，确保顺序正确
        group_messages.sort(key=lambda x: x.id)
        
        # 收集所有文本内容并合并
        all_texts = []
        full_texts = []
        for msg in group_messages:
            if msg.text and msg.text.strip():
                all_texts.append(msg.text.strip())
            # 使用完整的文本提取函数
            full_msg_text = get_full_message_text(msg)
            if full_msg_text.strip():
                full_texts.append(full_msg_text.strip())
        
        # 去重并合并文本
        unique_texts = []
        for text in all_texts:
            if text not in unique_texts:
                unique_texts.append(text)
        
        # 构建最终标题
        caption_text = "\n\n".join(unique_texts)
        
        # 生成媒体组的完整文本
        group_text = "\n".join(full_texts)
        
        # 提取联系人用户名
        contact_username = extract_contact_username(group_text) if 'extract_contact_username' in globals() else None
        
        # 如果存在联系人用户名，检查是否为重复消息
        if contact_username:
            # 设置重复消息的计数器阈值
            REPEAT_THRESHOLD = 5
            
            # 检查联系人是否已存在并获取当前计数器值
            exists, current_counter = check_contact_exists(contact_username)
            
            if exists:
                logger.info(f"检测到重复联系人: {contact_username}，当前计数器值: {current_counter}")
                
                # 如果计数器未达到阈值，增加计数器并跳过此消息
                if current_counter < REPEAT_THRESHOLD - 1:  # -1是因为之后会加1
                    new_counter = current_counter + 1
                    update_repeat_counter(contact_username, new_counter)
                    logger.info(f"跳过重复媒体组消息，联系人: {contact_username}，计数器已更新为: {new_counter}")
                    processing_message = False
                    return
                else:
                    # 计数器达到阈值，重置为0并继续处理消息
                    update_repeat_counter(contact_username, 0)
                    logger.info(f"重复媒体组消息计数达到阈值 ({REPEAT_THRESHOLD})，将允许转发并重置计数器")
        
        # 检查媒体组消息文本是否包含关键词
        has_keywords = False
        # 先检查提取的常规文本
        for text in unique_texts:
            if contains_keywords(text):
                has_keywords = True
                logger.info(f"媒体组 {group_id} 中的消息文本包含关键词")
                break
        
        # 如果常规文本没有关键词，再检查完整提取的文本
        if not has_keywords:
            for text in full_texts:
                if contains_keywords(text):
                    has_keywords = True
                    logger.info(f"媒体组 {group_id} 中的消息完整文本包含关键词")
                    break
        
        if not has_keywords:
            logger.info(f"跳过媒体组 {group_id} - 不包含任何指定关键词")
            processing_message = False
            return
        
        # 检查每日消息限额
        if daily_message_count >= MAX_DAILY_MESSAGES:
            logger.info(f"跳过媒体组 {group_id} - 已达到每日转发限额 ({MAX_DAILY_MESSAGES})")
            processing_message = False
            return
        
        # 检查冷却时间 - 避免初次启动时也有冷却
        if last_forward_time:
            current_time = datetime.now()
            time_since_last_forward = (current_time - last_forward_time).total_seconds() / 60
            if time_since_last_forward < COOLDOWN_MINUTES:
                remaining_minutes = COOLDOWN_MINUTES - time_since_last_forward
                logger.info(f"冷却时间未到，还需等待 {remaining_minutes:.1f} 分钟后才能转发媒体组")
                logger.info(f"媒体组 {group_id} 将在 {remaining_minutes:.1f} 分钟后尝试转发")
                await asyncio.sleep(remaining_minutes * 60)  # 等待剩余冷却时间
                
                # 再次检查是否可以发送消息（可能在等待期间达到了每日限额）
                if daily_message_count >= MAX_DAILY_MESSAGES:
                    logger.info(f"等待冷却时间后检查：跳过媒体组 {group_id} - 已达到每日转发限额 ({MAX_DAILY_MESSAGES})")
                    processing_message = False
                    return
        else:
            logger.info("首次转发媒体组，无需等待冷却时间")
            
        # 添加源信息和页脚
        if caption_text:
            caption_text += source_info + footer
        else:
            caption_text = source_info + footer if (source_info or footer) else ""
        
        # 准备所有媒体
        media_files = []
        temp_dir = tempfile.mkdtemp()
        
        try:
            # 现有代码...
            # 将媒体文件下载到临时目录
            for i, message in enumerate(group_messages):
                if message.media:
                    # 下载媒体
                    file_extension = get_media_extension(message.media)
                    temp_file = os.path.join(temp_dir, f"media_{group_id}_{i}{file_extension}")
                    await client.download_media(message, temp_file)
                    media_files.append(temp_file)
            
            # 如果没有媒体，直接返回
            if not media_files:
                logger.warning(f"媒体组 {group_id} 没有可提取的媒体内容")
                processing_message = False
                return
            
            # 发送收集到的全部媒体
            media_group = []
            
            for file in media_files:
                mime_type = mimetypes.guess_type(file)[0]
                
                if mime_type and mime_type.startswith('image'):
                    # 图片
                    media_group.append(InputMediaPhoto(file))
                elif mime_type and (mime_type.startswith('video') or mime_type.startswith('audio')):
                    # 视频或音频
                    media_group.append(InputMediaDocument(file))
                else:
                    # 其他文档
                    media_group.append(InputMediaDocument(file))
            
            # 最后处理：发送媒体组
            try:
                # 标题应该添加到最后一个媒体项，与原代码保持一致
                if caption_text and media_group:
                    # 将标题添加到最后一个媒体项
                    last_media = media_group[-1]
                    last_media.caption = caption_text
                    last_media.parse_mode = 'html' if FORMAT_AS_HTML else None
                
                # 发送媒体组
                sent_messages = await client.send_file(
                    destination_channel,
                    media_group,
                    caption=caption_text if len(media_group) == 1 else None,  # 单个媒体时也添加标题
                    parse_mode='html' if FORMAT_AS_HTML else None
                )
                
                # 如果是单条消息或列表的第一条，记录其ID
                first_sent_id = sent_messages[0].id if isinstance(sent_messages, list) else sent_messages.id
                logger.info(f"成功发送媒体组 {group_id} 到目标频道，首条消息ID: {first_sent_id}")
                
                # 记录媒体组哈希，防止重复发送
                
                # 更新转发计数和时间
                last_forward_time = datetime.now()
                increment_message_count()
                
                # 计算下次可转发时间
                next_forward_time = last_forward_time + timedelta(minutes=COOLDOWN_MINUTES)
                logger.info(f"下次可转发时间: {next_forward_time.strftime('%H:%M:%S')}")
                
                # 去除重复内容
                clean_text = remove_duplicated_text(group_text)
                logger.info(f"处理后的媒体组文本长度: 原始{len(group_text)}字符 -> 处理后{len(clean_text)}字符")
                
                try:
                    save_message_to_mysql(
                        group_messages[0].id,            # 使用第一条消息的ID作为原始ID
                        str(group_messages[0].chat_id),  # 源频道ID
                        chat_name,                       # 源频道名称
                        first_sent_id,                   # 转发后的第一条消息ID
                        clean_text,                      # 去重后的消息文本
                        contact_username,                # 联系人用户名
                        True,                            # 是媒体组
                        str(group_id)                    # 媒体组ID
                    )
                    logger.info(f"媒体组记录已保存到MySQL数据库，媒体组ID: {group_id}，联系人: {contact_username}")
                except Exception as db_error:
                    logger.error(f"保存媒体组记录到MySQL失败: {db_error}")
                
            except Exception as e:
                logger.error(f"发送媒体组 {group_id} 时出错: {e}")
                processing_message = False
                
        except Exception as e:
            logger.error(f"处理媒体组消息时出错: {e}")
            processing_message = False
            
        finally:
            # 清理临时文件
            try:
                for file_path in media_files:
                    if os.path.exists(file_path):
                        os.unlink(file_path)
                if os.path.exists(temp_dir):
                    os.rmdir(temp_dir)
                logger.info("临时媒体文件已清理")
            except Exception as e:
                logger.error(f"清理临时文件时出错: {e}")
            # 处理结束后，无论成功失败，都重置标志
            processing_message = False
            
    except Exception as e:
        logger.error(f"处理媒体组 {group_id} 时出错: {e}")
        # 确保错误情况下也重置标志
        processing_message = False

# 添加一个函数来判断媒体类型并返回适当的文件扩展名
def get_media_extension(media):
    """根据媒体类型返回适当的文件扩展名"""
    if isinstance(media, MessageMediaPhoto):
        return '.jpg'
    elif isinstance(media, MessageMediaDocument):
        for attribute in media.document.attributes:
            if isinstance(attribute, DocumentAttributeFilename):
                # 获取原始文件的扩展名
                return os.path.splitext(attribute.file_name)[1]
        # 如果没有找到文件名，默认使用.mp4（针对视频）
        return '.mp4'
    return '.bin'  # 默认二进制文件扩展名

if __name__ == '__main__':
    asyncio.run(main())
