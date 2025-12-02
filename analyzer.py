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
        
        try:
            # 准备请求
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                "temperature": 0.8,
                "max_tokens": 4000
            }
            
            # 发送请求
            start_time = time.time()
            response = requests.post(self.api_url, headers=headers, json=data, timeout=Config.API_TIMEOUT)
            elapsed_time = time.time() - start_time
            
            response.raise_for_status()
            result = response.json()
            
            summary = result['choices'][0]['message']['content']
            
            self.logger.info(f"周总结生成完成，耗时: {elapsed_time:.2f}秒")
            return summary
            
        except Exception as e:
            self.logger.error(f"生成周总结失败: {e}")
            return None
    
    def analyze_with_weekly_summaries(self, current_week_diaries: List[DiaryEntry], 
                                     historical_summaries: List[tuple]) -> Optional[str]:
        """使用历史周总结和本周日记进行分析"""
        from datetime import datetime
        
        self.logger.info(f"开始分析 (历史周总结: {len(historical_summaries)} 周, 本周日记: {len(current_week_diaries)} 篇)")
        
        # 格式化历史周总结
        historical_context = ""
        if historical_summaries:
            historical_context = "\n## 📚 历史周总结\n\n"
            for week_info, summary in historical_summaries:
                historical_context += f"### {week_info.year}年第{week_info.week}周 ({week_info.start_date.strftime('%m月%d日')}-{week_info.end_date.strftime('%m月%d日')})\n\n"
                historical_context += summary + "\n\n" + "="*50 + "\n\n"
        
        # 格式化本周日记
        current_week_content = ""
        if current_week_diaries:
            from diary_reader import DiaryReader
            diary_reader = DiaryReader(Config.DIARY_DIR)
            
            current_week_content = "\n## 📝 本周日记（截至今日）\n\n"
            for diary in current_week_diaries:
                diary_content = diary_reader.format_diary_for_ai(diary)
                current_week_content += diary_content + "\n\n" + "="*50 + "\n\n"
        
        # 创建系统提示
        system_prompt = f"""# 角色设定
你是我最信任的日记伙伴。

## 特点
1. **富有同理心**：感受情绪，理解困惑
2. **温和深刻**：温柔有深度，建议中肯
3. **亲切自然**：像老朋友一样交流
4. **鼓励为主**：关注进步，给予支持

## 任务
基于历史周总结和本周日记，对**本周（特别是今天）**的生活进行评价和建议。"""

        # 创建用户消息
        today = datetime.now()
        user_message = f"""今天是 {today.strftime('%Y年%m月%d日')}。

为了让你了解我，我提供了历史周总结和本周日记。

{historical_context}

{current_week_content}

请分析**本周（特别是今天）**的情况：
1. **感受**：我的情绪和状态变化
2. **模式**：结合历史，有什么值得关注的变化
3. **建议**：作为朋友的建议
4. **感悟**：值得记住的时刻

请参考以下格式回复：

# 生活分析
[整体分析，结合历史，300-500字]

# 关键发现
## 生活模式
- [发现1]

## 情绪状态
- [发现1]

## 时间管理
- [发现1]

# 深度反思
## 值得思考的问题
- [问题1]

## 可能被忽视的模式
- [模式1]

# 具体建议
## 短期行动
- [建议1]

## 长期方向
- [方向1]

## 习惯调整
- [习惯1]
"""
        
        # 保存请求日志
        payload = {
            "system_prompt": system_prompt,
            "user_message": user_message,
            "diary_count": len(current_week_diaries),
            "date_range": f"本周日记 + {len(historical_summaries)}周历史总结"
        }
        self.save_request_log(payload)
        
        # 等待用户确认
        self.logger.info("-" * Config.SEPARATOR_LENGTH)
        confirm = input("请输入 'y' 发送请求至 DeepSeek API，或输入 'n' 取消: ")
        
        if confirm.lower() != 'y':
            self.logger.info("用户取消了请求")
            return None
        
        self.logger.info("正在发送请求到 DeepSeek API...")
        
        try:
            # 准备请求
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                "temperature": 1.0,
                "max_tokens": Config.API_MAX_TOKENS
            }
            
            # 发送请求
            start_time = time.time()
            response = requests.post(self.api_url, headers=headers, json=data, timeout=Config.API_TIMEOUT)
            elapsed_time = time.time() - start_time
            
            response.raise_for_status()
            result = response.json()
            
            analysis_result = result['choices'][0]['message']['content']
            
            self.logger.info(f"分析完成！耗时: {elapsed_time:.2f}秒")
            self.logger.info(f"响应长度: {len(analysis_result)} 字符")
            
            # 保存分析结果
            self.save_analysis_result(analysis_result, current_week_diaries)
            
            return analysis_result
            
        except Exception as e:
            self.logger.error(f"API请求失败: {e}")
            return None