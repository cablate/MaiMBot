import asyncio
import os
import random
import time

from loguru import logger
from nonebot import get_driver, on_command, on_message, require
# 導入 Telegram 適配器
from nonebot.adapters.telegram import Bot as TelegramBot
from nonebot.adapters.telegram import Message as TelegramMessage
from nonebot.adapters.telegram.event import MessageEvent as TelegramMessageEvent
# 導入 Discord 適配器
from nonebot.adapters.discord import Bot as DiscordBot
from nonebot.adapters.discord import Message as DiscordMessage
from nonebot.adapters.discord.event import MessageEvent as DiscordMessageEvent
from nonebot.rule import to_me
from nonebot.typing import T_State

from ...common.database import Database
from ..moods.moods import MoodManager  # 导入情绪管理器
from ..schedule.schedule_generator import bot_schedule
from ..utils.statistic import LLMStatistics
from .bot import chat_bot
from .config import global_config
from .emoji_manager import emoji_manager
from .relationship_manager import relationship_manager
from .willing_manager import willing_manager

# 创建LLM统计实例
llm_stats = LLMStatistics("llm_statistics.txt")

# 添加标志变量
_message_manager_started = False

# 获取驱动器
driver = get_driver()
config = driver.config

Database.initialize(
        host= config.MONGODB_HOST,
        port= int(config.MONGODB_PORT),
        db_name= config.DATABASE_NAME,
        username= config.MONGODB_USERNAME,
        password= config.MONGODB_PASSWORD,
        auth_source= config.MONGODB_AUTH_SOURCE
)
print("\033[1;32m[初始化数据库完成]\033[0m")


# 导入其他模块
from ..memory_system.memory import hippocampus, memory_graph
from .bot import ChatBot

# from .message_send_control import message_sender
from .message_sender import message_manager, message_sender

# 初始化表情管理器
emoji_manager.initialize()

print(f"\033[1;32m正在唤醒{global_config.BOT_NICKNAME}......\033[0m")
# 创建机器人实例
chat_bot = ChatBot()
# 註冊群消息處理器 (Telegram)
telegram_group_msg = on_message(priority=5)
# 註冊Discord消息處理器
discord_group_msg = on_message(priority=5)
# 創建定時任務
scheduler = require("nonebot_plugin_apscheduler").scheduler



@driver.on_startup
async def start_background_tasks():
    """啟動後台任務"""
    # 啟動LLM統計
    llm_stats.start()
    print("\033[1;32m[初始化]\033[0m LLM統計功能已啟動")
    
    # 初始化並啟動情緒管理器
    mood_manager = MoodManager.get_instance()
    mood_manager.start_mood_update(update_interval=global_config.mood_update_interval)
    print("\033[1;32m[初始化]\033[0m 情緒管理器已啟動")
    
    # 只啟動表情包管理任務
    asyncio.create_task(emoji_manager.start_periodic_check(interval_MINS=global_config.EMOJI_CHECK_INTERVAL))
    await bot_schedule.initialize()
    bot_schedule.print_schedule()
    
@driver.on_startup
async def init_relationships():
    """在 NoneBot2 啟動時初始化關係管理器"""
    print("\033[1;32m[初始化]\033[0m 正在加載用戶關係數據...")
    await relationship_manager.load_all_relationships()
    asyncio.create_task(relationship_manager._start_relationship_manager())

@driver.on_bot_connect
async def _(bot: TelegramBot):
    """Telegram Bot連接成功時的處理"""
    global _message_manager_started
    print(f"\033[1;38;5;208m-----------{global_config.BOT_NICKNAME} Telegram成功連接！-----------\033[0m")
    await willing_manager.ensure_started()
    
    message_sender.set_bot(bot)
    print("\033[1;38;5;208m-----------Telegram消息發送器已啟動！-----------\033[0m")
    
    if not _message_manager_started:
        asyncio.create_task(message_manager.start_processor())
        _message_manager_started = True
        print("\033[1;38;5;208m-----------消息處理器已啟動！-----------\033[0m")
    
    asyncio.create_task(emoji_manager._periodic_scan(interval_MINS=global_config.EMOJI_REGISTER_INTERVAL))
    print("\033[1;38;5;208m-----------開始偷表情包！-----------\033[0m")

@driver.on_bot_connect
async def discord_bot_connect(bot: DiscordBot):
    """Discord Bot連接成功時的處理"""
    global _message_manager_started
    print(f"\033[1;38;5;208m-----------{global_config.BOT_NICKNAME} Discord成功連接！-----------\033[0m")
    await willing_manager.ensure_started()
    
    message_sender.set_bot(bot)
    print("\033[1;38;5;208m-----------Discord消息發送器已啟動！-----------\033[0m")
    
    if not _message_manager_started:
        asyncio.create_task(message_manager.start_processor())
        _message_manager_started = True
        print("\033[1;38;5;208m-----------消息處理器已啟動！-----------\033[0m")
    
