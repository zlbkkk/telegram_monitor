#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import logging
import asyncio
import random
import json
import re
from datetime import datetime
from dotenv import load_dotenv
from telethon import TelegramClient, events, functions, types
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument, PeerChannel
from telethon.utils import get_peer_id
import tempfile
import time

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

# 频道信息 - 新增单独的配置项，如果没有则使用原来的配置
SOURCE_GROUPS = os.getenv('SOURCE_GROUPS', os.getenv('SOURCE_CHANNELS', '')).split(',')
DESTINATION_GROUP = os.getenv('DESTINATION_GROUP', os.getenv('DESTINATION_CHANNEL', ''))

# 模式设置
USE_FORWARD = os.getenv('USE_FORWARD', 'False').lower() == 'true'  # 是否使用转发模式
FORWARD_HIDE_SENDER = os.getenv('FORWARD_HIDE_SENDER', 'True').lower() == 'true'  # 转发时是否隐藏原始发送者

# 模拟用户配置
DEFAULT_USERS_FILE = "fake_users.json"
USERS_FILE = os.getenv('USERS_FILE', DEFAULT_USERS_FILE)
MAX_USERS = int(os.getenv('MAX_USERS', '20'))  # 最多模拟多少个不同的用户

# 辅助函数：从链接中提取ID或用户名
def extract_identifier_from_link(link):
    """从Telegram链接中提取ID或用户名"""
    # 处理t.me/+XXXX格式的链接 (私有群组邀请链接)
    if '/+' in link:
        return link.split('/+', 1)[1].strip()
    
    # 处理t.me/joinchat/XXXX格式的链接
    if '/joinchat/' in link:
        return link.split('/joinchat/', 1)[1].strip()
        
    # 处理https://t.me/c/XXXX格式（私有群组直接链接）
    if '/c/' in link:
        try:
            parts = link.split('/c/', 1)[1].strip().split('/')
            if parts and parts[0].isdigit():
                return int(f"-100{parts[0]}")
        except:
            pass
            
    # 处理t.me/username格式的公开群组/频道链接
    link = link.replace('https://', '').replace('http://', '')
    if 't.me/' in link and '/+' not in link and '/joinchat/' not in link and '/c/' not in link:
        username = link.split('t.me/', 1)[1].strip()
        # 移除额外的路径部分
        if '/' in username:
            username = username.split('/', 1)[0]
        return username
            
    return link

# 生成随机用户资料
def load_or_create_users():
    """加载或创建模拟用户资料"""
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"读取用户数据文件失败: {e}")
    
    # 创建随机用户
    # 中文名字组合
    first_names = ["小明", "小红", "小刚", "小丽", "小花", "大壮", "小芳", "小白", "小黑", "大鹏", 
                   "晓东", "思思", "亦菲", "欣怡", "文轩", "宇轩", "子涵", "佳怡", "梓萱", "思源"]
    last_names = ["王", "李", "张", "刘", "陈", "杨", "赵", "黄", "周", "吴", 
                  "徐", "孙", "马", "朱", "胡", "林", "郭", "何", "高", "罗"]
    
    # 常见职业
    professions = ["程序员", "设计师", "医生", "教师", "工程师", "学生", "作家", "科研人员",
                  "营销专员", "客服", "销售", "产品经理", "CEO", "律师", "会计师", "自由职业者"]
    
    # 创建随机用户
    users = []
    for i in range(MAX_USERS):
        first_name = random.choice(first_names)
        last_name = random.choice(last_names)
        
        # 生成随机的用户信息
        user = {
            "id": i + 1,
            "first_name": first_name,
            "last_name": last_name,
            "full_name": f"{last_name}{first_name}",
            "username": f"user_{i+1}",
            "profession": random.choice(professions),
            "color": f"#{random.randint(0, 255):02x}{random.randint(0, 255):02x}{random.randint(0, 255):02x}",
            "emoji": random.choice(["😊", "😎", "🤔", "👍", "❤️", "😄", "🎉", "🌟", "💡", "🔥"])
        }
        users.append(user)
    
    # 保存用户数据
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存用户数据文件失败: {e}")
    
    return users

