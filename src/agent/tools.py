import os
import subprocess
import shlex
from datetime import datetime
from openrouter import OpenRouter
import yfinance as yf
import requests

# Load environment variables from local .env file (checking CWD first, then climbing up from script location)
env_path = ".env"
if not os.path.exists(env_path):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.abspath(os.path.join(script_dir, "..", "..", ".env"))

if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()

# --- Helper Functions (Tools) ---
MODEL_NAME = "openrouter/free"
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
def get_current_time():
    """
    Function: Retrieves the current system date and time formatted as a string.
    Returns: String representation of current time (e.g., 'YYYY-MM-DD HH:MM:SS').
    """
    now = datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")

# Refactored the original read_local_file function to use a Sub-agent
def read_local_file(filepath):
    """
    Function: Reads a file's content directly for small files. For larger files,
    delegates to a Sub-agent to summarize the content instead of returning it raw,
    to avoid overwhelming the main agent's context with token overflow.
    """
    # Files at or below this size are returned as-is - no need to burn an extra
    # API call and ~15-20s of latency summarizing something already small.
    RAW_READ_THRESHOLD = 2000
 
    try:
        base_dir = os.path.abspath(os.getcwd())
        target_path = os.path.abspath(filepath)
 
        if os.path.commonpath([base_dir, target_path]) != base_dir:
            return "Error: Security block!"
        
        if not target_path.startswith(base_dir):
            return "Error: Security block! Access to files outside the project directory is denied."
            
        if not os.path.exists(target_path):
            return f"Error: File '{filepath}' not found."
 
        file_size = os.path.getsize(target_path)
 
        # Small file: return raw content directly, skip the sub-agent entirely
        if file_size <= RAW_READ_THRESHOLD:
            with open(target_path, "r", encoding="utf-8") as f:
                content = f.read()
            return f"Content of '{filepath}':\n{content}"
 
        # Large file: read a chunk and delegate to a Sub-agent to summarize
        with open(target_path, "r", encoding="utf-8") as f:
            content = f.read(3000) # Read slightly larger size since the Sub-agent will summarize it
            
        print(f"    [Sub-Agent]: Analyzing file {filepath}...")
        sub_agent_prompt = f"You are a file analysis AI assistant. Please summarize the key content of the following code or document as concisely as possible:\n\n{content}"
        
        with OpenRouter(api_key=os.getenv("OPENROUTER_API_KEY")) as client:
            sub_response = client.chat.send(
                model=MODEL_NAME, # Use a free/cheap model for helper tasks
                messages=[{"role": "user", "content": sub_agent_prompt}]
            )
            summary = sub_response.choices[0].message.content
            
        return f"File Summary of {filepath} (file is {file_size} bytes, too large to read in full): {summary}"
            
    except Exception as e:
        return f"Error reading file: {str(e)}"

def get_stock_price(ticker):
    """Fetch current stock price using yfinance."""
    try:
        # Fetch stock data
        stock = yf.Ticker(ticker)
        # Fetch 1-day historical data (fastest way to get current price)
        hist = stock.history(period="1d")
        
        if hist.empty:
            return f"Error: Could not find data for ticker '{ticker}'. Please check if the ticker symbol is correct."
        
        # Retrieve the latest close price
        latest_price = hist['Close'].iloc[-1]
        currency = stock.info.get('currency', 'USD')
        name = stock.info.get('shortName', ticker)
        
        return f"The current price of {name} ({ticker}) is {latest_price:.2f} {currency}."
        
    except Exception as e:
        return f"Error fetching stock data: {str(e)}"

def list_directory(folder_path="."):
    """Simulate 'ls' command: List files and folders in the specified folder path."""
    try:
        base_dir = os.path.abspath(os.getcwd())
        target_path = os.path.abspath(folder_path)

        if os.path.commonpath([base_dir, target_path]) != base_dir:
            return "Error: Security block!"
        
        # Guardrail: Prevent directory listing outside the project directory
        if not target_path.startswith(base_dir):
            return "Error: Security block! Cannot list directories outside the project."
            
        if not os.path.exists(target_path):
            return f"Error: Directory '{folder_path}' not found."
            
        items = os.listdir(target_path)
        if not items:
            return "Directory is empty."
            
        return f"Contents of {folder_path}:\n" + "\n".join(f"- {item}" for item in items)
    except Exception as e:
        return f"Error listing directory: {str(e)}"

