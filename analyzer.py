#!/usr/bin/env python3
"""
日记分析模块 - 使用 DeepSeek API
"""

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from config import Config
from diary_reader import DiaryEntry
from logger import Logger
from user_profile import UserProfile
from weekly_summary import WeekInfo


# ============================================================
# API 客户端
# ============================================================

class ApiClient:
    """DeepSeek API 客户端"""
    
    def __init__(self, log_dir: Path):
        self.logger = Logger.get_logger("ApiClient")
        self.api_key = Config.get_api_key()
        self.api_url = Config.DEEPSEEK_API_URL
        self.model_name = Config.DEEPSEEK_MODEL
        
        self.interaction_log_dir = log_dir / "api_interactions"
        self.interaction_log_dir.mkdir(parents=True, exist_ok=True)
    
    def send_request(self, messages: List[Dict], temperature: float = 1.0, 
                     max_tokens: int = 4000, task_name: str = "请求",
                     json_response: bool = False) -> Optional[str]:
        """发送 API 请求并返回内容"""
        data = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if json_response:
            data["response_format"] = {"type": "json_object"}
        
        return self._send_with_retry(data, task_name)
    
    def _send_with_retry(self, data: Dict[str, Any], task_name: str) -> Optional[str]:
        """发送请求，带重试逻辑"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        prompt_length = sum(len(m.get('content', '')) for m in data.get('messages', []))
        self.logger.info(f"正在发送{task_name}，提示词长度: {prompt_length} 字符")
        
        while True:
            for attempt in range(3):
                try:
                    content, reasoning, usage = self._stream_request(headers, data, task_name)
                    self._save_interaction_log(data, content, task_name, reasoning, usage)
                    return content
                except Exception as e:
                    self.logger.warning(f"{task_name}失败 (尝试 {attempt + 1}/3): {e}")
                    if attempt < 2:
                        time.sleep(2)
            
            self.logger.error(f"{task_name}连续失败3次")
            choice = input("\n❌ 网络请求失败。按回车重试，'s' 跳过，'q' 退出: ").lower()
            if choice == 's':
                return None
            elif choice == 'q':
                raise KeyboardInterrupt("用户主动停止")
    
    def _stream_request(self, headers: Dict, data: Dict, task_name: str) -> tuple:
        """执行流式请求"""
        start_time = time.time()
        response = requests.post(
            self.api_url, headers=headers, json=data,
            timeout=Config.API_TIMEOUT, stream=True
        )
        response.raise_for_status()
        
        content, reasoning = "", ""
        usage_info = None
        
        for line in response.iter_lines():
            if not line:
                continue
            decoded = line.decode('utf-8')
            if not decoded.startswith('data: '):
                continue
            json_str = decoded[6:]
            if json_str == '[DONE]':
                break
            try:
                chunk = json.loads(json_str)
                if 'usage' in chunk:
                    usage_info = chunk['usage']
                if 'choices' in chunk and chunk['choices']:
                    delta = chunk['choices'][0].get('delta', {})
                    content += delta.get('content', '') or ''
                    reasoning += delta.get('reasoning_content', '') or ''
            except json.JSONDecodeError:
                continue
        
        elapsed = time.time() - start_time
        if usage_info:
            self.logger.info(
                f"{task_name}完成，耗时: {elapsed:.2f}s，回复: {len(content)}字，"
                f"Token: {usage_info.get('prompt_tokens', 0)}+{usage_info.get('completion_tokens', 0)}"
            )
        else:
            self.logger.info(f"{task_name}完成，耗时: {elapsed:.2f}s，回复: {len(content)}字")
        
        return content, reasoning, usage_info
    
    def _save_interaction_log(self, data: Dict, response: str, task_name: str,
                              reasoning: str = "", usage: Optional[Dict] = None):
        """保存交互日志"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = re.sub(r'[\\/*?:"<>|]', '_', task_name)
        filepath = self.interaction_log_dir / f"{timestamp}_{safe_name}.txt"
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Task: {task_name}\nModel: {data.get('model', 'unknown')}\n")
                if usage:
                    f.write(f"Tokens: {usage.get('prompt_tokens', 0)} + {usage.get('completion_tokens', 0)}\n")
                
                f.write("\n" + "="*40 + " REQUEST " + "="*40 + "\n")
                for msg in data.get('messages', []):
                    f.write(f"\n[{msg.get('role', '').upper()}]\n{'-'*20}\n{msg.get('content', '')}\n")
                
                if reasoning:
                    f.write("\n" + "="*40 + " REASONING " + "="*40 + "\n\n" + reasoning + "\n")
                f.write("\n" + "="*40 + " RESPONSE " + "="*40 + "\n\n" + response + "\n")
        except Exception as e:
            self.logger.error(f"保存交互日志失败: {e}")


