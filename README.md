# Agent Harness Template

A flexible and extensible Python-based AI agent harness designed to integrate memory, custom tools, and a database for long-term state management.

## 🚀 Capabilities

This agent is designed to be a pragmatic assistant with the following core capabilities:
- **Workspace Management**: Read, write, edit, and organize files within the project directory.
- **Dynamic Skill Loading**: Load specialized skills (e.g., security reviews, code navigation) on-the-fly to handle complex tasks.
- **Long-term Memory**: Store and retrieve user preferences and historical context via a database.
- **System Execution**: Execute shell commands and manage Git operations (commit, push, status).
- **Web Integration**: Perform real-time web searches and fetch stock market data.
- **Code Analysis**: Search across multiple files and perform targeted code modifications.

## 📁 Project Structure

```text
.
├── src/
│   └── agent/
│       ├── db.py             # Database management for long-term memory
│       ├── memory.py         # Logic for handling agent memory and context
│       ├── skills_loader.py  # Dynamic loading system for specialized skills
│       └── tools.py          # Definition of available tools the agent can use
├── skills/                   # Directory containing specialized skill definitions
├── main.py                   # Entry point of the application
├── agent_data.db             # SQLite database for persistence
├── chat_archive.jsonl        # Log of agent conversations
├── pyproject.toml            # Project dependencies and configuration
└── README.md                 # Project documentation
```

## 🛠️ Tech Stack

- **Language**: Python
- **Dependency Management**: `uv` (or pip)
- **Database**: SQLite
- **Version Control**: Git

## ⚙️ Getting Started

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt # or use uv sync
   ```

2. **Environment Setup**:
   Create a `.env` file in the root directory and add your required API keys.

3. **Run the Agent**:
   ```bash
   python main.py
   ```

## 🛡️ Specialized Skills
The agent can expand its capabilities by loading scripts from the `/skills` folder. Currently supported skills include:
- `code-navigation`: For deep diving into existing codebases.
- `file-editing`: For precise content modifications.
- `git-operations`: For managing version control.
- `security-review`: For auditing code for vulnerabilities.
