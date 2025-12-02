#!/usr/bin/env python3
"""
每周总结管理模块
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from diary_reader import DiaryEntry
from logger import Logger


class WeekInfo:
    """周信息类"""
    def __init__(self, year: int, week: int, start_date: datetime, end_date: datetime):
        self.year = year
        self.week = week  # ISO周数
        self.start_date = start_date  # 周一
        self.end_date = end_date  # 周日
        self.diaries: List[DiaryEntry] = []
    
    def __str__(self):
        return f"{self.year}年第{self.week}周 ({self.start_date.strftime('%Y-%m-%d')} 至 {self.end_date.strftime('%Y-%m-%d')})"
    
    def get_filename(self) -> str:
        """获取总结文件名"""
        return f"{self.year}_W{self.week:02d}_{self.start_date.strftime('%Y%m%d')}-{self.end_date.strftime('%Y%m%d')}.md"


class WeeklySummaryManager:
    """每周总结管理器"""
    
    def __init__(self, weekly_summary_dir: Path):
        self.weekly_summary_dir = weekly_summary_dir
        self.logger = Logger.get_logger("WeeklySummary")
        self.weekly_summary_dir.mkdir(exist_ok=True)
    
    def get_week_info(self, date: datetime) -> WeekInfo:
        """获取指定日期所在周的信息（周一到周日）"""
        # ISO周从周一开始，weekday()返回0-6，0是周一
        weekday = date.weekday()
        
        # 计算周一的日期
        monday = date - timedelta(days=weekday)
        # 计算周日的日期
        sunday = monday + timedelta(days=6)
        
        # 获取ISO周数
        iso_year, iso_week, _ = monday.isocalendar()
        
        return WeekInfo(iso_year, iso_week, monday, sunday)
    
    def group_diaries_by_week(self, diaries: List[DiaryEntry]) -> List[WeekInfo]:
        """将日记按周分组"""
        if not diaries:
            return []
        
        # 按周分组
        week_dict: Dict[Tuple[int, int], WeekInfo] = {}
        
        for diary in diaries:
            week_info = self.get_week_info(diary.date)
            key = (week_info.year, week_info.week)
            
            if key not in week_dict:
                week_dict[key] = week_info
            
            week_dict[key].diaries.append(diary)
        
        # 按日期排序
        weeks = sorted(week_dict.values(), key=lambda w: w.start_date)
        
        self.logger.info(f"日记已分组为 {len(weeks)} 周")
        return weeks
    
    def is_week_complete(self, week_info: WeekInfo) -> bool:
        """检查一周是否已完整经过（即周日已经过去）"""
        today = datetime.now().date()
        return week_info.end_date.date() < today
    
    def has_summary(self, week_info: WeekInfo) -> bool:
        """检查某周是否已有总结"""
        filename = week_info.get_filename()
        filepath = self.weekly_summary_dir / filename
        return filepath.exists()
    
    def get_summary_path(self, week_info: WeekInfo) -> Path:
        """获取总结文件路径"""
        filename = week_info.get_filename()
        return self.weekly_summary_dir / filename
    
    def get_weeks_need_summary(self, weeks: List[WeekInfo]) -> List[WeekInfo]:
        """获取需要生成总结的周（已完整经过且有日记但无总结）"""
        need_summary = []
        
        for week in weeks:
            # 必须是已完整经过的周
            if not self.is_week_complete(week):
                continue
            
            # 必须有日记
            if not week.diaries:
                continue
            
            # 必须没有总结
            if not self.has_summary(week):
                need_summary.append(week)
        
        return need_summary
    
    def get_all_summaries(self) -> List[Tuple[WeekInfo, str]]:
        """获取所有已有的周总结内容"""
        summaries = []
        
        # 读取所有总结文件
        try:
            summary_files = sorted(self.weekly_summary_dir.glob("*.md"))
        except Exception as e:
            self.logger.error(f"读取总结目录失败: {e}")
            return summaries
        
        for filepath in summary_files:
            try:
                # 从文件名解析周信息
                week_info = self._parse_filename(filepath)
                if not week_info:
                    continue
                
                # 读取内容
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                summaries.append((week_info, content))
            except Exception as e:
                self.logger.error(f"读取总结文件失败 {filepath}: {e}")
        
        return summaries
    
    def _parse_filename(self, filepath: Path) -> Optional[WeekInfo]:
        """从文件名解析周信息"""
        # 文件名格式: 2025_W01_20241230-20250105.md
        import re
        pattern = r'(\d{4})_W(\d{2})_(\d{8})-(\d{8})\.md'
        match = re.match(pattern, filepath.name)
        
        if not match:
            return None
        
        year = int(match.group(1))
        week = int(match.group(2))
        start_str = match.group(3)
        end_str = match.group(4)
        
        try:
            start_date = datetime.strptime(start_str, '%Y%m%d')
            end_date = datetime.strptime(end_str, '%Y%m%d')
            return WeekInfo(year, week, start_date, end_date)
        except ValueError:
            return None
    
    def save_summary(self, week_info: WeekInfo, summary: str):
        """保存周总结"""
        filepath = self.get_summary_path(week_info)
        
        try:
            # 添加元信息
            meta_info = f"""# {week_info.year}年第{week_info.week}周总结
**时间范围**: {week_info.start_date.strftime('%Y年%m月%d日')} 至 {week_info.end_date.strftime('%Y年%m月%d日')}
**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**日记数量**: {len(week_info.diaries)} 篇

---

"""
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(meta_info)
                f.write(summary)
            
            self.logger.info(f"周总结已保存: {filepath}")
        except Exception as e:
            self.logger.error(f"保存周总结失败: {e}")
    
    def format_week_diaries_for_ai(self, week_info: WeekInfo) -> str:
        """格式化周日记内容用于AI生成总结"""
        from diary_reader import DiaryReader
        
        diary_reader = DiaryReader(Path("./Daily"))
        
        formatted = f"""# {week_info.year}年第{week_info.week}周日记
**时间范围**: {week_info.start_date.strftime('%Y年%m月%d日')} 至 {week_info.end_date.strftime('%Y年%m月%d日')}

"""
        
        for diary in week_info.diaries:
            diary_content = diary_reader.format_diary_for_ai(diary)
            formatted += diary_content + "\n\n" + "="*50 + "\n\n"
        
        return formatted
