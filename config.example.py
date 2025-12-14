#!/usr/bin/env python3
"""配置管理模块 - 示例配置文件，请复制为 config.py 并修改"""

import os
from pathlib import Path
from typing import Optional, Tuple


class Config:
    """应用配置类"""
    
    # ===== API 配置 =====
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "<YOUR_API_KEY_HERE>")
    DEEPSEEK_API_URL: str = "https://api.deepseek.com/v1/chat/completions"
    DEEPSEEK_MODEL: str = "deepseek-reasoner"
    API_TIMEOUT: int = 180
    API_TEMPERATURE: float = 1.0
    API_MAX_TOKENS: int = 8000
    
    # ===== 路径配置 =====
    BASE_DIR: Path = Path(__file__).parent
    DIARY_DIR: Path = BASE_DIR / "Daily"
    DIARY_OLD_DIR: Path = BASE_DIR / "Daily_Old"
    OUTPUT_DIR: Path = BASE_DIR / "Weekly_Analysis"
    WEEKLY_SUMMARY_DIR: Path = BASE_DIR / "Weekly_Summary"
    LOG_DIR: Path = BASE_DIR / "log"
    
    # ===== 日志配置 =====
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"
    
    # ===== 显示配置 =====
    PREVIEW_LENGTH: int = 500
    SEPARATOR_LENGTH: int = 60
    
    # ===== 调试配置 =====
    PAUSE_AFTER_DAILY_EVALUATION: bool = False
    ENABLE_MEMORY_CONSOLIDATION: bool = True
    
    # ===== 需要创建的目录列表 =====
    _REQUIRED_DIRS = ("OUTPUT_DIR", "WEEKLY_SUMMARY_DIR", "LOG_DIR")
    
    @classmethod
    def validate(cls) -> Tuple[bool, Optional[str]]:
        """验证配置是否有效"""
        if not cls.DEEPSEEK_API_KEY:
            return False, "DEEPSEEK_API_KEY 未设置。请设置环境变量或在 config.py 中配置"
        
        if error := cls._ensure_directories():
            return False, error
        
        if not cls.DIARY_DIR.exists():
            return False, f"日记目录不存在: {cls.DIARY_DIR}\n请将日记文件放在该目录下"
        
        return True, None
    
    @classmethod
    def _ensure_directories(cls) -> Optional[str]:
        """确保必要目录存在"""
        try:
            for attr in cls._REQUIRED_DIRS:
                getattr(cls, attr).mkdir(exist_ok=True)
            return None
        except Exception as e:
            return f"创建目录失败: {e}"
    
    @classmethod
    def get_api_headers(cls) -> dict:
        """获取 API 请求头"""
        return {
            "Authorization": f"Bearer {cls.DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
