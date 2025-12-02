#!/usr/bin/env python3
"""
日记分析模块 - 使用DeepSeek API
"""

import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import requests

from diary_reader import DiaryEntry
from config import Config
from logger import Logger
from weekly_summary import WeekInfo


class DeepSeekAnalyzer:
    """使用DeepSeek API分析日记"""
    
    def __init__(self, log_dir: Path, output_dir: Path):
        self.log_dir = log_dir
        self.output_dir = output_dir
        self.logger = Logger.get_logger("Analyzer")
        
        # 从配置读取API设置
        self.api_key = Config.get_api_key()
        self.api_url = Config.DEEPSEEK_API_URL
        self.model_name = Config.DEEPSEEK_MODEL
    
    def save_request_log(self, payload: Dict[str, Any]):
        """保存请求内容到日志文件"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = self.log_dir / f"request_{timestamp}.txt"
        
        try:
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write("="*60 + "\n")
                f.write(f"请求时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"日记数量: {payload['diary_count']}\n")
                f.write(f"时间范围: {payload['date_range']}\n")
                f.write("="*60 + "\n\n")
                
                f.write("系统提示词:\n")
                f.write("-"*40 + "\n")
                f.write(payload['system_prompt'] + "\n\n")
                
                f.write("用户消息:\n")
                f.write("-"*40 + "\n")
                f.write(payload['user_message'] + "\n")
            
            self.logger.info(f"请求内容已保存到: {log_file}")
            self.logger.debug(f"请求内容长度: {len(payload['user_message'])} 字符")
            
        except IOError as e:
            self.logger.error(f"保存请求日志失败: {e}")
        except Exception as e:
            self.logger.error(f"保存请求日志时发生未知错误: {e}")
    
    def save_analysis_result(self, analysis: str, diaries: List[DiaryEntry]):
        """保存分析结果"""
        if not analysis:
            self.logger.warning("分析结果为空，跳过保存")
            return
        
        # 使用当前日期作为文件名
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        start_date = diaries[0].date.strftime("%Y%m%d")
        end_date = diaries[-1].date.strftime("%Y%m%d")
        
        filename = f"analysis_{start_date}-{end_date}_{timestamp}.md"
        filepath = self.output_dir / filename
        
        try:
            # 添加元信息
            meta_info = f"""# 日记分析报告
**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**分析范围**: {diaries[0].date.strftime('%Y-%m-%d')} 到 {diaries[-1].date.strftime('%Y-%m-%d')}
**日记数量**: {len(diaries)} 篇
**使用模型**: {self.model_name}

---

