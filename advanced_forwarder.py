#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import logging
import asyncio
import re
from datetime import datetime
from dotenv import load_dotenv
from telethon import TelegramClient, events, functions
from telethon.sessions import StringSession
from telethon.tl.types import MessageEntityTextUrl, MessageEntityUrl, MessageMediaPhoto, MessageMediaDocument, PeerChannel, InputPeerChannel
from telethon.tl.types import InputMediaPhoto, InputMediaDocument, InputMediaUploadedPhoto, InputMediaUploadedDocument
from telethon.utils import get_peer_id
import tempfile
from telethon.tl.types import DocumentAttributeFilename
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
import random
# 导入人类行为模拟模块
from human_simulator import simulate_join_behavior, simulate_human_browsing
import logging.handlers
import json
import time

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

# 是否使用joined_channels.json中的所有频道进行监控
USE_JOINED_CHANNELS_FILE = os.environ.get('USE_JOINED_CHANNELS_FILE', 'True').lower() in ['true', '1', 'yes', 'y']

# 标题过滤设置
TITLE_FILTER = os.getenv('TITLE_FILTER', '')  # 标题过滤关键词，多个用逗号分隔，为空则不过滤
# 将TITLE_KEYWORDS设置为空列表，禁用过滤功能
TITLE_KEYWORDS = []

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
    
    # 将joined_channels.json的所有链接也添加到SOURCE_CHANNELS中
    combined_source_channels = []
    
    # 首先添加环境变量中的SOURCE_CHANNELS
    for ch in SOURCE_CHANNELS:
        if ch.strip():
            combined_source_channels.append(ch.strip())
    
    # 然后添加joined_channels.json中的链接
    for ch in joined_channel_links:
        if ch.strip() and ch.strip() not in combined_source_channels:
            combined_source_channels.append(ch.strip())
    
    # 移除重复项
    combined_source_channels = list(set(combined_source_channels))
    logger.info(f"合并后将监控 {len(combined_source_channels)} 个频道/群组")
    
    # 尝试自动加入源频道
    logger.info("尝试自动加入配置的源频道...")
    join_results = []
    raw_source_channels = []  # 存储源频道的ID或实体
    
    # 准备所有需要加入的频道列表
    channels_to_join = []
    for ch_id in combined_source_channels:
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
    
    # 注册消息处理器
    @client.on(events.NewMessage(chats=processed_source_channels))
    async def forward_messages(event):
        try:
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
            
            # 如果消息是纯文本且不包含媒体，则跳过转发
            if not has_media:
                logger.info(f"跳过纯文本消息 (ID: {message.id}) - 根据设置只转发包含媒体的消息")
                return
            
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
                # 处理媒体消息 (已经确保了消息包含媒体)
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
                except Exception as e:
                    logger.error(f"转发媒体消息 {message.id} 失败: {e}")
                
                # 转发成功后添加小延迟，模拟人类行为
                delay_after_send = random.uniform(0.8, 2.5)
                logger.info(f"消息处理完成，等待 {delay_after_send:.1f} 秒...")
                await asyncio.sleep(delay_after_send)
        except Exception as e:
            logger.error(f"处理消息时出错: {e}")
            
    # 注册编辑消息处理器
    @client.on(events.MessageEdited(chats=processed_source_channels))
    async def forward_edited_messages(event):
        try:
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
                elif isinstance(message.media, MessageMediaDocument):
                    has_media = True
            
            # 如果消息是纯文本且不包含媒体，则跳过转发
            if not has_media:
                logger.info(f"跳过编辑的纯文本消息 (ID: {message.id}) - 根据设置只转发包含媒体的消息")
                return
            
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
                await client.send_file(
                    destination_channel,
                    message.media,
                    caption=new_message,
                    parse_mode='html' if FORMAT_AS_HTML else None
                )
                logger.info(f"已转发编辑的媒体消息 (ID: {message.id}) 到目标频道")
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
    
    # 启动通知
    logger.info("高级转发机器人已启动，正在监控频道...")
    logger.info(f"监控的频道: {processed_source_channels}")
    logger.info(f"目标频道: {DESTINATION_CHANNEL}")
    
    # 保持机器人运行
    await client.run_until_disconnected()

