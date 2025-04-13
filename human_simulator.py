#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import asyncio
import random
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from telethon.tl.functions.messages import ReadHistoryRequest
import os
import re
from datetime import datetime
import time

# 配置日志
# 使用和advanced_forwarder.py相同的日志配置
logger = logging.getLogger()

# API调用频率控制
class ApiRateLimiter:
    """API调用频率限制器，防止过于频繁的API调用触发Telegram限制"""
    
    def __init__(self):
        self.last_api_call = {}  # 记录每种API调用的最后时间
        self.consecutive_calls = {}  # 记录连续调用次数
        self.daily_call_counts = {}  # 记录每日调用次数
        self.daily_channel_calls = {}  # 记录每个频道的每日调用次数
        self.last_reset_day = datetime.now().day
        self.total_hourly_calls = 0  # 每小时总调用次数
        self.last_hour_reset = datetime.now().hour
        self.safe_mode = False  # 安全模式标志，当达到某个阈值时启用
        
    async def wait_if_needed(self, api_name, min_interval=1.5, jitter=0.5, force_wait=False, channel_id=None):
        """
        根据API调用频率决定是否需要等待
        
        参数:
            api_name: API调用名称/类型
            min_interval: 最小间隔时间(秒)
            jitter: 随机波动范围(秒)
            force_wait: 是否强制等待
            channel_id: 频道ID，用于记录每个频道的调用次数
        
        返回:
            等待的时间(秒)，如果决定跳过API调用则返回-1
        """
        # 检查是否需要重置每日计数
        current_day = datetime.now().day
        current_hour = datetime.now().hour
        
        if current_day != self.last_reset_day:
            self.daily_call_counts = {}
            self.daily_channel_calls = {}
            self.last_reset_day = current_day
            self.safe_mode = False
            logger.info("每日API计数已重置")
        
        if current_hour != self.last_hour_reset:
            self.total_hourly_calls = 0
            self.last_hour_reset = current_hour
            # 如果新的一小时开始且当前处于安全模式，有10%的几率关闭安全模式
            if self.safe_mode and random.random() < 0.1:
                self.safe_mode = False
                logger.info("安全模式已关闭，恢复正常API调用")
        
        # 获取当前时间
        now = time.time()
        
        # 初始化记录
        if api_name not in self.last_api_call:
            self.last_api_call[api_name] = now - min_interval * 2  # 确保首次调用不需要等待
            self.consecutive_calls[api_name] = 0
            self.daily_call_counts[api_name] = 0
        
        # 初始化频道记录
        if channel_id:
            if channel_id not in self.daily_channel_calls:
                self.daily_channel_calls[channel_id] = {}
            if api_name not in self.daily_channel_calls[channel_id]:
                self.daily_channel_calls[channel_id][api_name] = 0
        
        # 安全模式下抢先判断是否应该完全跳过此次API调用
        if self.safe_mode:
            # 安全模式下大幅度减少API调用
            if api_name == "send_reaction":
                return -1  # 安全模式下完全禁用点赞功能
            
            if api_name == "read_history":
                # 安全模式下只有5%的已读标记会被执行
                if random.random() > 0.05:
                    return -1
            
            # 安全模式下限制每小时的总调用次数
            if self.total_hourly_calls >= 30:  # 安全模式下每小时最多30次API调用
                logger.warning(f"安全模式下已达到每小时API调用上限，跳过 {api_name} 调用")
                return -1
        
        # 限制每个频道每种API的每日调用次数
        if channel_id:
            channel_api_limit = 20 if api_name == "read_history" else 50  # 每个频道每天最多标记已读20次
            if self.daily_channel_calls[channel_id].get(api_name, 0) >= channel_api_limit:
                logger.debug(f"频道 {channel_id} 的 {api_name} 调用已达到每日上限 {channel_api_limit}，跳过此次调用")
                return -1
        
        # 限制每种API的总每日调用次数
        api_daily_limits = {
            "read_history": 100,  # 每天最多标记已读100次
            "get_messages": 300,  # 每天最多获取消息300次
            "send_reaction": 20   # 每天最多点赞20次
        }
        
        if api_name in api_daily_limits and self.daily_call_counts[api_name] >= api_daily_limits[api_name]:
            logger.warning(f"{api_name} 已达每日调用上限 {api_daily_limits[api_name]}，跳过此次调用")
            
            # 如果已读标记达到限制，启用安全模式
            if api_name == "read_history" and not self.safe_mode:
                self.safe_mode = True
                logger.warning("已启用安全模式，将大幅减少API调用")
                
            return -1
        
        # 每小时API调用总次数限制 (所有类型API调合计)
        hourly_limit = 150  # 每小时最多150次API调用
        if self.total_hourly_calls >= hourly_limit:
            logger.warning(f"已达到每小时API调用总上限 {hourly_limit}，跳过 {api_name} 调用")
            # 达到每小时限制时也启用安全模式
            if not self.safe_mode:
                self.safe_mode = True
                logger.warning("已启用安全模式，将大幅减少API调用")
            return -1
        
        # 计算时间差
        time_since_last = now - self.last_api_call[api_name]
        
        # 更新连续调用和每日调用计数
        if time_since_last < min_interval * 2:
            self.consecutive_calls[api_name] += 1
        else:
            self.consecutive_calls[api_name] = 0
        
        self.daily_call_counts[api_name] += 1
        self.total_hourly_calls += 1
        if channel_id:
            self.daily_channel_calls[channel_id][api_name] = self.daily_channel_calls[channel_id].get(api_name, 0) + 1
        
        # 根据调用频率动态调整等待时间
        actual_interval = min_interval
        
        # 连续调用次数过多，逐渐增加等待时间
        if self.consecutive_calls[api_name] > 5:
            actual_interval += min(self.consecutive_calls[api_name] * 0.5, 10)
            logger.debug(f"连续{self.consecutive_calls[api_name]}次调用{api_name}，增加等待时间到{actual_interval:.1f}秒")
        
        # 每日调用次数过多，增加基础等待时间
        if self.daily_call_counts[api_name] > api_daily_limits.get(api_name, 500) * 0.7:
            actual_interval += 3.0
            logger.debug(f"今日已调用{api_name} {self.daily_call_counts[api_name]}次，接近上限，增加基础等待时间")
        
        # 安全模式下增加更多等待时间
        if self.safe_mode:
            actual_interval *= 1.5
            jitter *= 2
        
        # 计算需要等待的时间
        wait_time = 0
        
        if force_wait or time_since_last < actual_interval:
            # 需要等待的时间 + 随机波动
            wait_time = max(0, actual_interval - time_since_last) + random.uniform(0, jitter)
            await asyncio.sleep(wait_time)
        
        # 更新最后调用时间
        self.last_api_call[api_name] = time.time()
        
        return wait_time