"""
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(meta_info)
                f.write(analysis)
            
            self.logger.info(f"分析结果已保存到: {filepath}")
            
        except IOError as e:
            self.logger.error(f"保存分析结果失败: {e}")
        except Exception as e:
            self.logger.error(f"保存分析结果时发生未知错误: {e}")
    
    def _send_request_with_retry(self, data: Dict[str, Any], task_name: str = "请求") -> Optional[str]:
        """发送API请求，带有重试逻辑"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # 计算提示词长度
        prompt_length = 0
        if 'messages' in data:
            for message in data['messages']:
                if 'content' in message:
                    prompt_length += len(message['content'])
        
        self.logger.info(f"正在发送{task_name}，提示词长度: {prompt_length} 字符")
        
        while True:
            for attempt in range(3):
                try:
                    start_time = time.time()
                    response = requests.post(self.api_url, headers=headers, json=data, timeout=Config.API_TIMEOUT)
                    elapsed_time = time.time() - start_time
                    
                    response.raise_for_status()
                    result = response.json()
                    
                    content = result['choices'][0]['message']['content']
                    response_length = len(content)
                    self.logger.info(f"{task_name}完成，耗时: {elapsed_time:.2f}秒，回复长度: {response_length} 字符")
                    return content
                    
                except Exception as e:
                    self.logger.warning(f"{task_name}失败 (尝试 {attempt + 1}/3): {e}")
                    if attempt < 2:
                        time.sleep(2)
            
            # 3 retries failed
            self.logger.error(f"{task_name}连续失败3次")
            print("\n❌ 网络请求连续失败。")
            choice = input("按回车键再次重试(3次)，输入 's' 跳过本次，输入 'q' 退出程序: ")
            
            if choice.lower() == 's':
                return None
            elif choice.lower() == 'q':
                raise KeyboardInterrupt("用户主动停止")
            
            self.logger.info("正在重试...")

    def generate_weekly_summary(self, week_info: WeekInfo) -> Optional[str]:
        """生成周总结（不需要用户确认）"""
        if not week_info.diaries:
            self.logger.warning(f"{week_info} 没有日记")
            return None
        
        self.logger.info(f"正在生成 {week_info} 的总结...")
        
        # 格式化周日记
        from weekly_summary import WeeklySummaryManager
        manager = WeeklySummaryManager(Config.WEEKLY_SUMMARY_DIR)
        week_content = manager.format_week_diaries_for_ai(week_info)
        
        # 创建系统提示
        system_prompt = """# 角色设定
你是一位专业的日记总结助手。

## 任务
阅读本周日记，生成一份简洁完整的周总结（<2000字）。

## 要求
1. **内容完整**：概括这周记录的事情和想法
2. **结构清晰**：使用合理的分类和段落
3. **客观准确**：基于日记内容，不添加额外解读

## 格式参考
### 本周概览
[简要概述]

### 主要完成事项
[列出重要任务]

### 日常记录
[记录日常活动]

### 想法与思考
[总结想法感悟]

### 关注点
[需要关注的问题或持续进行、未完成的事项]"""
        
        # 创建用户消息
        start_date = week_info.start_date.strftime('%Y年%m月%d日')
        end_date = week_info.end_date.strftime('%Y年%m月%d日')
        
        user_message = f"""时间范围：{start_date} 至 {end_date}
日记数量：{len(week_info.diaries)} 篇

{week_content}

请生成周总结。"""
        
        # 准备请求数据
        data = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": 0.8,
            "max_tokens": 4000
        }
        
        return self._send_request_with_retry(data, "周总结生成")
    
    def generate_daily_evaluation(self, current_diary: DiaryEntry, context_diaries: List[DiaryEntry], weekly_summaries: List[tuple]) -> Optional[str]:
        """生成每日评价和建议"""
        self.logger.info(f"正在为 {current_diary.date.strftime('%Y-%m-%d')} 生成评价...")
        
        # 格式化历史周总结
        historical_context = ""
        if weekly_summaries:
            historical_context = "\n## 📚 历史周总结\n\n"
            for week_info, summary in weekly_summaries:
                historical_context += f"### {week_info.year}年第{week_info.week}周 ({week_info.start_date.strftime('%m月%d日')}-{week_info.end_date.strftime('%m月%d日')})\n\n"
                historical_context += summary + "\n\n" + "="*50 + "\n\n"
        
        # 格式化本周日记（包括今天）
        current_week_content = ""
        if context_diaries:
            from diary_reader import DiaryReader
            diary_reader = DiaryReader(Config.DIARY_DIR)
            
            current_week_content = "\n## 📝 本周日记（截至今日）\n\n"
            for diary in context_diaries:
                # format_diary_for_ai 已经排除了 AI 说 部分
                diary_content = diary_reader.format_diary_for_ai(diary)
                current_week_content += diary_content + "\n\n" + "="*50 + "\n\n"
        
        # 创建系统提示
        system_prompt = """# 角色设定
你是一位贴心的日记助手。

## 任务
阅读用户的历史周总结和本周日记，为**今天**的日记生成一份简短的评价和建议。

## 要求
1. **篇幅限制**：800字以内。
2. **内容聚焦**：针对今天的日记内容，结合之前的背景。
3. **语气风格**：亲切、鼓励、有洞察力。
4. **输出格式**：直接输出评价和建议内容，不要包含标题（因为会被添加到 "## AI 说" 标题下）。"""
        
        # 创建用户消息
        user_message = f"""今天是 {current_diary.date.strftime('%Y年%m月%d日')}。

{historical_context}

{current_week_content}

请为今天的日记写一段评价和建议。"""
        
        # 准备请求数据
        data = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": 0.8,
            "max_tokens": 2000
        }
        
        return self._send_request_with_retry(data, "每日评价生成")

    def generate_weekly_analysis(self, week_diaries: List[DiaryEntry], 
                                     historical_summaries: List[tuple]) -> Optional[str]:
        """生成每周分析建议（在周日触发）"""
        
        self.logger.info(f"正在生成周分析 ( 历史周总结: {len(historical_summaries)} 周, 本周日记: {len(week_diaries)} 篇)")
        
        # 格式化历史周总结
        historical_context = ""
        if historical_summaries:
            historical_context = "\n## 📚 历史周总结\n\n"
            for week_info, summary in historical_summaries:
                historical_context += f"### {week_info.year}年第{week_info.week}周 ({week_info.start_date.strftime('%m月%d日')}-{week_info.end_date.strftime('%m月%d日')})\n\n"
                historical_context += summary + "\n\n" + "="*50 + "\n\n"
        
        # 格式化本周日记
        current_week_content = ""
        if week_diaries:
            from diary_reader import DiaryReader
            diary_reader = DiaryReader(Config.DIARY_DIR)
            
            current_week_content = "\n## 📝 本周日记\n\n"
            for diary in week_diaries:
                diary_content = diary_reader.format_diary_for_ai(diary)
                current_week_content += diary_content + "\n\n" + "="*50 + "\n\n"
        
        # 创建系统提示
        system_prompt = f"""# 角色设定
你是一位专业的个人成长顾问。

## 任务
基于历史周总结和本周完整的日记，对**本周**进行深度分析，并提出下周的建议。

## 要求
1. **深度洞察**：发现行为模式和心理变化
2. **建设性**：建议具体可行
3. **前瞻性**：基于本周情况指导下周"""

        # 创建用户消息
        end_date = week_diaries[-1].date
        user_message = f"""本周结束日期：{end_date.strftime('%Y年%m月%d日')}。

为了让你了解我，我提供了历史周总结和本周日记。

{historical_context}

{current_week_content}

请对本周进行深度分析和建议：
1. **本周复盘**：关键成就与不足
2. **模式识别**：情绪、效率、习惯等方面的规律
3. **下周建议**：具体的改进方向和行动计划

请参考以下格式回复：

# 本周深度复盘
[分析内容，300-500字]

# 模式与洞察
## 情绪与状态
- [分析]

## 效率与习惯
- [分析]

# 下周行动建议
## 重点关注
- [建议]

## 具体行动
- [行动]
"""
        
        # 保存请求日志
        payload = {
            "system_prompt": system_prompt,
            "user_message": user_message,
            "diary_count": len(week_diaries),
            "date_range": f"本周日记 + {len(historical_summaries)}周历史总结"
        }
        self.save_request_log(payload)
        
        self.logger.info("正在发送请求到 DeepSeek API...")
        
        # 准备请求数据
        data = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": 1.0,
            "max_tokens": Config.API_MAX_TOKENS
        }
        
        analysis_result = self._send_request_with_retry(data, "周分析生成")
        
        if analysis_result:
            # 保存分析结果
            self.save_analysis_result(analysis_result, week_diaries)
            
        return analysis_result