async def handle_media_group(client, message, source_info, footer, destination_channel):
    """处理媒体组消息（多张图片/视频）"""
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
    """最终处理媒体组，发送所有媒体"""
    try:
        # 检查组是否存在
        if group_id not in media_groups:
            logger.warning(f"处理前媒体组 {group_id} 消失，可能已被处理")
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
            return
            
        # 按照ID排序，确保顺序正确
        group_messages.sort(key=lambda x: x.id)
        
        # 收集所有文本内容并合并
        all_texts = []
        for msg in group_messages:
            if msg.text and msg.text.strip():
                all_texts.append(msg.text.strip())
        
        # 去重并合并文本
        unique_texts = []
        for text in all_texts:
            if text not in unique_texts:
                unique_texts.append(text)
        
        # 构建最终标题
        caption_text = "\n\n".join(unique_texts)
        if caption_text:
            caption_text += source_info + footer
        else:
            caption_text = source_info + footer if (source_info or footer) else ""
        
        # 准备所有媒体
        media_files = []
        temp_dir = tempfile.mkdtemp()
        
        try:
            # 收集并下载所有媒体文件
            logger.info(f"开始处理来自「{chat_name}」的媒体组，共 {len(group_messages)} 条消息")
            for i, msg in enumerate(group_messages):
                if not msg.media:
                    continue
                
                try:
                    # 创建临时文件
                    file_ext = get_media_extension(msg.media)
                    temp_file = os.path.join(temp_dir, f"media_{i}{file_ext}")
                    
                    # 下载媒体
                    await client.download_media(msg.media, temp_file)
                    media_files.append(temp_file)
                    logger.info(f"已下载来自「{chat_name}」的媒体 {i+1}/{len(group_messages)}")
                except Exception as e:
                    logger.error(f"下载媒体 {i+1}/{len(group_messages)} 失败: {e}")
            
            # 检查是否有媒体
            if not media_files:
                logger.warning(f"媒体组 {group_id} 中没有可用媒体文件")
                return
                
            # 如果只有一个媒体文件，直接发送
            if len(media_files) == 1:
                try:
                    sent = await client.send_file(
                        destination_channel,
                        file=media_files[0],
                        caption=caption_text,
                        parse_mode='html' if FORMAT_AS_HTML else None
                    )
                    logger.info(f"已发送来自「{chat_name}」的单个媒体")
                    
                    # 为每个原始消息记录映射关系
                    for msg in group_messages:
                        message_key = f"{msg.chat_id}_{msg.id}"
                        messages_map[message_key] = sent.id
                except Exception as e:
                    logger.error(f"发送单个媒体失败: {e}")
                return
            
            # 作为媒体组发送
            try:
                logger.info(f"正在将 {len(media_files)} 个媒体作为一组发送（来自「{chat_name}」）")
                sent = await client.send_file(
                    entity=destination_channel,
                    file=media_files,
                    caption=caption_text,  # 标题会自动添加到最后一个媒体
                    parse_mode='html' if FORMAT_AS_HTML else None
                )
                
                # 记录映射关系
                if isinstance(sent, list):
                    # 如果返回的是消息列表，记录每个消息的映射
                    for i, original_msg in enumerate(group_messages):
                        if i < len(sent):
                            message_key = f"{original_msg.chat_id}_{original_msg.id}"
                            messages_map[message_key] = sent[i].id
                    logger.info(f"已将 {len(media_files)} 个媒体作为组发送成功（来自「{chat_name}」），生成 {len(sent)} 条消息")
                else:
                    # 如果返回单个消息，将所有原始消息映射到这一个
                    for original_msg in group_messages:
                        message_key = f"{original_msg.chat_id}_{original_msg.id}"
                        messages_map[message_key] = sent.id
                    logger.info(f"已将 {len(media_files)} 个媒体作为组发送成功（来自「{chat_name}」）")
            except Exception as e:
                logger.error(f"作为组发送媒体失败: {e}")
                
                # 如果组发送失败，尝试分别发送每个文件
                logger.info("尝试分别发送每个媒体文件...")
                success_count = 0
                
                for i, file_path in enumerate(media_files):
                    try:
                        # 只在最后一个媒体上添加标题
                        is_last = (i == len(media_files) - 1)
                        file_caption = caption_text if is_last else None
                        
                        sent = await client.send_file(
                            destination_channel,
                            file=file_path,
                            caption=file_caption,
                            parse_mode='html' if FORMAT_AS_HTML else None
                        )
                        
                        # 记录消息映射
                        if i < len(group_messages):
                            message_key = f"{group_messages[i].chat_id}_{group_messages[i].id}"
                            messages_map[message_key] = sent.id
                        
                        success_count += 1
                        logger.info(f"已单独发送第 {i+1}/{len(media_files)} 个媒体")
                        await asyncio.sleep(0.5)
                    except Exception as e2:
                        logger.error(f"单独发送媒体 {i+1} 也失败: {e2}")
                
                logger.info(f"共成功单独发送 {success_count}/{len(media_files)} 个媒体")
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
    except Exception as e:
        logger.error(f"处理媒体组出现严重错误: {e}")
        import traceback
        logger.error(traceback.format_exc())

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