# 创建全局API限速器实例
api_limiter = ApiRateLimiter()

# 决定是否执行API调用的函数
async def should_execute_api(api_name, channel_entity=None):
    """
    根据多种因素决定是否应该执行特定的API调用
    
    参数:
        api_name: API调用类型
        channel_entity: 频道实体
    
    返回:
        布尔值，表示是否应该执行此API
    """
    channel_id = getattr(channel_entity, 'id', None) if channel_entity else None
    
    # 基本几率映射 - 不同API的执行几率
    base_probability = {
        "read_history": 0.05,  # 只有5%的几率执行标记已读
        "get_messages": 0.7,   # 70%的几率执行获取消息
        "send_reaction": 0.01  # 1%的几率执行点赞
    }
    
    # 获取默认几率，如果没有特定设置则使用0.1
    prob = base_probability.get(api_name, 0.1)
    
    # 每个频道每天随机完全不调用API的几率
    if channel_id:
        # 使用频道ID作为种子以保持一天内对同一频道的一致决策
        seed = f"{channel_id}_{datetime.now().day}_{datetime.now().month}_{datetime.now().year}"
        random.seed(seed)
        if random.random() < 0.3:  # 30%的频道完全不调用API
            random.seed()  # 重置随机种子
            return False
        random.seed()  # 重置随机种子
    
    # 每天有20%的几率进入"安静模式"，大幅减少所有API调用
    quiet_day_seed = f"{datetime.now().day}_{datetime.now().month}_{datetime.now().year}"
    random.seed(quiet_day_seed)
    is_quiet_day = random.random() < 0.2
    random.seed()  # 重置随机种子
    
    if is_quiet_day:
        # 安静日减少90%的API调用
        prob *= 0.1
        logger.debug("今天是安静日，大幅减少API调用")
    
    # 最终决定是否执行
    return random.random() < prob

