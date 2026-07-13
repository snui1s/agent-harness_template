import os
import time
import json
from openrouter import OpenRouter

def offload_to_disk(messages, offload_file):
    """
    Function: Appends old/raw messages to a JSON Lines (JSONL) file for long-term cold storage.
    Args:
        messages (list): A list of message dictionaries to write to disk.
        offload_file (str): Path to the archive file.
    """
    with open(offload_file, "a", encoding="utf-8") as f:
        for msg in messages:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")
    print(f"  [Storage]: Offloaded {len(messages)} raw messages to disk.")

def compact_memory(conversation_history, max_active_messages, keep_recent, offload_file, model_name, system_prompt):
    """
    Function: Triggers memory compaction if active history exceeds max_active_messages.
    Returns:
        list: The updated conversation history (compacted or not).
    """
    if len(conversation_history) > max_active_messages:
        print("\n  [System]: Memory full. Triggering Compaction & Offloading...")
        
        messages_to_compact = conversation_history[:-keep_recent]
        recent_messages = conversation_history[-keep_recent:]
        
        offload_to_disk(messages_to_compact, offload_file)
        
        summary_prompt = "Summarize the key context and facts from these previous messages. Keep it concise:\n\n"
        for msg in messages_to_compact:
            summary_prompt += f"{msg['role'].upper()}: {msg['content']}\n"
            
        try:
            print("  [System]: Compacting context (summarizing)...")
            compaction_start_time = time.time()
            
            with OpenRouter(api_key=os.getenv("OPENROUTER_API_KEY")) as client:
                sum_response = client.chat.send(
                    model=model_name,
                    messages=[{"role": "user", "content": summary_prompt}]
                )
                compacted_summary = sum_response.choices[0].message.content
                
            compaction_end_time = time.time()
            compaction_duration = compaction_end_time - compaction_start_time
            
            updated_history = [
                {"role": "system", "content": f"{system_prompt}\n\n[Previous Context Summary]: {compacted_summary}"}
            ] + recent_messages
            print(f"  [System]: Compaction complete in {compaction_duration:.2f}s. Context compressed.\n")
            return updated_history
            
        except Exception as e:
            print(f"  [System Error]: Compaction failed ({e}). Using sliding window.")
            return recent_messages
            
    return conversation_history