# Telegram消息處理器
@telegram_group_msg.handle()
async def handle_telegram_message(bot: TelegramBot, event: TelegramMessageEvent, state: T_State):
    """處理Telegram消息"""
    # 輸出調試信息
    if hasattr(event, "chat"):
        group_id = event.chat.id
        user_id = event.from_.id
        print(f"\033[1;33m[調試信息]\033[0m 收到來自Telegram群組 ID: {group_id}, 用戶 ID: {user_id} 的消息")
        print(f"\033[1;33m[調試信息]\033[0m 允許的群組列表: {global_config.talk_allowed_groups}")
    
    # 轉換Telegram消息格式為內部格式
    message_obj = await create_internal_message(bot, event)
    if message_obj:
        await chat_bot.handle_message(message_obj, bot)
    else:
        print(f"\033[1;31m[調試信息]\033[0m 消息被過濾，無法創建內部消息對象")

# Discord消息處理器
@discord_group_msg.handle()
async def handle_discord_message(bot: DiscordBot, event: DiscordMessageEvent, state: T_State):
    """處理Discord消息"""
    # 如果是機器人發送的消息，直接忽略
    if event.get_user_id() == bot.self_id:
        return
    
    print(f"\033[1;34m[完整事件信息]\033[0m {event}")
        
    # 輸出調試信息
    guild_id = event.guild_id
    channel_id = event.channel_id
    user_id = event.get_user_id()
    print(f"\033[1;33m[調試信息]\033[0m 收到來自Discord服務器 ID: {guild_id}, 頻道 ID: {channel_id}, 用戶 ID: {user_id} 的消息")
    print(f"\033[1;33m[調試信息]\033[0m 允許的群組列表: {global_config.talk_allowed_groups}")
    
    # 轉換Discord消息格式為內部格式
    message_obj = await create_discord_internal_message(bot, event)
    if message_obj:
        await chat_bot.handle_message(message_obj, bot)
    else:
        print(f"\033[1;31m[調試信息]\033[0m Discord消息被過濾，無法創建內部消息對象")

async def create_internal_message(bot: TelegramBot, event: TelegramMessageEvent):
    """創建內部消息對象
    
    Args:
        bot: Telegram 機器人實例
        event: Telegram 消息事件
        
    Returns:
        Message: 內部消息對象，如果不符合處理條件則返回 None
    """
    # 導入消息類
    from .message import Message
    
    # 檢查消息類型
    is_private = hasattr(event, "chat") and event.chat.type == "private"
    is_group = hasattr(event, "chat") and event.chat.type in ["group", "supergroup"]
    
    if not (is_private or is_group):
        logger.debug("無法識別的消息類型，忽略")
        return None
    
    # 獲取消息資訊
    user_id = event.from_.id
    
    # 處理私聊消息
    if is_private:
        group_id = user_id  # 私聊時，使用用戶ID作為 group_id
        group_name = "私聊"
    # 處理群組消息
    else:
        group_id = event.chat.id
        group_name = event.chat.title
        
        # 群組消息需要檢查是否在允許的群組列表中
        if str(group_id) not in global_config.talk_allowed_groups and group_id not in global_config.talk_allowed_groups:
            logger.debug(f"群組 {group_id} 不在允許列表中，忽略消息")
            return None
    
    # 檢查用戶是否被封禁
    if str(user_id) in global_config.ban_user_id or user_id in global_config.ban_user_id:
        logger.debug(f"用戶 {user_id} 在封禁列表中，忽略消息")
        return None
    
    # 獲取發送者資訊
    user_nickname = event.from_.first_name
    if event.from_.last_name:
        user_nickname += f" {event.from_.last_name}"
    
    # 獲取消息文本內容
    # Telegram 消息可能在 text 或 message 屬性中
    message_text = ""
    if hasattr(event, "text") and event.text:
        message_text = event.text
    elif hasattr(event, "message") and event.message:
        message_text = str(event.message)
    
    # 創建內部消息對象，明确指定来源平台
    message = Message(
        group_id=group_id,
        user_id=user_id,
        message_id=event.message_id,
        user_cardname=user_nickname,
        raw_message=message_text,
        plain_text=message_text,
        reply_message=event.reply_to_message.message_id if event.reply_to_message else None,
        group_name=group_name,
        source_platform="telegram"  # 明确指定来源平台
    )
    await message.initialize()
    
    return message

