# Telegram 频道转发工具

这是一个基于用户账户的 Telegram 频道内容自动转发工具，可以将一个或多个源频道的消息自动转发到目标频道。

## 使用前提

要使用此转发工具，您需要满足以下条件：

1. **拥有 Telegram 用户账号**（非机器人账号）
2. **使用此账号加入源频道**（您想监控的频道）- 程序将尝试自动加入配置的源频道
3. **使用此账号加入目标频道**（您想转发消息到的频道）
4. **在目标频道拥有发送消息的权限**

## 安装步骤

1. 确保安装了 Python 3.7 或更高版本
2. 安装必要的依赖：
   ```
   pip install telethon python-dotenv
   ```
3. 获取 Telegram API 凭证：
   - 访问 https://my.telegram.org/auth
   - 登录后点击 "API development tools"
   - 创建一个新应用（可填写任意名称和描述）
   - 记下 `API_ID` 和 `API_HASH` 值

4. 复制 `.env.example` 文件为 `.env`，并填写以下信息：
   - API_ID：您从 my.telegram.org 获取的 API ID
   - API_HASH：您从 my.telegram.org 获取的 API Hash
   - SOURCE_CHANNELS：要监控的源频道 ID，多个用逗号分隔
   - DESTINATION_CHANNEL：目标频道 ID
   - TITLE_FILTER：频道标题过滤关键词，多个关键词用逗号分隔（可选）

## 新功能：自动加入频道

程序启动时，会尝试自动加入您在 SOURCE_CHANNELS 中配置的所有频道，这样可以省去手动加入每个频道的步骤。

### 支持的频道格式

现在SOURCE_CHANNELS支持以下格式的输入:

1. **频道ID**: 直接输入频道ID，如 `-1001234567890`
2. **频道链接**: 可以直接输入各种格式的频道链接，包括:
   - 公开频道链接: `t.me/channelname` 或 `https://t.me/channelname`
   - 私有频道邀请链接: `t.me/+ABCDEFG` 或 `https://t.me/joinchat/ABCDEFG`
   - 私有频道内容链接: `https://t.me/c/1234567890/123`

例如，您可以在 `.env` 文件中这样配置:
```
SOURCE_CHANNELS=-1001234567890,https://t.me/channelname,https://t.me/+ABCDEFG
```

### 自动加入流程

1. 程序会检查您的账号是否已加入各个源频道
2. 对于未加入的频道:
   - 对于公开频道(通过ID或用户名)，程序会直接加入
   - 对于私有频道(通过邀请链接)，程序会使用邀请链接自动加入
3. 程序会记录每个频道的加入结果
4. 成功加入的频道会被监控并转发消息

注意：
- 即使是私有频道，只要您有正确的邀请链接，程序就能自动加入
- 对于需要管理员批准的频道，可能仍需要您手动操作
- 频繁加入多个频道可能会触发Telegram的限制机制

## 获取频道 ID 方法

有几种方法可以获取频道 ID：

1. **使用此工具的临时会话**：
   - 首次运行工具会要求您登录
   - 登录后，关注/加入您想监控的频道，然后从频道转发一条消息给自己
   - 查看控制台输出，会显示消息来源的频道 ID

2. **使用 Telegram Web 版**：
   - 在 web.telegram.org 打开频道
   - URL 中会包含频道 ID，通常格式为 `-100xxxxxxxxx`

3. **使用其他机器人**：
   - 如 @username_to_id_bot 或 @getidsbot

## 高级设置

在 `.env` 文件中，您可以配置以下高级设置：

1. **INCLUDE_SOURCE**：是否在转发消息中包含源频道名称（True/False）
2. **ADD_FOOTER**：是否在转发消息末尾添加固定页脚信息（True/False）
3. **FOOTER_TEXT**：页脚显示的文字内容
4. **TITLE_FILTER**：频道标题过滤功能，只转发标题包含指定关键词的频道的消息
   - 多个关键词使用逗号分隔，例如：`新闻,科技,AI`
   - 不区分大小写
   - 留空表示不进行过滤，转发所有配置的源频道的消息

## 运行方法

1. 确保您已加入源频道和目标频道
2. 确保配置文件 `.env` 已设置正确
3. 执行程序：
   ```
   python advanced_forwarder.py
   ```
4. 首次运行时，程序会提示您输入手机号和验证码进行登录
5. 登录成功后，程序会自动保存会话信息，后续运行不需要重新登录

## 常见问题

1. **"Could not find the input entity"错误**：
   - 确保您的用户账户已加入/订阅源频道
   - 检查频道 ID 是否正确
   - 尝试先用 Telegram 客户端手动访问该频道

2. **"Unauthorized"错误**：
   - 可能是您的会话已过期，删除 `.env` 中的 USER_SESSION 值，重新运行程序登录

3. **消息不转发**：
   - 检查程序日志中是否检测到新消息
   - 确认目标频道 ID 正确且您有权限发送消息
   - 如果使用了 TITLE_FILTER，检查频道标题是否包含指定的关键词
   - 尝试重启程序

## 安全提示

1. 保持 `.env` 文件安全，不要分享您的 API 凭证和会话字符串
2. 此工具使用您的用户账户，所以任何操作都会以您的名义进行
3. 频繁使用自动化工具可能导致您的账户被 Telegram 限制

# Telegram Bot 日志系统

这是一个为Telegram Bot设计的日志系统，能够自动记录并管理按日期分类的日志文件。

## 系统组成

1. **日志配置**：已集成到主程序中，会自动将日志按天存储
2. **日志管理工具**：提供了一个专门的`log_manager.py`工具用于管理日志

## 特性

- **按天记录日志**：日志会自动按天分割存储
- **保留历史日志**：默认保留30天的日志历史
- **支持多种日志级别**：INFO, WARNING, ERROR等
- **便捷的日志分析**：提供统计、搜索和过滤功能

## 如何使用

### 日志管理工具

`log_manager.py` 是一个功能完整的命令行工具，使用方法如下：

```bash
# 列出所有日志文件
python log_manager.py --action list

# 查看特定日期的日志
python log_manager.py --action view --date 2025-04-13

# 查看并过滤日志
python log_manager.py --action view --date 2025-04-13 --filter "error"

# 导入已有的日志
python log_manager.py --action import --input example.log

# 统计最近7天的日志情况
python log_manager.py --action stats --days 7

# 清理7天前的日志
python log_manager.py --action clean --days 7
```

### 在程序中使用日志

日志系统已经集成到程序中，您可以直接使用：

```python
# 创建日志消息
logger.info("这是一条普通消息")
logger.warning("这是一条警告消息") 
logger.error("这是一条错误消息")
```

## 日志文件位置

日志文件存储在`logs`目录下，按日期命名：

- `telegram_YYYY-MM-DD.log` - 常规日志文件
- `telegram_error_YYYY-MM-DD.log` - 错误专用日志 (仅包含ERROR级别及以上)

## 日志系统维护

- 定期执行清理命令，避免日志占用过多磁盘空间
- 在排查问题时，可以使用统计功能快速定位常见错误

## 日志格式

标准日志格式为：
```
YYYY-MM-DD HH:MM:SS,SSS - 组件名称 - 日志级别 - 日志消息
```

例如：
```
2025-04-13 04:30:25,805 - telethon.network.connection.connection - INFO - Connection established
```

## 注意事项

- 日志文件使用UTF-8编码，确保所有文本显示正确
- 日志分析功能依赖正确的日志格式，自定义日志可能导致分析结果不准确 