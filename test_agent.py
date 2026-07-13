# สร้างไฟล์: test_agent.py
import json
from openrouter import OpenRouter
import os
import time

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

def offload_to_disk(messages):
    """ฟังก์ชันย้ายข้อความลงไฟล์"""
    with open(OFFLOAD_FILE, "a", encoding="utf-8") as f:
        for msg in messages:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")
    print(f"  [Storage]: Offloaded {len(messages)} raw messages to disk.")


def run_automated_test():
    """ทดสอบ compaction & offloading โดยอัตโนมัติ"""
    
    test_messages = []
    for i in range(15):
        test_messages.append({"role": "user", "content": f"Question {i}: Tell me about topic {i}"})
        test_messages.append({"role": "assistant", "content": f"Answer {i}: This is a detailed response about topic {i}. " * 5})
    
    print(f"Generated {len(test_messages)} test messages\n")
    
    conversation_history = []
    
    for i, msg in enumerate(test_messages):
        print(f"[{i+1}/{len(test_messages)}] Processing: {msg['role']}")
        
        conversation_history.append(msg)
        
        if len(conversation_history) > MAX_ACTIVE_MESSAGES:
            print(f"  ⚠️  Triggered compaction! (Active: {len(conversation_history)})")
            
            # ← เพิ่มบรรทัดนี้
            messages_to_compact = conversation_history[:-KEEP_RECENT]
            recent_messages = conversation_history[-KEEP_RECENT:]
            
            offload_to_disk(messages_to_compact)
            conversation_history = recent_messages  # ← update history
            
            if os.path.exists(OFFLOAD_FILE):
                with open(OFFLOAD_FILE, "r") as f:
                    offloaded_count = len(f.readlines())
                print(f"  ✅ Offloaded to disk: {offloaded_count} lines")
        
        print(f"  Current active messages: {len(conversation_history)}")
    
    print("\n✅ Test completed!")

if __name__ == "__main__":
    run_automated_test()