# 替换消息中的链接为可点击的HTML格式
def process_links_in_text(text):
    """处理文本中的URL链接，将其转换为HTML格式的可点击链接"""
    # 匹配URL的正则表达式
    url_pattern = r'(https?://[^\s]+)'
    
    # 将URL替换为HTML链接标签
    return re.sub(url_pattern, r'<a href="\1">\1</a>', text)

async def main():
    # 创建用户客户端
    try:
        if SESSION and SESSION.strip():
            # 尝试使用已有会话
            client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
            logger.info("使用已有会话登录...")
        else:
            # 创建新会话
            client = TelegramClient(StringSession(), API_ID, API_HASH)
            logger.info("首次运行，需要验证登录...")
    except ValueError:
        # SESSION字符串无效
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        logger.info("会话字符串无效，创建新会话...")
    
    try:
        # 启动客户端
        await client.start(phone=lambda: input('请输入手机号 (格式: +86xxxxxxxxxx): '))
        logger.info("登录成功!")
        
        # 输出当前用户信息
        me = await client.get_me()
        logger.info(f"当前登录账号: {me.first_name} {me.last_name if me.last_name else ''} (@{me.username if me.username else '无用户名'})")
        
        # 生成会话字符串
        session_string = client.session.save()
        
        # 如果是新会话或会话已更改，保存到.env文件
        if not SESSION or session_string != SESSION:
            logger.info("生成新的会话字符串...")
            
            # 更新.env文件
            try:
                env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
                with open(env_path, 'r', encoding='utf-8') as file:
                    lines = file.readlines()
                
                updated = False
                for i, line in enumerate(lines):
                    if line.strip().startswith('USER_SESSION='):
                        lines[i] = f'USER_SESSION={session_string}\n'
                        updated = True
                        break
                
                if not updated:
                    lines.append(f'USER_SESSION={session_string}\n')
                
                with open(env_path, 'w', encoding='utf-8') as file:
                    file.writelines(lines)
                
                logger.info("SESSION已保存到.env文件")
            except Exception as e:
                logger.error(f"保存SESSION到.env文件失败: {e}")
                logger.info(f"请手动将SESSION字符串添加到.env文件: {session_string}")
    except Exception as e:
        logger.error(f"登录过程出错: {e}")
        return
    
    # 加载模拟用户
    fake_users = load_or_create_users()
    logger.info(f"已加载 {len(fake_users)} 个模拟用户")
    
    logger.info(f"即将处理源群组: {SOURCE_GROUPS}")
    
    # 解析和验证群组
    source_groups = []
    for group in SOURCE_GROUPS:
        group = group.strip()
        if not group:
            continue
        
        logger.info(f"正在处理群组: {group}")
        
        try:
            # 处理链接或ID
            group_id = extract_identifier_from_link(group)
            logger.info(f"提取的群组标识符: {group_id}")
            entity = None
            
            # 尝试获取群组实体
            try:
                entity = await client.get_entity(group_id)
                logger.info(f"成功获取群组实体: {entity.title if hasattr(entity, 'title') else group_id} (ID: {entity.id})")
                
                # 检查是否为超级群组或频道
                is_channel = hasattr(entity, 'megagroup') or hasattr(entity, 'broadcast')
                logger.info(f"群组类型: {'超级群组/频道' if is_channel else '普通群组'}")
                
                source_groups.append(entity)
                logger.info(f"已将群组添加到监控列表: {entity.title}")
            except Exception as e:
                logger.error(f"无法获取群组 {group_id} 的实体: {e}")
                
                # 检查是否是格式问题
                if isinstance(group_id, str) and not group_id.startswith('-100') and group_id.isdigit() and len(group_id) > 6:
                    corrected_id = int(f"-100{group_id}")
                    logger.info(f"尝试修正群组ID格式: {group_id} -> {corrected_id}")
                    try:
                        entity = await client.get_entity(corrected_id)
                        logger.info(f"使用修正后的ID成功获取群组: {entity.title}")
                        source_groups.append(entity)
                        continue
                    except Exception as e_corrected:
                        logger.error(f"使用修正后的ID仍然失败: {e_corrected}")
                
                # 尝试加入群组
                try:
                    if isinstance(group_id, str) and (group_id.startswith('+') or '/joinchat/' in group):
                        # 处理私有群组邀请链接
                        invite_hash = group_id.replace('+', '')
                        if '/joinchat/' in invite_hash:
                            invite_hash = invite_hash.split('/joinchat/', 1)[1]
                        
                        logger.info(f"尝试通过邀请哈希加入私有群组: {invite_hash}")
                        result = await client(functions.messages.ImportChatInviteRequest(
                            hash=invite_hash
                        ))
                        if result and result.chats:
                            logger.info(f"成功加入私有群组: {result.chats[0].title} (ID: {result.chats[0].id})")
                            source_groups.append(result.chats[0])
                    elif isinstance(group_id, str) and not group_id.isdigit():
                        # 处理公开群组用户名
                        logger.info(f"尝试通过用户名加入公开群组: {group_id}")
                        result = await client(functions.channels.JoinChannelRequest(
                            channel=group_id
                        ))
                        if result and result.chats:
                            logger.info(f"成功加入公开群组: {result.chats[0].title} (ID: {result.chats[0].id})")
                            source_groups.append(result.chats[0])
                    else:
                        # 尝试直接使用ID加入
                        try:
                            channel_id = int(group_id)
                            logger.info(f"尝试通过ID加入群组: {channel_id}")
                            result = await client(functions.channels.JoinChannelRequest(
                                channel=channel_id
                            ))
                            if result and result.chats:
                                logger.info(f"成功通过ID加入群组: {result.chats[0].title} (ID: {result.chats[0].id})")
                                source_groups.append(result.chats[0])
                        except ValueError:
                            logger.error(f"无法将 {group_id} 转换为整数 ID")
                except Exception as join_err:
                    logger.error(f"加入群组 {group_id} 失败: {join_err}")
                    logger.warning(f"请手动加入群组 {group_id} 后再尝试")
                    
        except Exception as e:
            logger.error(f"处理群组 {group} 时出错: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    if not source_groups:
        logger.error("没有有效的源群组，程序将退出")
        return
    
    # 获取目标群组
    destination_group = None
    try:
        # 处理链接或ID
        dest_id = extract_identifier_from_link(DESTINATION_GROUP)
        logger.info(f"目标群组标识符: {dest_id}")
        
        try:
            destination_group = await client.get_entity(dest_id)
            logger.info(f"已连接到目标群组: {destination_group.title if hasattr(destination_group, 'title') else dest_id} (ID: {destination_group.id})")
            
            # 检查是否有发送消息的权限
            try:
                permissions = await client.get_permissions(destination_group)
                # 安全地检查权限，避免属性错误
                can_send = True  # 默认假设可以发送
                
                # 尝试不同的权限检查方法
                if hasattr(permissions, 'banned_rights') and hasattr(permissions.banned_rights, 'send_messages'):
                    can_send = not permissions.banned_rights.send_messages
                elif hasattr(permissions, 'send_messages'):
                    can_send = permissions.send_messages
                
                logger.info(f"目标群组发送权限检查结果: {can_send}")
                
                if not can_send:
                    logger.warning("警告: 权限检查显示您可能没有在目标群组发送消息的权限，但我们仍会尝试发送")
            except Exception as perm_error:
                logger.warning(f"权限检查失败，但将继续尝试发送消息: {perm_error}")
                logger.info("忽略权限检查错误，继续运行")
                
            # 发送测试消息
            try:
                test_user = random.choice(fake_users)
                test_message = f"""<b>{test_user['emoji']} {test_user['full_name']}</b> <i>({test_user['profession']})</i>
                
多人聊天模拟器已启动！现在开始监控源群组的消息..."""
                
                try:
                    await client.send_message(
                        entity=destination_group,
                        message=test_message,
                        parse_mode='html'
                    )
                    logger.info("已发送测试消息到目标群组")
                except Exception as e:
                    logger.error(f"发送测试消息到目标群组失败: {e}")
                    logger.warning("测试消息发送失败，但程序将继续运行")
            except Exception as e:
                logger.error(f"测试消息准备失败: {e}")
                logger.warning("继续执行程序")
        except Exception as e:
            logger.error(f"无法获取目标群组: {e}")
            logger.error("请确保:")
            logger.error("1. 您已经加入了目标群组")
            logger.error("2. 群组ID或链接正确")
            logger.error("3. 您在目标群组有发送消息的权限")
            
            # 尝试使用原始ID作为备选
            logger.warning(f"尝试使用原始ID/链接作为目标群组: {DESTINATION_GROUP}")
            destination_group = DESTINATION_GROUP
    except Exception as e:
        logger.error(f"处理目标群组时出错: {e}")
        logger.warning(f"尝试使用原始ID/链接作为目标群组: {DESTINATION_GROUP}")
        destination_group = DESTINATION_GROUP
    
    if not destination_group:
        logger.error("无法获取目标群组，程序将退出")
        return
    
    # 添加一个专门针对源群组的监听器
    source_group_ids = []
    for source in source_groups:
        if hasattr(source, 'id'):
            source_id = source.id
            # 确保ID格式正确（添加-100前缀如果需要）
            if str(source_id).isdigit() and len(str(source_id)) > 5:
                source_id = int(f"-100{source_id}")
                logger.info(f"添加修正后的源群组ID: {source_id}")
            source_group_ids.append(source_id)
            logger.info(f"添加源群组监听: {source_id}")
    
    logger.info(f"将监听以下源群组IDs: {source_group_ids}")
    
    # 添加专门监听源群组的处理器
    @client.on(events.NewMessage(chats=source_group_ids))
    async def handle_source_group_messages(event):
        try:
            # 获取消息
            message = event.message
            chat_id = event.chat_id
            
            # 记录详细信息
            logger.info(f"💬 源群组消息处理器收到新消息 - ID: {message.id}, 来自: {chat_id}")
            logger.info(f"💬 消息内容: {message.text if message.text else '(无文本)'}")
            
            # 获取消息来源信息
            chat = await event.get_chat()
            chat_title = chat.title if hasattr(chat, 'title') else f"群组 {chat_id}"
            
            # 随机选择一个虚拟用户
            user = random.choice(fake_users)
            
            logger.info(f"💬 选择模拟用户: {user['full_name']}")
            
            # 根据设置决定是转发原消息还是复制发送
            if USE_FORWARD:
                # 使用真实转发功能
                try:
                    logger.info(f"🔄 使用真实转发功能将消息从源群组转发到目标群组")
                    
                    # 转发消息，可选是否隐藏原始发送者
                    result = await client.forward_messages(
                        entity=destination_group,
                        messages=message.id,
                        from_peer=chat_id,
                        silent=False,
                        hide_via=FORWARD_HIDE_SENDER
                    )
                    logger.info(f"✅ 成功转发消息: {result.id}")
                    
                    # 可选：发送一条额外消息表明来源群组
                    source_note = f"<i>👆 以上消息来自群组: {chat_title}</i>"
                    await client.send_message(
                        entity=destination_group,
                        message=source_note,
                        parse_mode='html'
                    )
                    
                except Exception as e:
                    logger.error(f"❌ 转发消息失败: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    
                    # 转发失败时尝试使用复制方式
                    logger.info("尝试使用复制方式作为备选")
                    # 构建消息并转发（使用原来的复制方式）
                    if message.text:
                        # 处理文本消息
                        text = message.text
                        # 处理链接使其可点击
                        text = process_links_in_text(text)
                        
                        # 改进：使用消息引用格式，让消息看起来像是转发自其他用户
                        formatted_message = f"""<b>转发消息:</b>

<blockquote>
<b>{user['emoji']} {user['full_name']}</b> <i>({user['profession']})</i>

{text}
</blockquote>

<i>来自群组: {chat_title}</i>"""
                        
                        await client.send_message(
                            entity=destination_group,
                            message=formatted_message,
                            parse_mode='html',
                            link_preview=True
                        )
            else:
                # 使用原来的复制方式，但使用引用格式
                if message.text:
                    # 处理文本消息
                    text = message.text
                    # 处理链接使其可点击
                    text = process_links_in_text(text)
                    
                    # 改进：使用消息引用格式，让消息看起来像是转发自其他用户
                    formatted_message = f"""<b>转发消息:</b>

<blockquote>
<b>{user['emoji']} {user['full_name']}</b> <i>({user['profession']})</i>

{text}
</blockquote>

<i>来自群组: {chat_title}</i>"""
                    
                    try:
                        logger.info(f"🔄 开始复制转发文本消息到目标群组: {destination_group}")
                        result = await client.send_message(
                            entity=destination_group,
                            message=formatted_message,
                            parse_mode='html',
                            link_preview=True
                        )
                        logger.info(f"✅ 成功复制转发文本消息: {result.id}")
                    except Exception as e:
                        logger.error(f"❌ 复制转发消息失败: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
                    
                elif message.media:
                    # 媒体消息处理...
                    caption = message.text if message.text else ""
                    caption = process_links_in_text(caption)
                    
                    # 改进：使用消息引用格式，让消息看起来像是转发自其他用户
                    formatted_caption = f"""<b>转发消息:</b>

<blockquote>
<b>{user['emoji']} {user['full_name']}</b> <i>({user['profession']})</i>

{caption}
</blockquote>

<i>来自群组: {chat_title}</i>"""
                    
                    try:
                        logger.info(f"🔄 开始复制转发媒体消息到目标群组")
                        await client.send_file(
                            entity=destination_group,
                            file=message.media,
                            caption=formatted_caption[:1024],
                            parse_mode='html'
                        )
                        logger.info(f"✅ 成功复制转发媒体消息")
                    except Exception as e:
                        logger.error(f"❌ 复制转发媒体消息失败: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
                
                # 在消息之间添加随机延迟，使其看起来更自然
                delay = random.uniform(0.5, 2.0)
                await asyncio.sleep(delay)
            
        except Exception as e:
            logger.error(f"专门处理器处理消息错误: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    # 修复目标群组ID格式
    if isinstance(destination_group, (int, str)) and str(destination_group).isdigit() and len(str(destination_group)) > 5:
        # 对于数字ID，添加-100前缀
        corrected_destination = int(f"-100{destination_group}")
        logger.info(f"修正目标群组ID格式: {destination_group} -> {corrected_destination}")
        destination_group = corrected_destination
    
    logger.info(f"最终使用的目标群组: {destination_group}")
    
    # 监听原始事件流，确保所有消息都被捕获
    @client.on(events.Raw)
    async def debug_raw_events(event):
        try:
            # 记录原始事件类型
            event_name = type(event).__name__
            logger.info(f"接收到原始事件: {event_name}")
            
            # 尝试提取消息ID和聊天ID
            if hasattr(event, 'message'):
                logger.info(f"原始事件包含消息 - ID: {event.message.id if hasattr(event.message, 'id') else 'unknown'}")
                
                # 检查是否来自源群组
                if hasattr(event, 'chat_id'):
                    chat_id = event.chat_id
                    # 检查是否是来自源群组的消息
                    for source in source_groups:
                        if hasattr(source, 'id') and chat_id == source.id:
                            logger.info(f"原始事件确认来自源群组: {source.id}")
                            break
        except Exception as e:
            # 忽略错误，不影响主要功能
            pass
    
    # 启动通知
    logger.info("=========================================")
    logger.info("          多人聊天模拟器已启动           ")
    logger.info("=========================================")
    
    for group in source_groups:
        group_info = f"{group.title if hasattr(group, 'title') else group} (ID: {group.id if hasattr(group, 'id') else 'unknown'})"
        logger.info(f"正在监控群组: {group_info}")
    
    # 发送测试消息到源群组
    try:
        # 使用try-except确保即使发送测试消息失败也不会阻塞程序
        try:
            test_message = "这是一条测试消息，用于验证监听功能是否正常工作。如果您能在目标群组看到由虚拟用户转发的此消息，说明系统运行正常。"
            
            # 只给第一个源群组发送测试消息
            if source_groups:
                first_group = source_groups[0]
                logger.info(f"尝试发送测试消息到首个源群组: {first_group.title if hasattr(first_group, 'title') else first_group}")
                
                await client.send_message(entity=first_group, message=test_message)
                logger.info(f"已发送测试消息到源群组")
                logger.info("如果系统正常工作，您应该会看到此消息被转发到目标群组")
        except Exception as e:
            logger.error(f"发送测试消息到源群组失败: {e}")
            logger.warning("无法发送测试消息到源群组，但程序将继续运行")
    except Exception as e:
        logger.error(f"测试消息处理过程中出错: {e}")
    
    logger.info("开始监听消息...")
    logger.info("提示: 请在源群组中发送消息，系统将尝试转发到目标群组")
    
    # 保持客户端运行
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main()) 