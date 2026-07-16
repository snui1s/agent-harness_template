# Agent Harness

An open-source, Python-based AI agent harness with persistent long-term memory, multi-session chat management, dynamic skill loading, and a comprehensive tool system with security guardrails. Designed for extended, practical, real-world use beyond single-turn interactions.

## Capabilities

### Multi-Session Chat Management
- Create, list, and switch between independent chat sessions (browser-tab style) at any time, without losing context.
- Each session preserves its own conversation history and compaction state.
- Slash-command interface: `/new`, `/sessions`, `/switch`, `/help`, `/exit`.

### Long-Term Memory (Cross-Session)
- Automatic context compaction: when a session exceeds the active message threshold, older messages are archived and summarized by an LLM.
- Durable fact extraction: during compaction, reusable facts about the user (identity, preferences, ongoing projects, interests) are extracted and persisted in SQLite.
- Facts survive across sessions and are loaded into the system prompt on every new conversation, so the agent remembers you between chats.
- Duplicate detection prevents redundant facts from accumulating.

### Comprehensive Tool System (with Security)
- **File Operations**: Read, write (overwrite/append), edit (find-and-replace), delete, move/rename, view partial line ranges, get file metadata, multi-file search (grep-style).
  - All file operations are restricted to the project directory with real-path security checks to prevent traversal attacks.
- **Shell Execution**: Run arbitrary commands with a configurable timeout. Dangerous commands (rm, mv, mkdir, pip install, git push, etc.) require explicit user confirmation. Command chaining (`&&`, `||`) is blocked.
- **Git Integration**: Stage, commit, and push in a single call with confirmation.
- **Web Search**: Real-time web search via Tavily API.
- **Stock Price Lookup**: Current stock data via yfinance.
- **Current Time**: Local date/time retrieval.
- **Skill Loading**: On-demand loading of specialized skill instructions (`read_skill`), keeping the system prompt lean.
- **Large File Handling**: Files exceeding 10KB are automatically summarized by a sub-agent (via OpenRouter) to prevent token overflow.
- **Output Truncation**: Long tool outputs have head and tail preserved for readability.

### Dynamic Skill System
- Skills are loaded from the `skills/` directory, each as a standalone folder with a `SKILL.md` file.
- Only skill names and descriptions are included in the system prompt (cheap); full content is loaded on demand only when needed.
- Multiple skills can be loaded in a single call.
- Currently available skills:
  - `code-navigation`: Deep codebase analysis for security reviews, refactoring, debugging.
  - `file-editing`: Precise content modifications with safety checks.
  - `git-operations`: Version control management.
  - `security-review`: Evidence-based vulnerability auditing.
  - `unit-testing`: Writing, running, and fixing unit tests across any language.

### API Integration
- OpenRouter API for model access (configurable model selection, separate compaction model).
- Tavily API for web search.
- yfinance for stock market data.
- Retry logic with configurable delays and exponential backoff.
- Tool call limit safeguard to prevent infinite loops.

### Error Recovery
- Full conversation history rollback on API errors or exceptions.
- If compaction (LLM call) fails, the system falls back to a sliding-window approach instead of crashing.
- All messages are persisted to SQLite in real time before any LLM call, so no data is lost on failure.

### Persistence Layer (SQLite)
- Chat sessions table with title and timestamps.
- Messages table with optional tool call metadata.
- Long-term memory table with cross-session facts and near-duplicate detection.
- Archived messages table for compacted/offloaded content.
- Schema migration support for adding new columns as the system evolves.

### Testing
- 40 unit tests covering configuration loading, environment variable handling, .env file parsing, and memory compaction logic (response parsing, deduplication, fallback behavior).

## Project Structure

```text
.
├── src/
│   └── agent/
│       ├── config.py          # Configuration, env loading, constants
│       ├── db.py              # SQLite persistence layer (sessions, messages, memory, archives)
│       ├── memory.py          # Context compaction and long-term fact extraction
│       ├── prompts.py         # System prompt assembly (persona + README + skills + memory)
│       ├── session.py         # Session selection and resumption logic
│       ├── skills_loader.py   # Dynamic skill loading and description extraction
│       ├── tools.py           # Tool definitions and secure dispatcher
│       └── ui.py              # Spinner animation for thinking states
├── skills/                    # Directory containing specialized skill definitions
│   ├── code-navigation/
│   ├── file-editing/
│   ├── git-operations/
│   ├── security-review/
│   └── unit-testing/
├── tests/
│   ├── test_config.py         # 21 tests: paths, constants, models, API keys, .env parsing
│   └── test_memory.py         # 19 tests: compaction parsing, fact extraction, deduplication
├── main.py                    # Entry point: session loop, compaction, tool dispatch
├── agent_data.db              # SQLite database for all persistence
├── pyproject.toml             # Project dependencies and configuration
├── uv.lock                    # Locked dependency versions
└── README.md                  # Project documentation
```

## Tech Stack

- **Language**: Python 3.10+
- **Dependency Management**: uv (with lockfile) or pip
- **Database**: SQLite (single-file, zero-config)
- **LLM Access**: OpenRouter API
- **Version Control**: Git
- **Testing**: pytest 9.1+

## Getting Started

1. **Install Dependencies**:
   ```bash
   uv sync
   ```
   Or with pip:
   ```bash
   pip install -r requirements.txt
   ```

2. **Environment Setup**:
   Create a `.env` file in the project root and add your API keys:
   ```env
   OPENROUTER_API_KEY=your_key_here
   TAVILY_API_KEY=your_key_here
   ```

3. **Run the Agent**:
   ```bash
   uv run python main.py
   ```
   Or:
   ```bash
   python main.py
   ```

4. **Run Tests**:
   ```bash
   uv run pytest tests/ -v
   ```

## Configuration

Key configuration in `src/agent/config.py`:

| Parameter | Default | Description |
|---|---|---|
| `MODEL_NAME` | deepseek/deepseek-v4-flash | Primary model for conversation |
| `COMPACTION_MODEL` | google/gemini-2.5-flash-lite | Model used for memory compaction |
| `MAX_RETRIES` | 3 | Maximum API call retry attempts |
| `RETRY_DELAY` | 2 | Delay (seconds) between retries |
| `MAX_ACTIVE_MESSAGES` | 25 | Messages before compaction triggers |
| `KEEP_RECENT` | 4 | Recent messages preserved after compaction |
| `MAX_TOOL_CALLS` | 25 | Maximum tool calls per user turn |