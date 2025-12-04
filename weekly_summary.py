#!/usr/bin/env python3
"""
每周总结管理模块
"""

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from diary_reader import DiaryEntry
from logger import Logger


class WeekInfo:
    """周信息类"""
    
    def __init__(self, year: int, week: int, start_date: datetime, end_date: datetime):
        self.year = year
        self.week = week
        self.start_date = start_date
        self.end_date = end_date
        self.diaries: List[DiaryEntry] = []
    
    def __str__(self) -> str:
        return f"{self.year}年第{self.week}周 ({self.start_date.strftime('%Y-%m-%d')} 至 {self.end_date.strftime('%Y-%m-%d')})"
    
    def get_filename(self) -> str:
        """获取总结文件名"""
        return f"{self.year}_W{self.week:02d}_{self.start_date.strftime('%Y%m%d')}-{self.end_date.strftime('%Y%m%d')}.md"

    def format_for_ai(self) -> str:
        """格式化周日记内容用于 AI 生成总结"""
        header = f"""# {self.year}年第{self.week}周日记
**时间范围**: {self.start_date.strftime('%Y年%m月%d日')} 至 {self.end_date.strftime('%Y年%m月%d日')}

"""
        parts = [header]
        for diary in self.diaries:
            parts.extend([diary.format_for_ai(), "", "="*50, ""])
        return "\n".join(parts)


class WeeklySummaryManager:
    """每周总结管理器"""
    
    # 文件名解析正则
    FILENAME_PATTERN = re.compile(r'(\d{4})_W(\d{2})_(\d{8})-(\d{8})\.md')
    
    def __init__(self, weekly_summary_dir: Path):
        self.weekly_summary_dir = weekly_summary_dir
        self.logger = Logger.get_logger("WeeklySummary")
        self.weekly_summary_dir.mkdir(exist_ok=True)
    
    @staticmethod
    def get_week_info(date: datetime) -> WeekInfo:
        """获取指定日期所在周的信息（周一到周日）"""
        monday = date - timedelta(days=date.weekday())
        sunday = monday + timedelta(days=6)
        iso_year, iso_week, _ = monday.isocalendar()
        return WeekInfo(iso_year, iso_week, monday, sunday)
    
    def group_diaries_by_week(self, diaries: List[DiaryEntry]) -> List[WeekInfo]:
        """将日记按周分组"""
        if not diaries:
            return []
        
        week_dict: Dict[Tuple[int, int], WeekInfo] = {}
        for diary in diaries:
            week_info = self.get_week_info(diary.date)
            key = (week_info.year, week_info.week)
            if key not in week_dict:
                week_dict[key] = week_info
            week_dict[key].diaries.append(diary)
        
        weeks = sorted(week_dict.values(), key=lambda w: w.start_date)
        self.logger.info(f"日记已分组为 {len(weeks)} 周")
        return weeks
    
    def is_week_complete(self, week_info: WeekInfo) -> bool:
        """检查一周是否已完整经过"""
        return week_info.end_date.date() < datetime.now().date()
    
    def has_summary(self, week_info: WeekInfo) -> bool:
        """检查某周是否已有总结"""
        return self.get_summary_path(week_info).exists()
    
    def get_summary_path(self, week_info: WeekInfo) -> Path:
        """获取总结文件路径"""
        return self.weekly_summary_dir / week_info.get_filename()
    
    def get_weeks_need_summary(self, weeks: List[WeekInfo]) -> List[WeekInfo]:
        """获取需要生成总结的周"""
        return [w for w in weeks 
                if self.is_week_complete(w) and w.diaries and not self.has_summary(w)]
    
    def get_all_summaries(self) -> List[Tuple[WeekInfo, str]]:
        """获取所有已有的周总结内容"""
        summaries = []
        try:
            for filepath in sorted(self.weekly_summary_dir.glob("*.md")):
                week_info = self._parse_filename(filepath)
                if week_info:
                    content = filepath.read_text(encoding='utf-8')
                    summaries.append((week_info, content))
        except Exception as e:
            self.logger.error(f"读取总结目录失败: {e}")
        return summaries
    
    def _parse_filename(self, filepath: Path) -> Optional[WeekInfo]:
        """从文件名解析周信息"""
        match = self.FILENAME_PATTERN.match(filepath.name)
        if not match:
            return None
        
        try:
            year, week = int(match.group(1)), int(match.group(2))
            start_date = datetime.strptime(match.group(3), '%Y%m%d')
            end_date = datetime.strptime(match.group(4), '%Y%m%d')
            return WeekInfo(year, week, start_date, end_date)
        except ValueError:
            return None
    
    def save_summary(self, week_info: WeekInfo, summary: str):
        """保存周总结"""
        filepath = self.get_summary_path(week_info)
        
        meta = f"""# {week_info.year}年第{week_info.week}周总结
**时间范围**: {week_info.start_date.strftime('%Y年%m月%d日')} 至 {week_info.end_date.strftime('%Y年%m月%d日')}
**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**日记数量**: {len(week_info.diaries)} 篇

---

"""
        try:
            filepath.write_text(meta + summary, encoding='utf-8')
            self.logger.info(f"周总结已保存: {filepath}")
        except Exception as e:
            self.logger.error(f"保存周总结失败: {e}")

    def get_historical_summaries(self, current_date: datetime) -> List[Tuple[WeekInfo, str]]:
        """获取指定日期之前的历史周总结"""
        current_week = self.get_week_info(current_date)
        return [(w, s) for w, s in self.get_all_summaries() 
                if w.end_date < current_week.start_date]

