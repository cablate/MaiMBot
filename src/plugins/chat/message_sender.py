import asyncio
import os
import time
from typing import Dict, List, Optional, Union

from loguru import logger
from nonebot.adapters import Bot as BaseBot
from nonebot.adapters.telegram import Bot as TelegramBot
from nonebot.adapters.discord import Bot as DiscordBot

from .cq_code import cq_code_tool
from .message import Message, Message_Sending, Message_Thinking, MessageSet
from .storage import MessageStorage
from .utils import calculate_typing_time
from .config import global_config

# 获取当前平台类型
platform_type = os.getenv("PLATFORM_TYPE", "telegram").lower()
logger.info(f"消息发送器 - 当前平台类型：{platform_type}")

class Message_Sender:
    """发送器"""
    def __init__(self):
        self.message_interval = (0.5, 1)  # 消息间隔时间范围(秒)
        self.last_send_time = 0
        self._current_bot = None
        self.platform_type = platform_type
        
    def set_bot(self, bot: BaseBot):
        """设置当前bot实例"""
        self._current_bot = bot
        
    async def send_group_message(
        self, 
        group_id: int, 
        send_text: str, 
        auto_escape: bool = False,
        reply_message_id: int = None,
        at_user_id: int = None
    ) -> None:

        if not self._current_bot:
            raise RuntimeError("Bot未设置，请先调用set_bot方法设置bot实例")
            
        message = send_text
        
        # 模擬打字時間
        typing_time = calculate_typing_time(message)
        if typing_time > 10:
            typing_time = 10
        await asyncio.sleep(typing_time)
        
        # 根据不同的平台发送消息
        if self.platform_type == "telegram" and isinstance(self._current_bot, TelegramBot):
            await self._send_telegram_message(
                group_id=group_id,
                message=message,
                reply_to_message_id=reply_message_id
            )
        elif self.platform_type == "discord" and isinstance(self._current_bot, DiscordBot):
            await self._send_discord_message(
                channel_id=group_id,
                message=message,
                reference_message_id=reply_message_id
            )
        else:
            logger.warning(f"平台类型({self.platform_type})与机器人实例类型不匹配，或不支持的平台")
            try:
                # 尝试通用发送方法
                if isinstance(self._current_bot, TelegramBot):
                    await self._send_telegram_message(
                        group_id=group_id,
                        message=message,
                        reply_to_message_id=reply_message_id
                    )
                elif isinstance(self._current_bot, DiscordBot):
                    await self._send_discord_message(
                        channel_id=group_id,
                        message=message,
                        reference_message_id=reply_message_id
                    )
                else:
                    # 原有的OneBot逻辑作为后备
                    # 如果需要回复
                    if reply_message_id:
                        reply_cq = cq_code_tool.create_reply_cq(reply_message_id)
                        message = reply_cq + message
                    
                    await self._current_bot.send_group_msg(
                        group_id=group_id,
                        message=message,
                        auto_escape=auto_escape
                    )
                    logger.info(f"使用通用方法发送消息成功: {message}")
            except Exception as e:
                logger.error(f"发送消息失败: {e}")
    
    async def _send_telegram_message(
        self,
        group_id: int,
        message: str,
        reply_to_message_id: Optional[int] = None
    ) -> None:
        """发送Telegram消息"""
        try:
            params = {
                "chat_id": group_id,
                "text": message
            }
            
            if reply_to_message_id:
                params["reply_to_message_id"] = reply_to_message_id
                
            await self._current_bot.call_api("send_message", **params)
            logger.info(f"Telegram消息发送成功: {message}")
        except Exception as e:
            logger.error(f"Telegram消息发送失败: {e}")
            
    async def _send_discord_message(
        self,
        channel_id: int,
        message: str,
        reference_message_id: Optional[int] = None
    ) -> None:
        """发送Discord消息
        
        Args:
            channel_id: Discord频道ID
            message: 消息内容
            reference_message_id: 回复的消息ID
        """
        try:
            # 构建发送参数
            message_params = {
                "content": message
            }
            
            # 如果需要回复消息
            if reference_message_id:
                message_params["message_reference"] = {"message_id": reference_message_id}
            
            # 使用正确的Discord API方法和参数
            await self._current_bot.send(
                channel_id=channel_id,  # 目标频道ID
                message=message_params  # 消息内容及其他参数
            )
            logger.info(f"Discord消息发送成功: {message}")
        except Exception as e:
            logger.error(f"Discord消息发送失败: {e}")
            # 尝试备用方法
            try:
                # 备用方法: 使用call_api
                await self._current_bot.call_api(
                    "create_message", 
                    channel_id=str(channel_id),
                    content=message
                )
                logger.info(f"使用备用方法发送Discord消息成功: {message}")
            except Exception as e2:
                logger.error(f"备用方法发送Discord消息也失败: {e2}")
                # 记录调试信息
                logger.debug(f"当前机器人类型: {type(self._current_bot)}")
                logger.debug(f"可用API: {[m for m in dir(self._current_bot) if not m.startswith('_')]}")
                
    async def send_telegram_photo(
        self,
        group_id: int,
        photo_path: str,
        caption: Optional[str] = None,
        reply_to_message_id: Optional[int] = None
    ) -> None:
        """发送Telegram图片
        
        Args:
            group_id: 群组ID
            photo_path: 图片文件路径
            caption: 图片说明文字
            reply_to_message_id: 回复的消息ID
        """
        if not isinstance(self._current_bot, TelegramBot) or self.platform_type != "telegram":
            logger.warning("当前不是Telegram平台或机器人类型不匹配，无法发送图片")
            return
            
        try:
            params = {
                "chat_id": group_id,
            }
            
            # 打开图片文件
            with open(photo_path, 'rb') as photo_file:
                params["photo"] = photo_file
                
                # 添加可选参数
                if caption:
                    params["caption"] = caption
                if reply_to_message_id:
                    params["reply_to_message_id"] = reply_to_message_id
                
                # 发送图片
                await self._current_bot.call_api("send_photo", **params)
                logger.info(f"Telegram图片发送成功: {photo_path}")
        except Exception as e:
            logger.error(f"Telegram图片发送失败: {e}")
            
    async def send_discord_file(
        self,
        channel_id: int,
        file_path: str,
        content: Optional[str] = None,
        reference_message_id: Optional[int] = None
    ) -> None:
        """发送Discord文件/图片
        
        Args:
            channel_id: Discord频道ID
            file_path: 文件路径
            content: 附加文本内容
            reference_message_id: 回复的消息ID
        """
        if not isinstance(self._current_bot, DiscordBot) or self.platform_type != "discord":
            logger.warning("当前不是Discord平台或机器人类型不匹配，无法发送文件")
            return
            
        try:
            # 打开文件
            with open(file_path, 'rb') as file:
                # 构建消息参数
                message_params = {
                    "content": content or "",
                    "file": {"file": file, "filename": os.path.basename(file_path)}
                }
                
                # 如果需要回复消息
                if reference_message_id:
                    message_params["message_reference"] = {"message_id": reference_message_id}
                
                # 使用Discord API发送文件
                await self._current_bot.send(
                    channel_id=channel_id,
                    message=message_params
                )
                logger.info(f"Discord文件发送成功: {file_path}")
        except Exception as e:
            logger.error(f"Discord文件发送失败: {e}")
            # 尝试备用方法
            try:
                with open(file_path, 'rb') as file:
                    await self._current_bot.call_api(
                        "create_message",
                        channel_id=str(channel_id),
                        content=content or "",
                        files=[{"file": file, "filename": os.path.basename(file_path)}]
                    )
                    logger.info(f"使用备用方法发送Discord文件成功: {file_path}")
            except Exception as e2:
                logger.error(f"备用方法发送Discord文件也失败: {e2}")
                logger.debug(f"当前机器人类型: {type(self._current_bot)}")
                logger.debug(f"可用API: {[m for m in dir(self._current_bot) if not m.startswith('_')]}")


