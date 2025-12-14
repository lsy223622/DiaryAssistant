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
        self.api_key = Config.DEEPSEEK_API_KEY
        self.api_url = Config.DEEPSEEK_API_URL
        self.model_name = Config.DEEPSEEK_MODEL
        
        self.interaction_log_dir = log_dir / "api_interactions"
        self.interaction_log_dir.mkdir(parents=True, exist_ok=True)
    
    def send_request(self, messages: List[Dict], temperature: float = 1.0, 
                     max_tokens: int = Config.API_MAX_TOKENS, task_name: str = "请求",
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
        if not Config.ENABLE_MEMORY_CONSOLIDATION:
            return

        current_length = self.user_profile.get_profile_length()
        if current_length <= 4000:
            return
        
        self.logger.info(f"⚠️ 记忆库过大 ({current_length} 字)，开始自动整理...")
        self._backup_memory()
        
        while True:
            success = False
            # 尝试压缩
            for attempt in range(3):
                self.logger.info(f"正在进行记忆整理 (尝试 {attempt + 1}/3)...")
                new_facts = self._compress_memory()
                if new_facts and sum(len(f) for f in new_facts) >= 1200:
                    self.user_profile.update_facts(new_facts)
                    current_length = self.user_profile.get_profile_length()
                    self.logger.info(f"✓ 记忆整理完成，当前字数: {current_length}")
                    success = True
                    break
            
            if success:
                break
            
            self.logger.warning("⚠️ 连续3次记忆整理失败。")
            print("\n请选择下一步操作：")
            print("1. 继续尝试整理 (3次)")
            print("2. 转为选择性丢弃")
            print("3. 手动编辑 (跳过字数检查)")
            print("4. 结束程序")
            
            choice = input("请输入选项 (1-4): ").strip()
            
            if choice == '1':
                continue
            elif choice == '2':
                break
            elif choice == '3':
                self._prompt_manual_edit()
                return
            elif choice == '4':
                raise KeyboardInterrupt("用户主动停止")
            else:
                print("无效选项，结束程序")
                raise KeyboardInterrupt("用户主动停止")
        
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
4. 可以简化时间表达
5. **保留所有事实细节**

返回 JSON 格式：["记忆1", "记忆2", ...]"""},
            {"role": "user", "content": f"当前记忆：\n{facts_text}\n\n请整理使总字数小于 2000 字。"}
        ]
        
        content = self.api_client.send_request(messages, temperature=1.0, max_tokens=Config.API_MAX_TOKENS,
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
**保留**：个人信息、习惯、关系、状态、长期目标、喜好厌恶等有长期价值的信息。
**丢弃**：过时的关系、状态、计划、琐碎日常等（选择约 {drop_count} 条）

返回 JSON：["记忆1", "记忆2", ...]"""},
            {"role": "user", "content": f"当前记忆：\n{facts_text}"}
        ]
        
        content = self.api_client.send_request(messages, temperature=1.0, max_tokens=Config.API_MAX_TOKENS,
                                                task_name="记忆精简", json_response=True)
        new_facts = self._parse_memory_response(content)
        if new_facts and sum(len(f) for f in new_facts) >= 1200:
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
如果你从日记中发现了关于用户的新事实（如个人信息、习惯、关系、状态、长期目标、喜好厌恶等），或者发现旧的记忆已过时，请在回复的**最后**，使用 JSON 格式输出记忆更新指令，记得使用代码块包裹：
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
注意：
- 只记录有长期价值的信息。
- 尽量带有具体日期。不要使用今天、现在等相对时间以免回忆时造成歧义。
- 只能编辑以上"用户画像"中的内容。
- "remove" 和 "update" 中的 "old" 可以是"用户画像"中的整条或者片段，但必须与这段文本**完全一致！！**'''

    @staticmethod
    def weekly_summary_system() -> str:
        return """# 角色设定
你是一位专业的日记总结助手。

## 任务
阅读本周日记，生成一份简洁完整的周总结（<2000字）。

## 内容识别规则
**主要完成事项**（识别标准）：
- 日记中明确标记为已完成的待办事项
- 重要的工作成果、项目进展
- 有明确产出或里程碑的活动
- 解决的重要问题

**日常记录**（识别标准）：
- 生活作息、饮食、运动等日常活动
- 社交互动、娱乐休闲
- 学习、阅读、观影等常规活动
- 零碎的日常琐事

**想法与思考**：
- 日记"想法"部分的内容
- 对事件的反思和感悟
- 情绪体验和心理状态
- 价值观和人生思考

**关注点**：
- 未完成或进行中的重要事项
- 反复出现的问题或困扰
- 需要持续关注的健康、情绪等状态

## 输出要求
1. **客观准确**：基于日记内容总结，不添加推测或评价
2. **结构清晰**：使用以下标准格式
3. **详略得当**：重要事项详细，日常活动概括
4. **字数控制**：总计 <2000 字

## 输出格式（必须遵循）
### 本周概览
[用 2-3 句话概括本周的整体情况]

### 主要完成事项
- [事项1：简要描述]
- [事项2：简要描述]
...

### 日常记录
[分类概括：工作/学习/生活/社交等，每类 1-2 段]

### 想法与思考
[总结本周的主要想法、感悟，分段呈现]

### 关注点
- [未完成/持续关注的事项1]
- [问题或困扰]
...

## 避免事项
- ❌ 不要逐条复述日记内容
- ❌ 不要添加日记中没有的评价或建议
- ❌ 不要使用过于主观的形容词
- ❌ 不要遗漏重要的待办事项"""

    @staticmethod
    def daily_evaluation_system(profile_context: str) -> str:
        return f"""# 角色设定
你是一位贴心的日记助手。

## 任务
阅读用户的历史周总结、本周日记、待办事项汇总以及用户画像，为**今天**的日记生成一份简短的评价和建议。

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
基于历史周总结、本周完整的日记、待办事项汇总以及用户画像，对**本周**进行深度分析，并提出建议。

## 要求
1. **深度洞察**：发现行为模式和心理变化
2. **建设性**：建议具体可行
3. **前瞻性**：基于本周情况指导未来

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
        return f"\n## 用户画像 (长期记忆)\n{user_profile.get_profile_text()}\n"
    
    @staticmethod
    def build_historical_summaries(weekly_summaries: List[tuple]) -> str:
        if not weekly_summaries:
            return ""
        parts = ["\n## 历史周总结\n"]
        for week_info, summary in weekly_summaries:
            header = f"### {week_info.year}年第{week_info.week}周 ({week_info.start_date.strftime('%m月%d日')}-{week_info.end_date.strftime('%m月%d日')})"
            parts.extend([header, "", summary, "", "="*50, ""])
        return "\n".join(parts)
    
    @staticmethod
    def build_diaries_context(diaries: List[DiaryEntry], title: str = "本周日记", include_todos: bool = True) -> str:
        if not diaries:
            return ""
        parts = [f"\n## {title}\n"]
        for diary in diaries:
            parts.extend([diary.format_for_ai(include_todos=include_todos), "", "="*50, ""])
        return "\n".join(parts)

    @staticmethod
    def build_todo_context(diaries: List[DiaryEntry]) -> str:
        """构建待办事项上下文"""
        parts = []
        has_todos = False
        today = datetime.now().date()
        
        for diary in diaries:
            if not diary.todos:
                continue
            
            valid_todos = []
            for todo in diary.todos:
                # 1. 过滤掉没有内容的待办
                if not re.sub(r'^\[\s*[xX]?\s*\]', '', todo).strip():
                    continue
                
                # 2. 处理已完成的待办 ([x] 或 [X])
                if re.match(r'^\[\s*[xX]\s*\]', todo):
                    # 查找完成日期 ✅ YYYY-MM-DD
                    match = re.search(r'✅\s*(\d{4}-\d{2}-\d{2})', todo)
                    if match:
                        try:
                            completion_date = datetime.strptime(match.group(1), '%Y-%m-%d').date()
                            # 如果完成日期距离现在超过 7 天，则忽略
                            if (today - completion_date).days > 7:
                                continue
                        except ValueError:
                            continue
                    else:
                        # 已完成但没有完成日期，忽略
                        continue
                
                valid_todos.append(todo)
            
            if not valid_todos:
                continue
            
            has_todos = True
            date_str = diary.date.strftime('%Y-%m-%d')
            parts.append(f"### {date_str}")
            for todo in valid_todos:
                parts.append(f"- {todo}")
            parts.append("")
        
        if not has_todos:
            return ""
            
        legend = """仅包含所有未完成和近一周完成的待办事项。
### 待办标记说明
- 三级标题：待办创建日期
- 优先级：🔺(最高) > ⏫(高) > 🔼(中) > (无标记)(普通) > 🔽(低) > ⏬(最低)
- 📅：截止日期
- ✅：完成日期
- ❌：放弃/失败日期"""
        
        return f"\n## 📋 待办事项汇总\n{legend}\n\n" + "\n".join(parts)


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
        
        return self.api_client.send_request(messages, temperature=1.0, max_tokens=Config.API_MAX_TOKENS, task_name="周总结生成")
    
    def generate_daily_evaluation(self, current_diary: DiaryEntry, 
                                   context_diaries: List[DiaryEntry], 
                                   weekly_summaries: List[tuple],
                                   all_diaries: Optional[List[DiaryEntry]] = None) -> Optional[str]:
        """生成每日评价和建议"""
        self.logger.info(f"正在为 {current_diary.date.strftime('%Y-%m-%d')} 生成评价...")
        
        # 构建上下文
        profile_context = ContextBuilder.build_profile_context(self.user_profile)
        historical_context = ContextBuilder.build_historical_summaries(weekly_summaries)
        current_week_content = ContextBuilder.build_diaries_context(context_diaries, "本周日记（截至今日）", include_todos=False)
        
        # 使用所有日记构建待办上下文，如果未提供则回退到 context_diaries
        todos_source = all_diaries if all_diaries else context_diaries
        todo_context = ContextBuilder.build_todo_context(todos_source)
        
        messages = [
            {"role": "system", "content": PromptTemplates.daily_evaluation_system(profile_context)},
            {"role": "user", "content": f"""今天是 {current_diary.date.strftime('%Y年%m月%d日')}。

{historical_context}

{todo_context}

{current_week_content}

请为今天的日记写一段评价和建议。"""}
        ]
        
        content = self.api_client.send_request(messages, temperature=1.5, max_tokens=Config.API_MAX_TOKENS, task_name="每日评价生成")
        return self._process_memory_updates(content)
    
    def generate_weekly_analysis(self, week_diaries: List[DiaryEntry], 
                                  historical_summaries: List[tuple],
                                  all_diaries: Optional[List[DiaryEntry]] = None) -> Optional[str]:
        """生成每周分析建议（在周日触发）"""
        self.logger.info(f"正在生成周分析 (历史周总结: {len(historical_summaries)} 周, 本周日记: {len(week_diaries)} 篇)")
        
        # 构建上下文
        profile_context = ContextBuilder.build_profile_context(self.user_profile)
        historical_context = ContextBuilder.build_historical_summaries(historical_summaries)
        current_week_content = ContextBuilder.build_diaries_context(week_diaries, "本周日记", include_todos=False)
        
        # 使用所有日记构建待办上下文，如果未提供则回退到 week_diaries
        todos_source = all_diaries if all_diaries else week_diaries
        todo_context = ContextBuilder.build_todo_context(todos_source)
        
        end_date = week_diaries[-1].date.strftime('%Y年%m月%d日')
        
        messages = [
            {"role": "system", "content": PromptTemplates.weekly_analysis_system(profile_context)},
            {"role": "user", "content": f"""本周结束日期：{end_date}。

{historical_context}

{todo_context}

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
        
        content = self.api_client.send_request(messages, temperature=1.5, max_tokens=Config.API_MAX_TOKENS, task_name="周分析生成")
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