def search_in_files(keyword, folder_path="."):
    """Simulate 'grep' command: Search for keyword within .py, .txt, .json, .md, .env files."""
    try:
        base_dir = os.path.abspath(os.getcwd())
        target_path = os.path.abspath(folder_path)

        if os.path.commonpath([base_dir, target_path]) != base_dir:
            return "Error: Security block!"
        
        if not target_path.startswith(base_dir):
            return "Error: Security block! Cannot search outside the project."
            
        allowed_extensions = ('.py', '.txt', '.json', '.md', '.env')
        results = []
        
        for root, dirs, files in os.walk(target_path):
            for file in files:
                if file.endswith(allowed_extensions):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            lines = f.readlines()
                            for i, line in enumerate(lines):
                                if keyword in line:
                                    # Store file path, matching line number, and matching line content
                                    rel_path = os.path.relpath(file_path, base_dir)
                                    results.append(f"{rel_path} (Line {i+1}): {line.strip()}")
                    except:
                        pass # Skip unreadable or system files
                        
        if not results:
            return f"No matches found for '{keyword}'."
            
        return f"Found '{keyword}' in:\n" + "\n".join(results[:50]) # Limit results to 50 items to prevent token overflow
    except Exception as e:
        return f"Error searching files: {str(e)}"

def edit_local_file(filepath, content, mode="w"):
    """
    Create or edit a local file.
    mode='w' is to overwrite the entire file.
    mode='a' is to append content to the end of the file.
    """
    try:
        base_dir = os.path.abspath(os.getcwd())
        target_path = os.path.abspath(filepath)

        if os.path.commonpath([base_dir, target_path]) != base_dir:
            return "Error: Security block!"
        
        if not target_path.startswith(base_dir):
            return "Error: Security block! Cannot edit files outside the project."
            
        if mode not in ["w", "a"]:
            return "Error: Mode must be 'w' (overwrite) or 'a' (append)."
            
        with open(target_path, mode, encoding="utf-8") as f:
            f.write(content)
            
        action = "Overwritten" if mode == "w" else "Appended to"
        return f"Success: {action} file '{filepath}'."
    except Exception as e:
        return f"Error editing file: {str(e)}"

