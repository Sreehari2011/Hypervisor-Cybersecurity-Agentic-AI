import logging
from langgraph.graph import StateGraph, END
from langchain_core.messages import SystemMessage, ToolMessage, AIMessage, HumanMessage
from agents.registry import AGENTS_CONFIG, get_agent_tools
from core.state import HypervisorState
from core.memory import manage_episodic_memory, MEMORY_TOOLS
from config import MODEL_PLANNER, LLM_BASE_URL, LLM_API_KEY, MODEL_EXECUTOR
from langchain_openai import ChatOpenAI

logger = logging.getLogger("HypervisorTrace")

def create_agent_node(agent_config):
    """Creates a graph node for a specific agent."""
    name = agent_config["name"]
    system_prompt = agent_config["system_prompt"]
    model_name = agent_config["model"]
    
    tools = get_agent_tools(name) + MEMORY_TOOLS

    # ----------------------- TOKEN BLEEDING ISSUE - START ---------------------------
    # ADDED stop sequences to prevent the model from generating further garbage tokens

    llm = ChatOpenAI(
        model=MODEL_PLANNER, 
        base_url=LLM_BASE_URL, 
        api_key=LLM_API_KEY,
        temperature=0.0,
        stop=["<|channel|>", "<|im_end|>", "<|eot_id|>", "<|end_of_text|>"]
    )
    llm_with_tools = llm.bind_tools(tools)

    # ---------------------- TOKEN BLEEDING ISSUE - END ------------------------------

    async def agent_node(state: HypervisorState):
        messages = state["messages"]
        summary = state.get("episodic_summary", "")

        logger.info(f"[AGENT INVOCATION] Node '{name}' executing. Turn Count: {state.get('turn_count', 0)}")
        
        dynamic_system_content = system_prompt
        if summary:
            dynamic_system_content += f"\n\n=================================\n### CURRENT ENGAGEMENT MEMORY (EPISODIC)\n{summary}\n=================================\n"
            
        if messages and isinstance(messages[-1], ToolMessage):
            last_tool_out = messages[-1].content
            if "Transferring to" in last_tool_out:
                logger.info(f"[STATE INJECTION] Injected Handoff {{ToolMessage}} Context into '{name}' System Prompt.")
                dynamic_system_content += f"\n\n### HANDOFF DIRECTIVE FROM PREVIOUS AGENT:\n{last_tool_out}"

        try:
            response = await llm_with_tools.ainvoke([SystemMessage(content=dynamic_system_content)] + messages)

            # ---------------------- TOKEN BLEEDING ISSUE - START ------------------------------
            # IMPLEMENTING a special token sanitizer

            if hasattr(response, 'tool_calls') and response.tool_calls:
                for tc in response.tool_calls:
                    original_name = tc.get("name", "")
                    if "<|" in original_name:
                        tc["name"] = original_name.split("<|")[0].strip()
                        
                if "tool_calls" in response.additional_kwargs:
                    for raw_tc in response.additional_kwargs["tool_calls"]:
                        if "function" in raw_tc and "name" in raw_tc["function"]:
                            raw_name = raw_tc["function"]["name"]
                            if "<|" in raw_name:
                                raw_tc["function"]["name"] = raw_name.split("<|")[0].strip()
                                
            # If the JSON was completely malformed due to tokens, break the loop manually
            if hasattr(response, 'invalid_tool_calls') and response.invalid_tool_calls:
                error_msg = "[SYSTEM FAULT TRAPPED]: You generated an invalid tool format or hallucinated model tags (e.g., <|channel|>). DO NOT DO THIS. Use ONLY standard JSON with the exact tool names provided."
                return {
                    "messages": [HumanMessage(content=error_msg)],
                    "sender": name,
                    "turn_count": state.get("turn_count", 0) + 1
                }
            # ---------------------- TOKEN BLEEDING ISSUE - END ------------------------------
            
            # --- ANTI-HALLUCINATION TRAP ---
            has_tools = hasattr(response, 'tool_calls') and response.tool_calls
            has_invalid_tools = hasattr(response, 'invalid_tool_calls') and response.invalid_tool_calls
            
            if has_tools:
                tool_names = [tc['name'] for tc in response.tool_calls]
                logger.info(f"[AGENT RESPONSE] '{name}' generated {{AIMessage}} containing tool_calls: {tool_names}")
            elif has_invalid_tools:
                logger.info(f"[AGENT RESPONSE] '{name}' generated {{AIMessage}} containing INVALID tool_calls.")
            else:
                logger.info(f"[AGENT RESPONSE] '{name}' generated plain text {{AIMessage}} (No tools).")
            
            # If the proxy returns empty content without ANY tool calls
            if not response.content and not has_tools and not has_invalid_tools:
                msg = HumanMessage(content="[SYSTEM FAULT TRAPPED]: Your previous output was completely empty. You must rethink your approach and use execute_code to write a Python script if standard tools are failing.")
                return {
                    "messages": [msg],
                    "sender": name,
                    "turn_count": state.get("turn_count", 0) + 1
                }
                
            return {
                "messages": [response],
                "sender": name,
                "turn_count": state.get("turn_count", 0) + 1
            }
            
        except Exception as e:
            # --- NODE-LEVEL AUTO RECOVERY ---
            # If the Proxy crashes (HTTP 500) or LangChain fails to parse the output to prevent this issue, injecting a HumanMessage so the LLM feels like the environment is forcing it to pivot
            error_msg = f"[SYSTEM FAULT TRAPPED]: The LLM proxy encountered a critical error or generated malformed tokens. Error: {str(e)}\n\nDo not repeat the previous action. You must pivot immediately to using execute_code to write a Python script to accomplish your objective."
            return {
                "messages": [HumanMessage(content=error_msg)],
                "sender": name,
                "turn_count": state.get("turn_count", 0) + 1
            }
    
    return agent_node

