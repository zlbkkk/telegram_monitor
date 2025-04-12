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

# 配置日志
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

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

# 格式设置
INCLUDE_SOURCE = os.getenv('INCLUDE_SOURCE', 'False').lower() == 'true'  # 是否在转发时包含来源信息
ADD_FOOTER = os.getenv('ADD_FOOTER', 'False').lower() == 'true'  # 是否添加页脚
FOOTER_TEXT = os.getenv('FOOTER_TEXT', '由机器人自动转发')  # 页脚文本

# 标题过滤设置
TITLE_FILTER = os.getenv('TITLE_FILTER', '')  # 标题过滤关键词，多个用逗号分隔，为空则不过滤
# 将TITLE_KEYWORDS设置为空列表，禁用过滤功能
TITLE_KEYWORDS = []

# 存储媒体组的字典，键为媒体组ID，值为该组的消息列表
media_groups = {}

class HumanLikeSettings:
    # 模拟人类操作的间隔时间范围（秒）
    JOIN_DELAY_MIN = 30  # 加入频道最小延迟
    JOIN_DELAY_MAX = 50  # 加入频道最大延迟，增加延迟上限更接近人类
    
    # 有时人类会暂停很长时间，模拟上厕所、接电话等
    LONG_BREAK_CHANCE = 0.2  # 20%的几率会有一个长时间暂停
    LONG_BREAK_MIN = 60  # 长暂停最小时间（秒）
    LONG_BREAK_MAX = 90  # 长暂停最大时间（秒）
    
    # 消息转发的延迟
    FORWARD_DELAY_MIN = 2   # 消息转发最小延迟
    FORWARD_DELAY_MAX = 10  # 消息转发最大延迟
    
    # 不再跳过任何消息，确保全部转发
    SKIP_MESSAGE_CHANCE = 0.0  # 设置为0，禁用随机跳过功能
    
    # 在转发大量媒体时设置随机间隔
    MEDIA_BATCH_DELAY_MIN = 0.5
    MEDIA_BATCH_DELAY_MAX = 3.0

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
        channels_to_join.append(ch_id)
    
    # 显示准备加入的频道总数
    logger.info(f"准备加入 {len(channels_to_join)} 个频道，将模拟人类操作速度...")
    
    # 处理每个频道，添加随机延迟
    channels_processed = 0
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
                                logger.info(f"成功通过邀请链接加入: {result.chats[0].title} (ID: {channel_id})")
                                join_results.append(f"✅ 已通过邀请链接加入: {result.chats[0].title}")
                        except Exception as e1:
                            logger.error(f"第一种方式加入失败: {e1}")
                            # 如果错误是"已经是成员"，则视为成功
                            if "already a participant" in str(e1).lower():
                                logger.info("用户已是频道成员，无需重复加入")
                                success = True
                                # 直接通过链接获取频道实体
                                try:
                                    channel_entity = await client.get_entity(ch_id)
                                    channel_id = channel_entity.id
                                    logger.info(f"成功获取已加入频道的实体: {channel_entity.title} (ID: {channel_id})")
                                    join_results.append(f"✅ 已是频道成员: {channel_entity.title}")
                                except Exception as e_entity:
                                    logger.error(f"获取已加入频道实体失败: {e_entity}")
                            # 如果链接格式是+开头且尚未成功，尝试第二种方式
                            elif not success and '/+' in ch_id:
                                try:
                                    # 方式二：直接使用原始链接
                                    logger.info(f"尝试使用第二种方式加入: 使用完整链接直接获取实体")
                                    channel_entity = await client.get_entity(ch_id)
                                    if channel_entity:
                                        success = True
                                        channel_id = channel_entity.id
                                        logger.info(f"通过第二种方式成功获取频道实体: {channel_entity.title} (ID: {channel_id})")
                                        join_results.append(f"✅ 已通过第二种方式加入: {channel_entity.title}")
                                except Exception as e2:
                                    logger.error(f"第二种方式也失败了: {e2}")
                        
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
                    except Exception as e:
                        logger.error(f"无法访问私有频道ID: {invite_hash}, 错误: {e}")
                        join_results.append(f"❌ 无法访问私有频道: {ch_id}")
                elif username:
                    # 通过用户名加入公开频道
                    logger.info(f"尝试加入公开频道: @{username}")
                    try:
                        # 首先尝试获取实体
                        channel_entity = await client.get_entity(username)
                        
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
                            
                            # 使用更真实的人类浏览行为代替简单延迟
                            logger.info("开始模拟人类浏览行为...")
                            await simulate_join_behavior(client, channel_entity)
                        else:
                            logger.warning(f"加入频道失败，返回结果中没有频道信息: {username}")
                            join_results.append(f"❌ 加入失败，无法获取频道信息: {username}")
                    except Exception as e:
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
                    logger.info(f"使用修正后的ID格式成功连接频道: {channel_entity.title} (ID: {corrected_id}, Peer ID: {channel_peer})")
                    continue
                except Exception as e:
                    # 修正格式后仍然失败，继续尝试原始ID
                    logger.info(f"使用修正后的ID格式仍然失败: {e}")
            
            # 尝试获取频道实体
            channel_entity = await client.get_entity(ch_id)
            channel_peer = get_peer_id(channel_entity)
            processed_source_channels.append(channel_entity)
            logger.info(f"成功解析频道: {channel_entity.title} (ID: {ch_id}, Peer ID: {channel_peer})")
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
        logger.info(f"已连接到目标频道: {destination_channel.title if hasattr(destination_channel, 'title') else destination_channel.id}")
        
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
    
    # 注册消息处理器
    @client.on(events.NewMessage(chats=processed_source_channels))
    async def forward_messages(event):
        try:
            # 增加更详细的日志
            logger.info(f"收到来自频道 {event.chat_id} 的新消息: {event.message.id}")
            
            # 注释掉随机跳过功能，确保所有消息都被处理
            # 模拟人类行为：有小概率跳过某些消息
            # if random.random() < HumanLikeSettings.SKIP_MESSAGE_CHANCE:
            #     logger.info("模拟人类行为：随机跳过此消息")
            #     return
            
            # 模拟人类行为：增加随机延迟，像人类那样需要时间阅读消息
            reading_delay = random.uniform(HumanLikeSettings.FORWARD_DELAY_MIN, HumanLikeSettings.FORWARD_DELAY_MAX)
            logger.info(f"模拟阅读延迟: {reading_delay:.1f}秒")
            await asyncio.sleep(reading_delay)
            
            # 获取消息内容
            message = event.message
            
            # 记录消息，可能需要用于后续编辑更新
            message_key = f"{event.chat_id}_{event.message.id}"
            
            # 获取来源信息
            source_chat = await event.get_chat()
            source_info = f"\n\n来源: {source_chat.title}" if INCLUDE_SOURCE and hasattr(source_chat, 'title') else ""
            
            # 注释掉标题过滤代码，确保所有消息都被转发
            '''
            # 检查标题是否包含过滤关键词
            if TITLE_KEYWORDS and hasattr(source_chat, 'title'):
                chat_title = source_chat.title.lower()
                
                # 如果标题不包含任何一个关键词，则跳过该消息
                if not any(keyword.lower() in chat_title for keyword in TITLE_KEYWORDS):
                    logger.info(f"频道标题 '{source_chat.title}' 不包含任何指定关键词，跳过该消息")
                    return
                
                # 记录匹配情况
                matched_keywords = [keyword for keyword in TITLE_KEYWORDS if keyword.lower() in chat_title]
                logger.info(f"频道标题 '{source_chat.title}' 匹配关键词: {', '.join(matched_keywords)}")
            '''
            
            # 获取页脚
            footer = f"\n\n{FOOTER_TEXT}" if ADD_FOOTER else ""
            
            # 不再使用直接转发方式，因为会显示"Forwarded from"标记
            # 改为根据消息类型重新创建消息
            
            # 检查是否为媒体组的一部分
            if message.grouped_id:
                logger.info(f"检测到媒体组消息，组ID: {message.grouped_id}")
                await handle_media_group(client, message, source_info, footer, destination_channel)
            else:
                # 处理普通消息
                if message.media:
                    # 处理媒体消息
                    logger.info("处理媒体消息=======================================================")
                    caption = message.text if message.text else ""
                    caption = caption + source_info + footer
                    
                    # 重新发送媒体（不是转发）
                    await client.send_file(
                        destination_channel, 
                        message.media,
                        caption=caption[:1024],  # Telegram限制caption最多1024字符
                        parse_mode='md'
                    )
                    logger.info("媒体消息发送成功")
                elif message.text:
                    # 处理纯文本消息
                    logger.info("处理纯文本消息=====================================================")
                    text = message.text + source_info + footer
                    
                    # 重新发送文本（不是转发）
                    await client.send_message(
                        destination_channel,
                        text,
                        parse_mode='md',
                        link_preview=True
                    )
                    logger.info("文本消息发送成功")
                else:
                    logger.warning(f"未知消息类型，无法处理: {message}")
                
                logger.info(f"已发送消息内容（非转发）从ID {event.chat_id} 到目标频道")
        except Exception as e:
            logger.error(f"发送消息时出错: {e}")
            # 打印更详细的错误信息
            import traceback
            logger.error(traceback.format_exc())
    
    # 注册频道反应处理器（如点赞）
    @client.on(events.MessageEdited(chats=processed_source_channels))
    async def handle_edits(event):
        try:
            # 处理消息编辑
            message_key = f"{event.chat_id}_{event.message.id}"
            logger.info(f"检测到消息编辑，ID: {event.id}")
            
            # 已经注释掉随机忽略逻辑，确保所有编辑都被处理
            # if random.random() < 0.3:
            #     logger.info("模拟人类行为：忽略此编辑消息")
            #     return
            
            # 模拟阅读编辑消息的延迟
            await asyncio.sleep(random.uniform(3.0, 10.0))
            
            # TODO: 实现编辑消息的处理逻辑，确保更新已转发的消息
            # 这部分代码需要增加，以支持更新已发送的消息
        except Exception as e:
            logger.error(f"处理消息编辑时出错: {e}")
    
    # 启动通知
    logger.info("高级转发机器人已启动，正在监控频道...")
    logger.info(f"监控的频道: {processed_source_channels}")
    logger.info(f"目标频道: {DESTINATION_CHANNEL}")
    
    # 保持机器人运行
    await client.run_until_disconnected()