# ============================================================
# 记忆管理器
# ============================================================

class MemoryManager:
    """用户记忆库管理"""
    
    def __init__(self, user_profile: UserProfile, api_client: ApiClient, log_dir: Path):
        self.user_profile = user_profile
        self.api_client = api_client
        self.log_dir = log_dir
        self.logger = Logger.get_logger("MemoryManager")
    
    def extract_and_apply_updates(self, content: str) -> str:
        """从内容中提取记忆更新并应用，返回清理后的内容"""
        json_match = re.search(r'```json\s*(\{.*?"memory_updates".*?\})\s*```', content, re.DOTALL)
        if not json_match:
            return content
        
        try:
            updates = json.loads(json_match.group(1))
            if "memory_updates" in updates:
                self.user_profile.update(updates["memory_updates"])
                self.check_and_optimize()
            return content.replace(json_match.group(0), "").strip()
        except Exception as e:
            self.logger.error(f"处理记忆更新失败: {e}")
            return content
    
    def check_and_optimize(self):
        """检查并优化记忆库大小"""
        current_length = self.user_profile.get_profile_length()
        if current_length <= 4000:
            return
        
        self.logger.info(f"⚠️ 记忆库过大 ({current_length} 字)，开始自动整理...")
        self._backup_memory()
        
        # 尝试压缩
        for attempt in range(3):
            self.logger.info(f"正在进行记忆整理 (尝试 {attempt + 1}/3)...")
            new_facts = self._compress_memory()
            if new_facts and sum(len(f) for f in new_facts) >= 1400:
                self.user_profile.update_facts(new_facts)
                current_length = self.user_profile.get_profile_length()
                self.logger.info(f"✓ 记忆整理完成，当前字数: {current_length}")
                break
        
        # 如果还是太大，尝试精简
        if current_length > 2400:
            self._prune_if_needed(current_length)
        
        # 最后检查
        if self.user_profile.get_profile_length() > 2400:
            self._prompt_manual_edit()
    
    def _backup_memory(self):
        """备份当前记忆"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = self.log_dir / f"memory_backup_{timestamp}.json"
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(self.user_profile.facts, f, ensure_ascii=False, indent=2)
            self.logger.info(f"已备份记忆到: {backup_path}")
        except Exception as e:
            self.logger.error(f"备份记忆失败: {e}")
    
    def _compress_memory(self) -> Optional[List[str]]:
        """使用 AI 压缩记忆"""
        facts_text = json.dumps(self.user_profile.facts, ensure_ascii=False, indent=2)
        
        messages = [
            {"role": "system", "content": """你是记忆整理专家。任务：
1. 清理重复内容
2. 合并同一主题的内容
3. 清理不重要的主观评价
4. **保留所有事实细节**

返回 JSON 格式：["记忆1", "记忆2", ...]"""},
            {"role": "user", "content": f"当前记忆：\n{facts_text}\n\n请整理使总字数小于 2000 字。"}
        ]
        
        content = self.api_client.send_request(messages, temperature=0.6, max_tokens=4000,
                                                task_name="记忆整理", json_response=True)
        return self._parse_memory_response(content)
    
    def _prune_if_needed(self, current_length: int):
        """按需精简记忆"""
        avg_len = current_length / len(self.user_profile.facts) if self.user_profile.facts else 30
        drop_count = int((current_length - 2000) / avg_len) + 1
        
        self.logger.info(f"⚠️ 记忆库仍过大，尝试丢弃约 {drop_count} 条...")
        
        facts_text = json.dumps(self.user_profile.facts, ensure_ascii=False, indent=2)
        messages = [
            {"role": "system", "content": f"""你是记忆整理专家。需要选择性丢弃记忆。
**保留**：长期目标、重要关系、健康状况、核心喜好
**丢弃**：过时计划、琐碎日常（约 {drop_count} 条）

