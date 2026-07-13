# hello from the other side
from openrouter import OpenRouter
import os
import time
import json
from datetime import datetime
import yfinance as yf
from src.agent.tools import *
from src.agent.memory import compact_memory
import platform

# Resolve script directory for absolute path references
script_dir = os.path.dirname(os.path.abspath(__file__))

# Load environment variables from local .env file relative to script location
env_path = os.path.join(script_dir, ".env")
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()

# --- Configurations ---
MAX_RETRIES = 3
RETRY_DELAY = 2
# MODEL_NAME = "qwen/qwen3-next-80b-a3b-thinking"
MODEL_NAME = "tencent/hy3:free"
# MODEL_NAME = "openrouter/free"

# Memory management parameters
MAX_ACTIVE_MESSAGES = 6 # Recommended range: 30-40
KEEP_RECENT = 2 # Recommended range: 3-6
OFFLOAD_FILE = os.path.join(script_dir, "chat_archive.jsonl")

conversation_history = []

# --- Persona Setup ---

SYSTEM_PROMPT = f"""You are an intelligent, highly pragmatic AI assistant with broad general knowledge and advanced workspace file management capabilities.

CRITICAL OPERATIONAL GUIDELINES:
1. TOOL USAGE: Call tools ONLY when strictly necessary. Answer general knowledge, philosophy, or history questions directly using your own internal knowledge without relying on tools.
2. FILE EDITING & TRUST: When you use the 'edit_local_file' or 'replace_in_file' tools to modify content, trust the success message returned by the tool. DO NOT call 'read_local_file', 'view_file_lines', or 'list_directory' immediately afterward to verify your action. Once the tool returns a success status, consider the task complete and reply to the user immediately.
3. SMART FILE INSPECTION: When dealing with large files, prefer using 'get_file_info' first to check the size, or 'view_file_lines' to read specific portions instead of reading the entire file, to keep latency low and save token usage.
4. TARGETED MODIFICATIONS: When asked to modify a specific function, variable, or block of code within an existing file, prefer using 'replace_in_file' over 'edit_local_file' to avoid accidentally destroying other parts of the file.
5. CONCISE COMPLETION: Avoid multi-step verification loops. Execute the requested action, review the output from the tool, and provide your final response directly to the user.
6. GIT COMMIT & PUSH: When the user asks to commit and/or push changes, use the 'git_commit_and_push' tool directly - do NOT run 'git add', 'git commit', 'git push' one by one via 'execute_shell_command'. Only use 'execute_shell_command' with 'git status' or 'git diff' first if you genuinely need to inspect changes before deciding on a commit message.
NOTE: This system runs on {platform.system()} ({os.name}). Use {platform.system()}-appropriate shell syntax."""
# Initialize the conversation state with the system persona
conversation_history = [{"role": "system", "content": SYSTEM_PROMPT}]

print("=== Agent Harness Started (Compaction, Offloading & Tools) ===")
print(f"Offloaded data will be saved to: {OFFLOAD_FILE}")
print("Type 'exit' or 'quit' to terminate the session.\n")

# --- Main Conversation Loop ---