def get_file_info(filepath):
    """
    Retrieve metadata of a file (file size, last modified timestamp).
    Helps the agent evaluate file size before reading to avoid token overflow.
    """
    try:
        base_dir = os.path.abspath(os.getcwd())
        target_path = os.path.abspath(filepath)

        if os.path.commonpath([base_dir, target_path]) != base_dir:
            return "Error: Security block!"
        
        # Hard Guardrail: Prevent inspecting files outside the project directory
        if not target_path.startswith(base_dir):
            return "Error: Security block! Access to files outside the project directory is denied."
            
        if not os.path.exists(target_path):
            return f"Error: File '{filepath}' not found."
            
        # Retrieve file stats
        file_stats = os.stat(target_path)
        file_size_bytes = file_stats.st_size
        modified_time = datetime.fromtimestamp(file_stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
        
        # Format file size unit for readability
        if file_size_bytes < 1024:
            size_str = f"{file_size_bytes} Bytes"
        elif file_size_bytes < 1024 * 1024:
            size_str = f"{file_size_bytes / 1024:.2f} KB"
        else:
            size_str = f"{file_size_bytes / (1024 * 1024):.2f} MB"
            
        return f"File Info for '{filepath}':\n- Size: {size_str}\n- Last Modified: {modified_time}"
        
    except Exception as e:
        return f"Error fetching file info: {str(e)}"

def view_file_lines(filepath, start_line=1, end_line=50):
    """
    Read specific lines of a file (similar to head/tail commands).
    Helps save tokens and reduce latency when reading large files.
    """
    try:
        base_dir = os.path.abspath(os.getcwd())
        target_path = os.path.abspath(filepath)

        if os.path.commonpath([base_dir, target_path]) != base_dir:
            return "Error: Security block!"
        
        # Hard Guardrail: Restrict file reading to the project directory
        if not target_path.startswith(base_dir):
            return "Error: Security block! Access to files outside the project directory is denied."
            
        if not os.path.exists(target_path):
            return f"Error: File '{filepath}' not found."
            
        if start_line < 1 or end_line < start_line:
            return "Error: Invalid line range. 'start_line' must be >= 1 and 'end_line' must be >= 'start_line'."
            
        output_lines = []
        with open(target_path, "r", encoding="utf-8") as f:
            for current_line_num, line in enumerate(f, start=1):
                if current_line_num >= start_line and current_line_num <= end_line:
                    output_lines.append(f"{current_line_num}: {line}")
                if current_line_num > end_line:
                    break
                    
        if not output_lines:
            return f"No content found in the specified line range ({start_line}-{end_line}) for '{filepath}'."
            
        return f"Content of '{filepath}' (Lines {start_line}-{end_line}):\n" + "".join(output_lines)
        
    except Exception as e:
        return f"Error viewing file lines: {str(e)}"

def replace_in_file(filepath, old_text, new_text):
    """
    Find and replace specific text within a file (similar to the 'sed' command).
    Allows the agent to modify specific parts of code or text accurately without overwriting the entire file.
    """
    try:
        base_dir = os.path.abspath(os.getcwd())
        target_path = os.path.abspath(filepath)

        if os.path.commonpath([base_dir, target_path]) != base_dir:
            return "Error: Security block!"
        
        # Hard Guardrail: Restrict file editing to the project directory
        if not target_path.startswith(base_dir):
            return "Error: Security block! Access to files outside the project directory is denied."
            
        if not os.path.exists(target_path):
            return f"Error: File '{filepath}' not found."
            
        # 1. Read the entire file content
        with open(target_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        # 2. Verify if the target old text exists in the file
        if old_text not in content:
            return f"Error: The target text to replace was not found in '{filepath}'. Please double-check the exact string."
            
        # 3. Perform string replacement
        updated_content = content.replace(old_text, new_text)
        
        # 4. Write the updated content back to the file
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(updated_content)
            
        return f"Success: Successfully replaced the specified text in '{filepath}'."
        
    except Exception as e:
        return f"Error replacing text in file: {str(e)}"

def delete_local_file(filepath):
    """Simulate 'rm' command: Delete unnecessary or temporary files to keep the workspace organized."""
    try:
        base_dir = os.path.abspath(os.getcwd())
        target_path = os.path.abspath(filepath)

        if os.path.commonpath([base_dir, target_path]) != base_dir:
            return "Error: Security block!"
        
        # Hard Guardrail: Strictly prohibit deleting files outside the project directory
        if not target_path.startswith(base_dir):
            return "Error: Security block! Cannot delete files outside the project."
            
        if not os.path.exists(target_path):
            return f"Error: File '{filepath}' not found."
            
        if os.path.isdir(target_path):
            return f"Error: '{filepath}' is a directory. This tool only deletes files."
        
        confirm = input(f"\n[!!!] Agent requests to DELETE file: '{filepath}'. Allow? (y/n): ")
        if confirm.lower() != 'y':
            return "Error: File deletion aborted by user."

        os.remove(target_path)
        return f"Success: Deleted file '{filepath}'."
    except Exception as e:
        return f"Error deleting file: {str(e)}"

def move_or_rename_file(source_path, dest_path):
    """Simulate 'mv' command: Move a file to a new path or rename it within the project."""
    try:
        base_dir = os.path.abspath(os.getcwd())
        src_abs = os.path.abspath(source_path)
        dst_abs = os.path.abspath(dest_path)

        if os.path.commonpath([base_dir, dst_abs]) != base_dir or os.path.commonpath([base_dir, src_abs]) != base_dir:
            return "Error: Security block!"
        
        # Hard Guardrail: Prohibit actions outside the project directory
        if not src_abs.startswith(base_dir) or not dst_abs.startswith(base_dir):
            return "Error: Security block! Actions outside the project directory are denied."
            
        if not os.path.exists(src_abs):
            return f"Error: Source file '{source_path}' not found."
            
        # Automatically create destination directories if they don't exist
        dest_dir = os.path.dirname(dst_abs)
        if dest_dir and not os.path.exists(dest_dir):
            os.makedirs(dest_dir, exist_ok=True)
            
        os.rename(src_abs, dst_abs)
        return f"Success: Moved/Renamed '{source_path}' to '{dest_path}'."
    except Exception as e:
        return f"Error moving/renaming file: {str(e)}"

# Commands blocked outright, regardless of confirmation
SHELL_BLOCKED_PATTERNS = [
    'rm -rf /', 'rm -rf ~', 'sudo', ':(){', 'dd if=', 'mkfs',
    '> /dev/', 'chmod 777', '| sh', '| bash', 'curl | ', 'wget | ',
    'shutdown', 'reboot', 'halt', '/etc/passwd', '/etc/shadow',
    'eval ', 'exec(', '.ssh/', 'ssh-keygen'
]

# Commands allowed to run, but require explicit user confirmation first
SHELL_DANGEROUS_PREFIXES = [
    'rm', 'mv', 'git push', 'git reset', 'git checkout --',
    'kill', 'pkill', 'npm publish', 'pip install', 'pip uninstall'
]

SHELL_TIMEOUT_SECONDS = 10
SHELL_OUTPUT_LIMIT = 5000

def execute_shell_command(command, confirmed=False):
    """
    Execute a shell command inside the project working directory with safety guardrails.
    Blocks destructive patterns outright, and requires explicit confirmation for
    dangerous-but-legitimate commands (rm, mv, git push, etc.) before actually running them.
    """
    try:
        if not command or not command.strip():
            return "Error: No command provided."

        # Reject chained commands - shlex.split() cannot separate them into
        # distinct subprocess calls, which silently mangles things like
        # 'git add -A && git commit -m "..."' into a single broken command.
        for chain_op in ['&&', '||', ';', '|']:
            if chain_op in command:
                return (f"Error: Chained commands ('{chain_op}') are not supported. "
                        f"Call this tool once per command instead (e.g. run 'git add -A' "
                        f"first, then call again for 'git commit -m ...').")

        lowered = command.lower()

        # 1. Hard block: never allowed, no matter what
        for pattern in SHELL_BLOCKED_PATTERNS:
            if pattern in lowered:
                return f"Error: Blocked - command matches a forbidden pattern ('{pattern}')."

        # 2. Soft block: dangerous commands need confirmed=True to proceed
        stripped = command.strip()
        for prefix in SHELL_DANGEROUS_PREFIXES:
            if stripped.startswith(prefix) or f" {prefix} " in f" {stripped} ":
                if not confirmed:
                    return (f"CONFIRMATION_REQUIRED: The command '{command}' is potentially "
                            f"destructive or impactful. Ask the user to confirm before "
                            f"re-calling this tool with confirmed=true.")
                break

        # 3. Parse safely without shell=True (no pipe/redirect injection)
        try:
            cmd_parts = shlex.split(command)
        except ValueError as e:
            return f"Error: Could not parse command ({str(e)})."

        if not cmd_parts:
            return "Error: Empty command after parsing."

        # 4. Restrict working directory to the project folder
        base_dir = os.path.abspath(os.getcwd())

        # 5. Run with a strict timeout and capped output
        result = subprocess.run(
            cmd_parts,
            shell=False,
            cwd=base_dir,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=SHELL_TIMEOUT_SECONDS
        )

        stdout = result.stdout[:SHELL_OUTPUT_LIMIT]
        stderr = result.stderr[:SHELL_OUTPUT_LIMIT]

        if len(result.stdout) > SHELL_OUTPUT_LIMIT:
            stdout += "\n[...output truncated...]"

        return (f"Exit Code: {result.returncode}\n"
                f"STDOUT:\n{stdout}\n"
                f"STDERR:\n{stderr}")

    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {SHELL_TIMEOUT_SECONDS} seconds."
    except FileNotFoundError:
        return f"Error: Command not found ('{command.split()[0]}')."
    except Exception as e:
        return f"Error executing command: {str(e)}"

def git_commit_and_push(commit_message, confirmed=False):
    """
    Stages all changes, commits with the given message, and pushes to the remote -
    all in a single tool call. Avoids the need to chain 'git add && git commit && git push',
    which execute_shell_command cannot run as one command.
    Requires explicit user confirmation before actually running, since it modifies
    the remote repository.
    """
    if not commit_message or not commit_message.strip():
        return "Error: A commit message is required."

    if not confirmed:
        return (f"CONFIRMATION_REQUIRED: This will run 'git add -A', commit with message "
                f"'{commit_message}', and push to the remote. Ask the user to confirm "
                f"before re-calling this tool with confirmed=true.")

    base_dir = os.path.abspath(os.getcwd())

    try:
        # 1. Stage all changes
        r1 = subprocess.run(
            ['git', 'add', '-A'],
            cwd=base_dir, capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=SHELL_TIMEOUT_SECONDS
        )
        if r1.returncode != 0:
            return f"Failed at 'git add -A':\n{r1.stderr[:SHELL_OUTPUT_LIMIT]}"

        # 2. Commit
        r2 = subprocess.run(
            ['git', 'commit', '-m', commit_message],
            cwd=base_dir, capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=SHELL_TIMEOUT_SECONDS
        )
        if r2.returncode != 0:
            if "nothing to commit" in r2.stdout.lower():
                return "Nothing to commit - working tree is already clean."
            return f"Failed at 'git commit':\n{r2.stdout[:SHELL_OUTPUT_LIMIT]}\n{r2.stderr[:SHELL_OUTPUT_LIMIT]}"

        # 3. Push
        r3 = subprocess.run(
            ['git', 'push'],
            cwd=base_dir, capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=30
        )
        if r3.returncode != 0:
            return (f"Committed locally but push failed:\n{r3.stderr[:SHELL_OUTPUT_LIMIT]}\n"
                    f"(Commit is saved locally - you can retry the push once the issue is fixed.)")

        return (f"Success: Changes committed and pushed.\n"
                f"Commit: {r2.stdout.strip()}\n"
                f"Push: {r3.stderr.strip()}")

    except subprocess.TimeoutExpired:
        return "Error: Git operation timed out."
    except FileNotFoundError:
        return "Error: 'git' command not found. Is Git installed and on PATH?"
    except Exception as e:
        return f"Error during git commit/push: {str(e)}"

def web_search(query, max_results=5):
    """Search the web for current information."""
    if not TAVILY_API_KEY:
        return "Error: TAVILY_API_KEY not set in .env"
    
    try:
        response = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "max_results": max_results
            },
            timeout=10
        )
        data = response.json()
        
        results = []
        for r in data.get("results", []):
            results.append(f"- {r['title']}: {r['content'][:200]}... (Source: {r['url']})")
        
        if not results:
            return f"No results found for '{query}'."
        
        return f"Search results for '{query}':\n" + "\n".join(results)
        
    except requests.exceptions.Timeout:
        return "Error: Search request timed out."
    except Exception as e:
        return f"Error searching web: {str(e)}"


