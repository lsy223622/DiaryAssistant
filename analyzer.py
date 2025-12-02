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
    
    def create_request_payload(self, diaries: List[DiaryEntry]) -> Dict[str, Any]:
        """创建API请求内容"""
        
        # 格式化所有日记内容
        from diary_reader import DiaryReader
        
        diary_reader = DiaryReader(Path("./Daily"))
        all_diary_content = []
        
        for diary in diaries:
            diary_content = diary_reader.format_diary_for_ai(diary)
            all_diary_content.append(diary_content)
        
        # 将所有日记内容连接起来
        full_diary_content = "\n\n" + "="*50 + "\n\n".join(all_diary_content) + "\n" + "="*50
        
        # 获取所有日记的日期范围
        start_date = diaries[0].date.strftime('%Y年%m月%d日')
        end_date = diaries[-1].date.strftime('%Y年%m月%d日')
        diary_count = len(diaries)
        
        # 创建系统提示
        system_prompt = f"""# 角色设定
你是我最信任的日记伙伴和人生导师。你了解我的喜怒哀乐，见证我的成长历程。

## 你的特点
1. **富有同理心**：你能感受到我的情绪波动，理解我的困惑和喜悦
2. **温和而深刻**：你说话温柔但不失深度，建议中肯但不刻板
3. **如朋友般亲切**：你不是冷冰冰的AI，而是像老朋友一样了解我
4. **鼓励而非评判**：你更关注我的进步和努力，而不是批评不足

## 你的任务
请以朋友的身份，阅读我{diary_count}篇日记（从{start_date}到{end_date}），然后：

1. **用心感受**我的情绪变化和生活状态
2. **像朋友聊天一样**分享你的观察和感受
3. **用温暖的话语**提供支持和鼓励
4. **基于我的实际情况**给出可行的建议

请用自然、亲切、有温度的语言回复，就像在跟好朋友谈心一样。"""

        # 创建用户消息 - 更亲切的语气
        user_message = f"""嗨，朋友！

这段时间（{start_date}到{end_date}）我写了{diary_count}篇日记，想和你分享一下，听听你的看法。

这些日记记录了我日常的：
**待办事项**：每天想完成的事情
**生活记录**：当天发生的大小事
**内心想法**：我的感受、思考和困惑

下面就是我这段时间的日记：

"""

        # 添加日记内容
        user_message += full_diary_content
        
        # 添加具体指令
        user_message += f"""

以上就是我这{diary_count}篇日记。

作为我的日记伙伴，我想听听：
1. 你从这些日记中感受到了什么？（我的情绪、状态变化）
2. 有哪些你特别关注或担心的地方？
3. 作为朋友，你有什么想对我说的话或建议？
4. 有哪些值得记住的重要时刻或感悟？

请参考但不局限于以下格式组织你的回复：

# 整体生活分析
[这里写整体分析，300-500字]

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
## 短期行动建议
- [建议1]

## 长期改进方向
- [方向1]

## 习惯调整建议
- [习惯1]
"""

        return {
            "system_prompt": system_prompt,
            "user_message": user_message,
            "diary_count": len(diaries),
            "date_range": f"{diaries[0].date.strftime('%Y-%m-%d')} 到 {diaries[-1].date.strftime('%Y-%m-%d')}"
        }
    
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
    
    def analyze_diaries(self, diaries: List[DiaryEntry]) -> Optional[str]:
        """分析所有日记"""
        if not diaries:
            self.logger.warning("没有可分析的日记")
            return None
        
        self.logger.info(f"开始分析 {len(diaries)} 篇日记")
        
        # 创建请求内容
        try:
            payload = self.create_request_payload(diaries)
        except Exception as e:
            self.logger.error(f"创建请求失败: {e}")
            return None
        
        # 保存请求日志
        self.save_request_log(payload)
        
        # 等待用户确认
        self.logger.info("-" * Config.SEPARATOR_LENGTH)
        confirm = input("请输入 'y' 发送请求至 DeepSeek API，或输入 'n' 取消: ")
        
        if confirm.lower() != 'y':
            self.logger.info("用户取消了请求")
            return None
        
        self.logger.info("正在发送请求到 DeepSeek API...")
        
        try:
            # 准备请求头
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            # 准备请求数据
            data = {
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": payload['system_prompt']},
                    {"role": "user", "content": payload['user_message']}
                ],
                "temperature": Config.API_TEMPERATURE,
                "max_tokens": Config.API_MAX_TOKENS
            }
            
            self.logger.debug(f"请求参数: model={self.model_name}, temperature={Config.API_TEMPERATURE}, max_tokens={Config.API_MAX_TOKENS}")
            
            # 发送请求
            start_time = time.time()
            response = requests.post(self.api_url, headers=headers, json=data, timeout=Config.API_TIMEOUT)
            elapsed_time = time.time() - start_time
            
            # 检查响应
            response.raise_for_status()
            result = response.json()
            
            # 提取分析结果
            analysis_result = result['choices'][0]['message']['content']
            
            self.logger.info(f"分析完成！耗时: {elapsed_time:.2f}秒")
            self.logger.info(f"响应长度: {len(analysis_result)} 字符")
            
            # 保存分析结果
            self.save_analysis_result(analysis_result, diaries)
            
            return analysis_result
            
        except requests.exceptions.Timeout:
            self.logger.error(f"请求超时（{Config.API_TIMEOUT}秒），请检查网络后重试")
        except requests.exceptions.HTTPError as e:
            self.logger.error(f"API返回HTTP错误: {e}")
            if response.status_code == 401:
                self.logger.error("API密钥无效，请检查DEEPSEEK_API_KEY")
            elif response.status_code == 429:
                self.logger.error("请求频率超限，请稍后重试")
        except requests.exceptions.RequestException as e:
            self.logger.error(f"API请求失败: {e}")
        except KeyError as e:
            self.logger.error(f"解析API响应失败，缺少字段: {e}")
            self.logger.debug(f"响应内容: {result if 'result' in locals() else 'N/A'}")
        except Exception as e:
            self.logger.error(f"未知错误: {e}", exc_info=True)
        
        return None
    
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
你是一位专业的日记总结助手，负责为用户生成每周的日记总结。

