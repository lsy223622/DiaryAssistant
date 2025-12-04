#!/usr/bin/env python3
"""
日记读取和解析模块
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from logger import Logger


# ============================================================
# 配置类
# ============================================================

@dataclass
class SectionVariants:
    """日记各部分的标题变体配置"""
    todo: List[str] = field(default_factory=lambda: ["今日待办", "待办", "todo", "Todo", "TODOs"])
    record: List[str] = field(default_factory=lambda: ["随手记录", "记录", "record", "Record", "日志", "流水"])
    thought: List[str] = field(default_factory=lambda: ["心情", "心情和想法", "想法", "thought", "Thought", "感悟", "思考"])
    attachment: List[str] = field(default_factory=lambda: ["附件", "附件 / 链接", "attachments", "Attachments", "附件和链接"])
    ai_comment: List[str] = field(default_factory=lambda: ["AI 说", "AI说", "AI评价", "AI建议"])


# ============================================================
# Markdown 解析器
# ============================================================

class MarkdownParser:
    """Markdown 文档解析工具类"""
    
    # 列表项匹配模式（预编译提升性能）
    LIST_PATTERNS = [
        re.compile(r'^[-*]\s*(.+)$'),       # - 或 * 开头
        re.compile(r'^\d+\.\s*(.+)$'),       # 数字开头
        re.compile(r'^\[\s*\]\s*(.+)$'),     # [ ] 待办格式
        re.compile(r'^\[\s*x\s*\]\s*(.+)$', re.IGNORECASE),  # [x] 完成格式
    ]
    
    @staticmethod
    def extract_title(content: str, default: str = "") -> str:
        """提取文档标题（第一个 # 开头的行）"""
        lines = content.strip().split('\n')
        if lines and lines[0].startswith('#'):
            return lines[0].lstrip('#').strip()
        return default
    
    @staticmethod
    def find_section_boundary(content: str, section_names: List[str]) -> Optional[Tuple[int, int]]:
        """查找指定章节的边界，返回 (start, end) 或 None"""
        for name in section_names:
            pattern = rf'^#+\s*{re.escape(name)}\s*$'
            match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)
            if match:
                start = match.end()
                next_match = re.search(r'^#+\s*', content[start:], re.MULTILINE)
                end = start + next_match.start() if next_match else len(content)
                return (start, end)
        return None
    
    @staticmethod
    def find_first_marker_position(content: str, markers: List[str]) -> int:
        """查找第一个匹配标记的位置，未找到返回内容长度"""
        min_pos = len(content)
        for marker in markers:
            pattern = rf'^#+\s*{re.escape(marker)}\s*$'
            match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)
            if match and match.start() < min_pos:
                min_pos = match.start()
        return min_pos
    
    @classmethod
    def extract_section_text(cls, content: str, section_names: List[str]) -> str:
        """提取章节的纯文本内容"""
        boundary = cls.find_section_boundary(content, section_names)
        return content[boundary[0]:boundary[1]].strip() if boundary else ""
    
    @classmethod
    def extract_section_items(cls, content: str, section_names: List[str]) -> List[str]:
        """提取章节中的列表项（去重）"""
        text = cls.extract_section_text(content, section_names)
        if not text:
            return []
        return cls._deduplicate(cls._parse_list_items(text))
    
    @classmethod
    def _parse_list_items(cls, text: str) -> List[str]:
        """从文本中解析列表项"""
        items = []
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue
            for pattern in cls.LIST_PATTERNS:
                match = pattern.match(line)
                if match:
                    items.append(match.group(1).strip())
                    break
        return items
    
    @staticmethod
    def _deduplicate(items: List[str]) -> List[str]:
        """列表去重，保持顺序"""
        seen = set()
        return [x for x in items if x and x not in seen and not seen.add(x)]


# ============================================================
# 日记条目
# ============================================================

class DiaryEntry:
    """日记条目类"""
    
    def __init__(self, date: datetime, file_path: Path):
        self.date = date
        self.file_path = file_path
        self.title: str = ""
        self.todos: List[str] = []
        self.records: List[str] = []
        self.thoughts: List[str] = []
        self.ai_comment: str = ""
        self.content: str = ""
        self.raw_content: str = ""
    
    def __str__(self) -> str:
        return f"DiaryEntry({self.date.strftime('%Y-%m-%d')})"

    def format_for_ai(self) -> str:
        """格式化日记内容，用于发送给 AI"""
        sections = [
            ("## 待办事项", self.todos),
            ("## 记录", self.records),
            ("## 想法", self.thoughts),
        ]
        
        parts = [f"# {self.date.strftime('%Y年%m月%d日')} {self.title}", ""]
        for header, items in sections:
            parts.append(header)
            parts.extend(f"- {item}" for item in items) if items else parts.append("无")
            parts.append("")
        
        return "\n".join(parts)


