#!/usr/bin/env python3
"""
清除日记中的 AI 评价脚本
功能：
1. 备份所有日记到 log 目录下的带时间戳文件夹
2. 遍历所有日记文件，移除 "AI 说" 及其之后的内容
"""

import shutil
import re
import sys
from pathlib import Path
from datetime import datetime

# 添加当前目录到Python路径，以便导入模块
sys.path.insert(0, str(Path(__file__).parent))

from config import Config
from logger import Logger

def clear_ai_comments():
    # 初始化日志
    logger = Logger.get_logger("ClearAI")
    Logger.log_separator(logger)
    logger.info("🧹 开始执行清除 AI 评价任务")
    
    # 1. 创建备份
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = Config.LOG_DIR / f"backup_{timestamp}"
    
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"📦 创建备份目录: {backup_dir}")
    except Exception as e:
        logger.error(f"创建备份目录失败: {e}")
        return

    # 获取所有日记文件
    diary_dirs = [Config.DIARY_DIR, Config.DIARY_OLD_DIR]
    files_to_process = []

    for d_dir in diary_dirs:
        if d_dir.exists():
            for f in d_dir.glob("*.md"):
                files_to_process.append(f)
        else:
            logger.warning(f"目录不存在: {d_dir}")

    if not files_to_process:
        logger.warning("没有找到任何日记文件")
        return

    logger.info(f"🔍 找到 {len(files_to_process)} 个日记文件，准备备份...")

    # 2. 备份文件
    backup_count = 0
    for file_path in files_to_process:
        try:
            shutil.copy2(file_path, backup_dir / file_path.name)
            backup_count += 1
        except Exception as e:
            logger.error(f"备份文件失败 {file_path.name}: {e}")
            # 如果备份失败，是否继续？为了安全起见，最好停止或跳过该文件
            # 这里选择跳过该文件的处理
            files_to_process.remove(file_path)

    logger.info(f"✅ 成功备份 {backup_count} 个文件")
    Logger.log_separator(logger)

    # 3. 清除 AI 评价
    ai_variants = ["AI 说", "AI说", "AI评价", "AI建议"]
    # 匹配行首的标题，如 "## AI 说", "# AI评价" 等
    pattern_str = r'^#+\s*(' + '|'.join(map(re.escape, ai_variants)) + r')\s*$'
    header_pattern = re.compile(pattern_str, re.IGNORECASE)

    processed_count = 0
    skipped_count = 0

    for file_path in files_to_process:
        try:
            # 读取内容
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            new_lines = []
            found_ai = False
            
            for line in lines:
                # 检查是否是 AI 评价的标题行
                if header_pattern.match(line.strip()):
                    found_ai = True
                    break # 找到后直接停止，丢弃之后的所有内容
                new_lines.append(line)
            
            if found_ai:
                # 移除末尾的空行，保持整洁
                while new_lines and new_lines[-1].strip() == "":
                    new_lines.pop()
                
                # 写回文件
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.writelines(new_lines)
                    # 确保文件末尾有一个换行符（如果文件不为空）
                    if new_lines:
                        f.write('\n')
                
                processed_count += 1
                logger.info(f"✂️  已清除: {file_path.name}")
            else:
                skipped_count += 1
                # logger.debug(f"未发现 AI 评价: {file_path.name}")

        except Exception as e:
            logger.error(f"处理文件出错 {file_path.name}: {e}")

    Logger.log_separator(logger)
    logger.info(f"🎉 处理完成")
    logger.info(f"   - 已清除: {processed_count} 个文件")
    logger.info(f"   - 未发现/跳过: {skipped_count} 个文件")
    logger.info(f"   - 备份位置: {backup_dir}")
    Logger.log_separator(logger)

if __name__ == "__main__":
    clear_ai_comments()
