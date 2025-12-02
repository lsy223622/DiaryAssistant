#!/usr/bin/env python3
"""
日志管理模块
"""

import logging
import sys
from datetime import datetime
from typing import Optional

from config import Config


class Logger:
    """统一日志管理类"""
    
    _loggers = {}
    
    @classmethod
    def get_logger(cls, name: str = "DiaryAssistant") -> logging.Logger:
        """获取或创建logger实例"""
        if name in cls._loggers:
            return cls._loggers[name]
        
        logger = logging.getLogger(name)
        logger.setLevel(getattr(logging, Config.LOG_LEVEL))
        
        # 避免重复添加handler
        if logger.handlers:
            return logger
        
        # 控制台handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            "%(levelname)s: %(message)s"
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
        
        # 文件handler
        log_file = Config.LOG_DIR / f"app_{datetime.now().strftime('%Y%m%d')}.log"
        try:
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            file_formatter = logging.Formatter(
                Config.LOG_FORMAT,
                datefmt=Config.LOG_DATE_FORMAT
            )
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            logger.warning(f"无法创建日志文件: {e}")
        
        cls._loggers[name] = logger
        return logger
    
    @classmethod
    def log_separator(cls, logger: logging.Logger, char: str = "=", length: Optional[int] = None):
        """打印分隔线"""
        if length is None:
            length = Config.SEPARATOR_LENGTH
        logger.info(char * length)