class MessageContainer:
    """单个群的发送/思考消息容器"""
    def __init__(self, group_id: int, max_size: int = 100):
        self.group_id = group_id
        self.max_size = max_size
        self.messages = []
        self.last_send_time = 0
        self.thinking_timeout = 20  # 思考超时时间（秒）
        
    def get_timeout_messages(self) -> List[Message_Sending]:
        """获取所有超时的Message_Sending对象（思考时间超过30秒），按thinking_start_time排序"""
        current_time = time.time()
        timeout_messages = []
        
        for msg in self.messages:
            if isinstance(msg, Message_Sending):
                if current_time - msg.thinking_start_time > self.thinking_timeout:
                    timeout_messages.append(msg)
                    
        # 按thinking_start_time排序，时间早的在前面
        timeout_messages.sort(key=lambda x: x.thinking_start_time)
                    
        return timeout_messages
        
    def get_earliest_message(self) -> Optional[Union[Message_Thinking, Message_Sending]]:
        """获取thinking_start_time最早的消息对象"""
        if not self.messages:
            return None
        earliest_time = float('inf')
        earliest_message = None
        for msg in self.messages:            
            msg_time = msg.thinking_start_time
            if msg_time < earliest_time:
                earliest_time = msg_time
                earliest_message = msg     
        return earliest_message
        
    def add_message(self, message: Union[Message_Thinking, Message_Sending]) -> None:
        """添加消息到队列"""
        # print(f"\033[1;32m[添加消息]\033[0m 添加消息到对应群")
        if isinstance(message, MessageSet):
            for single_message in message.messages:
                self.messages.append(single_message)
        else:
            self.messages.append(message)
            
    def remove_message(self, message: Union[Message_Thinking, Message_Sending]) -> bool:
        """移除消息，如果消息存在则返回True，否则返回False"""
        try:
            if message in self.messages:
                self.messages.remove(message)
                return True
            return False
        except Exception as e:
            print(f"\033[1;31m[错误]\033[0m 移除消息时发生错误: {e}")
            return False
        
    def has_messages(self) -> bool:
        """检查是否有待发送的消息"""
        return bool(self.messages)
        
    def get_all_messages(self) -> List[Union[Message, Message_Thinking]]:
        """获取所有消息"""
        return list(self.messages)
        

