#!/usr/bin/env python3
"""
用户画像管理模块
"""

import json
from pathlib import Path
from typing import Any, Dict, List

from logger import Logger


class UserProfile:
    """用户画像（长期记忆）管理"""
    
    def __init__(self, profile_path: Path):
        self.profile_path = profile_path
        self.logger = Logger.get_logger("UserProfile")
        self.facts: List[str] = self._load_profile()

    def _load_profile(self) -> List[str]:
        """加载用户画像"""
        if not self.profile_path.exists():
            self.logger.debug("用户画像文件不存在，初始化为空")
            return []
        try:
            data = json.loads(self.profile_path.read_text(encoding='utf-8'))
            if isinstance(data, list):
                self.logger.debug(f"已加载 {len(data)} 条记忆")
                return [str(item) for item in data]
            return []
        except Exception as e:
            self.logger.error(f"加载用户画像失败: {e}")
            return []

    def save_profile(self):
        """保存用户画像"""
        try:
            self.profile_path.write_text(
                json.dumps(self.facts, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )
            self.logger.info("用户画像已保存")
        except Exception as e:
            self.logger.error(f"保存用户画像失败: {e}")

    def get_profile_text(self) -> str:
        """获取格式化的画像文本"""
        if not self.facts:
            return "暂无个人信息记录。"
        return "\n".join(f"- {fact}" for fact in self.facts)

    def get_profile_length(self) -> int:
        """获取画像总字数"""
        return sum(len(fact) for fact in self.facts)

    def update_facts(self, new_facts: List[str]):
        """替换所有记忆"""
        self.facts = new_facts
        self.save_profile()
        self.logger.info(f"画像已更新，共 {len(self.facts)} 条")

    def update(self, operations: Dict[str, Any]):
        """
        更新画像
        operations: {
            "add": ["fact1", "fact2"],
            "remove": ["fact to remove"],
            "update": [{"old": "old fact", "new": "new fact"}]
        }
        """
        added = self._handle_add(operations.get("add", []))
        removed = self._handle_remove(operations.get("remove", []))
        updated = self._handle_update(operations.get("update", []))

        if added or removed or updated:
            self.logger.info(f"画像更新: +{added}, -{removed}, ~{updated}")
            self.save_profile()

    def _handle_add(self, facts_to_add: List[str]) -> int:
        """处理添加操作"""
        count = 0
        for fact in facts_to_add:
            if fact and fact not in self.facts:
                self.facts.append(fact)
                count += 1
        return count

    def _handle_remove(self, facts_to_remove: List[str]) -> int:
        """处理删除操作"""
        count = 0
        for fact in facts_to_remove:
            if not fact:
                continue
            if fact in self.facts:
                self.facts.remove(fact)
                count += 1
            else:
                # 模糊匹配
                candidates = [f for f in self.facts if fact in f]
                if len(candidates) == 1:
                    self.facts.remove(candidates[0])
                    count += 1
                else:
                    self.logger.warning(f"无法找到要删除的记忆: {fact}")
        return count

    def _handle_update(self, updates: List[Dict]) -> int:
        """处理更新操作"""
        count = 0
        for item in updates:
            old_fact = item.get("old")
            new_fact = item.get("new")
            if not old_fact or new_fact is None:
                continue
            
            if old_fact in self.facts:
                idx = self.facts.index(old_fact)
                self.facts[idx] = new_fact
                count += 1
            else:
                # 模糊匹配
                candidates = [(i, f) for i, f in enumerate(self.facts) if old_fact in f]
                if len(candidates) == 1:
                    idx, original = candidates[0]
                    self.facts[idx] = original.replace(old_fact, new_fact)
                    count += 1
                else:
                    self.logger.warning(f"无法找到要更新的记忆: {old_fact}")
        return count
