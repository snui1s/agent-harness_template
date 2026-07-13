from openrouter import OpenRouter
import os
import time
import json  # นำเข้า json สำหรับการทำ Offloading

# Load environment variables
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
MODEL_NAME = "qwen/qwen3-next-80b-a3b-thinking"

# ตั้งค่าเรื่อง Memory
MAX_ACTIVE_MESSAGES = 6  # จำนวนข้อความสูงสุดใน RAM
KEEP_RECENT = 2          # จำนวนข้อความล่าสุดที่จะเก็บไว้แบบไม่ย่อ (ต้องไม่หลุดบริบทปัจจุบัน)
OFFLOAD_FILE = "chat_archive.jsonl"  # ไฟล์สำหรับเก็บประวัติเก่า

conversation_history = []

print("=== Agent Harness Started (Compaction & Offloading) ===")
print(f"Offloaded data will be saved to: {OFFLOAD_FILE}")
print("พิมพ์ 'exit' หรือ 'quit' เพื่อออกจากการทำงาน\n")

def offload_to_disk(messages):
    """ฟังก์ชันย้ายข้อความดิบลงไฟล์ (Cold Storage)"""
    with open(OFFLOAD_FILE, "a", encoding="utf-8") as f:
        for msg in messages:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")
    print(f"  [Storage]: Offloaded {len(messages)} raw messages to disk.")

while True:
    user_input = input("You: ")
    
    if user_input.lower() in ['exit', 'quit']:
        print("Shutting down agent...")
        break
        
    if not user_input.strip():
        continue

    conversation_history.append({"role": "user", "content": user_input})

    # --- 1. Memory Compaction & Offloading Logic ---
    if len(conversation_history) > MAX_ACTIVE_MESSAGES:
        print("\n  [System]: Memory full. Triggering Compaction & Offloading...")
        
        # แบ่งข้อความเป็น 2 ส่วน: ส่วนที่จะโดนย้าย/ย่อ กับ ส่วนที่จะเก็บไว้ใน Active Memory
        messages_to_compact = conversation_history[:-KEEP_RECENT]
        recent_messages = conversation_history[-KEEP_RECENT:]
        
        # 1.1 Offload: เซฟข้อความที่กำลังจะถูกย่อลงไฟล์ดิสก์
        offload_to_disk(messages_to_compact)
        
        # 1.2 Compaction: สร้าง Prompt สั่งให้ LLM ย่อประวัติชุดนี้
        summary_prompt = "Summarize the key context and facts from these previous messages. Keep it concise:\n\n"
        for msg in messages_to_compact:
            summary_prompt += f"{msg['role'].upper()}: {msg['content']}\n"
            
        try:
            with OpenRouter(api_key=os.getenv("OPENROUTER_API_KEY")) as client:
                sum_response = client.chat.send(
                    model=MODEL_NAME,
                    messages=[{"role": "user", "content": summary_prompt}],
                )
                compacted_summary = sum_response.choices[0].message.content
                
            # 1.3 Rebuild History: [System Prompt (เรื่องย่อ)] + [ข้อความล่าสุด]
            conversation_history = [
                {"role": "system", "content": f"Context Summary: {compacted_summary}"}
            ] + recent_messages
            print("  [System]: Compaction complete. Context compressed.\n")
            
        except Exception as e:
            print(f"  [System Error]: Compaction failed ({e}). Using sliding window.")
            # Fallback: ถ้าย่อล้มเหลว อย่างน้อยเราก็เซฟลงไฟล์ไปแล้ว แค่ตัดของเก่าทิ้งใน RAM
            conversation_history = recent_messages

    # --- 2. Main Agent Call (พร้อม Retry) ---
    attempt = 0
    while attempt < MAX_RETRIES:
        try:
            if attempt > 0:
                print(f"  [Retrying... {attempt}/{MAX_RETRIES}]")
            
            with OpenRouter(api_key=os.getenv("OPENROUTER_API_KEY")) as client:
                response = client.chat.send(
                    model=MODEL_NAME,
                    messages=conversation_history
                )
                
                answer = response.choices[0].message.content
                print(f"Agent: {answer}\n")
                
                conversation_history.append({"role": "assistant", "content": answer})
                break
                
        except Exception as e:
            attempt += 1
            print(f"  [Error]: {e}")
            
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
            else:
                print("  [System]: Max retries reached. Please try asking again.\n")
                conversation_history.pop()