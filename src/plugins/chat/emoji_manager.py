import asyncio
import os
import random
import time
import traceback
from typing import Optional

from loguru import logger
from nonebot import get_driver
from nonebot.adapters.telegram import MessageSegment as TelegramMessageSegment

from ...common.database import Database
from ..chat.config import global_config
from ..chat.utils import get_embedding
from ..chat.utils_image import image_path_to_base64
from ..models.utils_model import LLM_request

driver = get_driver()
config = driver.config


class EmojiManager:
    _instance = None
    EMOJI_DIR = "data/emoji"  # 表情包存储目录
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.db = None
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        self.db = Database.get_instance()
        self._scan_task = None
        self.vlm = LLM_request(model=global_config.vlm, temperature=0.3, max_tokens=1000)
        self.llm_emotion_judge = LLM_request(model=global_config.llm_normal_minor, max_tokens=60,temperature=0.8) #更高的温度，更少的token（后续可以根据情绪来调整温度）
        
    def _ensure_emoji_dir(self):
        """确保表情存储目录存在"""
        os.makedirs(self.EMOJI_DIR, exist_ok=True)
    
    def initialize(self):
        """初始化数据库连接和表情目录"""
        if not self._initialized:
            try:
                self.db = Database.get_instance()
                self._ensure_emoji_collection()
                self._ensure_emoji_dir()
                self._initialized = True
                # 启动时执行一次完整性检查
                self.check_emoji_file_integrity()
            except Exception as e:
                logger.error(f"初始化表情管理器失败: {str(e)}")
                
    def _ensure_db(self):
        """确保数据库已初始化"""
        if not self._initialized:
            self.initialize()
        if not self._initialized:
            raise RuntimeError("EmojiManager not initialized")
        
    def _ensure_emoji_collection(self):
        """确保emoji集合存在并创建索引
        
        这个函数用于确保MongoDB数据库中存在emoji集合,并创建必要的索引。
        
        索引的作用是加快数据库查询速度:
        - embedding字段的2dsphere索引: 用于加速向量相似度搜索,帮助快速找到相似的表情包
        - tags字段的普通索引: 加快按标签搜索表情包的速度
        - filename字段的唯一索引: 确保文件名不重复,同时加快按文件名查找的速度
        
        没有索引的话,数据库每次查询都需要扫描全部数据,建立索引后可以大大提高查询效率。
        """
        if 'emoji' not in self.db.db.list_collection_names():
            self.db.db.create_collection('emoji')
            self.db.db.emoji.create_index([('embedding', '2dsphere')])
            self.db.db.emoji.create_index([('tags', 1)])
            self.db.db.emoji.create_index([('filename', 1)], unique=True)
            
    def record_usage(self, emoji_id: str):
        """记录表情使用次数"""
        try:
            self._ensure_db()
            self.db.db.emoji.update_one(
                {'_id': emoji_id},
                {'$inc': {'usage_count': 1}}
            )
        except Exception as e:
            logger.error(f"记录表情使用失败: {str(e)}")
            
    async def get_emoji_for_text(self, text: str) -> Optional[str]:
        """根据文本内容获取相关表情包
        Args:
            text: 输入文本
        Returns:
            Optional[Tuple[str, str]]: 表情包文件路徑和描述，如果沒有找到則返回None
        """
        try:
            if isinstance(text, list):
                text = ' '.join(text)
                
            self._ensure_db()
            emoji_data = await self._get_related_emoji(text)
            
            if emoji_data:
                emoji_path = os.path.join(self.EMOJI_DIR, emoji_data['filename'])
                emoji_desc = emoji_data.get('description', '一個表情包')
                
                # 檢查文件是否存在
                if not os.path.exists(emoji_path):
                    logger.warning(f"表情包文件不存在: {emoji_path}")
                    return None
                    
                self.record_usage(emoji_data['_id'])
                return emoji_path, emoji_desc
            else:
                logger.debug("未找到相關表情包")
                return None
        except Exception as e:
            logger.error(f"獲取表情包時出錯: {traceback.format_exc()}")
            return None
    
    async def _get_related_emoji(self, text: str):
        """獲取與文本相關的表情包"""
        embedding = await get_embedding(text)
        if not embedding:
            return None
            
        # 使用餘弦相似度搜索
        pipeline = [
            {
                "$addFields": {
                    "similarity": {
                        "$function": {
                            "body": """
                            function(a, b) {
                                var dotProduct = 0;
                                var normA = 0;
                                var normB = 0;
                                for (var i = 0; i < a.length; i++) {
                                    dotProduct += a[i] * b[i];
                                    normA += a[i] * a[i];
                                    normB += b[i] * b[i];
                                }
                                return dotProduct / (Math.sqrt(normA) * Math.sqrt(normB));
                            }
                            """,
                            "args": ["$embedding", embedding],
                            "lang": "js"
                        }
                    }
                }
            },
            {"$match": {"similarity": {"$gt": 0.4}}},
            {"$sort": {"similarity": -1}},
            {"$limit": 5}
        ]
        
        results = list(self.db.db.emoji.aggregate(pipeline))
        
        if not results:
            return None
            
        # 按照相似度加權隨機選擇
        weights = [result['similarity'] for result in results]
        total_weight = sum(weights)
        
        if total_weight == 0:
            return random.choice(results)
            
        # 歸一化權重
        norm_weights = [w/total_weight for w in weights]
        
        # 加權隨機選擇
        selected_emoji = random.choices(results, weights=norm_weights, k=1)[0]
        
        return selected_emoji

    async def create_telegram_emoji_msgment(self, text: str) -> Optional[TelegramMessageSegment]:
        """創建Telegram表情包消息段"""
        emoji_data = await self.get_emoji_for_text(text)
        
        if not emoji_data:
            return None
            
        emoji_path, emoji_desc = emoji_data
        
        # 創建Telegram圖片消息段
        # 使用open()讀取文件為二進制
        try:
            with open(emoji_path, 'rb') as f:
                return TelegramMessageSegment.photo(f)
        except Exception as e:
            logger.error(f"获取表情包失败: {str(e)}")
            return None

    async def _get_emoji_discription(self, image_base64: str) -> str:
        """获取表情包的标签"""
        try:
            prompt = '这是一个表情包，使用中文简洁的描述一下表情包的内容和表情包所表达的情感'
            
            content, _ = await self.vlm.generate_response_for_image(prompt, image_base64)
            logger.debug(f"输出描述: {content}")
            return content
            
        except Exception as e:
            logger.error(f"获取标签失败: {str(e)}")
            return None
    
    async def _check_emoji(self, image_base64: str) -> str:
        try:
            prompt = f'这是一个表情包，请回答这个表情包是否满足\"{global_config.EMOJI_CHECK_PROMPT}\"的要求，是则回答是，否则回答否，不要出现任何其他内容'
            
            content, _ = await self.vlm.generate_response_for_image(prompt, image_base64)
            logger.debug(f"输出描述: {content}")
            return content
            
        except Exception as e:
            logger.error(f"获取标签失败: {str(e)}")
            return None
        
    async def _get_kimoji_for_text(self, text:str):
        try:
            prompt = f'这是{global_config.BOT_NICKNAME}将要发送的消息内容:\n{text}\n若要为其配上表情包，请你输出这个表情包应该表达怎样的情感，应该给人什么样的感觉，不要太简洁也不要太长，注意不要输出任何对消息内容的分析内容，只输出\"一种什么样的感觉\"中间的形容词部分。'
            
            content, _ = await self.llm_emotion_judge.generate_response_async(prompt)
            logger.info(f"输出描述: {content}")
            return content
            
        except Exception as e:
            logger.error(f"获取标签失败: {str(e)}")
            return None
                    
    async def scan_new_emojis(self):
        """扫描新的表情包"""
        try:
            emoji_dir = "data/emoji"
            os.makedirs(emoji_dir, exist_ok=True)

            # 获取所有支持的图片文件
            files_to_process = [f for f in os.listdir(emoji_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif'))]
            
            for filename in files_to_process:
                image_path = os.path.join(emoji_dir, filename)
                
                # 检查是否已经注册过
                existing_emoji = self.db.db['emoji'].find_one({'filename': filename})
                if existing_emoji:
                    continue
                
                # 压缩图片并获取base64编码
                image_base64 = image_path_to_base64(image_path)
                if image_base64 is None:
                    os.remove(image_path)
                    continue
                
                # 获取表情包的描述
                discription = await self._get_emoji_discription(image_base64)
                if global_config.EMOJI_CHECK:
                    check = await self._check_emoji(image_base64)
                    if '是' not in check:
                        os.remove(image_path)
                        logger.info(f"描述: {discription}")
                        logger.info(f"其不满足过滤规则，被剔除 {check}")
                        continue
                    logger.info(f"check通过 {check}")
                embedding = await get_embedding(discription)
                if discription is not None:
                    # 准备数据库记录
                    emoji_record = {
                        'filename': filename,
                        'path': image_path,
                        'embedding':embedding,
                        'discription': discription,
                        'timestamp': int(time.time())
                    }
                    
                    # 保存到数据库
                    self.db.db['emoji'].insert_one(emoji_record)
                    logger.success(f"注册新表情包: {filename}")
                    logger.info(f"描述: {discription}")
                else:
                    logger.warning(f"跳过表情包: {filename}")
                
        except Exception as e:
            logger.error(f"扫描表情包失败: {str(e)}")
            logger.error(traceback.format_exc())
    
    async def _periodic_scan(self, interval_MINS: int = 10):
        """定期扫描新表情包"""
        while True:
            print("\033[1;36m[表情包]\033[0m 开始扫描新表情包...")
            await self.scan_new_emojis()
            await asyncio.sleep(interval_MINS * 60)  # 每600秒扫描一次


    def check_emoji_file_integrity(self):
        """检查表情包文件完整性
        如果文件已被删除，则从数据库中移除对应记录
        """
        try:
            self._ensure_db()
            # 获取所有表情包记录
            all_emojis = list(self.db.db.emoji.find())
            removed_count = 0
            total_count = len(all_emojis)
            
            for emoji in all_emojis:
                try:
                    if 'path' not in emoji:
                        logger.warning(f"发现无效记录（缺少path字段），ID: {emoji.get('_id', 'unknown')}")
                        self.db.db.emoji.delete_one({'_id': emoji['_id']})
                        removed_count += 1
                        continue
                    
                    if 'embedding' not in emoji:
                        logger.warning(f"发现过时记录（缺少embedding字段），ID: {emoji.get('_id', 'unknown')}")
                        self.db.db.emoji.delete_one({'_id': emoji['_id']})
                        removed_count += 1
                        continue
                        
                    # 检查文件是否存在
                    if not os.path.exists(emoji['path']):
                        logger.warning(f"表情包文件已被删除: {emoji['path']}")
                        # 从数据库中删除记录
                        result = self.db.db.emoji.delete_one({'_id': emoji['_id']})
                        if result.deleted_count > 0:
                            logger.success(f"成功删除数据库记录: {emoji['_id']}")
                            removed_count += 1
                        else:
                            logger.error(f"删除数据库记录失败: {emoji['_id']}")
                except Exception as item_error:
                    logger.error(f"处理表情包记录时出错: {str(item_error)}")
                    continue
            
            # 验证清理结果
            remaining_count = self.db.db.emoji.count_documents({})
            if removed_count > 0:
                logger.success(f"已清理 {removed_count} 个失效的表情包记录")
                logger.info(f"清理前总数: {total_count} | 清理后总数: {remaining_count}")
            else:
                logger.info(f"已检查 {total_count} 个表情包记录")
                
        except Exception as e:
            logger.error(f"检查表情包完整性失败: {str(e)}")
            logger.error(traceback.format_exc())

    async def start_periodic_check(self, interval_MINS: int = 120):
        while True:
            self.check_emoji_file_integrity()
            await asyncio.sleep(interval_MINS * 60)



# 创建全局单例
emoji_manager = EmojiManager() 