async def handle_media_group(client, message, source_info, footer, destination_channel):
    """处理媒体组消息（多张图片/视频）"""
    
    # 为每个媒体组ID创建一个列表
    if message.grouped_id not in media_groups:
        media_groups[message.grouped_id] = []
    
    # 将当前消息添加到组中
    media_groups[message.grouped_id].append(message)
    
    # 等待更长时间，确保收集到媒体组的所有消息
    # 这是因为Telegram发送媒体组时，消息可能不会同时到达
    await asyncio.sleep(2)
    
    # 创建任务处理媒体组
    asyncio.create_task(process_media_group_delayed(client, message.grouped_id, source_info, footer, destination_channel))

async def process_media_group_delayed(client, grouped_id, source_info, footer, destination_channel):
    """延迟处理媒体组，确保收集到所有消息"""
    
    # 再等待一段时间，确保收集到所有媒体
    await asyncio.sleep(3)
    
    # 检查该媒体组是否存在
    if grouped_id not in media_groups:
        logger.warning(f"找不到媒体组 {grouped_id}，可能已被处理")
        return
    
    # 获取该组的所有消息并从字典中移除(避免重复处理)
    group_messages = media_groups.pop(grouped_id)
    
    if not group_messages:
        logger.warning(f"媒体组 {grouped_id} 中没有消息")
        return
        
    # 记录找到的消息数量
    logger.info(f"媒体组 {grouped_id} 收集到 {len(group_messages)} 条消息")
    
    # 按照ID排序，确保顺序正确
    group_messages.sort(key=lambda x: x.id)
    
    # 获取消息的标题
    caption_text = ""
    for msg in group_messages:
        if msg.text:
            caption_text = msg.text + source_info + footer
            break
    
    # 筛选出包含媒体的消息
    media_messages = [msg for msg in group_messages if msg.media]
    
    # 如果没有媒体消息，直接返回
    if not media_messages:
        logger.warning("没有找到媒体消息")
        return
        
    # 如果只有一个媒体，直接发送
    if len(media_messages) == 1:
        try:
            msg = media_messages[0]
            await client.send_file(
                destination_channel,
                file=msg.media,
                caption=caption_text[:1024] if caption_text else None,
                parse_mode='md',
                force_document=False
            )
            logger.info("单个媒体已发送")
        except Exception as e:
            logger.error(f"单个媒体发送失败: {e}")
        return
    
    try:
        logger.info(f"开始处理媒体组，共 {len(media_messages)} 个媒体")
        
        # 我们直接将所有媒体重新发送为一个群组，使用备用方法
        # 首先需要获取所有原始媒体文件
        media_files = []
        
        for i, msg in enumerate(media_messages):
            try:
                # 下载媒体到临时文件
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=get_media_extension(msg.media))
                temp_path = temp_file.name
                temp_file.close()
                
                # 下载媒体
                await client.download_media(msg.media, temp_path)
                media_files.append(temp_path)
                logger.info(f"已下载第 {i+1}/{len(media_messages)} 个媒体")
            except Exception as e:
                logger.error(f"下载媒体 {i+1} 失败: {e}")
        
        # 把所有媒体作为组发送
        if media_files:
            try:
                # 将所有媒体文件作为一组发送
                # 注意：在这里我们指定caption_text只在最后一个媒体上显示
                logger.info(f"正在发送 {len(media_files)} 个媒体文件到目标频道...")
                
                # 明确指定参数，确保媒体组正确发送
                await client.send_file(
                    entity=destination_channel,
                    file=media_files,
                    caption=caption_text[:1024] if caption_text else None,
                    parse_mode='md',
                    force_document=False,  # 确保显示为媒体而非文件附件
                    supports_streaming=True  # 支持视频流媒体播放
                )
                logger.info(f"已将 {len(media_files)} 个媒体作为一组发送成功")
            except Exception as e:
                logger.error(f"发送媒体组时出错: {e}")
                raise  # 将错误传递给外层的异常处理
        else:
            logger.warning("没有可用的媒体文件可发送")
        
        # 清理临时文件
        for file_path in media_files:
            try:
                os.unlink(file_path)
            except:
                pass
        
        logger.info("临时文件已清理")
        logger.info(f"媒体组处理完成，共处理 {len(media_messages)} 个媒体")
    except Exception as e:
        # 如果组发送失败，尝试一个一个发送
        logger.error(f"作为组发送媒体失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        try:
            logger.info("尝试单独发送每个媒体...")
            
            # 前面的媒体无文字说明
            for i, path in enumerate(media_files[:-1]):
                if os.path.exists(path):
                    await client.send_file(
                        entity=destination_channel,
                        file=path,
                        force_document=False,  # 确保显示为媒体而非文件附件
                        supports_streaming=True  # 支持视频流媒体播放
                    )
                    logger.info(f"已单独发送第 {i+1}/{len(media_files)} 个媒体")
                    # 每发送一个媒体后短暂暂停，避免API速率限制
                    await asyncio.sleep(0.5)
            
            # 最后一个媒体带文字说明
            if media_files and os.path.exists(media_files[-1]):
                await client.send_file(
                    entity=destination_channel,
                    file=media_files[-1],
                    caption=caption_text[:1024] if caption_text else None,
                    parse_mode='md',
                    force_document=False,  # 确保显示为媒体而非文件附件
                    supports_streaming=True  # 支持视频流媒体播放
                )
                logger.info("已单独发送最后一个媒体（带文字说明）")
            
            # 清理临时文件
            for file_path in media_files:
                try:
                    os.unlink(file_path)
                except:
                    pass
            
            logger.info("备用方法发送成功，临时文件已清理")
        except Exception as e2:
            logger.error(f"单独发送也失败: {e2}")
            logger.error(traceback.format_exc())
            
            # 清理临时文件
            for file_path in media_files:
                try:
                    os.unlink(file_path)
                except:
                    pass

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
    return ''  # 如果无法确定类型，返回空字符串

if __name__ == '__main__':
    asyncio.run(main()) 