import os
from dataclasses import dataclass, field
from typing import Dict, Optional, Set, Union

import tomli
from loguru import logger


@dataclass
class BotConfig:
    """机器人配置类"""    
    BOT_QQ: Optional[int] = 1
    BOT_NICKNAME: Optional[str] = None
    
    # 平臺識別
    PLATFORM: str = "telegram"  # 平臺類型: "telegram" 或 "qq"
    
    # 消息處理相關配置
    MIN_TEXT_LENGTH: int = 2  # 最小處理文本長度
    MAX_CONTEXT_SIZE: int = 15  # 上下文最大消息數
    emoji_chance: float = 0.2  # 發送表情包的基礎概率
    
    ENABLE_PIC_TRANSLATE: bool = True  # 是否啟用圖片翻譯
    
    talk_allowed_groups: Set[Union[int, str]] = field(default_factory=set)  # 支持數字(QQ)或字符串(Telegram)
    talk_frequency_down_groups: Set[Union[int, str]] = field(default_factory=set)
    thinking_timeout: int = 100  # 思考時間
    
    response_willing_amplifier: float = 1.0  # 回复意愿放大系数
    response_interested_rate_amplifier: float = 1.0  # 回复兴趣度放大系数
    down_frequency_rate: float = 3.5  # 降低回复频率的群组回复意愿降低系数
    
    ban_user_id: Set[Union[int, str]] = field(default_factory=set)  # 支持數字(QQ)或字符串(Telegram)
    
    build_memory_interval: int = 30  # 记忆构建间隔（秒）
    forget_memory_interval: int = 300  # 记忆遗忘间隔（秒）
    EMOJI_CHECK_INTERVAL: int = 120  # 表情包检查间隔（分钟）
    EMOJI_REGISTER_INTERVAL: int = 10  # 表情包注册间隔（分钟）
    EMOJI_SAVE: bool = True  # 偷表情包
    EMOJI_CHECK: bool = False #是否开启过滤
    EMOJI_CHECK_PROMPT: str = "符合公序良俗" # 表情包过滤要求

    ban_words: Set[str] = field(default_factory=set)

    max_response_length: int = 1024  # 最大回复长度
    
    # 模型配置
    llm_reasoning: Dict[str, str] = field(default_factory=lambda: {})
    llm_reasoning_minor: Dict[str, str] = field(default_factory=lambda: {})
    llm_normal: Dict[str, str] = field(default_factory=lambda: {})
    llm_normal_minor: Dict[str, str] = field(default_factory=lambda: {})
    llm_topic_judge: Dict[str, str] = field(default_factory=lambda: {})
    llm_summary_by_topic: Dict[str, str] = field(default_factory=lambda: {})
    llm_emotion_judge: Dict[str, str] = field(default_factory=lambda: {})
    embedding: Dict[str, str] = field(default_factory=lambda: {})
    vlm: Dict[str, str] = field(default_factory=lambda: {})
    moderation: Dict[str, str] = field(default_factory=lambda: {})

    MODEL_R1_PROBABILITY: float = 0.8  # R1模型概率
    MODEL_V3_PROBABILITY: float = 0.1  # V3模型概率
    MODEL_R1_DISTILL_PROBABILITY: float = 0.1  # R1蒸馏模型概率
    
    enable_advance_output: bool = False  # 是否启用高级输出
    enable_kuuki_read: bool = True # 是否启用读空气功能
    
    mood_update_interval: float = 1.0 # 情绪更新间隔 单位秒
    mood_decay_rate: float = 0.95 # 情绪衰减率
    mood_intensity_factor: float = 0.7 # 情绪强度因子

    # 默认人设
    PROMPT_PERSONALITY=[
        "曾经是一个学习地质的女大学生，现在学习心理学和脑科学，你会刷贴吧",
        "是一个女大学生，你有黑色头发，你会刷小红书",
        "是一个女大学生，你会刷b站，对ACG文化感兴趣"
    ]
    PROMPT_SCHEDULE_GEN="一个曾经学习地质,现在学习心理学和脑科学的女大学生，喜欢刷qq，贴吧，知乎和小红书"
    
    PERSONALITY_1: float = 0.6 # 第一种人格概率
    PERSONALITY_2: float = 0.3 # 第二种人格概率
    PERSONALITY_3: float = 0.1 # 第三种人格概率
    
    @staticmethod
    def get_config_dir() -> str:
        """获取配置文件目录"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        root_dir = os.path.abspath(os.path.join(current_dir, '..', '..', '..'))
        config_dir = os.path.join(root_dir, 'config')
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        return config_dir

    
    @classmethod
    def load_config(cls, config_path: str = None) -> "BotConfig":
        """从TOML配置文件加载配置"""
        config = cls()
        if os.path.exists(config_path):
            with open(config_path, "rb") as f:
                try:
                    toml_dict = tomli.load(f)
                except(tomli.TOMLDecodeError) as e:
                    logger.critical(f"配置文件bot_config.toml填写有误，请检查第{e.lineno}行第{e.colno}处：{e.msg}")
                    exit(1)
            
            # 平臺配置
            if "platform" in toml_dict:
                platform_config = toml_dict["platform"]
                config.PLATFORM = platform_config.get("type", config.PLATFORM)
                
            if 'personality' in toml_dict:
                personality_config=toml_dict['personality']
                personality=personality_config.get('prompt_personality')
                if len(personality) >= 2:
                    logger.info(f"载入自定义人格:{personality}")
                    config.PROMPT_PERSONALITY=personality_config.get('prompt_personality',config.PROMPT_PERSONALITY)
                logger.info(f"载入自定义日程prompt:{personality_config.get('prompt_schedule',config.PROMPT_SCHEDULE_GEN)}")
                config.PROMPT_SCHEDULE_GEN=personality_config.get('prompt_schedule',config.PROMPT_SCHEDULE_GEN)
                config.PERSONALITY_1=personality_config.get('personality_1_probability',config.PERSONALITY_1)
                config.PERSONALITY_2=personality_config.get('personality_2_probability',config.PERSONALITY_2)
                config.PERSONALITY_3=personality_config.get('personality_3_probability',config.PERSONALITY_3)

            if "emoji" in toml_dict:
                emoji_config = toml_dict["emoji"]
                config.EMOJI_CHECK_INTERVAL = emoji_config.get("check_interval", config.EMOJI_CHECK_INTERVAL)
                config.EMOJI_REGISTER_INTERVAL = emoji_config.get("register_interval", config.EMOJI_REGISTER_INTERVAL)
                config.EMOJI_CHECK_PROMPT = emoji_config.get('check_prompt',config.EMOJI_CHECK_PROMPT)
                config.EMOJI_SAVE = emoji_config.get('auto_save',config.EMOJI_SAVE)
                config.EMOJI_CHECK = emoji_config.get('enable_check',config.EMOJI_CHECK)
            
            if "cq_code" in toml_dict:
                cq_code_config = toml_dict["cq_code"]
                config.ENABLE_PIC_TRANSLATE = cq_code_config.get("enable_pic_translate", config.ENABLE_PIC_TRANSLATE)
            
            # 机器人基础配置
            if "bot" in toml_dict:
                bot_config = toml_dict["bot"]
                bot_qq = bot_config.get("qq")
                if bot_qq:
                    config.BOT_QQ = int(bot_qq)
                config.BOT_NICKNAME = bot_config.get("nickname", config.BOT_NICKNAME)
                
            if "response" in toml_dict:
                response_config = toml_dict["response"]
                config.MODEL_R1_PROBABILITY = response_config.get("model_r1_probability", config.MODEL_R1_PROBABILITY)
                config.MODEL_V3_PROBABILITY = response_config.get("model_v3_probability", config.MODEL_V3_PROBABILITY)
                config.MODEL_R1_DISTILL_PROBABILITY = response_config.get("model_r1_distill_probability", config.MODEL_R1_DISTILL_PROBABILITY)
                config.max_response_length = response_config.get("max_response_length", config.max_response_length)
                
            # 加载模型配置
            if "model" in toml_dict:
                model_config = toml_dict["model"]
                
                if "llm_reasoning" in model_config:
                    config.llm_reasoning = model_config["llm_reasoning"]
                
                if "llm_reasoning_minor" in model_config:
                    config.llm_reasoning_minor = model_config["llm_reasoning_minor"]
                
                if "llm_normal" in model_config:
                    config.llm_normal = model_config["llm_normal"]
                
                if "llm_normal_minor" in model_config:
                    config.llm_normal_minor = model_config["llm_normal_minor"]
                    
                if "llm_topic_judge" in model_config:
                    config.llm_topic_judge = model_config["llm_topic_judge"]
                
                if "llm_summary_by_topic" in model_config:
                    config.llm_summary_by_topic = model_config["llm_summary_by_topic"]
                
                if "llm_emotion_judge" in model_config:
                    config.llm_emotion_judge = model_config["llm_emotion_judge"]
                
                if "vlm" in model_config:
                    config.vlm = model_config["vlm"]
                    
                if "embedding" in model_config:
                    config.embedding = model_config["embedding"]
                
                if "moderation" in model_config:
                    config.moderation = model_config["moderation"]
                
            # 消息配置
            if "message" in toml_dict:
                msg_config = toml_dict["message"]
                config.MIN_TEXT_LENGTH = msg_config.get("min_text_length", config.MIN_TEXT_LENGTH)
                config.MAX_CONTEXT_SIZE = msg_config.get("max_context_size", config.MAX_CONTEXT_SIZE)
                config.emoji_chance = msg_config.get("emoji_chance", config.emoji_chance)
                config.ban_words=msg_config.get("ban_words",config.ban_words)
                config.thinking_timeout = msg_config.get("thinking_timeout", config.thinking_timeout)
                config.response_willing_amplifier = msg_config.get("response_willing_amplifier", config.response_willing_amplifier)
                config.response_interested_rate_amplifier = msg_config.get("response_interested_rate_amplifier", config.response_interested_rate_amplifier)
                config.down_frequency_rate = msg_config.get("down_frequency_rate", config.down_frequency_rate)

            if "memory" in toml_dict:
                memory_config = toml_dict["memory"]
                config.build_memory_interval = memory_config.get("build_memory_interval", config.build_memory_interval)
                config.forget_memory_interval = memory_config.get("forget_memory_interval", config.forget_memory_interval)
                
            if "mood" in toml_dict:
                mood_config = toml_dict["mood"]
                config.mood_update_interval = mood_config.get("mood_update_interval", config.mood_update_interval)
                config.mood_decay_rate = mood_config.get("mood_decay_rate", config.mood_decay_rate)
                config.mood_intensity_factor = mood_config.get("mood_intensity_factor", config.mood_intensity_factor)
            
            # 群组配置
            if "groups" in toml_dict:
                groups_config = toml_dict["groups"]
                
                # 處理允許的群組 - 支持 int 和 str 類型
                print(f"允許的群組: {groups_config.get('talk_allowed', [])}")
                allowed_groups = groups_config.get("talk_allowed", [])
                config.talk_allowed_groups = set()
                for group in allowed_groups:
                    try:
                        if isinstance(group, int):
                            config.talk_allowed_groups.add(group)
                        else:
                            # 嘗試轉換為整數 (QQ群號)，如果失敗則保留為字符串 (Telegram群ID)
                            try:
                                config.talk_allowed_groups.add(int(group))
                            except (ValueError, TypeError):
                                config.talk_allowed_groups.add(group)
                    except Exception as e:
                        logger.warning(f"群組ID格式錯誤: {group}, {e}")
                
                # 處理降頻群組
                freq_down_groups = groups_config.get("talk_frequency_down", [])
                config.talk_frequency_down_groups = set()
                for group in freq_down_groups:
                    try:
                        if isinstance(group, int):
                            config.talk_frequency_down_groups.add(group)
                        else:
                            try:
                                config.talk_frequency_down_groups.add(int(group))
                            except (ValueError, TypeError):
                                config.talk_frequency_down_groups.add(group)
                    except Exception as e:
                        logger.warning(f"群組ID格式錯誤: {group}, {e}")
                
                # 處理屏蔽用戶
                ban_users = groups_config.get("ban_user_id", [])
                config.ban_user_id = set()
                for user in ban_users:
                    try:
                        if isinstance(user, int):
                            config.ban_user_id.add(user)
                        else:
                            try:
                                config.ban_user_id.add(int(user))
                            except (ValueError, TypeError):
                                config.ban_user_id.add(user)
                    except Exception as e:
                        logger.warning(f"用戶ID格式錯誤: {user}, {e}")
            
            if "others" in toml_dict:
                others_config = toml_dict["others"]
                config.enable_advance_output = others_config.get("enable_advance_output", config.enable_advance_output)
                config.enable_kuuki_read = others_config.get("enable_kuuki_read", config.enable_kuuki_read)
            
            logger.success(f"成功加载配置文件: {config_path}")
                
        return config 
    
# 获取配置文件路径

bot_config_floder_path = BotConfig.get_config_dir()
print(f"正在品鉴配置文件目录: {bot_config_floder_path}")
bot_config_path = os.path.join(bot_config_floder_path, "bot_config.toml")
if os.path.exists(bot_config_path):
    # 如果开发环境配置文件不存在，则使用默认配置文件
    print(f"异常的新鲜，异常的美味: {bot_config_path}")
    logger.info("使用bot配置文件")
else:
    logger.info("没有找到美味")

global_config = BotConfig.load_config(config_path=bot_config_path)


if not global_config.enable_advance_output:
    logger.remove()
    pass

