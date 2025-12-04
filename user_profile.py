import json
from pathlib import Path
from typing import List, Dict, Any
from logger import Logger

class UserProfile:
    def __init__(self, profile_path: Path):
        self.profile_path = profile_path
        self.logger = Logger.get_logger("UserProfile")
        self.facts: List[str] = self._load_profile()

    def _load_profile(self) -> List[str]:
        if not self.profile_path.exists():
            return []
        try:
            with open(self.profile_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return [str(item) for item in data]
                return []
        except Exception as e:
            self.logger.error(f"Failed to load user profile: {e}")
            return []

    def save_profile(self):
        try:
            with open(self.profile_path, 'w', encoding='utf-8') as f:
                json.dump(self.facts, f, ensure_ascii=False, indent=2)
            self.logger.info("User profile saved.")
        except Exception as e:
            self.logger.error(f"Failed to save user profile: {e}")

    def get_profile_text(self) -> str:
        if not self.facts:
            return "暂无个人信息记录。"
        return "\n".join([f"- {fact}" for fact in self.facts])

    def update(self, operations: Dict[str, Any]):
        """
        operations structure:
        {
            "add": ["fact1", "fact2"],
            "remove": ["fact to remove"],
            "update": [{"old": "old fact", "new": "new fact"}]
        }
        """
        added_count = 0
        removed_count = 0
        updated_count = 0

        # Handle Add
        for fact in operations.get("add", []):
            if fact not in self.facts:
                self.facts.append(fact)
                added_count += 1

        # Handle Remove
        for fact_to_remove in operations.get("remove", []):
            if not fact_to_remove:
                continue
                
            if fact_to_remove in self.facts:
                self.facts.remove(fact_to_remove)
                removed_count += 1
            else:
                # 尝试模糊匹配 (包含关系)
                candidates = [f for f in self.facts if fact_to_remove in f]
                if len(candidates) == 1:
                    target = candidates[0]
                    self.facts.remove(target)
                    removed_count += 1
                    self.logger.info(f"Fuzzy removed: '{target}' (matched '{fact_to_remove}')")
                else:
                    self.logger.warning(f"Could not find fact to remove: {fact_to_remove}")

        # Handle Update
        for update_item in operations.get("update", []):
            old_fact = update_item.get("old")
            new_fact = update_item.get("new")
            
            if not old_fact or new_fact is None:
                continue

            if old_fact in self.facts:
                index = self.facts.index(old_fact)
                self.facts[index] = new_fact
                updated_count += 1
            else:
                # 尝试模糊匹配 (包含关系)
                candidates = [i for i, f in enumerate(self.facts) if old_fact in f]
                if len(candidates) == 1:
                    index = candidates[0]
                    original_fact = self.facts[index]
                    # 替换匹配到的部分
                    self.facts[index] = original_fact.replace(old_fact, new_fact)
                    updated_count += 1
                    self.logger.info(f"Fuzzy updated: '{original_fact}' -> '{self.facts[index]}'")
                else:
                    self.logger.warning(f"Could not find fact to update: {old_fact}")

        if added_count or removed_count or updated_count:
            self.save_profile()
            self.logger.info(f"Profile updated: +{added_count}, -{removed_count}, ~{updated_count}")

    def get_profile_length(self) -> int:
        """Get total character count of all facts."""
        return sum(len(fact) for fact in self.facts)

    def update_facts(self, new_facts: List[str]):
        """Replace all facts with a new list."""
        self.facts = new_facts
        self.save_profile()
        self.logger.info(f"Profile facts replaced. New count: {len(self.facts)}")
