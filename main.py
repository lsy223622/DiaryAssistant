#!/usr/bin/env python3
"""
日记分析助手 - 使用 DeepSeek API 分析日记，提供智能建议
"""

import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent))

from diary_reader import DiaryReader, DiaryEntry
from analyzer import DeepSeekAnalyzer
from config import Config
from logger import Logger
from weekly_summary import WeeklySummaryManager
from user_profile import UserProfile


class DiaryAssistant:
    """日记分析助手主类"""
    
    def __init__(self):
        self.logger = Logger.get_logger("Main")
        self.reader: Optional[DiaryReader] = None
        self.analyzer: Optional[DeepSeekAnalyzer] = None
        self.weekly_manager: Optional[WeeklySummaryManager] = None
        self.user_profile: Optional[UserProfile] = None
        self.diaries: List[DiaryEntry] = []
    
    # ===== 初始化 =====
    
    def initialize(self) -> bool:
        """初始化应用"""
        self._print_banner()
        
        valid, error = Config.validate()
        if not valid:
            self.logger.error(f"配置验证失败: {error}")
            return False
        
        self._log_paths()
        return self._init_components()
    
    def _print_banner(self) -> None:
        """打印程序标题"""
        Logger.log_separator(self.logger)
        self.logger.info("📖 日记分析助手")
        self.logger.info("   使用 DeepSeek AI 提供智能分析")
        Logger.log_separator(self.logger)
    
    def _log_paths(self) -> None:
        """记录路径配置"""
        self.logger.info(f"日记目录: {Config.BASE_DIR}")
    
    def _init_components(self) -> bool:
        """初始化组件"""
        try:
            self.reader = DiaryReader([Config.DIARY_DIR, Config.DIARY_OLD_DIR])
            self.user_profile = UserProfile(Config.BASE_DIR / "user_profile.json")
            self.analyzer = DeepSeekAnalyzer(Config.LOG_DIR, Config.OUTPUT_DIR, self.user_profile)
            self.weekly_manager = WeeklySummaryManager(Config.WEEKLY_SUMMARY_DIR)
            self.logger.info("组件初始化成功")
            return True
        except Exception as e:
            self.logger.error(f"初始化失败: {e}", exc_info=True)
            return False
    
    # ===== 日记加载 =====
    
    def load_diaries(self) -> bool:
        """加载日记"""
        self.logger.info("\n📚 正在读取日记文件...")
        
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
    
    def _show_recent_diaries(self, count: int = 5) -> None:
        """显示最近的日记信息"""
        self.logger.info(f"\n最近 {min(count, len(self.diaries))} 篇日记:")
        for diary in self.diaries[-count:]:
            self.logger.info(
                f"  📅 {diary.date:%Y-%m-%d}: "
                f"{len(diary.todos)}个待办 / {len(diary.records)}条记录 / {len(diary.thoughts)}条想法"
            )
    
    def _get_context_diaries(self, current: DiaryEntry) -> List[DiaryEntry]:
        """获取当前日记所在周的上下文日记"""
        week = self.weekly_manager.get_week_info(current.date)
        return [d for d in self.diaries if week.start_date <= d.date <= current.date]
    
    # ===== 每日评价 =====
    
    def process_daily_evaluations(self) -> bool:
        """处理每日评价"""
        Logger.log_separator(self.logger)
        self.logger.info("🤖 检查每日评价...")
        Logger.log_separator(self.logger)
        
        self.diaries.sort(key=lambda x: x.date)
        count = 0
        
        for i, diary in enumerate(self.diaries):
            if diary.ai_comment:
                continue
            
            if self._process_single_diary(diary, i):
                count += 1
                if not self._handle_post_evaluation(diary):
                    break
        
        self.logger.info(f"✓ {'所有日记都已有评价' if count == 0 else f'完成 {count} 篇日记的评价生成'}")
        return True
    
    def _process_single_diary(self, diary: DiaryEntry, index: int) -> bool:
        """处理单篇日记的评价"""
        self.logger.info(f"[{index+1}/{len(self.diaries)}] 发现未评价日记: {diary.date:%Y-%m-%d}")
        
        historical = self.weekly_manager.get_historical_summaries(diary.date)
        context = self._get_context_diaries(diary)
        
        # 获取截至当前日期的所有日记，用于构建完整的待办列表
        all_diaries_until_now = [d for d in self.diaries if d.date <= diary.date]
        
        evaluation = self.analyzer.generate_daily_evaluation(diary, context, historical, all_diaries=all_diaries_until_now)
        if not evaluation:
            self.logger.error("生成评价失败")
            return False
        
        if not self.reader.append_ai_comment(diary.file_path, evaluation):
            self.logger.error("添加评价失败")
            return False
        
        self.logger.info(f"✓ 已添加评价到 {diary.file_path.name}")
        diary.ai_comment = evaluation
        return True
    
    def _handle_post_evaluation(self, diary: DiaryEntry) -> bool:
        """处理评价后的操作（周分析、暂停确认）"""
        # 周日生成周分析
        if diary.date.weekday() == 6:
            self.logger.info("-" * Config.SEPARATOR_LENGTH)
            self.logger.info(f"📅 检测到周日 ({diary.date:%Y-%m-%d})，正在生成周分析报告...")
            context = self._get_context_diaries(diary)
            historical = self.weekly_manager.get_historical_summaries(diary.date)
            
            # 获取截至当前日期的所有日记
            all_diaries_until_now = [d for d in self.diaries if d.date <= diary.date]
            
            self.analyzer.generate_weekly_analysis(context, historical, all_diaries=all_diaries_until_now)
        
        # 暂停确认
        if Config.PAUSE_AFTER_DAILY_EVALUATION:
            self.logger.info("-" * Config.SEPARATOR_LENGTH)
            if input("按回车继续下一篇，输入 'n' 退出: ").lower() == 'n':
                self.logger.info("用户停止生成每日评价")
                return False
        return True
    
    # ===== 周总结 =====
    
    def check_and_generate_weekly_summaries(self) -> bool:
        """检查并生成缺失的周总结"""
        Logger.log_separator(self.logger)
        self.logger.info("📊 检查周总结...")
        Logger.log_separator(self.logger)
        
        weeks = self.weekly_manager.group_diaries_by_week(self.diaries)
        need_summary = self.weekly_manager.get_weeks_need_summary(weeks)
        
        if not need_summary:
            self.logger.info("✓ 所有已完整经过的周都已有总结")
            return True
        
        self.logger.info(f"发现 {len(need_summary)} 周需要生成总结")
        
        for i, week in enumerate(need_summary, 1):
            self.logger.info(f"\n[{i}/{len(need_summary)}] 正在生成 {week} 的总结...")
            
            if summary := self.analyzer.generate_weekly_summary(week):
                self.weekly_manager.save_summary(week, summary)
                self.logger.info(f"✓ {week} 总结完成")
            else:
                self.logger.error(f"生成 {week} 的总结失败")
                return False
        
        self.logger.info("\n✓ 所有周总结已生成完毕")
        return True
    
    # ===== 主流程 =====
    
    def run(self) -> None:
        """运行主程序"""
        try:
            if not self.initialize() or not self.load_diaries():
                return
            
            if not self.check_and_generate_weekly_summaries():
                self.logger.error("周总结生成失败，程序终止")
                return
            
            self.process_daily_evaluations()
            
            Logger.log_separator(self.logger)
            self.logger.info("✨ 程序执行完成")
            Logger.log_separator(self.logger)
            
        except KeyboardInterrupt:
            self.logger.info("\n\n⚠️  用户中断程序")
        except Exception as e:
            self.logger.error(f"程序运行出错: {e}", exc_info=True)


def main():
    """程序入口"""
    DiaryAssistant().run()


if __name__ == "__main__":
    main()
