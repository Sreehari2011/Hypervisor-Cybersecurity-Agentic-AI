import json
import os
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from config import MODEL_PLANNER, LLM_BASE_URL, LLM_API_KEY, WORKSPACE_DIR

SEMANTIC_DB_PATH = os.path.join(WORKSPACE_DIR, "semantic_memory.json")

if not os.path.exists(SEMANTIC_DB_PATH):
    with open(SEMANTIC_DB_PATH, 'w') as f:
        json.dump({"memories": []}, f)

# --- 1. SEMANTIC MEMORY TOOLS (RAG) ---

@tool
def store_semantic_memory(topic: str, technical_details: str):
    """
    Stores a critical technical finding, exploit methodology, or credential for long-term use.
    Use this when you find a password, a working exploit, or a critical vulnerability.
    """
    try:
        with open(SEMANTIC_DB_PATH, 'r') as f:
            data = json.load(f)
        
        data["memories"].append({
            "topic": topic,
            "details": technical_details
        })
        
        with open(SEMANTIC_DB_PATH, 'w') as f:
            json.dump(data, f, indent=4)
        return f"Successfully stored memory under topic: {topic}"
    except Exception as e:
        return f"Memory Storage Error: {e}"

@tool
def query_semantic_memory(query: str):
    """
    Searches the long-term semantic memory for previously discovered credentials, IPs, or exploits.
    """
    try:
        with open(SEMANTIC_DB_PATH, 'r') as f:
            data = json.load(f)
        
        # Simple keyword-based semantic search fallback
        results = []
        for mem in data["memories"]:
            if query.lower() in mem["topic"].lower() or query.lower() in mem["details"].lower():
                results.append(f"Topic: {mem['topic']}\nDetails: {mem['details']}")
                
        if not results:
            return f"No memories found matching '{query}'."
        return "\n\n".join(results)
    except Exception as e:
        return f"Memory Query Error: {e}"

MEMORY_TOOLS = [store_semantic_memory, query_semantic_memory]

# --- 2. EPISODIC MEMORY MANAGER (Background Node) ---

EPISODIC_PROMPT = """You are the Hypervisor's Episodic Memory Builder.
Your task is to summarize the following conversation history into a highly technical, chronological context state.
This summary will replace the LLM's raw message history to prevent Context Window Explosion.

CRITICAL REQUIREMENTS:
1. Preserve ALL discovered IP addresses, ports, URLs, and directory paths.
2. Preserve ALL discovered credentials, hashes, and access tokens.
3. Document the exact attack vectors that succeeded or failed.
4. Note the current access level (e.g., unauthenticated, low-privilege shell, root).
6. State the User Objective
7. State the objectives completed and their outcomes
8. State the immediate pending objective.
9. ACTIONS TRACKER: Explicitly list the shell commands that were just executed (e.g., "Already ran ss -tunp 3 times") so the agent DOES NOT repeat them.
10. CRYPTOGRAPHIC LEDGER (CRITICAL): You MUST preserve any exact strings, file paths, or text blocks tagged as [POTENTIAL_KEY], [CIPHERTEXT], or [ALGORITHM]. Do not truncate or summarize potential cryptographic keys or hex/base64 strings.

PREVIOUS SUMMARY:
{previous_summary}

NEW MESSAGES TO INCORPORATE:
{new_messages}

Output ONLY the new, comprehensive technical summary. Do not add introductory conversational text.
"""

async def manage_episodic_memory(state):
    """
    LangGraph Node: Triggered when message history gets too long.
    Compresses history into the `episodic_summary` and safely wipes old messages
    using a custom reducer signal to bypass LangGraph RemoveMessage bugs.
    """
    messages = state["messages"]
    previous_summary = state.get("episodic_summary", "No previous summary.")
    
    # Keeping the first message (Original User Prompt) and the last 2 messages (recent context), Everything in between gets summarized and deleted to keep the context window in control.
    if len(messages) <= 12:
        return {"turn_count": state.get("turn_count", 0) + 1}
        
    messages_to_summarize = messages[1:-2]
    
    # Format messages for the prompt
    history_text = "\n".join([f"{m.type}: {m.content}" for m in messages_to_summarize if m.content])
    
    # Initialize the LLM (Using the higher-tier Planner model for accurate summarization)
    llm = ChatOpenAI(
        model=MODEL_PLANNER, 
        base_url=LLM_BASE_URL,
        api_key=LLM_API_KEY 
    )
    
    prompt = EPISODIC_PROMPT.format(
        previous_summary=previous_summary,
        new_messages=history_text
    )
    
    try:
        response = await llm.ainvoke([SystemMessage(content=prompt)])
        new_summary = response.content
        
        # --- WIPE SIGNAL ---
        wipe_signal = SystemMessage(
            content="[INTERNAL SYSTEM: WIPING HISTORY]", 
            additional_kwargs={"action": "WIPE_HISTORY"}
        )
        
        # construct new clean history: Wipe signal + Original Goal + Last 2 Messages
        new_history = [wipe_signal, messages[0]] + messages[-6]
        
        return {
            "episodic_summary": new_summary,
            "messages": new_history,
            "turn_count": 0
        }
    except Exception as e:
        # Graceful failure: If summarization crashes, don't crash the entire execution graph. Just reset turns and append a warning.
        return {
            "turn_count": 0, 
            "episodic_summary": previous_summary + f"\n\n[SYSTEM WARNING: Episodic Memory Engine encountered an error during compression: {str(e)}. Proceed with existing context.]"
        }