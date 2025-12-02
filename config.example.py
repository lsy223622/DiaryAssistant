#!/usr/bin/env python3
"""
配置管理模块
"""

import os
from pathlib import Path
from typing import Optional


class Config:
    """应用配置类"""
    
    # API配置
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "<YOUR_API_KEY_HERE>")
    DEEPSEEK_API_URL: str = "https://api.deepseek.com/v1/chat/completions"
    DEEPSEEK_MODEL: str = "deepseek-reasoner"
    
    # API参数
    API_TIMEOUT: int = 180
    API_TEMPERATURE: float = 0.75
    API_MAX_TOKENS: int = 8000
    
    # 路径配置
    BASE_DIR: Path = Path(__file__).parent
    DIARY_DIR: Path = BASE_DIR / "Daily"
    OUTPUT_DIR: Path = BASE_DIR / "Weekly_Analysis"
    WEEKLY_SUMMARY_DIR: Path = BASE_DIR / "Weekly_Summary"
    LOG_DIR: Path = BASE_DIR / "log"
    
    # 日志配置
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"
    
    # 显示配置
    PREVIEW_LENGTH: int = 500
    SEPARATOR_LENGTH: int = 60
        
    # 调试配置
    PAUSE_AFTER_DAILY_EVALUATION: bool = False
    
    @classmethod
    def validate(cls) -> tuple[bool, Optional[str]]:
        """验证配置是否有效"""
        if not cls.DEEPSEEK_API_KEY:
            return False, "DEEPSEEK_API_KEY 未设置。请设置环境变量或在 config.py 中配置"
        
        # 创建必要的目录
        try:
            cls.OUTPUT_DIR.mkdir(exist_ok=True)
            cls.WEEKLY_SUMMARY_DIR.mkdir(exist_ok=True)
            cls.LOG_DIR.mkdir(exist_ok=True)
        except Exception as e:
            return False, f"创建目录失败: {e}"
        
        # 检查日记目录
        if not cls.DIARY_DIR.exists():
            return False, f"日记目录不存在: {cls.DIARY_DIR}\n请将日记文件放在该目录下"
        
        return True, None
    
    @classmethod
    def get_api_key(cls) -> str:
        """获取API密钥（优先从环境变量读取）"""
        # 请通过环境变量 `DEEPSEEK_API_KEY` 设置密钥。
        # 如果未设置，将返回空字符串，调用方应处理无密钥的情况。
        return cls.DEEPSEEK_API_KEY