class HumanBehaviorSimulator:
    """模拟真实人类在Telegram上的浏览行为"""
    
    @staticmethod
    async def simulate_browsing(client, channel_entity, intensity='medium'):
        """
        模拟真实的频道内容浏览行为
        
        参数:
            client: Telethon客户端实例
            channel_entity: 频道实体
            intensity: 浏览强度 - 'light'(轻度), 'medium'(中度), 'deep'(深度)
        """
        try:
            channel_title = getattr(channel_entity, 'title', '未知频道')
            channel_id = getattr(channel_entity, 'id', None)
            logger.info(f"开始真实浏览频道: {channel_title} (ID: {channel_id})")
            
            # 检查是否是API限速器的安全模式
            if api_limiter.safe_mode:
                logger.info("当前处于API安全模式，将最小化API调用")
            
            # 检查此次访问是否应该完全不调用API，只模拟浏览行为
            no_api_visit = not await should_execute_api("any", channel_entity)
            if no_api_visit:
                logger.info(f"决定此次访问频道 {channel_title} 时不调用任何API，仅模拟浏览")
                # 模拟停留一段时间
                stay_time = random.uniform(5.0, 20.0)
                logger.info(f"模拟在频道停留 {stay_time:.1f} 秒")
                await asyncio.sleep(stay_time)
                return
            
            # 模拟人类打开频道时的初始标记操作
            try:
                # 首先检查是否应该获取最新消息
                if await should_execute_api("get_messages", channel_entity):
                    # 限制API调用频率
                    api_wait = await api_limiter.wait_if_needed("get_messages", min_interval=2.0, channel_id=channel_id)
                    
                    if api_wait >= 0:  # 如果没有被跳过
                        # 首先获取最新的一条消息ID
                        latest_msgs = await client.get_messages(channel_entity, limit=1)
                        
                        if latest_msgs and len(latest_msgs) > 0:
                            latest_id = latest_msgs[0].id
                            
                            # 模拟打开频道时的短暂停顿
                            await asyncio.sleep(random.uniform(0.7, 1.5))
                            
                            # 检查是否应该标记已读
                            if await should_execute_api("read_history", channel_entity):
                                # 初始化已读状态，标记进入频道时的可见消息
                                api_wait = await api_limiter.wait_if_needed("read_history", min_interval=3.0, jitter=1.0, channel_id=channel_id)
                                if api_wait >= 0:  # 如果没有被跳过
                                    await client(ReadHistoryRequest(
                                        peer=channel_entity,
                                        max_id=latest_id
                                    ))
                                    logger.debug(f"已初始化频道已读状态，最新消息ID: {latest_id}")
            except Exception as e:
                logger.debug(f"初始化频道已读状态失败: {e}")
            
            # 根据浏览强度决定获取消息数量，降低数量以减少API调用
            if intensity == 'light':
                message_count = random.randint(1, 3)
            elif intensity == 'medium':
                message_count = random.randint(2, 5)
            else:  # deep
                message_count = random.randint(3, 8)
            
            # 如果API调用过于频繁，降低获取的消息数量
            if api_limiter.daily_call_counts.get("get_messages", 0) > 200:
                message_count = max(1, message_count // 2)
                logger.debug(f"API调用频繁，降低获取消息数量到 {message_count}")
            
            # 模拟滚动行为：有时人们会快速滚动浏览一下全局
            if random.random() < 0.3 and intensity != 'light':
                # 快速滚动预览
                logger.info("模拟快速滚动预览频道内容...")
                await asyncio.sleep(random.uniform(1.0, 2.5))
            
            # 检查是否应该获取消息
            messages = []
            if await should_execute_api("get_messages", channel_entity):
                # 限制API调用频率
                api_wait = await api_limiter.wait_if_needed("get_messages", min_interval=2.0, channel_id=channel_id)
                if api_wait >= 0:  # 如果没有被跳过
                    # 获取一批随机数量的最近消息
                    messages = await client.get_messages(channel_entity, limit=message_count)
            
            if not messages:
                if len(messages) == 0:
                    logger.info(f"频道 {channel_title} 没有获取到消息或决定不获取，模拟浏览空频道")
                    # 模拟浏览空频道
                    empty_browse_time = random.uniform(2.0, 8.0)
                    logger.info(f"模拟浏览空频道，停留 {empty_browse_time:.1f} 秒")
                    await asyncio.sleep(empty_browse_time)
                    return
            
            logger.info(f"获取到 {len(messages)} 条消息，开始模拟阅读")
            
            # 模拟阅读过程
            for i, message in enumerate(messages):
                # 计算合适的阅读时间
                reading_time = HumanBehaviorSimulator._calculate_reading_time(message)
                logger.info(f"阅读消息 {i+1}/{len(messages)}，停留 {reading_time:.1f} 秒")
                
                # 首先暂停模拟阅读时间
                await asyncio.sleep(reading_time)
                
                # 检查是否应该标记已读
                if await should_execute_api("read_history", channel_entity):
                    try:
                        # 调用API真正将消息标记为已读
                        api_wait = await api_limiter.wait_if_needed("read_history", min_interval=3.5, jitter=1.5, channel_id=channel_id)
                        if api_wait >= 0:  # 如果没有被跳过
                            await client(ReadHistoryRequest(
                                peer=channel_entity,
                                max_id=message.id
                            ))
                            
                            # 80%的概率暂停一小段时间，模拟人类阅读完后的反应时间
                            if random.random() < 0.8:
                                await asyncio.sleep(random.uniform(0.3, 1.2))
                            
                            logger.debug(f"消息 {message.id} 已标记为已读")
                    except Exception as e:
                        logger.debug(f"标记消息为已读失败: {e}")
                
                # 检查是否应该互动（点赞）
                if intensity != 'light' and await should_execute_api("send_reaction", channel_entity):
                    try:
                        # 模拟思考时间，然后点赞
                        await asyncio.sleep(random.uniform(0.5, 2.0))
                        # 随机选择一个反应表情
                        reaction = random.choice(['👍', '❤️', '🔥', '👏', '🎉'])
                        
                        # 检查API调用频率
                        api_wait = await api_limiter.wait_if_needed("send_reaction", min_interval=5.0, jitter=2.0, channel_id=channel_id)
                        if api_wait >= 0:  # 如果没有被跳过
                            await client.send_reaction(channel_entity, message.id, reaction)
                            logger.info(f"对消息 {message.id} 进行了: {reaction}")
                            
                            # 点赞后稍作停顿
                            await asyncio.sleep(random.uniform(0.5, 1.5))
                    except Exception as e:
                        logger.debug(f"点赞失败: {e}")
                
                # 模拟浏览中的暂停
                if i > 0 and random.random() < 0.2:  # 20%的几率暂停阅读
                    pause_time = random.uniform(2.0, 8.0)
                    logger.info(f"模拟阅读中的暂停: {pause_time:.1f}秒")
                    await asyncio.sleep(pause_time)
            
            # 模拟浏览结束，可能滚动加载更多（降低概率到5%）
            if intensity != 'light' and random.random() < 0.05 and await should_execute_api("get_messages", channel_entity):
                logger.info(f"在 {channel_title} 中模拟滚动加载更多消息...")
                await asyncio.sleep(random.uniform(1.0, 3.0))
                
                # 限制API调用频率
                api_wait = await api_limiter.wait_if_needed("get_messages", min_interval=3.0, channel_id=channel_id)
                if api_wait >= 0:  # 如果没有被跳过
                    # 降低额外获取的消息数量
                    more_messages = await client.get_messages(
                        channel_entity, 
                        limit=random.randint(1, 3),  # 减少额外加载的消息数
                        offset_id=messages[-1].id
                    )
                    if more_messages:
                        logger.info(f"加载额外 {len(more_messages)} 条消息")
                        # 为简化代码，这里不再递归处理这些消息，而是简单浏览
                        avg_reading_time = sum(HumanBehaviorSimulator._calculate_reading_time(msg) * 0.6 for msg in more_messages)
                        await asyncio.sleep(avg_reading_time)
            
            # 模拟离开频道前的最后操作 - 例如回到频道顶部
            if random.random() < 0.2:  # 降低概率到20%
                logger.info("模拟返回频道顶部...")
                await asyncio.sleep(random.uniform(0.5, 1.5))
            
            logger.info(f"频道 {channel_title} 浏览完成")
            
        except Exception as e:
            logger.error(f"浏览频道过程中出错: {e}")
            # 出错时记录但不中断程序
            await asyncio.sleep(1.0)

    @staticmethod
    def _calculate_reading_time(message):
        """根据消息内容计算一个合理的阅读时间"""
        try:
            # 基础时间 1-2 秒
            base_time = random.uniform(1.0, 2.0)
            
            # 如果消息有文本，根据长度增加时间
            if hasattr(message, 'message') and message.message:
                # 平均阅读速度约为每分钟200字
                # 每个字符大约需要0.05秒
                text_length = len(message.message)
                text_time = text_length * 0.05 * random.uniform(0.8, 1.2)  # 添加一些随机性
                base_time += text_time
            
            # 如果消息包含媒体，增加查看时间
            if message.media:
                # 图片或GIF需要更多时间
                if isinstance(message.media, MessageMediaPhoto):
                    base_time += random.uniform(1.5, 4.0)
                # 文档/视频需要更长时间
                elif isinstance(message.media, MessageMediaDocument):
                    base_time += random.uniform(2.0, 7.0)
            
            # 上限控制，避免停留时间过长
            return min(base_time, 15.0)
        except Exception as e:
            logger.debug(f"计算阅读时间时出错: {e}")
            # 发生错误时返回一个随机的默认值
            return random.uniform(1.5, 3.0)

# 对外暴露的简便接口
async def simulate_human_browsing(client, channel, intensity='medium'):
    """外部调用的简便接口"""
    return await HumanBehaviorSimulator.simulate_browsing(client, channel, intensity)

async def simulate_join_behavior(client, channel):
    """模拟加入后的行为"""
    return await HumanBehaviorSimulator.simulate_browsing(client, channel) 