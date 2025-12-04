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
    
    def initialize(self) -> bool:
        """初始化应用"""
        self._print_banner()
        
        # 验证配置
        valid, error_msg = Config.validate()
        if not valid:
            self.logger.error(f"配置验证失败: {error_msg}")
            return False
        
        self.logger.info(f"日记目录: {Config.DIARY_DIR}, {Config.DIARY_OLD_DIR}")
        self.logger.debug(f"Base Dir: {Config.BASE_DIR}")
        self.logger.debug(f"Log Dir: {Config.LOG_DIR}")
        self.logger.info(f"输出目录: {Config.OUTPUT_DIR}")
        
        # 初始化组件
        try:
            self.reader = DiaryReader([Config.DIARY_DIR, Config.DIARY_OLD_DIR])
            
            # 初始化用户画像
            profile_path = Config.BASE_DIR / "user_profile.json"
            self.user_profile = UserProfile(profile_path)
            
            self.analyzer = DeepSeekAnalyzer(
                Config.LOG_DIR,
                Config.OUTPUT_DIR,
                self.user_profile
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
    
    def _get_context_diaries(self, current_diary: DiaryEntry) -> List[DiaryEntry]:
        """获取当前日记所在周的上下文日记（包括当前日记）"""
        week_info = self.weekly_manager.get_week_info(current_diary.date)
        self.logger.debug(f"获取上下文日记: {current_diary.date} (Week: {week_info.week_str})")
        context_diaries = []
        for d in self.diaries:
            if d.date >= week_info.start_date and d.date <= current_diary.date:
                context_diaries.append(d)
        self.logger.debug(f"找到 {len(context_diaries)} 篇上下文日记")
        return context_diaries

    def process_daily_evaluations(self) -> bool:
        """处理每日评价"""
        Logger.log_separator(self.logger)
        self.logger.info("🤖 检查每日评价...")
        Logger.log_separator(self.logger)
        
        # 确保日记按时间排序
        self.diaries.sort(key=lambda x: x.date)
        
        count = 0
        for i, diary in enumerate(self.diaries):
            # 检查是否已有评价
            if diary.ai_comment:
                continue
            
            self.logger.info(f"[{i+1}/{len(self.diaries)}] 发现未评价日记: {diary.date.strftime('%Y-%m-%d')}")
            
            # 获取上下文
            # 1. 历史周总结（这天所在周之前的周）
            historical_summaries = self.weekly_manager.get_historical_summaries(diary.date)
            self.logger.debug(f"获取到 {len(historical_summaries)} 个历史周总结")
            
            # 2. 本周日记（这天所在周，直到这天）
            context_diaries = self._get_context_diaries(diary)
            
            # 生成评价
            self.logger.debug(f"开始生成每日评价: {diary.date}")
            evaluation = self.analyzer.generate_daily_evaluation(
                diary,
                context_diaries,
                historical_summaries
            )
            
            if evaluation:
                # 追加到文件
                if self.reader.append_ai_comment(diary.file_path, evaluation):
                    self.logger.info(f"✓ 已添加评价到 {diary.file_path.name}")
                    diary.ai_comment = evaluation # 更新内存中的对象
                    count += 1
                    
                    # 如果是周日，生成周分析报告
                    if diary.date.weekday() == 6:
                        self.logger.info("-" * Config.SEPARATOR_LENGTH)
                        self.logger.info(f"📅 检测到周日 ({diary.date.strftime('%Y-%m-%d')})，正在生成周分析报告...")
                        self.analyzer.generate_weekly_analysis(context_diaries, historical_summaries)
                    
                    # 根据配置决定是否暂停
                    if Config.PAUSE_AFTER_DAILY_EVALUATION:
                        self.logger.info("-" * Config.SEPARATOR_LENGTH)
                        confirm = input("按回车继续下一篇，输入 'n' 退出每日评价生成: ")
                        if confirm.lower() == 'n':
                            self.logger.info("用户停止生成每日评价")
                            break
                else:
                    self.logger.error(f"添加评价失败")
            else:
                self.logger.error(f"生成评价失败")
        
        if count == 0:
            self.logger.info("✓ 所有日记都已有评价")
        else:
            self.logger.info(f"✓ 完成 {count} 篇日记的评价生成")
            
        return True

    def check_and_generate_weekly_summaries(self) -> bool:
        """检查并生成缺失的周总结"""
        Logger.log_separator(self.logger)
        self.logger.info("📊 检查周总结...")
        Logger.log_separator(self.logger)
        
        # 按周分组日记
        weeks = self.weekly_manager.group_diaries_by_week(self.diaries)
        self.logger.debug(f"日记已分组为 {len(weeks)} 周")
        
        # 找出需要生成总结的周
        need_summary = self.weekly_manager.get_weeks_need_summary(weeks)
        self.logger.debug(f"需要生成总结的周: {need_summary}")
        
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
            
            # 处理每日评价
            if not self.process_daily_evaluations():
                self.logger.error("每日评价生成失败")
            
            # 显示结果
            # self.show_result(result)
            
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
