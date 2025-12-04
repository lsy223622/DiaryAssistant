#!/usr/bin/env python3
"""
清除日记中的 AI 评价脚本
功能：备份日记并移除 "AI 说" 及其之后的内容
"""

import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent))

from config import Config
from logger import Logger


@dataclass
class ClearResult:
    """清理结果"""
    processed: int = 0
    skipped: int = 0
    backup_dir: Path = None


class AICleaner:
    """AI 评价清理器"""
    
    AI_VARIANTS = ("AI 说", "AI说", "AI评价", "AI建议")
    HEADER_PATTERN = re.compile(
        r'^#+\s*(' + '|'.join(map(re.escape, AI_VARIANTS)) + r')\s*$',
        re.IGNORECASE
    )
    
    def __init__(self):
        self.logger = Logger.get_logger("ClearAI")
    
    def run(self) -> None:
        """执行清理任务"""
        Logger.log_separator(self.logger)
        self.logger.info("🧹 开始执行清除 AI 评价任务")
        
        # 收集文件
        files = self._collect_files()
        if not files:
            self.logger.warning("没有找到任何日记文件")
            return
        
        self.logger.info(f"🔍 找到 {len(files)} 个日记文件")
        
        # 备份
        backup_dir = self._backup_files(files)
        if not backup_dir:
            return
        
        # 清理
        result = self._clear_files(files)
        result.backup_dir = backup_dir
        
        self._print_summary(result)
    
    def _collect_files(self) -> List[Path]:
        """收集所有日记文件"""
        files = []
        for diary_dir in (Config.DIARY_DIR, Config.DIARY_OLD_DIR):
            if diary_dir.exists():
                files.extend(diary_dir.glob("*.md"))
            else:
                self.logger.warning(f"目录不存在: {diary_dir}")
        return files
    
    def _backup_files(self, files: List[Path]) -> Path:
        """备份文件到 log 目录"""
        backup_dir = Config.LOG_DIR / f"backup_{datetime.now():%Y%m%d_%H%M%S}"
        
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"📦 创建备份目录: {backup_dir}")
        except Exception as e:
            self.logger.error(f"创建备份目录失败: {e}")
            return None
        
        count = 0
        for f in files:
            try:
                shutil.copy2(f, backup_dir / f.name)
                count += 1
            except Exception as e:
                self.logger.error(f"备份失败 {f.name}: {e}")
        
        self.logger.info(f"✅ 成功备份 {count} 个文件")
        Logger.log_separator(self.logger)
        return backup_dir
    
    def _clear_files(self, files: List[Path]) -> ClearResult:
        """清理文件中的 AI 评价"""
        result = ClearResult()
        
        for file_path in files:
            if self._clear_single_file(file_path):
                result.processed += 1
                self.logger.info(f"✂️  已清除: {file_path.name}")
            else:
                result.skipped += 1
        
        return result
    
    def _clear_single_file(self, file_path: Path) -> bool:
        """清理单个文件，返回是否有修改"""
        try:
            lines = file_path.read_text(encoding='utf-8').splitlines(keepends=True)
            new_lines = []
            
            for line in lines:
                if self.HEADER_PATTERN.match(line.strip()):
                    break
                new_lines.append(line)
            else:
                return False  # 未找到 AI 标记
            
            # 移除末尾空行
            while new_lines and not new_lines[-1].strip():
                new_lines.pop()
            
            # 写回（确保末尾换行）
            content = ''.join(new_lines)
            if content and not content.endswith('\n'):
                content += '\n'
            file_path.write_text(content, encoding='utf-8')
            return True
            
        except Exception as e:
            self.logger.error(f"处理出错 {file_path.name}: {e}")
            return False
    
    def _print_summary(self, result: ClearResult) -> None:
        """打印处理结果摘要"""
        Logger.log_separator(self.logger)
        self.logger.info("🎉 处理完成")
        self.logger.info(f"   - 已清除: {result.processed} 个文件")
        self.logger.info(f"   - 未发现/跳过: {result.skipped} 个文件")
        self.logger.info(f"   - 备份位置: {result.backup_dir}")


def clear_ai_comments():
    """入口函数"""
    AICleaner().run()


if __name__ == "__main__":
    clear_ai_comments()
