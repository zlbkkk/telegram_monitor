#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
人类行为模拟模块 (Human Behavior Simulator)

本模块用于模拟人类在 Telegram 中的真实浏览行为，使脚本操作看起来更像真人。
包含以下主要功能：
1. 模拟真实的内容浏览行为（阅读时间基于内容长度和类型动态调整）
2. 模拟随机点赞和互动行为（根据设定的强度随机进行）
3. 模拟加入频道后的典型浏览模式
4. 模拟人类对不同内容类型的不同关注时间

使用方法:
    from human_simulator import simulate_join_behavior, simulate_human_browsing
    
    # 模拟加入频道后的浏览行为
    await simulate_join_behavior(client, channel_entity)
    
    # 模拟人类浏览行为，强度可选: 'light', 'medium', 'deep'
    await simulate_human_browsing(client, channel_entity, intensity='medium')

注意:
- 该模块依赖于 Telethon 库
- 浏览强度会影响互动程度和浏览深度
- 所有操作都有随机延迟和行为模式，模拟真实性
- 该模块不会修改或删除任何内容，仅执行读取和反应操作

作者: Claude AI Assistant
版本: 1.0
日期: 2024-04-12
"""

import logging
import asyncio
import random
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument

# 配置日志
logger = logging.getLogger(__name__)

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
            logger.info(f"开始真实浏览频道: {channel_title}")
            
            # 根据浏览强度决定获取消息数量
            if intensity == 'light':
                message_count = random.randint(3, 5)
            elif intensity == 'medium':
                message_count = random.randint(5, 15)
            else:  # deep
                message_count = random.randint(10, 25)
                
            # 获取一批随机数量的最近消息
            messages = await client.get_messages(channel_entity, limit=message_count)
            
            if not messages:
                logger.info(f"频道 {channel_title} 没有可浏览的消息")
                return
                
            logger.info(f"获取到 {len(messages)} 条消息，开始模拟阅读")
            
            # 模拟阅读过程
            for i, message in enumerate(messages):
                # 计算合适的阅读时间
                reading_time = HumanBehaviorSimulator._calculate_reading_time(message)
                logger.info(f"阅读消息 {i+1}/{len(messages)}，停留 {reading_time:.1f} 秒")
                await asyncio.sleep(reading_time)
                
                # 随机互动 - 仅对中度和深度浏览进行
                if intensity != 'light' and random.random() < 0.5:  # 5%几率点赞
                    try:
                        # 模拟思考时间，然后点赞
                        await asyncio.sleep(random.uniform(0.5, 2.0))
                        # 随机选择一个反应表情
                        reaction = random.choice(['👍', '❤️', '🔥', '👏', '🎉'])
                        await client.send_reaction(channel_entity, message.id, reaction)
                        logger.info(f"对消息 {message.id} 进行了: {reaction}")
                        
                        # 点赞后稍作停顿
                        await asyncio.sleep(random.uniform(0.5, 1.5))
                    except Exception as e:
                        logger.debug(f"点赞失败: {e}")
                
                # 深度浏览时，极少数情况下模拟保存媒体
                if intensity == 'deep' and message.media and random.random() < 0.01:  # 1%几率保存媒体
                    try:
                        # 模拟查看媒体的额外时间
                        await asyncio.sleep(random.uniform(1.0, 3.0))
                        # 注意：这里仅模拟行为，不实际下载
                        logger.info(f"模拟保存媒体消息 {message.id}")
                        await asyncio.sleep(random.uniform(0.5, 2.0))
                    except Exception as e:
                        logger.debug(f"保存媒体操作模拟失败: {e}")
            
            # 模拟浏览结束，可能滚动加载更多
            if intensity != 'light' and random.random() < 0.3:  # 30%几率继续浏览更多
                logger.info(f"在 {channel_title} 中模拟滚动加载更多消息...")
                await asyncio.sleep(random.uniform(1.0, 3.0))
                # 获取更多消息并继续浏览
                more_messages = await client.get_messages(
                    channel_entity, 
                    limit=random.randint(3, 8),
                    offset_id=messages[-1].id
                )
                if more_messages:
                    logger.info(f"加载额外 {len(more_messages)} 条消息")
                    # 为简化代码，这里不再递归处理这些消息，而是简单浏览
                    avg_reading_time = sum(HumanBehaviorSimulator._calculate_reading_time(msg) * 0.6 for msg in more_messages)
                    await asyncio.sleep(avg_reading_time)
            
            logger.info(f"频道 {channel_title} 浏览完成")
            
        except Exception as e:
            logger.error(f"浏览频道过程中出错: {e}")
            # 出错时记录但不中断程序
            await asyncio.sleep(1.0)
    
    @staticmethod
    def _calculate_reading_time(message):
        """计算消息的合理阅读时间"""
        base_time = random.uniform(1.5, 4.0)  # 基础浏览时间
        
        # 文字内容：根据长度增加时间
        if message.text:
            # 每100个字符增加0.5-2秒阅读时间
            text_length = len(message.text)
            text_time = (text_length / 100) * random.uniform(0.5, 2.0)
            base_time += min(text_time, 8.0)  # 最多增加8秒
        
        # 媒体内容：增加查看时间
        if message.media:
            if isinstance(message.media, MessageMediaPhoto):
                base_time += random.uniform(2.0, 6.0)  # 图片需要2-6秒额外时间
            elif isinstance(message.media, MessageMediaDocument):
                # 视频或文件需要更长时间
                if hasattr(message.media, 'document') and hasattr(message.media.document, 'mime_type'):
                    if 'video' in message.media.document.mime_type:
                        base_time += random.uniform(5.0, 15.0)  # 视频需要5-15秒
                    else:
                        base_time += random.uniform(1.0, 4.0)  # 其他文档1-4秒
        
        return min(base_time, 20.0)  # 单条消息最多浏览20秒
    
    @staticmethod
    async def simulate_join_and_browse(client, channel_entity, browse_intensity='light'):
        """模拟加入频道后的浏览行为，包括加入前查看和加入后浏览"""
        try:
            # 1. 模拟查看频道信息
            await asyncio.sleep(random.uniform(2.0, 5.0))
            
            # 2. 进行频道浏览
            await HumanBehaviorSimulator.simulate_browsing(client, channel_entity, browse_intensity)
            
            return True
        except Exception as e:
            logger.error(f"模拟加入和浏览过程中出错: {e}")
            return False

# 对外暴露的简便接口
async def simulate_human_browsing(client, channel, intensity='medium'):
    """外部调用的简便接口"""
    return await HumanBehaviorSimulator.simulate_browsing(client, channel, intensity)

async def simulate_join_behavior(client, channel):
    """模拟加入后的行为"""
    return await HumanBehaviorSimulator.simulate_join_and_browse(client, channel) 