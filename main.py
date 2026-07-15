# hello from the other side
from openrouter import OpenRouter
import os
import time
import json
from datetime import datetime

from src.agent import config
from src.agent import db
from src.agent import prompts
from src.agent import session
from src.agent.tools import my_tools, dispatch_tool
from src.agent.memory import compact_memory
from src.agent.ui import Spinner

# --- Startup Initialization ---
init_db_result = db.init_db()
current_session_id, conversation_history = session.select_session()
SYSTEM_PROMPT = conversation_history[0]["content"]

print("=== Agent Harness Started (Sessions, Compaction & Tools) ===")
print(f"Current session: [{current_session_id}]")
print("Commands: '/new <title>' new chat | '/sessions' list chats | '/switch <id>' change chat | '/help' help menu | '/exit' or '/quit' to leave.\n")

# --- Main Conversation Loop ---

while True:
    user_input = input("You: ")
    
    # Check for loop termination command
    if user_input.lower() in ['/exit', '/quit']:
        print("Shutting down agent...")
        break
        
    # Ignore empty inputs and prompt again
    if not user_input.strip():
        continue

    # --- Slash commands for session management & help ---
    if user_input.lower() == "/help":
        print("=== Available Commands ===")
        print("  /help          - Show this help menu with all available commands")
        print("  /sessions      - List all chat sessions (tabs) and see their IDs")
        print("  /new <title>   - Start a new chat session (e.g. '/new Web Development')")
        print("  /switch <id>   - Switch to an existing chat session by its ID (e.g. '/switch 3')")
        print("  /exit, /quit   - Terminate the agent harness session\n")
        continue

    if user_input.lower() == "/sessions":
        for s in db.list_sessions():
            marker = " (current)" if s["id"] == current_session_id else ""
            print(f"  [{s['id']}] {s['title']}  (last updated: {s['updated_at']}){marker}")
        print()
        continue

    if user_input.lower().startswith("/new"):
        title = user_input[4:].strip() or f"Chat {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        current_session_id = db.create_session(title)
        SYSTEM_PROMPT = prompts.build_system_prompt()
        conversation_history = [{"role": "system", "content": SYSTEM_PROMPT}]
        print(f"Switched to new session [{current_session_id}] '{title}'\n")
        continue

    if user_input.lower().startswith("/switch"):
        target = user_input[7:].strip()
        if target.isdigit() and db.session_exists(int(target)):
            current_session_id = int(target)
            archived_count, last_summary = db.get_compaction_state(current_session_id)
            loaded = db.load_messages(current_session_id, skip=archived_count)
            SYSTEM_PROMPT = prompts.build_system_prompt()
            if last_summary:
                SYSTEM_PROMPT += f"\n\n[Previous Context Summary]: {last_summary}"
            if not loaded or loaded[0].get("role") != "system":
                loaded = [{"role": "system", "content": SYSTEM_PROMPT}] + loaded
            else:
                loaded[0]["content"] = SYSTEM_PROMPT
            conversation_history = loaded
            print(f"Switched to session [{current_session_id}] with {len(conversation_history)} message(s)\n")
        else:
            print(f"Session '{target}' not found. Use '/sessions' to see available chats.\n")
        continue

    # State Update: Append the new user message to the active conversation history
    conversation_history.append({"role": "user", "content": user_input})
    _t0 = time.time()
    db.save_message(current_session_id, "user", user_input)
    print(f"  [DEBUG] db.save_message(user) took {time.time()-_t0:.3f}s")

    # --- State: Memory Compaction Logic ---
    print(f"  [DEBUG] conversation_history length: {len(conversation_history)} (compaction threshold: {config.MAX_ACTIVE_MESSAGES})")
    _t0 = time.time()
    conversation_history = compact_memory(
        conversation_history,
        config.MAX_ACTIVE_MESSAGES,
        config.KEEP_RECENT,
        config.COMPACTION_MODEL,
        SYSTEM_PROMPT,
        session_id=current_session_id
    )
    print(f"  [DEBUG] compact_memory took {time.time()-_t0:.3f}s")

    # --- State: Main Agent Call Loop (with Retries, Tools, and Safeguards) ---
    attempt = 0
    tool_call_count = 0       
    loop_iteration = 0
    loop_start_time = time.time()
    
    # Take a backup snapshot of conversation history before starting thinking to allow clean recovery on errors
    safe_history_backup = list(conversation_history) 
    
    while attempt < config.MAX_RETRIES:
        try:
            loop_iteration += 1
            print(f"  [DEBUG] --- Loop iteration {loop_iteration} (attempt={attempt}, tool_calls_so_far={tool_call_count}) ---")
            
            if attempt > 0:
                print(f"  [Retrying... {attempt}/{config.MAX_RETRIES}]")
            
            # --- Start timing AI processing ---
            print(f"  [Thinking...] (sending {len(conversation_history)} messages to API)") 
            agent_start_time = time.time() 
            
            with OpenRouter(api_key=config.OPENROUTER_API_KEY) as client:
                spinner = Spinner("Reflecting")
                spinner.start()
                try:
                    response = client.chat.send(
                        model=config.MODEL_NAME,
                        messages=conversation_history,
                        tools=my_tools
                    )
                finally:
                    spinner.stop()
                
                message = response.choices[0].message
                
                # --- Stop timing AI ---
                agent_end_time = time.time()
                agent_duration = agent_end_time - agent_start_time
                print(f"  [DEBUG] API call returned in {agent_duration:.2f}s | has_tool_calls={bool(hasattr(message, 'tool_calls') and message.tool_calls)}")

                if hasattr(message, 'tool_calls') and message.tool_calls:
                    if tool_call_count >= config.MAX_TOOL_CALLS:
                        print("  [System]: Too many tool calls. Forcing stop to prevent infinite loop.")
                        conversation_history = safe_history_backup[:-1] 
                        break
                        
                    print(f"  [System]: Agent decided to use a tool (took {agent_duration:.2f}s)")
                    tool_call_count += len(message.tool_calls)
                    
                    assistant_msg = message.model_dump(exclude_none=True)
                    conversation_history.append(assistant_msg)
                    # Persist the assistant tool-call message to SQLite
                    tc_json = json.dumps(assistant_msg.get("tool_calls", []), ensure_ascii=False)
                    db.save_message(
                        current_session_id, "assistant",
                        assistant_msg.get("content") or "",
                        tool_calls_json=tc_json
                    )
                    
                    for tool_call in message.tool_calls:
                        func_name = tool_call.function.name
                        try:
                            args = json.loads(tool_call.function.arguments)
                        except:
                            args = {}
                            
                        # Run the dispatcher
                        tool_result = dispatch_tool(func_name, args)
                        
                        tool_msg = {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": func_name,
                            "content": str(tool_result)
                        }
                        conversation_history.append(tool_msg)
                        # Persist tool result to SQLite
                        db.save_message(
                            current_session_id, "tool",
                            str(tool_result),
                            tool_call_id=tool_call.id,
                            tool_name=func_name
                        )
                    
                    continue
                
                else:
                    answer = message.content or "[No text response]"
                    total_elapsed = time.time() - loop_start_time
                    print(f"  [DEBUG] Total loop time: {total_elapsed:.2f}s across {loop_iteration} iteration(s)")
                    print(f"\nAgent (took {agent_duration:.2f}s): {answer}\n")
                    conversation_history.append({"role": "assistant", "content": answer})
                    db.save_message(current_session_id, "assistant", answer)
                    break 
                
        except Exception as e:
            attempt += 1
            print(f"  [Error]: {e}")
            
            # Rollback to safe state on errors
            conversation_history = list(safe_history_backup) 
            
            if attempt < config.MAX_RETRIES:
                time.sleep(config.RETRY_DELAY)
            else:
                print("  [System]: Max retries reached. Please try asking again.\n")
                conversation_history = conversation_history[:-1]
                break