def router(state: HypervisorState):
    messages = state["messages"]
    last_message = messages[-1]
    turn_count = state.get("turn_count", 0)
    sender = state.get("sender", "Unknown")

    logger.info(f"[ROUTER START] Router evaluating State from sender: '{sender}'")

    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        for tool_call in last_message.tool_calls:
            tool_name = tool_call["name"]
            
            # Check if the tool is an Agent Handoff (e.g., transfer_to_redteam_agent)
            if tool_name.startswith("transfer_to_"):
                target_agent_name_raw = tool_name.replace("transfer_to_", "")
                # Find the actual properly formatted agent name in your config
                for ag in AGENTS_CONFIG:
                    if ag["name"].lower() == target_agent_name_raw.lower():
                        logger.info(f"[ROUTER REDIRECT] Routing from {sender} to Specialist: {ag['name']}")
                        return ag["name"]
        
        # If it's a standard tool (nmap, gobuster, etc.), route to call_tool
        logger.info(f"[ROUTER REDIRECT] Tool Call detected ({[t['name'] for t in last_message.tool_calls]}). Routing to 'call_tool'.")
        return "call_tool"

    # 2. Handle Invalid/Malformed Tool Calls (Force them to the ToolNode to report errors)
    if hasattr(last_message, 'invalid_tool_calls') and last_message.invalid_tool_calls:
        logger.info("[ROUTER REDIRECT] Malformed tool call detected. Routing to 'call_tool' for error reporting.")
        return "call_tool"

    if "🛑 ENGAGEMENT COMPLETE 🛑" in str(last_message.content):
        logger.info("[ROUTER REDIRECT] Engagement Complete signal detected. Routing to END.")
        return END
    
    if "[SYSTEM FAULT TRAPPED]" in str(last_message.content):
        logger.warning(f"[ROUTER REDIRECT] System Fault Trapped. Bouncing back to sender: '{sender}'")
        return sender
    
    if turn_count > 25 or len(messages) > 40:
        logger.info("[ROUTER REDIRECT] Memory threshold exceeded. Routing to Memory_Manager.")
        return "Memory_Manager"
    
    logger.info("[ROUTER REDIRECT] No actionable routing triggers. Routing to END.")
    return END

def build_hypervisor_graph():
    workflow = StateGraph(HypervisorState)
    
    for agent_cfg in AGENTS_CONFIG:
        workflow.add_node(agent_cfg["name"], create_agent_node(agent_cfg))

    workflow.add_node("Memory_Manager", manage_episodic_memory)

    from langgraph.prebuilt import ToolNode
    all_tools =[] 
    for ag in AGENTS_CONFIG:
        all_tools.extend(get_agent_tools(ag["name"]))
    all_tools.extend(MEMORY_TOOLS)
    unique_tools = {t.name: t for t in all_tools}.values()
    
    workflow.add_node("call_tool", ToolNode(list(unique_tools)))

    workflow.set_entry_point("Selection_Agent")

    for agent_cfg in AGENTS_CONFIG:
        name = agent_cfg["name"]
        workflow.add_conditional_edges(
            name,
            router,
            {
                "call_tool": "call_tool",
                "Memory_Manager": "Memory_Manager",
                END: END,
                **{cfg["name"]: cfg["name"] for cfg in AGENTS_CONFIG}
            }
        )

    def route_back_from_memory(state):
        return state["sender"]
        
    workflow.add_conditional_edges("Memory_Manager", route_back_from_memory)

    def route_back_from_tool(state):
        messages = state.get("messages",[])
        if messages and isinstance(messages[-1], ToolMessage):
            content = messages[-1].content
            if "Transferring to" in content:
                for ag in AGENTS_CONFIG:
                    if ag["name"].lower() in content.lower():
                        logger.info(f"[HANDOFF SUCCESS] ToolNode routing State directly to Specialist: '{ag['name']}'")
                        return ag["name"]
        logger.info(f"[TOOL COMPLETE] Routing State back to sender: '{state.get('sender')}'")
        return state.get("sender")
    
    routing_map = {cfg["name"]: cfg["name"] for cfg in AGENTS_CONFIG}
    
    workflow.add_conditional_edges(
        "call_tool", 
        route_back_from_tool,
        routing_map
    )

    return workflow