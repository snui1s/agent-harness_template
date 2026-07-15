# Agent Harness Template

A flexible and extensible Python-based AI agent harness designed to integrate memory, custom tools, and a database for long-term state management.

## Capabilities

This agent is designed as a pragmatic assistant with the following core capabilities:
- **Workspace Management**: Ability to read, write, edit, and organize files within the project directory.
- **Dynamic Skill Loading**: Ability to load specialized skills (e.g., security reviews, code navigation) dynamically to handle complex tasks.
- **Long-term Memory**: Persistence of user preferences and historical context via a database.
- **System Execution**: Execution of shell commands and management of Git operations (commit, push, status).
- **Web Integration**: Real-time web search capabilities and stock market data retrieval.
- **Code Analysis**: Multi-file search and targeted code modifications.

## Project Structure

```text
.
├── src/
│   └── agent/
│       ├── db.py             # SQLite persistence layer (sessions, messages, memory)
│       ├── memory.py         # Context compaction and long-term fact extraction
│       ├── skills_loader.py  # Dynamic loading system for specialized skills
│       └── tools.py          # Definition of available tools the agent can use
├── skills/                   # Directory containing specialized skill definitions
├── main.py                   # Entry point of the application
├── agent_data.db             # SQLite database for all persistence
├── pyproject.toml            # Project dependencies and configuration
└── README.md                 # Project documentation
```

## Tech Stack

- **Language**: Python
- **Dependency Management**: `uv` (or pip)
- **Database**: SQLite
- **Version Control**: Git

## Getting Started

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt # or use uv sync
   ```

2. **Environment Setup**:
   Create a `.env` file in the root directory and add the required API keys.

3. **Run the Agent**:
   ```bash
   python main.py
   ```

## Specialized Skills
The agent can expand its capabilities by loading scripts from the `/skills` folder. Currently supported skills include:
- `code-navigation`: For deep diving into existing codebases.
- `file-editing`: For precise content modifications.
- `git-operations`: For managing version control.
- `security-review`: For auditing code for vulnerabilities.
