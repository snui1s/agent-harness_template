import os
import time
import json
from openrouter import OpenRouter
from . import db

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


def _parse_compaction_response(raw_text):
    """
    Split a combined 'SUMMARY: ... FACTS: [...]' response into (summary, facts).
    Falls back gracefully if the model doesn't follow the format exactly.
    """
    summary = raw_text.strip()
    facts = []

    if "FACTS:" in raw_text:
        summary_part, facts_part = raw_text.split("FACTS:", 1)
        summary_part = summary_part.strip()
        if summary_part.upper().startswith("SUMMARY:"):
            summary_part = summary_part[len("SUMMARY:"):].strip()
        summary = summary_part or summary

        facts_part = facts_part.strip()
        if facts_part.startswith("```"):
            facts_part = facts_part.strip("`")
            if facts_part.lower().startswith("json"):
                facts_part = facts_part[4:].strip()
        try:
            parsed = json.loads(facts_part)
            if isinstance(parsed, list):
                facts = [str(f).strip() for f in parsed if str(f).strip()]
        except Exception:
            facts = []
    elif raw_text.strip().upper().startswith("SUMMARY:"):
        summary = raw_text.strip()[len("SUMMARY:"):].strip()

    return summary, facts


def compact_memory(conversation_history, max_active_messages, keep_recent, offload_file, model_name, system_prompt, session_id=None):
    """
    Function: Triggers memory compaction if active history exceeds max_active_messages.
    While compacting, also extracts any durable, reusable facts about the user (identity,
    preferences, ongoing projects) and saves them to the long-term memory table so they
    persist across sessions - not just within this one.
    Returns:
        list: The updated conversation history (compacted or not).
    """
    if len(conversation_history) > max_active_messages:
        print("\n  [System]: Memory full. Triggering Compaction & Offloading...")
        
        messages_to_compact = conversation_history[:-keep_recent]
        recent_messages = conversation_history[-keep_recent:]
        
        offload_to_disk(messages_to_compact, offload_file)
        
        combined_prompt = (
            "You are compacting a conversation history. Read the messages below and respond "
            "in EXACTLY this format (no extra text before or after):\n\n"
            "SUMMARY: <a concise summary of the key context and facts from these messages>\n"
            "FACTS: <a JSON array of short, durable facts about the user - identity, preferences, "
            "ongoing projects, constraints - that would still be useful in a completely different, "
            "future conversation. Ignore anything trivial or task-specific. Use [] if there is nothing "
            "worth remembering long-term.>\n\n"
            "Messages:\n"
        )
        for msg in messages_to_compact:
            combined_prompt += f"{msg['role'].upper()}: {msg.get('content', '')}\n"
            
        try:
            print("  [System]: Compacting context (summarizing + extracting memory)...")
            compaction_start_time = time.time()
            
            with OpenRouter(api_key=os.getenv("OPENROUTER_API_KEY")) as client:
                sum_response = client.chat.send(
                    model=model_name,
                    messages=[{"role": "user", "content": combined_prompt}]
                )
                raw_content = sum_response.choices[0].message.content
                
            compaction_end_time = time.time()
            compaction_duration = compaction_end_time - compaction_start_time

            compacted_summary, extracted_facts = _parse_compaction_response(raw_content)

            if extracted_facts:
                for fact in extracted_facts:
                    db.save_memory_fact(fact, session_id)
                print(f"  [Memory]: Saved {len(extracted_facts)} long-term fact(s): {extracted_facts}")
            
            updated_history = [
                {"role": "system", "content": f"{system_prompt}\n\n[Previous Context Summary]: {compacted_summary}"}
            ] + recent_messages
            print(f"  [System]: Compaction complete in {compaction_duration:.2f}s. Context compressed.\n")
            return updated_history
            
        except Exception as e:
            print(f"  [System Error]: Compaction failed ({e}). Using sliding window.")
            return recent_messages
            
    return conversation_history