class MessageManager:
    """管理所有群的消息容器"""
    def __init__(self):
        self.containers: Dict[str, MessageContainer] = {}
        self.storage = MessageStorage()
        self._running = True
        
    def get_container(self, group_id: int) -> MessageContainer:
        """获取或创建群的消息容器"""
        if group_id not in self.containers:
            self.containers[group_id] = MessageContainer(group_id)
        return self.containers[group_id]
        
    def add_message(self, message: Union[Message_Thinking, Message_Sending, MessageSet]) -> None:
        """添加消息到对应群的消息容器"""
        group_id = message.group_id if not isinstance(message, MessageSet) else message.group_id
        self.get_container(group_id).add_message(message)
        
    async def process_group_messages(self, group_id: int):
        """处理群消息"""
        # if int(time.time() / 3) == time.time() / 3:
            # print(f"\033[1;34m[调试]\033[0m 开始处理群{group_id}的消息")
        container = self.get_container(group_id)
        if container.has_messages():
            #最早的对象，可能是思考消息，也可能是发送消息
            message_earliest = container.get_earliest_message() #一个message_thinking or message_sending
            
            #如果是思考消息
            if isinstance(message_earliest, Message_Thinking):
                #优先等待这条消息
                message_earliest.update_thinking_time()
                thinking_time = message_earliest.thinking_time
                print(f"\033[1;34m[调试]\033[0m 消息正在思考中，已思考{int(thinking_time)}秒\033[K\r", end='', flush=True)
                
                # 检查是否超时
                if thinking_time > global_config.thinking_timeout:
                    print(f"\033[1;33m[警告]\033[0m 消息思考超时({thinking_time}秒)，移除该消息")
                    container.remove_message(message_earliest)
            else:# 如果不是message_thinking就只能是message_sending    
                print(f"\033[1;34m[调试]\033[0m 消息'{message_earliest.processed_plain_text}'正在发送中")
                # 檢查是否是表情符號消息
                if message_earliest.is_emoji:
                    print(f"\033[1;34m[调试]\033[0m 消息'{message_earliest.processed_plain_text}' is emoji msg")
                    # 根据消息来源平台选择发送方式
                    if message_earliest.source_platform == "telegram" and isinstance(message_sender._current_bot, TelegramBot) and not message_earliest.translate_cq:
                        # 從CQ碼中提取圖片路徑
                        import re
                        cq_pattern = r'file=(.*?)[,\]]'
                        match = re.search(cq_pattern, message_earliest.processed_plain_text)
                        if match:
                            photo_path = match.group(1)
                            await message_sender.send_telegram_photo(
                                group_id=group_id, 
                                photo_path=photo_path,
                                caption=message_earliest.detailed_plain_text if hasattr(message_earliest, 'detailed_plain_text') else None
                            )
                        else:
                            print(f"無法從CQ碼提取圖片路徑: {message_earliest.processed_plain_text}")
                    elif message_earliest.source_platform == "discord" and isinstance(message_sender._current_bot, DiscordBot):
                        # 对于Discord，尝试发送文件
                        import re
                        cq_pattern = r'file=(.*?)[,\]]'
                        match = re.search(cq_pattern, message_earliest.processed_plain_text)
                        if match:
                            file_path = match.group(1)
                            await message_sender.send_discord_file(
                                channel_id=group_id,
                                file_path=file_path,
                                content=message_earliest.detailed_plain_text if hasattr(message_earliest, 'detailed_plain_text') else None
                            )
                        else:
                            # 如果没有文件路径，按普通消息发送
                            await message_sender.send_group_message(group_id, message_earliest.processed_plain_text, auto_escape=False)
                    else:
                        # 其他平台或情况使用原方式發送
                        await message_sender.send_group_message(group_id, message_earliest.processed_plain_text, auto_escape=False)
                else:
                    print(f"\033[1;34m[调试]\033[0m 消息'{message_earliest.processed_plain_text}' 非 emoji、普通消息發送中")
                    # 移除思考時間和是否為頭部消息的檢查
                    await message_sender.send_group_message(
                        group_id=group_id, 
                        send_text=message_earliest.processed_plain_text, 
                        auto_escape=False, 
                        reply_message_id=message_earliest.reply_message_id if hasattr(message_earliest, 'reply_message_id') else None
                    )
                
                container.remove_message(message_earliest)
            
            #获取并处理超时消息
            message_timeout = container.get_timeout_messages() #也许是一堆message_sending
            if message_timeout:
                print(f"\033[1;34m[调试]\033[0m 发现{len(message_timeout)}条超时消息")
                for msg in message_timeout:
                    if msg == message_earliest:
                        continue  # 跳过已经处理过的消息
                        
                    try:
                        #发送
                        if msg.is_emoji:
                            await message_sender.send_group_message(group_id, msg.processed_plain_text, auto_escape=False)
                        else:
                            await message_sender.send_group_message(group_id, msg.processed_plain_text, auto_escape=False)
                            
                        
                        #如果是表情包，则替换为"[表情包]"
                        if msg.is_emoji:
                            msg.processed_plain_text = "[表情包]"
                        await self.storage.store_message(msg, None)
                        
                        # 安全地移除消息
                        if not container.remove_message(msg):
                            print("\033[1;33m[警告]\033[0m 尝试删除不存在的消息")
                    except Exception as e:
                        print(f"\033[1;31m[错误]\033[0m 处理超时消息时发生错误: {e}")
                        continue
            
    async def start_processor(self):
        """启动消息处理器"""
        while self._running:
            await asyncio.sleep(1)
            tasks = []
            for group_id in self.containers.keys():
                tasks.append(self.process_group_messages(group_id))
            
            await asyncio.gather(*tasks)

# 创建全局消息管理器实例
message_manager = MessageManager()
# 创建全局发送器实例
message_sender = Message_Sender()