while True:
    user_input = input("You: ")
    
    # Check for loop termination command
    if user_input.lower() in ['exit', 'quit']:
        print("Shutting down agent...")
        break
        
    # Ignore empty inputs and prompt again
    if not user_input.strip():
        continue

    # State Update: Append the new user message to the active conversation history
    conversation_history.append({"role": "user", "content": user_input})

    # --- State: Memory Compaction & Offloading Logic ---
    conversation_history = compact_memory(
        conversation_history,
        MAX_ACTIVE_MESSAGES,
        KEEP_RECENT,
        OFFLOAD_FILE,
        MODEL_NAME,
        SYSTEM_PROMPT
    )

    # --- State: Main Agent Call Loop (with Retries, Tools, and Safeguards) ---
    attempt = 0
    tool_call_count = 0       
    MAX_TOOL_CALLS = 5
    
    # Take a backup snapshot of conversation history before starting thinking to allow clean recovery on errors
    safe_history_backup = list(conversation_history) 
    
    while attempt < MAX_RETRIES:
        try:
            if attempt > 0:
                print(f"  [Retrying... {attempt}/{MAX_RETRIES}]")
            
            # --- Start timing AI processing ---
            print("  [Thinking...]") 
            agent_start_time = time.time() 
            
            with OpenRouter(api_key=os.getenv("OPENROUTER_API_KEY")) as client:
                response = client.chat.send(
                    model=MODEL_NAME,
                    messages=conversation_history,
                    tools=my_tools
                )
                
                message = response.choices[0].message
                
                # --- Stop timing AI ---
                agent_end_time = time.time()
                agent_duration = agent_end_time - agent_start_time

                if hasattr(message, 'tool_calls') and message.tool_calls:
                    if tool_call_count >= MAX_TOOL_CALLS:
                        print("  [System]: Too many tool calls. Forcing stop to prevent infinite loop.")
                        conversation_history = safe_history_backup[:-1] 
                        break
                        
                    print(f"  [System]: Agent decided to use a tool (took {agent_duration:.2f}s)")
                    tool_call_count += len(message.tool_calls)
                    
                    conversation_history.append(message.model_dump(exclude_none=True))
                    
                    for tool_call in message.tool_calls:
                        func_name = tool_call.function.name
                        
                        try:
                            args = json.loads(tool_call.function.arguments)
                        except:
                            args = {}
                            
                        tool_result = ""
                        
                        # --- Start timing tool execution ---
                        tool_start_time = time.time() 
                        
                        if func_name == "get_current_time":
                            tool_result = get_current_time()
                            tool_end_time = time.time()
                            print(f"  [Tool]: get_current_time() => {tool_result} (took {tool_end_time - tool_start_time:.2f}s)")
                            
                        elif func_name == "read_local_file":
                            target_file = args.get("filepath", "")
                            tool_result = read_local_file(target_file)
                            tool_end_time = time.time()
                            print(f"  [Tool]: read_local_file('{target_file}') => [Read {len(str(tool_result))} chars] (took {tool_end_time - tool_start_time:.2f}s)")
                            
                        elif func_name == "get_stock_price":
                            target_ticker = args.get("ticker", "")
                            tool_result = get_stock_price(target_ticker.upper()) 
                            tool_end_time = time.time()
                            print(f"  [Tool]: get_stock_price('{target_ticker}') => {tool_result} (took {tool_end_time - tool_start_time:.2f}s)")
                        
                        elif func_name == "list_directory":
                            folder = args.get("folder_path", ".")
                            tool_result = list_directory(folder)
                            tool_end_time = time.time()
                            print(f"  [Tool]: list_directory('{folder}') => (took {tool_end_time - tool_start_time:.2f}s)")
                            
                        elif func_name == "search_in_files":
                            keyword = args.get("keyword", "")
                            folder = args.get("folder_path", ".")
                            tool_result = search_in_files(keyword, folder)
                            tool_end_time = time.time()
                            print(f"  [Tool]: search_in_files('{keyword}') => (took {tool_end_time - tool_start_time:.2f}s)")
                            
                        elif func_name == "edit_local_file":
                            filepath = args.get("filepath", "")
                            content = args.get("content", "")
                            mode = args.get("mode", "w")
                            tool_result = edit_local_file(filepath, content, mode)
                            tool_end_time = time.time()
                            print(f"  [Tool]: edit_local_file('{filepath}', mode='{mode}') => {tool_result} (took {tool_end_time - tool_start_time:.2f}s)")
                            
                        elif func_name == "get_file_info":
                            filepath = args.get("filepath", "")
                            tool_result = get_file_info(filepath)
                            tool_end_time = time.time()
                            print(f"  [Tool]: get_file_info('{filepath}') => {tool_result} (took {tool_end_time - tool_start_time:.2f}s)")
                            
                        elif func_name == "view_file_lines":
                            filepath = args.get("filepath", "")
                            start = args.get("start_line", 1)
                            end = args.get("end_line", 50)
                            tool_result = view_file_lines(filepath, start, end)
                            tool_end_time = time.time()
                            print(f"  [Tool]: view_file_lines('{filepath}', {start}-{end}) => (took {tool_end_time - tool_start_time:.2f}s)")
                            
                        elif func_name == "replace_in_file":
                            filepath = args.get("filepath", "")
                            old_txt = args.get("old_text", "")
                            new_txt = args.get("new_text", "")
                            tool_result = replace_in_file(filepath, old_txt, new_txt)
                            tool_end_time = time.time()
                            print(f"  [Tool]: replace_in_file('{filepath}') => {tool_result} (took {tool_end_time - tool_start_time:.2f}s)")
                            
                        elif func_name == "delete_local_file":
                            filepath = args.get("filepath", "")
                            tool_result = delete_local_file(filepath)
                            tool_end_time = time.time()
                            print(f"  [Tool]: delete_local_file('{filepath}') => {tool_result} (took {tool_end_time - tool_start_time:.2f}s)")
                            
                        elif func_name == "move_or_rename_file":
                            src = args.get("source_path", "")
                            dst = args.get("dest_path", "")
                            tool_result = move_or_rename_file(src, dst)
                            tool_end_time = time.time()
                            print(f"  [Tool]: move_or_rename_file('{src}' -> '{dst}') => {tool_result} (took {tool_end_time - tool_start_time:.2f}s)")

                        elif func_name == "execute_shell_command":
                            shell_cmd = args.get("command", "")
                            # Ignore any "confirmed" value the model tries to set on its own -
                            # confirmation must come from a real human response, not the model's guess.
                            tool_result = execute_shell_command(shell_cmd, confirmed=False)
                            tool_end_time = time.time()
                            print(f"  [Tool]: execute_shell_command('{shell_cmd}') => {tool_result} (took {tool_end_time - tool_start_time:.2f}s)")

                            if isinstance(tool_result, str) and tool_result.startswith("CONFIRMATION_REQUIRED"):
                                confirm_input = input(f"  [Confirm]: Allow this command to run? (y/n): ").strip().lower()
                                if confirm_input == "y":
                                    tool_result = execute_shell_command(shell_cmd, confirmed=True)
                                    print(f"  [Tool]: execute_shell_command('{shell_cmd}', confirmed) => {tool_result}")
                                else:
                                    tool_result = "User declined to run this command."
                                    print("  [System]: Command declined by user.")

                        elif func_name == "git_commit_and_push":
                            commit_msg = args.get("commit_message", "")
                            # Same rule as execute_shell_command - the model cannot self-confirm.
                            tool_result = git_commit_and_push(commit_msg, confirmed=False)
                            tool_end_time = time.time()
                            print(f"  [Tool]: git_commit_and_push('{commit_msg}') => {tool_result} (took {tool_end_time - tool_start_time:.2f}s)")

                            if isinstance(tool_result, str) and tool_result.startswith("CONFIRMATION_REQUIRED"):
                                confirm_input = input(f"  [Confirm]: Allow commit & push? (y/n): ").strip().lower()
                                if confirm_input == "y":
                                    tool_result = git_commit_and_push(commit_msg, confirmed=True)
                                    print(f"  [Tool]: git_commit_and_push('{commit_msg}', confirmed) => {tool_result}")
                                else:
                                    tool_result = "User declined to commit/push."
                                    print("  [System]: Commit/push declined by user.")

                        conversation_history.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": func_name,
                            "content": str(tool_result)
                        })
                    
                    continue
                
                else:
                    answer = message.content
                    print(f"\nAgent (took {agent_duration:.2f}s): {answer}\n")
                    conversation_history.append({"role": "assistant", "content": answer})
                    break 
                
        except Exception as e:
            attempt += 1
            print(f"  [Error]: {e}")
            
            # Rollback to safe state on errors
            conversation_history = list(safe_history_backup) 
            
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
            else:
                print("  [System]: Max retries reached. Please try asking again.\n")
                conversation_history = conversation_history[:-1]
                break