返回 JSON：["记忆1", "记忆2", ...]"""},
            {"role": "user", "content": f"当前记忆：\n{facts_text}"}
        ]
        
        content = self.api_client.send_request(messages, temperature=0.5, max_tokens=4000,
                                                task_name="记忆精简", json_response=True)
        new_facts = self._parse_memory_response(content)
        if new_facts and sum(len(f) for f in new_facts) >= 1400:
            self.user_profile.update_facts(new_facts)
            self.logger.info(f"✓ 记忆精简完成，当前字数: {self.user_profile.get_profile_length()}")
    
    def _parse_memory_response(self, content: Optional[str]) -> Optional[List[str]]:
        """解析 AI 返回的记忆列表"""
        if not content:
            return None
        try:
            data = json.loads(content)
            if isinstance(data, list):
                return [str(i) for i in data]
            if isinstance(data, dict):
                for val in data.values():
                    if isinstance(val, list):
                        return [str(i) for i in val]
            return None
        except Exception as e:
            self.logger.error(f"解析记忆响应失败: {e}")
            return None
    
    def _prompt_manual_edit(self):
        """提示用户手动编辑"""
        self.logger.warning(f"⚠️ 记忆库仍过大，需要手动编辑")
        print(f"\n🛑 请手动编辑: {self.user_profile.profile_path}")
        input("编辑完成后按回车继续...")
        self.user_profile.facts = self.user_profile._load_profile()


# ============================================================
# 提示词模板
# ============================================================

class PromptTemplates:
    """提示词模板"""
    
    MEMORY_UPDATE_INSTRUCTION = '''
## 记忆更新功能
如果你从日记中发现了关于用户的新事实（如新的长期目标、重要关系、健康状况、喜好厌恶等），或者发现旧的记忆已过时，请在回复的**最后**，使用 JSON 格式输出记忆更新指令：
```json
{
    "memory_updates": {
        "add": ["新事实1", "新事实2"],
        "remove": ["过时事实1"],
        "update": [{"old": "旧事实", "new": "新事实"}]
    }
}
```
如果没有更新，则不需要输出此 JSON 块。
注意：只记录长期有价值的信息，"remove" 和 "update" 中的 "old" 必须与"用户画像"中的文本完全一致。'''

    @staticmethod
    def weekly_summary_system() -> str:
        return """# 角色设定
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

    @staticmethod
    def daily_evaluation_system(profile_context: str) -> str:
        return f"""# 角色设定
你是一位贴心的日记助手。

## 任务
阅读用户的历史周总结、本周日记以及用户画像，为**今天**的日记生成一份简短的评价和建议。

## 要求
1. **篇幅限制**：800字以内。
2. **内容聚焦**：针对今天的日记内容，结合之前的背景。
3. **语气风格**：亲切、鼓励、有洞察力。
4. **输出格式**：直接输出评价和建议内容，不要包含标题。

{profile_context}
{PromptTemplates.MEMORY_UPDATE_INSTRUCTION}"""

    @staticmethod
    def weekly_analysis_system(profile_context: str) -> str:
        return f"""# 角色设定
你是一位专业的个人成长顾问。

## 任务
基于历史周总结、本周完整的日记以及用户画像，对**本周**进行深度分析，并提出下周的建议。

## 要求
1. **深度洞察**：发现行为模式和心理变化
2. **建设性**：建议具体可行
3. **前瞻性**：基于本周情况指导下周

{profile_context}
{PromptTemplates.MEMORY_UPDATE_INSTRUCTION}"""


# ============================================================
# 上下文构建器
# ============================================================

class ContextBuilder:
    """上下文内容构建器"""
    
    @staticmethod
    def build_profile_context(user_profile: Optional[UserProfile]) -> str:
        if not user_profile:
            return ""
        return f"\n## 👤 用户画像 (长期记忆)\n{user_profile.get_profile_text()}\n"
    
    @staticmethod
    def build_historical_summaries(weekly_summaries: List[tuple]) -> str:
        if not weekly_summaries:
            return ""
        parts = ["\n## 📚 历史周总结\n"]
        for week_info, summary in weekly_summaries:
            header = f"### {week_info.year}年第{week_info.week}周 ({week_info.start_date.strftime('%m月%d日')}-{week_info.end_date.strftime('%m月%d日')})"
            parts.extend([header, "", summary, "", "="*50, ""])
        return "\n".join(parts)
    
    @staticmethod
    def build_diaries_context(diaries: List[DiaryEntry], title: str = "本周日记") -> str:
        if not diaries:
            return ""
        parts = [f"\n## 📝 {title}\n"]
        for diary in diaries:
            parts.extend([diary.format_for_ai(), "", "="*50, ""])
        return "\n".join(parts)


# ============================================================
# 分析器主类
# ============================================================

