#!/usr/bin/env python3
"""
日记分析模块 - 使用DeepSeek API
"""

import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import requests
import re
import json

from diary_reader import DiaryEntry
from config import Config
from logger import Logger
from weekly_summary import WeekInfo
from user_profile import UserProfile


class DeepSeekAnalyzer:
    """使用DeepSeek API分析日记"""
    
    def __init__(self, log_dir: Path, output_dir: Path, user_profile: Optional[UserProfile] = None):
        self.log_dir = log_dir
        self.output_dir = output_dir
        self.user_profile = user_profile
        self.logger = Logger.get_logger("Analyzer")
        
        # 创建交互日志目录
        self.interaction_log_dir = self.log_dir / "api_interactions"
        self.interaction_log_dir.mkdir(parents=True, exist_ok=True)
        
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
    
    def _check_and_optimize_memory(self):
        """检查并优化记忆库大小"""
        if not self.user_profile:
            return

        current_length = self.user_profile.get_profile_length()
        if current_length <= 4000:
            return

        self.logger.info(f"⚠️ 记忆库过大 ({current_length} 字 > 4000 字)，开始自动整理...")
        
        # 备份当前记忆
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = self.log_dir / f"memory_backup_{timestamp}.json"
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(self.user_profile.facts, f, ensure_ascii=False, indent=2)
            self.logger.info(f"已备份当前记忆到: {backup_path}")
        except Exception as e:
            self.logger.error(f"备份记忆失败: {e}")
        
        # 1. 尝试压缩整理
        new_facts = None
        for attempt in range(3):
            self.logger.info(f"正在进行记忆整理 (尝试 {attempt + 1}/3)...")
            temp_facts = self._compress_memory(self.user_profile.facts)
            
            if temp_facts:
                temp_length = sum(len(f) for f in temp_facts)
                if temp_length < 1400:
                    self.logger.warning(f"压缩后字数过少 ({temp_length} < 1400)，放弃本次修改...")
                    continue
                
                new_facts = temp_facts
                break
            else:
                self.logger.warning("记忆整理返回结果无效或解析失败")
        
        if new_facts:
            new_length = sum(len(f) for f in new_facts)
            self.user_profile.update_facts(new_facts)
            self.logger.info(f"✓ 记忆整理完成，当前字数: {new_length}")
            current_length = new_length
        else:
            self.logger.warning("记忆整理多次失败，保持原样")

        # 2. 如果还是太大，尝试选择性丢弃
        if current_length > 2000:
            # 估算需要丢弃的数量 (假设平均每条记忆30字)
            avg_len = current_length / len(self.user_profile.facts) if self.user_profile.facts else 30
            drop_chars = current_length - 2000
            drop_count = int(drop_chars / avg_len) + 1
            
            self.logger.info(f"⚠️ 记忆库仍然过大 ({current_length} 字)，尝试丢弃约 {drop_count} 条次要记忆...")
            
            new_facts = self._prune_memory(self.user_profile.facts, drop_count)
            if new_facts:
                new_length = sum(len(f) for f in new_facts)
                if new_length < 1400:
                     self.logger.warning(f"丢弃后字数过少 ({new_length} < 1400)，放弃本次修改...")
                else:
                    self.user_profile.update_facts(new_facts)
                    self.logger.info(f"✓ 记忆精简完成，当前字数: {new_length}")
                    current_length = new_length

        # 3. 如果还是太大，暂停程序
        if current_length > 2000:
            self.logger.warning(f"⚠️ 记忆库仍然过大 ({current_length} 字)，自动处理无法满足要求。")
            print("\n🛑 记忆库过大，请手动编辑 user_profile.json 文件。")
            print(f"当前文件路径: {self.user_profile.profile_path}")
            input("编辑完成后，请按回车键继续...")
            # 重新加载
            self.user_profile.facts = self.user_profile._load_profile()
            self.logger.info(f"已重新加载记忆库，当前字数: {self.user_profile.get_profile_length()}")

    def _compress_memory(self, facts: List[str]) -> Optional[List[str]]:
        """使用AI整理压缩记忆"""
        facts_text = json.dumps(facts, ensure_ascii=False, indent=2)
        
        system_prompt = """你是一位专业的记忆整理专家。
用户的长期记忆库过大，需要你进行整理和压缩。

任务：
1. 清理重复内容。
2. 合并同一主题的内容（例如将多条关于"跑步"的记录合并）。
3. 清理不是很有意义的主观评价。
4. **核心要求**：不要减少记忆的信息量，保留所有事实细节。

请直接返回整理后的记忆列表，格式为 JSON 字符串：
["记忆1", "记忆2", ...]
"""
        
        user_message = f"""当前记忆列表：
{facts_text}

请整理上述记忆，使总字数小于 2000 字，尽可能保留信息量。"""

        data = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": 0.5, # 使用较低温度以保证准确性
            "max_tokens": 4000,
            "response_format": {"type": "json_object"}
        }

        content = self._send_request_with_retry(data, "记忆整理")
        return self._parse_memory_response(content)

    def _prune_memory(self, facts: List[str], drop_count: int) -> Optional[List[str]]:
        """使用AI选择性丢弃记忆"""
        facts_text = json.dumps(facts, ensure_ascii=False, indent=2)
        
        system_prompt = f"""你是一位专业的记忆整理专家。
用户的长期记忆库严重超标，需要你进行选择性丢弃。

任务：
1. 识别并丢弃相对不重要的记忆。
2. **保留**：关于长期目标、重要人际关系、健康状况、核心喜好厌恶等关键信息。
3. **丢弃**：过时的短期计划、琐碎的日常记录、不再相关的信息。
4. 大约需要丢弃 {drop_count} 条记录。

请直接返回筛选后的记忆列表，格式为 JSON 字符串：
["记忆1", "记忆2", ...]
"""
        
        user_message = f"""当前记忆列表：
{facts_text}

请筛选上述记忆，丢弃次要信息。"""

        data = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": 0.5,
            "max_tokens": 4000,
            "response_format": {"type": "json_object"}
        }

        content = self._send_request_with_retry(data, "记忆精简")
        return self._parse_memory_response(content)

    def _parse_memory_response(self, content: Optional[str]) -> Optional[List[str]]:
        """解析AI返回的记忆列表"""
        if not content:
            return None
        
        try:
            # 尝试直接解析 JSON
            data = json.loads(content)
            if isinstance(data, list):
                return [str(i) for i in data]
            if isinstance(data, dict):
                # 应对可能返回 {"memories": [...]} 的情况
                for key in data:
                    if isinstance(data[key], list):
                        return [str(i) for i in data[key]]
            
            # 如果直接解析失败，尝试从代码块提取
            json_match = re.search(r'```json\s*(\[.*?\])\s*```', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(1))
            
            return None
        except Exception as e:
            self.logger.error(f"解析记忆响应失败: {e}")
            return None

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
        
        # 强制开启流式模式，以避免长连接超时和响应截断
        data['stream'] = True
        
        while True:
            for attempt in range(3):
                try:
                    start_time = time.time()
                    # 开启 stream=True
                    response = requests.post(self.api_url, headers=headers, json=data, timeout=Config.API_TIMEOUT, stream=True)
                    
                    response.raise_for_status()
                    
                    content = ""
                    import json
                    
                    # 处理流式响应
                    for line in response.iter_lines():
                        if line:
                            decoded_line = line.decode('utf-8')
                            if decoded_line.startswith('data: '):
                                json_str = decoded_line[6:]
                                if json_str == '[DONE]':
                                    break
                                try:
                                    chunk = json.loads(json_str)
                                    if 'choices' in chunk and len(chunk['choices']) > 0:
                                        delta = chunk['choices'][0].get('delta', {})
                                        if 'content' in delta and delta['content']:
                                            content += delta['content']
                                except json.JSONDecodeError:
                                    continue
                    
                    elapsed_time = time.time() - start_time
                    response_length = len(content)
                    self.logger.info(f"{task_name}完成，耗时: {elapsed_time:.2f}秒，回复长度: {response_length} 字符")
                    
                    # 保存交互日志
                    self._save_interaction_log(data, content, task_name)
                    
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

    def _save_interaction_log(self, data: Dict[str, Any], response: str, task_name: str):
        """保存完整的请求和响应内容"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # 简单的文件名清理
        safe_task_name = re.sub(r'[\\/*?:"<>|]', '_', task_name)
        filename = f"{timestamp}_{safe_task_name}.txt"
        filepath = self.interaction_log_dir / filename
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Task: {task_name}\n")
                f.write(f"Model: {data.get('model', 'unknown')}\n")
                f.write("="*40 + " REQUEST " + "="*40 + "\n")
                
                if 'messages' in data:
                    for msg in data['messages']:
                        role = msg.get('role', 'unknown')
                        content = msg.get('content', '')
                        f.write(f"\n[{role.upper()}]\n")
                        f.write("-" * 20 + "\n")
                        f.write(content + "\n")
                else:
                    f.write(json.dumps(data, ensure_ascii=False, indent=2))

                f.write("\n" + "="*40 + " RESPONSE " + "="*40 + "\n\n")
                f.write(response + "\n")
                f.write("\n" + "="*89 + "\n")
                
            self.logger.debug(f"交互日志已保存: {filepath}")
        except Exception as e:
            self.logger.error(f"保存交互日志失败: {e}")
    
    def generate_weekly_summary(self, week_info: WeekInfo) -> Optional[str]:
        """生成周总结（不需要用户确认）"""
        if not week_info.diaries:
            self.logger.warning(f"{week_info} 没有日记")
            return None
        
        self.logger.info(f"正在生成 {week_info} 的总结...")
        
        # 格式化周日记
        week_content = week_info.format_for_ai()
        
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
            current_week_content = "\n## 📝 本周日记（截至今日）\n\n"
            for diary in context_diaries:
                # format_diary_for_ai 已经排除了 AI 说 部分
                diary_content = diary.format_for_ai()
                current_week_content += diary_content + "\n\n" + "="*50 + "\n\n"
        
        # 用户画像上下文
        profile_context = ""
        if self.user_profile:
            profile_context = f"\n## 👤 用户画像 (长期记忆)\n{self.user_profile.get_profile_text()}\n"

        # 创建系统提示
        system_prompt = f"""# 角色设定
