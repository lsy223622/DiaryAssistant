#!/usr/bin/env python3
"""日志管理模块"""

import logging
import sys
from datetime import datetime
from typing import Dict, Optional

from config import Config


class Logger:
    """统一日志管理类"""
    
    _loggers: Dict[str, logging.Logger] = {}
    _CONSOLE_FORMAT = "%(levelname)s: %(message)s"
    
    @classmethod
    def get_logger(cls, name: str = "DiaryAssistant") -> logging.Logger:
        """获取或创建logger实例"""
        if name in cls._loggers:
            return cls._loggers[name]
        
        logger = logging.getLogger(name)
        logger.setLevel(getattr(logging, Config.LOG_LEVEL))
        
        if not logger.handlers:
            cls._setup_handlers(logger)
        
        cls._loggers[name] = logger
        return logger
    
    @classmethod
    def _setup_handlers(cls, logger: logging.Logger) -> None:
        """设置日志处理器"""
        # 控制台
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(logging.INFO)
        console.setFormatter(logging.Formatter(cls._CONSOLE_FORMAT))
        logger.addHandler(console)
        
        # 文件
        cls._add_file_handler(logger)
    
    @classmethod
    def _add_file_handler(cls, logger: logging.Logger) -> None:
        """添加文件处理器"""
        log_file = Config.LOG_DIR / f"app_{datetime.now():%Y%m%d}.log"
        try:
            handler = logging.FileHandler(log_file, encoding='utf-8')
            handler.setLevel(logging.DEBUG)
            handler.setFormatter(logging.Formatter(
                Config.LOG_FORMAT, datefmt=Config.LOG_DATE_FORMAT
            ))
            logger.addHandler(handler)
        except Exception as e:
            logger.warning(f"无法创建日志文件: {e}")
    
    @classmethod
    def log_separator(cls, logger: logging.Logger, char: str = "=", 
                      length: Optional[int] = None) -> None:
        """打印分隔线"""
        logger.info(char * (length or Config.SEPARATOR_LENGTH))