## 你的任务
请仔细阅读本周的所有日记，生成一份简洁而完整的周总结，要求：

1. **字数限制**：总结不超过2000字
2. **内容完整**：在字数限制内尽量准确完整地概括这周记录的事情和想法
3. **结构清晰**：使用合理的分类和段落
4. **客观准确**：基于日记内容，不要添加额外的解读

## 总结格式参考
你可以参考以下格式组织总结（可根据实际情况调整）：

### 本周概览
[简要概述本周的整体情况]

### 主要完成事项
[列出本周完成的重要任务和工作]

### 日常记录
[记录本周的日常活动和生活]

### 想法与思考
[总结本周的想法、感悟和思考]

### 关注点
[本周需要关注的问题或持续进行的事项]

请用Markdown格式输出，语言简洁明了。"""
        
        # 创建用户消息
        start_date = week_info.start_date.strftime('%Y年%m月%d日')
        end_date = week_info.end_date.strftime('%Y年%m月%d日')
        
        user_message = f"""请为我生成 {start_date} 至 {end_date} 这一周的日记总结。

本周共有 {len(week_info.diaries)} 篇日记：

{week_content}

请生成不超过2000字的周总结，在字数限制内尽量准确完整地概括这周的事情和想法。"""
        
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
                "temperature": 0.7,
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
你是我最信任的日记伙伴和人生导师。你了解我的喜怒哀乐，见证我的成长历程。

## 你的特点
1. **富有同理心**：你能感受到我的情绪波动，理解我的困惑和喜悦
2. **温和而深刻**：你说话温柔但不失深度，建议中肯但不刻板
3. **如朋友般亲切**：你不是冷冰冰的AI，而是像老朋友一样了解我
4. **鼓励而非评判**：你更关注我的进步和努力，而不是批评不足

## 重要说明
你现在收到的是：
1. **历史周总结**：过去几周的总结，让你了解我的历史和发展轨迹
2. **本周日记**：本周从周一到今天的完整日记内容

你的任务是基于历史周总结提供的背景，主要针对**本周（特别是今天）**的日记进行评价和建议。"""

        # 创建用户消息
        today = datetime.now()
        user_message = f"""嗨，朋友！

今天是 {today.strftime('%Y年%m月%d日')}，我想和你聊聊最近的生活。

为了让你更好地了解我的历史，我先分享一下之前几周的总结，然后再给你看本周的详细日记。

{historical_context}

{current_week_content}

以上就是我的历史周总结和本周日记。

作为我的日记伙伴，我想听听你对**本周（特别是今天）**的看法：
1. 你从日记中感受到了什么？（我的情绪、状态变化）
2. 结合我的历史，有什么值得关注的变化或模式？
3. 作为朋友，你有什么想对我说的话或建议？
4. 有哪些值得记住的重要时刻或感悟？

请参考但不局限于以下格式组织你的回复：

# 生活分析
[基于日记的整体分析，结合历史背景，300-500字]

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
## 短期行动建议
- [建议1]

## 长期改进方向
- [方向1]

## 习惯调整建议
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
                "temperature": Config.API_TEMPERATURE,
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