你是一位贴心的日记助手。

## 任务
阅读用户的历史周总结、本周日记以及用户画像，为**今天**的日记生成一份简短的评价和建议。

## 要求
1. **篇幅限制**：800字以内。
2. **内容聚焦**：针对今天的日记内容，结合之前的背景。
3. **语气风格**：亲切、鼓励、有洞察力。
4. **输出格式**：直接输出评价和建议内容，不要包含标题（因为会被添加到 "## AI 说" 标题下）。

{profile_context}

## 记忆更新功能
如果你从今天的日记中发现了关于用户的新事实（如新的长期目标、重要关系、健康状况、喜好厌恶等），或者发现旧的记忆已过时，请在回复的**最后**，使用 JSON 格式输出记忆更新指令。
格式如下：
```json
{{
    "memory_updates": {{
        "add": ["新事实1", "新事实2"],
        "remove": ["过时事实1"],
        "update": [{{"old": "旧事实", "new": "新事实"}}]
    }}
}}
```
如果没有更新，则不需要输出此 JSON 块。
注意：
1. 只记录长期有价值的信息，不要记录琐碎日常。
2. "remove" 和 "update" 中的 "old" 必须与"用户画像"中列出的文本完全一致。
"""
        
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
        
        content = self._send_request_with_retry(data, "每日评价生成")
        
        if content and self.user_profile:
            # 提取并处理 JSON
            json_match = re.search(r'```json\s*(\{.*?"memory_updates".*?\})\s*```', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
                try:
                    updates = json.loads(json_str)
                    if "memory_updates" in updates:
                        self.user_profile.update(updates["memory_updates"])
                        # 检查并优化记忆库
                        self._check_and_optimize_memory()
                    # 从内容中移除 JSON 块
                    content = content.replace(json_match.group(0), "").strip()
                except Exception as e:
                    self.logger.error(f"处理记忆更新失败: {e}")
        
        return content

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
            current_week_content = "\n## 📝 本周日记\n\n"
            for diary in week_diaries:
                diary_content = diary.format_for_ai()
                current_week_content += diary_content + "\n\n" + "="*50 + "\n\n"
        
        # 用户画像上下文
        profile_context = ""
        if self.user_profile:
            profile_context = f"\n## 👤 用户画像 (长期记忆)\n{self.user_profile.get_profile_text()}\n"

        # 创建系统提示
        system_prompt = f"""# 角色设定
