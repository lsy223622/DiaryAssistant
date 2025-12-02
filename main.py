#!/usr/bin/env python3
"""
日记分析助手
使用DeepSeek API分析日记,提供智能建议
"""

import sys
from pathlib import Path
from typing import List, Optional

# 添加当前目录到Python路径
sys.path.insert(0, str(Path(__file__).parent))

from diary_reader import DiaryReader, DiaryEntry
from analyzer import DeepSeekAnalyzer
from config import Config
from logger import Logger
from weekly_summary import WeeklySummaryManager


class DiaryAssistant:
    """日记分析助手主类"""
    
    def __init__(self):
        self.logger = Logger.get_logger("Main")
        self.reader: Optional[DiaryReader] = None
        self.analyzer: Optional[DeepSeekAnalyzer] = None
        self.weekly_manager: Optional[WeeklySummaryManager] = None
        self.diaries: List[DiaryEntry] = []
    
    def initialize(self) -> bool:
        """初始化应用"""
        self._print_banner()
        
        # 验证配置
        valid, error_msg = Config.validate()
        if not valid:
            self.logger.error(f"配置验证失败: {error_msg}")
            return False
        
        self.logger.info(f"日记目录: {Config.DIARY_DIR}")
        self.logger.info(f"输出目录: {Config.OUTPUT_DIR}")
        
        # 初始化组件
        try:
            self.reader = DiaryReader(Config.DIARY_DIR)
            self.analyzer = DeepSeekAnalyzer(
                Config.LOG_DIR,
                Config.OUTPUT_DIR
            )
            self.weekly_manager = WeeklySummaryManager(Config.WEEKLY_SUMMARY_DIR)
            self.logger.info("组件初始化成功")
            return True
        except Exception as e:
            self.logger.error(f"初始化失败: {e}", exc_info=True)
            return False
    
    def _print_banner(self):
        """打印程序标题"""
        Logger.log_separator(self.logger)
        self.logger.info("📖 日记分析助手")
        self.logger.info("   使用 DeepSeek AI 提供智能分析")
        Logger.log_separator(self.logger)
    
    def load_diaries(self) -> bool:
        """加载日记"""
        self.logger.info("")
        self.logger.info("📚 正在读取日记文件...")
        
        try:
            self.diaries = self.reader.get_all_diaries()
        except Exception as e:
            self.logger.error(f"读取日记失败: {e}")
            return False
        
        if not self.diaries:
            self.logger.error("没有找到日记文件")
            return False
        
        self.logger.info(f"✓ 成功读取 {len(self.diaries)} 篇日记")
        self._show_recent_diaries()
        return True
    
    def _show_recent_diaries(self, count: int = 5):
        """显示最近的日记信息"""
        self.logger.info("")
        self.logger.info(f"最近 {min(count, len(self.diaries))} 篇日记:")
        
        for diary in self.diaries[-count:]:
            date_str = diary.date.strftime("%Y-%m-%d")
            todo_count = len(diary.todos)
            record_count = len(diary.records)
            thought_count = len(diary.thoughts)
            self.logger.info(
                f"  📅 {date_str}: "
                f"{todo_count}个待办 / {record_count}条记录 / {thought_count}条想法"
            )
    
    def check_and_generate_weekly_summaries(self) -> bool:
        """检查并生成缺失的周总结"""
        Logger.log_separator(self.logger)
        self.logger.info("📊 检查周总结...")
        Logger.log_separator(self.logger)
        
        # 按周分组日记
        weeks = self.weekly_manager.group_diaries_by_week(self.diaries)
        
        # 找出需要生成总结的周
        need_summary = self.weekly_manager.get_weeks_need_summary(weeks)
        
        if not need_summary:
            self.logger.info("✓ 所有已完整经过的周都已有总结")
            return True
        
        self.logger.info(f"发现 {len(need_summary)} 周需要生成总结")
        
        # 为每周生成总结
        for i, week in enumerate(need_summary, 1):
            self.logger.info("")
            self.logger.info(f"[{i}/{len(need_summary)}] 正在生成 {week} 的总结...")
            
            # 生成总结
            summary = self.analyzer.generate_weekly_summary(week)
            
            if not summary:
                self.logger.error(f"生成 {week} 的总结失败")
                return False
            
            # 保存总结
            self.weekly_manager.save_summary(week, summary)
            self.logger.info(f"✓ {week} 总结完成")
        
        self.logger.info("")
        self.logger.info(f"✓ 所有周总结已生成完毕")
        return True
    
    def analyze(self, diaries: List[DiaryEntry]) -> Optional[str]:
        """分析日记（使用历史周总结+本周日记）"""
        Logger.log_separator(self.logger)
        self.logger.info("🔍 开始分析日记...")
        Logger.log_separator(self.logger)
        
        try:
            # 获取本周信息
            from datetime import datetime
            today = datetime.now()
            current_week = self.weekly_manager.get_week_info(today)
            
            # 获取本周的日记
            current_week_diaries = [d for d in diaries if current_week.start_date.date() <= d.date.date() <= current_week.end_date.date()]
            
            # 获取所有历史周总结
            all_summaries = self.weekly_manager.get_all_summaries()
            
            self.logger.info(f"本周日记: {len(current_week_diaries)} 篇")
            self.logger.info(f"历史周总结: {len(all_summaries)} 周")
            
            result = self.analyzer.analyze_with_weekly_summaries(
                current_week_diaries, 
                all_summaries
            )
            return result
        except Exception as e:
            self.logger.error(f"分析过程出错: {e}", exc_info=True)
            return None
    
    def show_result(self, result: str):
        """显示分析结果"""
        if not result:
            self.logger.error("❌ 分析失败")
            return
        
        Logger.log_separator(self.logger)
        self.logger.info("✅ 分析完成!")
        Logger.log_separator(self.logger)
        
        # 显示结果预览
        self.logger.info("")
        self.logger.info("📄 分析结果预览:")
        print("-" * Config.SEPARATOR_LENGTH)
        
        if len(result) > Config.PREVIEW_LENGTH:
            print(result[:Config.PREVIEW_LENGTH] + "...")
            print(f"\n... (内容较长，完整内容请查看保存的文件)")
        else:
            print(result)
        
        print("-" * Config.SEPARATOR_LENGTH)
        
        # 显示文件位置
        self.logger.info("")
        self.logger.info(f"📁 文件位置:")
        self.logger.info(f"   每日分析: {Config.OUTPUT_DIR.absolute()}")
        self.logger.info(f"   周总结: {Config.WEEKLY_SUMMARY_DIR.absolute()}")
        self.logger.info(f"   请求日志: {Config.LOG_DIR.absolute()}")
    
    def run(self):
        """运行主程序"""
        try:
            # 初始化
            if not self.initialize():
                return
            
            # 加载日记
            if not self.load_diaries():
                return
            
            # 检查并生成周总结
            if not self.check_and_generate_weekly_summaries():
                self.logger.error("周总结生成失败，程序终止")
                return
            
            # 选择日记（这里已不需要，直接分析本周）
            # 分析日记（使用历史周总结+本周日记）
            result = self.analyze(self.diaries)
            
            # 显示结果
            self.show_result(result)
            
            Logger.log_separator(self.logger)
            self.logger.info("✨ 程序执行完成")
            Logger.log_separator(self.logger)
            
        except KeyboardInterrupt:
            self.logger.info("\n\n⚠️  用户中断程序")
        except Exception as e:
            self.logger.error(f"程序运行出错: {e}", exc_info=True)


def main():
    """程序入口"""
    assistant = DiaryAssistant()
    assistant.run()


if __name__ == "__main__":
    main()
