# DiaryAssistant Copilot Instructions

## Project Overview
DiaryAssistant is a Python-based tool that analyzes personal markdown diaries using the DeepSeek API. It generates daily evaluations, weekly summaries, and deep insights.

## Architecture & Core Components
- **Entry Point**: `main.py` initializes `DiaryReader`, `DeepSeekAnalyzer`, and `WeeklySummaryManager`.
- **Data Ingestion**: `diary_reader.py` parses Markdown diary files (`YYYY-MM-DD.md`) from `Daily/`.
  - **Parsing Logic**: Identifies sections like "待办", "记录", "想法", "附件", "AI 说" using regex and keyword variants.
- **Analysis Engine**: `analyzer.py` interacts with the DeepSeek API (`deepseek-reasoner`).
  - **Retry Logic**: Implements a robust retry mechanism for API calls (`_send_request_with_retry`).
  - **Output**: Saves weekly analysis to `AI_Suggestion/` and weekly summaries to `Weekly_Summary/`.
- **Weekly Management**: `weekly_summary.py` groups diaries by ISO weeks (Mon-Sun) and manages summary file paths.
- **Configuration**: `config.py` manages paths and API settings.

## Key Workflows
- **Run Analysis**: Execute `python main.py` (or `run.bat` on Windows).
- **Daily Evaluation**: Generates advice for the current day's entry based on recent context.
- **Weekly Summary**: Automatically generates summaries for completed weeks if missing.

## Coding Conventions
- **Path Handling**: Always use `pathlib.Path` for file operations. Paths are relative to `Config.BASE_DIR`.
- **Logging**: Use `logger.Logger` for all output. Do not use `print` directly except for CLI interactions.
- **Type Hinting**: Use Python type hints (`List`, `Dict`, `Optional`, etc.) extensively.
- **Error Handling**: Wrap file I/O and API calls in `try-except` blocks. Log errors using `self.logger.error`.

## Project-Specific Patterns
- **Diary Format**:
  ```markdown
  # Title
  ## 待办
  - [ ] ...

  ## 记录
  - ...

  ## 想法
  - ...

  ## 附件
  > ...(Ignored by parser)

  ## AI 说
  (Generated content goes here)
  ```
- **API Interaction**:
  - Construct `messages` list with `system` and `user` roles.
  - Use `analyzer._send_request_with_retry` for all API calls.
  - Log prompt length and response time.

## Directory Structure
- `Daily/`: Source markdown diaries.
- `AI_Suggestion/`: Generated weekly analysis reports.
- `Weekly_Summary/`: Generated weekly summaries.
- `log/`: Application logs and request payloads.