async def create_discord_internal_message(bot: DiscordBot, event: DiscordMessageEvent):
    """創建Discord內部消息對象
    
    Args:
        bot: Discord 機器人實例
        event: Discord 消息事件
        
    Returns:
        Message: 內部消息對象，如果不符合處理條件則返回 None
    """
    # 導入消息類
    from .message import Message
    
    # 獲取消息資訊
    guild_id = event.guild_id  # Discord服务器ID
    channel_id = event.channel_id  # Discord频道ID
    user_id = event.get_user_id()  # 用户ID
    message_id = event.message_id  # 消息ID
    
    # 用channel_id作為群組ID，因為Discord中消息是基於頻道的
    group_id = channel_id
    
    # 檢查頻道是否在允許的群組列表中
    if str(group_id) not in global_config.talk_allowed_groups and group_id not in global_config.talk_allowed_groups:
        logger.debug(f"Discord頻道 {group_id} 不在允許列表中，忽略消息")
        return None
    
    # 檢查用戶是否被封禁
    if str(user_id) in global_config.ban_user_id or user_id in global_config.ban_user_id:
        logger.debug(f"用戶 {user_id} 在封禁列表中，忽略消息")
        return None
    
    # 獲取發送者資訊
    user_nickname = str(user_id)  # 使用用户ID作为昵称的基础
    user_cardname = str(user_id)  # 使用用户ID作为群昵称
    group_name = f"Discord頻道 {channel_id}"
    
    # 嘗試獲取更多用戶信息
    try:
        # 獲取Discord服務器和頻道名稱
        guild_info = await bot.get_guild(guild_id=guild_id)
        channel_info = await bot.get_channel(channel_id=channel_id)
        
        # 使用getattr获取对象属性，而不是使用get方法
        guild_name = getattr(guild_info, "name", "未知服務器")
        channel_name = getattr(channel_info, "name", "未知頻道")
        group_name = f"{guild_name} - {channel_name}"
        
        # 獲取用戶信息
        member_info = await bot.get_guild_member(guild_id=guild_id, user_id=user_id)
        if member_info:
            # 同样使用getattr获取对象属性
            if hasattr(member_info, "nick") and member_info.nick:
                user_nickname = member_info.nick
            elif hasattr(member_info, "user") and hasattr(member_info.user, "username"):
                user_nickname = member_info.user.username
            user_cardname = user_nickname
    except Exception as e:
        logger.error(f"獲取Discord信息出錯: {e}")
    
    # 獲取消息文本內容
    message_text = event.get_message()
    if not isinstance(message_text, str):
        # 如果返回的不是字符串，尝试转换为字符串
        message_text = str(message_text)
    
    # 獲取回復消息ID
    reply_message_id = None
    if hasattr(event, "referenced_message") and event.referenced_message:
        reply_message_id = event.referenced_message.id
    
    # 創建內部消息對象，添加source_platform标识为discord
    message = Message(
        group_id=group_id,
        user_id=user_id,
        message_id=message_id,
        user_cardname=user_cardname,
        user_nickname=user_nickname,
        raw_message=message_text,
        plain_text=message_text,
        reply_message=reply_message_id,
        group_name=group_name,
        source_platform="discord"  # 添加平台标识
    )
    await message.initialize()
    
    return message

# 添加build_memory定時任務
@scheduler.scheduled_job("interval", seconds=global_config.build_memory_interval, id="build_memory")
async def build_memory_task():
    """每build_memory_interval秒執行一次記憶構建"""
    print("\033[1;32m[記憶構建]\033[0m -------------------------------------------開始構建記憶-------------------------------------------")
    start_time = time.time()
    await hippocampus.operation_build_memory(chat_size=20)
    end_time = time.time()
    print(f"\033[1;32m[記憶構建]\033[0m -------------------------------------------記憶構建完成：耗時: {end_time - start_time:.2f} 秒-------------------------------------------")
    
@scheduler.scheduled_job("interval", seconds=global_config.forget_memory_interval, id="forget_memory") 
async def forget_memory_task():
    """每30秒執行一次記憶構建"""
    # print("\033[1;32m[記憶遺忘]\033[0m 開始遺忘記憶...")
    # await hippocampus.operation_forget_topic(percentage=0.1)
    # print("\033[1;32m[記憶遺忘]\033[0m 記憶遺忘完成")

@scheduler.scheduled_job("interval", seconds=global_config.build_memory_interval + 10, id="merge_memory")
async def merge_memory_task():
    """每30秒執行一次記憶構建"""
    # print("\033[1;32m[記憶整合]\033[0m 開始整合")
    # await hippocampus.operation_merge_memory(percentage=0.1)
    # print("\033[1;32m[記憶整合]\033[0m 記憶整合完成")

@scheduler.scheduled_job("interval", seconds=30, id="print_mood")
async def print_mood_task():
    """每30秒打印一次情緒狀態"""
    mood_manager = MoodManager.get_instance()
    mood_manager.print_mood_status()
  