# ============================================================
# 日记读取器
# ============================================================

class DiaryReader:
    """读取和解析日记文件"""
    
    def __init__(self, diary_dirs: List[Path], variants: Optional[SectionVariants] = None):
        self.diary_dirs = diary_dirs
        self.logger = Logger.get_logger("DiaryReader")
        self.variants = variants or SectionVariants()
    
    def read_diary_file(self, file_path: Path) -> Optional[DiaryEntry]:
        """读取单个日记文件"""
        if not file_path.exists():
            self.logger.debug(f"文件不存在: {file_path}")
            return None
        
        date = self._parse_date_from_filename(file_path)
        if not date:
            return None
        
        content = self._read_file_content(file_path)
        if content is None:
            return None
        
        entry = DiaryEntry(date, file_path)
        entry.raw_content = content
        self._parse_diary_content(entry, content)
        return entry
    
    def _parse_date_from_filename(self, file_path: Path) -> Optional[datetime]:
        """从文件名解析日期"""
        try:
            return datetime.strptime(file_path.stem, "%Y-%m-%d")
        except ValueError as e:
            self.logger.warning(f"无法解析文件名中的日期: {file_path.name} - {e}")
            return None
    
    def _read_file_content(self, file_path: Path) -> Optional[str]:
        """读取文件内容"""
        try:
            return file_path.read_text(encoding='utf-8', errors='ignore')
        except Exception as e:
            self.logger.error(f"读取文件失败 {file_path}: {e}")
            return None
    
    def _parse_diary_content(self, entry: DiaryEntry, content: str):
        """解析日记内容"""
        # 提取标题
        default_title = f"日记 {entry.date.strftime('%Y-%m-%d')}"
        entry.title = MarkdownParser.extract_title(content, default_title)
        
        # 截取附件前的主要内容
        cut_pos = MarkdownParser.find_first_marker_position(content, self.variants.attachment)
        main_content = content[:cut_pos].strip()
        entry.content = main_content
        
        # 提取各部分
        entry.todos = MarkdownParser.extract_section_items(main_content, self.variants.todo)
        entry.records = MarkdownParser.extract_section_items(main_content, self.variants.record)
        entry.thoughts = MarkdownParser.extract_section_items(main_content, self.variants.thought)
        
        # AI 评论从完整内容提取（可能在附件之后）
        entry.ai_comment = MarkdownParser.extract_section_text(content, self.variants.ai_comment)
    
    def append_ai_comment(self, file_path: Path, comment: str) -> bool:
        """向日记文件追加 AI 评论"""
        try:
            with file_path.open('a', encoding='utf-8') as f:
                f.write(f"\n\n## AI 说\n\n{comment}\n")
            return True
        except Exception as e:
            self.logger.error(f"追加 AI 评论失败 {file_path}: {e}")
            return False
    
    def get_all_diaries(self) -> List[DiaryEntry]:
        """获取所有日记"""
        md_files = self._collect_diary_files()
        if not md_files:
            return []
        
        diaries = []
        for file_path in md_files:
            if file_path.stem.endswith('x'):  # 跳过未完成日记
                continue
            if diary := self.read_diary_file(file_path):
                diaries.append(diary)
        
        diaries.sort(key=lambda x: x.date)
        self.logger.info(f"成功解析 {len(diaries)}/{len(md_files)} 篇日记")
        return diaries
    
    def _collect_diary_files(self) -> List[Path]:
        """收集所有日记文件"""
        md_files = []
        for diary_dir in self.diary_dirs:
            if not diary_dir.exists():
                self.logger.warning(f"目录不存在: {diary_dir}")
                continue
            try:
                files = list(diary_dir.glob("*.md"))
                md_files.extend(files)
                self.logger.info(f"在 {diary_dir.name} 中找到 {len(files)} 个日记文件")
            except Exception as e:
                self.logger.error(f"读取日记目录失败 {diary_dir}: {e}")
        
        self.logger.info(f"总共找到 {len(md_files)} 个日记文件")
        return md_files