# --- Tool Definitions ---

my_tools = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Use this to get the current date and time. Useful when the user asks what time it is or what day it is.",
            "parameters": {
                "type": "object",
                "properties": {}, 
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_local_file",
            "description": "Read the contents of a local file. Use this when the user asks you to inspect a file, check code, or read logs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "The exact path to the file (e.g., 'main.py', 'chat_archive.jsonl')"
                    }
                },
                "required": ["filepath"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_price",
            "description": "Get the current stock price for a given company. You MUST provide the exact stock ticker symbol (e.g., 'AAPL' for Apple, 'TSLA' for Tesla, 'PTT.BK' for PTT Thailand). If the user provides a company name instead of a ticker, you must infer and use the correct official ticker symbol.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "The official stock ticker symbol (e.g., AAPL, MSFT, OR.BK)."
                    }
                },
                "required": ["ticker"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List files and directories in a specified folder. Acts like the 'ls' command. Use this to explore the project structure.",
            "parameters": {
                "type": "object",
                "properties": {
                    "folder_path": {
                        "type": "string",
                        "description": "The path to the folder to list (e.g., '.', './src', 'data'). Default is '.'."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_in_files",
            "description": "Search for a specific keyword across text-based files in a directory. Acts like the 'grep' command. Useful for finding variables, functions, or bugs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "The exact text, variable, or function name to search for."
                    },
                    "folder_path": {
                        "type": "string",
                        "description": "The directory path to search within. Default is '.'."
                    }
                },
                "required": ["keyword"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_local_file",
            "description": "Edit or create a local file. You can either overwrite the entire file or append content to it. Acts like a text editor.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "The exact path to the file to edit (e.g., 'main.py')."
                    },
                    "content": {
                        "type": "string",
                        "description": "The complete string of content to write or append to the file."
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["w", "a"],
                        "description": "Use 'w' to overwrite the file completely, or 'a' to append content to the end. Default is 'w'."
                    }
                },
                "required": ["filepath", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_file_info",
            "description": "Get file metadata such as size and last modified timestamp. Use this to check file size before reading it to avoid token overflow.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "The exact path to the file (e.g., 'main.py', 'chat_archive.jsonl')."
                    }
                },
                "required": ["filepath"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "view_file_lines",
            "description": "Read specific lines of a file rather than the whole document. Acts like head/tail commands. Highly recommended for inspecting portions of large files or logs to save token usage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "The exact path to the file."
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "The line number to start reading from (inclusive). Default is 1."
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "The line number to stop reading at (inclusive). Default is 50."
                    }
                },
                "required": ["filepath"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "replace_in_file",
            "description": "Find and replace a specific block of text or code within a file. Acts like the 'sed' command or string replacement. Use this to modify specific functions or variables without overwriting the entire file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "The exact path to the file to modify."
                    },
                    "old_text": {
                        "type": "string",
                        "description": "The exact current text or code block inside the file that needs to be replaced."
                    },
                    "new_text": {
                        "type": "string",
                        "description": "The new text or code block to insert in place of the old text."
                    }
                },
                "required": ["filepath", "old_text", "new_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_local_file",
            "description": "Delete a temporary or unwanted file from the project. Acts like the 'rm' command. Use this for cleanup.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "The exact path of the file to delete."
                    }
                },
                "required": ["filepath"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "move_or_rename_file",
            "description": "Move a file to a new location or rename it. Acts like the 'mv' command. Useful for restructuring workspace layout.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source_path": {
                        "type": "string",
                        "description": "The current path of the file."
                    },
                    "dest_path": {
                        "type": "string",
                        "description": "The target new path or new name for the file."
                    }
                },
                "required": ["source_path", "dest_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_shell_command",
            "description": "Execute a shell command in the project working directory (e.g. running tests, checking git status, listing processes). Destructive or impactful commands (rm, mv, git push, pip install, kill, etc.) will be blocked unless 'confirmed' is set to true - if the tool returns CONFIRMATION_REQUIRED, ask the user to confirm before retrying with confirmed=true. Never attempt to bypass this by chaining commands or using sudo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The exact shell command to run (e.g. 'ls -la', 'python -m pytest', 'git status')."
                    },
                    "confirmed": {
                        "type": "boolean",
                        "description": "Set to true only after the user has explicitly confirmed a dangerous command should proceed. Default is false."
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_commit_and_push",
            "description": "Stage all changes, commit with the given message, and push to the remote repository - in one call. Use this instead of execute_shell_command when the user wants to commit and push, since chained commands (&&) are not supported by execute_shell_command. Requires user confirmation before actually running (call once to get CONFIRMATION_REQUIRED, then again with confirmed=true after the user agrees). Recommended to run 'git status' and 'git diff' via execute_shell_command first if you need to inspect changes before writing the commit message.",
            "parameters": {
                "type": "object",
                "properties": {
                    "commit_message": {
                        "type": "string",
                        "description": "The commit message to use. Should be clear and descriptive of the changes."
                    },
                    "confirmed": {
                        "type": "boolean",
                        "description": "Set to true only after the user has explicitly confirmed the commit and push should proceed. Default is false."
                    }
                },
                "required": ["commit_message"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current, up-to-date, or real-time information (news, recent events, prices, documentation, facts you're unsure about, or anything that may have changed after your training data). Use this whenever the user asks about something time-sensitive or when you're not confident your internal knowledge is current.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query. Be specific and concise (e.g. 'Python 3.13 release date' rather than a full sentence question)."
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of search results to return. Default is 5."
                    }
                },
                "required": ["query"]
            }
        }
    }

]