你是一位专业的个人成长顾问。

## 任务
基于历史周总结、本周完整的日记以及用户画像，对**本周**进行深度分析，并提出下周的建议。

## 要求
1. **深度洞察**：发现行为模式和心理变化
2. **建设性**：建议具体可行
3. **前瞻性**：基于本周情况指导下周

{profile_context}

## 记忆更新功能
如果你从本周的日记和分析中发现了关于用户的新事实（如新的长期目标、重要关系、健康状况、喜好厌恶等），或者发现旧的记忆已过时，请在回复的**最后**，使用 JSON 格式输出记忆更新指令。
格式如下：
```json
{{
    "memory_updates": {{
        "add": ["新事实1", "新事实2"],
        "remove": ["过时事实1"],
        "update": [{{"old": "旧事实", "new": "新事实"}}]
    }}
}}
```
如果没有更新，则不需要输出此 JSON 块。
注意：
1. 只记录长期有价值的信息，不要记录琐碎日常。
2. "remove" 和 "update" 中的 "old" 必须与"用户画像"中列出的文本完全一致。
"""

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
        
        if analysis_result and self.user_profile:
            # 提取并处理 JSON
            json_match = re.search(r'```json\s*(\{.*?"memory_updates".*?\})\s*```', analysis_result, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
                try:
                    updates = json.loads(json_str)
                    if "memory_updates" in updates:
                        self.user_profile.update(updates["memory_updates"])
                        # 检查并优化记忆库
                        self._check_and_optimize_memory()
                    # 从内容中移除 JSON 块
                    analysis_result = analysis_result.replace(json_match.group(0), "").strip()
                except Exception as e:
                    self.logger.error(f"处理记忆更新失败: {e}")

        if analysis_result:
            # 保存分析结果
            self.save_analysis_result(analysis_result, week_diaries)
            
        return analysis_result