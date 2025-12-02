#!/usr/bin/env python3
"""
日记读取和解析模块
"""

import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from logger import Logger


class DiaryEntry:
    """日记条目类"""
    def __init__(self, date: datetime, file_path: Path):
        self.date = date
        self.file_path = file_path
        self.title = ""
        self.todos = []
        self.records = []
        self.thoughts = []
        self.content = ""
        self.raw_content = ""
    
    def __str__(self):
        return f"DiaryEntry({self.date.strftime('%Y-%m-%d')})"

class DiaryReader:
    """读取和解析日记文件"""
    
    def __init__(self, diary_dir: Path):
        self.diary_dir = diary_dir
        self.logger = Logger.get_logger("DiaryReader")
        
        # 支持的所有标题变体
        self.todo_variants = ["今日待办", "待办", "todo", "Todo", "TODOs"]
        self.record_variants = ["随手记录", "记录", "record", "Record", "日志", "流水"]
        self.thought_variants = ["心情", "心情和想法", "想法", "thought", "Thought", "感悟", "思考"]
        self.attachment_variants = ["附件", "附件 / 链接", "attachments", "Attachments", "附件和链接"]
    
    def read_diary_file(self, file_path: Path) -> Optional[DiaryEntry]:
        """读取单个日记文件"""
        if not file_path.exists():
            self.logger.debug(f"文件不存在: {file_path}")
            return None
        
        # 从文件名提取日期
        try:
            date_str = file_path.stem  # 去掉扩展名
            date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError as e:
            self.logger.warning(f"无法解析文件名中的日期: {file_path.name} - {e}")
            return None
        
        # 创建日记条目
        entry = DiaryEntry(date, file_path)
        
        # 读取文件内容
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except IOError as e:
            self.logger.error(f"读取文件失败 {file_path}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"读取文件时发生未知错误 {file_path}: {e}")
            return None
        
        entry.raw_content = content
        
        # 解析日记内容
        self._parse_diary_content(entry, content)
        
        return entry
    
    def _parse_diary_content(self, entry: DiaryEntry, content: str):
        """解析日记内容"""
        # 提取标题（第一行）
        lines = content.strip().split('\n')
        if lines and lines[0].startswith('#'):
            # 移除开头的#和空格
            entry.title = lines[0].replace('#', '').strip()
        else:
            entry.title = f"日记 {entry.date.strftime('%Y-%m-%d')}"
        
        # 找到附件分割点（忽略附件及之后的内容）
        cut_index = len(content)
        for marker in self.attachment_variants:
            # 匹配 # 附件 或 ## 附件
            pattern = rf'^#+\s*{re.escape(marker)}\s*$'
            match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)
            if match:
                idx = match.start()
                if idx < cut_index:
                    cut_index = idx
        
        # 提取附件前的内容
        main_content = content[:cut_index].strip()
        entry.content = main_content
        
        # 提取各个部分
        entry.todos = self._extract_section(main_content, self.todo_variants)
        entry.records = self._extract_section(main_content, self.record_variants)
        entry.thoughts = self._extract_section(main_content, self.thought_variants)
    
    def _extract_section(self, content: str, section_names: List[str]) -> List[str]:
        """提取特定部分的内容"""
        items = []
        
        for section_name in section_names:
            # 尝试匹配 ## 标题 或 # 标题
            patterns = [
                rf'^##\s*{re.escape(section_name)}\s*$',
                rf'^#\s*{re.escape(section_name)}\s*$'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)
                if match:
                    # 提取从这个标题到下一个标题或文件结束的内容
                    start_pos = match.end()
                    
                    # 查找下一个标题开始位置
                    next_title_pattern = r'^#+\s*'
                    next_match = re.search(next_title_pattern, content[start_pos:], re.MULTILINE)
                    
                    if next_match:
                        end_pos = start_pos + next_match.start()
                        section_text = content[start_pos:end_pos]
                    else:
                        section_text = content[start_pos:]
                    
                    # 提取列表项
                    section_items = self._extract_list_items(section_text)
                    items.extend(section_items)
                    break  # 找到第一个匹配就跳出
        
        # 去重
        seen = set()
        unique_items = []
        for item in items:
            if item.strip() and item.strip() not in seen:
                seen.add(item.strip())
                unique_items.append(item.strip())
        
        return unique_items
    
    def _extract_list_items(self, text: str) -> List[str]:
        """从文本中提取列表项"""
        items = []
        
        # 匹配多种列表格式
        patterns = [
            r'^[-*]\s*(.+)$',  # - 或 * 开头的
            r'^\d+\.\s*(.+)$',  # 数字开头的
            r'^\[\s*\].\s*(.+)$',  # [ ] 待办格式
            r'^\[\s*x\s*\].\s*(.+)$',  # [x] 完成格式
        ]
        
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            for pattern in patterns:
                match = re.match(pattern, line)
                if match:
                    items.append(match.group(1).strip())
                    break
        
        return items
    
    def get_all_diaries(self) -> List[DiaryEntry]:
        """获取所有日记"""
        diaries = []
        
        # 查找所有md文件
        try:
            md_files = list(self.diary_dir.glob("*.md"))
            self.logger.info(f"找到 {len(md_files)} 个日记文件")
        except Exception as e:
            self.logger.error(f"读取日记目录失败: {e}")
            return diaries
        
        # 逐个读取
        success_count = 0
        for file_path in md_files:
            diary = self.read_diary_file(file_path)
            if diary:
                diaries.append(diary)
                success_count += 1
        
        # 按日期排序（从早到晚）
        diaries.sort(key=lambda x: x.date)
        
        self.logger.info(f"成功解析 {success_count}/{len(md_files)} 篇日记")
        if success_count < len(md_files):
            self.logger.warning(f"有 {len(md_files) - success_count} 篇日记解析失败")
        
        return diaries
    
    def format_diary_for_ai(self, diary: DiaryEntry) -> str:
        """格式化日记内容，用于发送给AI"""
        formatted = f"""# {diary.date.strftime('%Y年%m月%d日')} {diary.title}

## 待办事项
"""
        if diary.todos:
            for todo in diary.todos:
                formatted += f"- {todo}\n"
        else:
            formatted += "无\n"
        
        formatted += "\n## 记录\n"
        if diary.records:
            for record in diary.records:
                formatted += f"- {record}\n"
        else:
            formatted += "无\n"
        
        formatted += "\n## 想法\n"
        if diary.thoughts:
            for thought in diary.thoughts:
                formatted += f"- {thought}\n"
        else:
            formatted += "无\n"
        
        return formatted