class DeepSeekAnalyzer:
    """使用 DeepSeek API 分析日记"""
    
    def __init__(self, log_dir: Path, output_dir: Path, user_profile: Optional[UserProfile] = None):
        self.log_dir = log_dir
        self.output_dir = output_dir
        self.user_profile = user_profile
        self.logger = Logger.get_logger("Analyzer")
        
        self.api_client = ApiClient(log_dir)
        self.memory_manager = MemoryManager(user_profile, self.api_client, log_dir) if user_profile else None
    
    def generate_weekly_summary(self, week_info: WeekInfo) -> Optional[str]:
        """生成周总结"""
        if not week_info.diaries:
            self.logger.warning(f"{week_info} 没有日记")
            return None
        
        self.logger.info(f"正在生成 {week_info} 的总结...")
        
        week_content = week_info.format_for_ai()
        start_date = week_info.start_date.strftime('%Y年%m月%d日')
        end_date = week_info.end_date.strftime('%Y年%m月%d日')
        
        messages = [
            {"role": "system", "content": PromptTemplates.weekly_summary_system()},
            {"role": "user", "content": f"""时间范围：{start_date} 至 {end_date}
日记数量：{len(week_info.diaries)} 篇

{week_content}

请生成周总结。"""}
        ]
        
        return self.api_client.send_request(messages, temperature=0.8, max_tokens=4000, task_name="周总结生成")
    
    def generate_daily_evaluation(self, current_diary: DiaryEntry, 
                                   context_diaries: List[DiaryEntry], 
                                   weekly_summaries: List[tuple]) -> Optional[str]:
        """生成每日评价和建议"""
        self.logger.info(f"正在为 {current_diary.date.strftime('%Y-%m-%d')} 生成评价...")
        
        # 构建上下文
        profile_context = ContextBuilder.build_profile_context(self.user_profile)
        historical_context = ContextBuilder.build_historical_summaries(weekly_summaries)
        current_week_content = ContextBuilder.build_diaries_context(context_diaries, "本周日记（截至今日）")
        
        messages = [
            {"role": "system", "content": PromptTemplates.daily_evaluation_system(profile_context)},
            {"role": "user", "content": f"""今天是 {current_diary.date.strftime('%Y年%m月%d日')}。

{historical_context}

{current_week_content}

请为今天的日记写一段评价和建议。"""}
        ]
        
        content = self.api_client.send_request(messages, temperature=1.0, max_tokens=2000, task_name="每日评价生成")
        return self._process_memory_updates(content)
    
    def generate_weekly_analysis(self, week_diaries: List[DiaryEntry], 
                                  historical_summaries: List[tuple]) -> Optional[str]:
        """生成每周分析建议（在周日触发）"""
        self.logger.info(f"正在生成周分析 (历史周总结: {len(historical_summaries)} 周, 本周日记: {len(week_diaries)} 篇)")
        
        # 构建上下文
        profile_context = ContextBuilder.build_profile_context(self.user_profile)
        historical_context = ContextBuilder.build_historical_summaries(historical_summaries)
        current_week_content = ContextBuilder.build_diaries_context(week_diaries, "本周日记")
        
        end_date = week_diaries[-1].date.strftime('%Y年%m月%d日')
        
        messages = [
            {"role": "system", "content": PromptTemplates.weekly_analysis_system(profile_context)},
            {"role": "user", "content": f"""本周结束日期：{end_date}。

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
"""}
        ]
        
        content = self.api_client.send_request(messages, temperature=1.0, max_tokens=Config.API_MAX_TOKENS, task_name="周分析生成")
        content = self._process_memory_updates(content)
        
        if content:
            self.save_analysis_result(content, week_diaries)
        
        return content
    
    def _process_memory_updates(self, content: Optional[str]) -> Optional[str]:
        """处理响应内容中的记忆更新"""
        if content and self.memory_manager:
            return self.memory_manager.extract_and_apply_updates(content)
        return content
    
    def save_analysis_result(self, analysis: str, diaries: List[DiaryEntry]):
        """保存分析结果"""
        if not analysis:
            return
        
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        start_date = diaries[0].date.strftime("%Y%m%d")
        end_date = diaries[-1].date.strftime("%Y%m%d")
        filepath = self.output_dir / f"analysis_{start_date}-{end_date}_{timestamp}.md"
        
        meta = f"""# 日记分析报告
**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**分析范围**: {diaries[0].date.strftime('%Y-%m-%d')} 到 {diaries[-1].date.strftime('%Y-%m-%d')}
**日记数量**: {len(diaries)} 篇

---

"""
        try:
            filepath.write_text(meta + analysis, encoding='utf-8')
            self.logger.info(f"分析结果已保存到: {filepath}")
        except Exception as e:
            self.logger.error(f"保存分析结果失败: {e}")
