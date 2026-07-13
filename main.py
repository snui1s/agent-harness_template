from openrouter import OpenRouter
import os
import time
import json
from datetime import datetime
import yfinance as yf

# Load environment variables from local .env file
if os.path.exists(".env"):
    with open(".env", "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()

# --- Configurations ---
MAX_RETRIES = 3
RETRY_DELAY = 2
# MODEL_NAME = "qwen/qwen3-next-80b-a3b-thinking"
MODEL_NAME ="openrouter/free"

# Memory management parameters
MAX_ACTIVE_MESSAGES = 6 # 30-40
KEEP_RECENT = 2 # 3-6
OFFLOAD_FILE = "chat_archive.jsonl"

conversation_history = []

# --- Helper Functions (Tools) ---

def get_current_time():
    """
    Function: Retrieves the current system date and time formatted as a string.
    Returns: String representation of current time (e.g., 'YYYY-MM-DD HH:MM:SS').
    """
    now = datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")

def read_local_file(filepath):
    """
    Function: อ่านเนื้อหาไฟล์ในเครื่อง (แบบจำกัดให้อยู่แค่ในโฟลเดอร์โปรเจกต์เท่านั้น)
    """
    try:
        base_dir = os.path.abspath(os.getcwd())
        target_path = os.path.abspath(filepath)
        
        # Guardrail: ล็อกเป้าให้อยู่แค่ในโฟลเดอร์โปรเจกต์
        if not target_path.startswith(base_dir):
            return "Error: Security block! Access to files outside the project directory is denied."
            
        if not os.path.exists(target_path):
            return f"Error: File '{filepath}' not found."
            
        with open(target_path, "r", encoding="utf-8") as f:
            content = f.read(2000) # จำกัดการอ่านกัน Token ล้น
            if len(content) == 2000:
                content += "\n...[TRUNCATED]..."
            return content
            
    except Exception as e:
        return f"Error reading file: {str(e)}"

def get_stock_price(ticker):
    """ดึงราคาหุ้นปัจจุบันด้วย yfinance"""
    try:
        # ดึงข้อมูลหุ้น
        stock = yf.Ticker(ticker)
        # ดึงข้อมูลราคาย้อนหลัง 1 วัน (เร็วที่สุดในการดึงราคาปัจจุบัน)
        hist = stock.history(period="1d")
        
        if hist.empty:
            return f"Error: Could not find data for ticker '{ticker}'. Please check if the ticker symbol is correct."
        
        # ดึงราคาปิดล่าสุด
        latest_price = hist['Close'].iloc[-1]
        currency = stock.info.get('currency', 'USD')
        name = stock.info.get('shortName', ticker)
        
        return f"The current price of {name} ({ticker}) is {latest_price:.2f} {currency}."
        
    except Exception as e:
        return f"Error fetching stock data: {str(e)}"

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
    }
]

# --- Persona Setup ---

SYSTEM_PROMPT = """You are an intelligent AI assistant with broad general knowledge. Answer general knowledge, philosophy, or history questions using your own knowledge.
You have access to tools, but only call them when truly necessary (e.g. when asked for the current time or to read a local file).
For general knowledge questions, answer directly without relying on tools."""

# Initialize the conversation state with the system persona
conversation_history = [{"role": "system", "content": SYSTEM_PROMPT}]

print("=== Agent Harness Started (Compaction, Offloading & Tools) ===")
print(f"Offloaded data will be saved to: {OFFLOAD_FILE}")
print("พิมพ์ 'exit' หรือ 'quit' เพื่อออกจากการทำงาน\n")

def offload_to_disk(messages):
    """
    Function: Appends old/raw messages to a JSON Lines (JSONL) file for long-term cold storage.
    Args:
        messages (list): A list of message dictionaries to write to disk.
    """
    with open(OFFLOAD_FILE, "a", encoding="utf-8") as f:
        for msg in messages:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")
    print(f"  [Storage]: Offloaded {len(messages)} raw messages to disk.")

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
    if len(conversation_history) > MAX_ACTIVE_MESSAGES:
        print("\n  [System]: Memory full. Triggering Compaction & Offloading...")
        
        messages_to_compact = conversation_history[:-KEEP_RECENT]
        recent_messages = conversation_history[-KEEP_RECENT:]
        
        offload_to_disk(messages_to_compact)
        
        summary_prompt = "Summarize the key context and facts from these previous messages. Keep it concise:\n\n"
        for msg in messages_to_compact:
            summary_prompt += f"{msg['role'].upper()}: {msg['content']}\n"
            
        try:
            print("  [System]: Compacting context (summarizing)...")
            compaction_start_time = time.time() # จับเวลาย่อความ
            
            with OpenRouter(api_key=os.getenv("OPENROUTER_API_KEY")) as client:
                sum_response = client.chat.send(
                    model=MODEL_NAME,
                    messages=[{"role": "user", "content": summary_prompt}]
                )
                compacted_summary = sum_response.choices[0].message.content
                
            compaction_end_time = time.time()
            compaction_duration = compaction_end_time - compaction_start_time
            
            conversation_history = [
                {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n[Previous Context Summary]: {compacted_summary}"}
            ] + recent_messages
            print(f"  [System]: Compaction complete in {compaction_duration:.2f}s. Context compressed.\n")
            
        except Exception as e:
            print(f"  [System Error]: Compaction failed ({e}). Using sliding window.")
            conversation_history = recent_messages

    # --- State: Main Agent Call Loop (with Retries, Tools, and Safeguards) ---
    attempt = 0
    tool_call_count = 0       
    MAX_TOOL_CALLS = 3        
    
    while attempt < MAX_RETRIES:
        history_backup = list(conversation_history) 
        
        try:
            if attempt > 0:
                print(f"  [Retrying... {attempt}/{MAX_RETRIES}]")
            
            # --- เริ่มจับเวลา AI ประมวลผล ---
            print("  [Thinking...]") 
            agent_start_time = time.time() 
            
            with OpenRouter(api_key=os.getenv("OPENROUTER_API_KEY")) as client:
                response = client.chat.send(
                    model=MODEL_NAME,
                    messages=conversation_history,
                    tools=my_tools
                )
                
                message = response.choices[0].message
                
                agent_end_time = time.time()
                agent_duration = agent_end_time - agent_start_time
                # --- จบจับเวลา AI ---

                if hasattr(message, 'tool_calls') and message.tool_calls:
                    if tool_call_count >= MAX_TOOL_CALLS:
                        print("  [System]: Too many tool calls. Forcing stop to prevent infinite loop.")
                        conversation_history = history_backup[:-1] 
                        break
                        
                    print(f"  [System]: Agent decided to use a tool (took {agent_duration:.2f}s)")
                    tool_call_count += 1
                    
                    conversation_history.append(message.model_dump(exclude_none=True))
                    
                    for tool_call in message.tool_calls:
                        func_name = tool_call.function.name
                        
                        try:
                            args = json.loads(tool_call.function.arguments)
                        except:
                            args = {}
                            
                        tool_result = ""
                        
                        # --- เริ่มจับเวลาการรัน Tool ---
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
                            
                        # --- จบจับเวลา Tool ---
                            
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
            conversation_history = history_backup 
            
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
            else:
                print("  [System]: Max retries reached. Please try asking again.\n")
                conversation_history = conversation_history[:-1]
                break