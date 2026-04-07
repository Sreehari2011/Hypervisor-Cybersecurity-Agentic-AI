import asyncio
import sys
import json
import uuid
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.status import Status
from rich.text import Text
from rich.theme import Theme
from rich.table import Table
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from langgraph.checkpoint.memory import MemorySaver 

from core.graph import build_hypervisor_graph

import os, logging

if not os.path.exists("logs"):
    os.makedirs("logs")

logging.basicConfig(
    filename='logs/hypervisor_flow.log',
    filemode='a',
    format='[%(asctime)s] %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    level=logging.INFO
)
logger = logging.getLogger("HypervisorTrace")

custom_theme = Theme({
    "info": "dim cyan",
    "warning": "magenta",
    "danger": "bold red",
    "system": "bold green",
    "tool": "bright_black"
})

console = Console(theme=custom_theme)

text_logo = """


[bold white]Security Co-Pilot[/bold white][bold blue]

dP     dP                                               oo
88     88
88aaaaa88  dP    dP 88d888b. .d8888b. 88d888b. dP   .dP dP .d8888b. .d8888b. 88d888b.
88     88  88    88 88'  `88 88ooood8 88'  `88 88   d8' 88 Y8ooooo. 88'  `88 88'  `88
88     88  88.  .88 88.  .88 88.  ... 88       88 .88'  88       88 88.  .88 88
dP     dP  `8888P88 88Y888P' `88888P' dP       8888P'   dP `88888P' `88888P' dP
                .88 88
            d8888P  dP[/bold blue]""".strip("\n")

status_info = """
                                                    [bold white]Autonomous Agentic Kill-Chain Mesh[/bold white]
                                                       [bold white]CLI Version VD1.1 [DEVELOPMENT][/bold white]""".strip("\n")

orb_icon = """

                  ###############                  
           #############################           
       ###############       ###############       
     ##########                     ##########     
     #####               *               #####     
     #####       *****************       #####     
     #####   *************************   #####     
     #####   *************************   #####     
     #####   *************************   #####     
     #####   ******************   ****   #####     
     #####   *****************   *****   #####     
     #####   ***************    ******   #####     
     #####   ****    *****    ********   #####     
     #####   ******    *     *********   #####     
     #####   *******        **********   #####     
     #####    *******     ***********    #####     
      #####   *********  ************   #####      
      #####    *********************    #####      
       #####     *****************     #####       
        ######     *************     ######        
         #######      *******      #######         
           #######       *       #######           
             #######           #######             
               #########   #########               
                 #################                 
                     #########
""".strip("\n")

styled_orb = orb_icon.replace("#", "[bold blue]#[/]").replace("*", "[bold green]*[/]")

final_banner = Table.grid(expand=False, padding=(0, 4))
final_banner.add_column(vertical="middle", no_wrap=True) 
final_banner.add_column(vertical="middle", no_wrap=True)

text_stack = Table.grid(expand=False)
text_stack.add_column()
text_stack.add_row(text_logo)
text_stack.add_row("")
text_stack.add_row(status_info)

final_banner.add_row(text_stack, styled_orb)

def format_tool_call(tool_name: str, args: dict) -> Panel:
    """Formats a tool call into a sleek console block."""
    arg_str = json.dumps(args, indent=2)
    syntax = Syntax(arg_str, "json", theme="monokai", line_numbers=False, word_wrap=True)
    return Panel(
        syntax, 
        title=f"[bold yellow]⚙️ Executing Tool: {tool_name}[/bold yellow]", 
        border_style="yellow",
        expand=False
    )

def format_tool_result(result: str) -> Panel:
    """Formats raw tool output."""
    display_text = result if len(result) < 1500 else result[:1500] + "\n\n...[OUTPUT TRUNCATED FOR DISPLAY]..."
    syntax = Syntax(display_text, "bash", theme="ansi_dark", word_wrap=True)
    return Panel(
        syntax,
        title="[dim]↳ Tool Output[/dim]",
        border_style="bright_black",
        expand=False
    )

async def main():
    logger.info("="*60)
    logger.info("HYPERVISOR BOOT SEQUENCE INITIATED")
    logger.info("="*60)
    console.print(final_banner)
    
    with Status("[system]Initializing Autonomous Mesh...[/system]", spinner="dots", console=console):
        memory = MemorySaver()
        app = build_hypervisor_graph().compile(checkpointer=memory)
        await asyncio.sleep(1)
    
    console.print(f"[bold green]✓ Mesh Network Online. 10 Specialist Agents Loaded.[/bold green]")
    console.print(f"[bold green]✓ Episodic Memory Engine & Background Shell Management Active.[/bold green]")
    console.print("[dim]Type 'exit' to shutdown. Type '/reset' to start a new prompt with wiped memory.[/dim]\n")

    current_thread_id = str(uuid.uuid4())

    while True:
        try:
            user_input = console.input("\n[bold cyan]PROMPT > [/bold cyan]")
            if user_input.lower() in ["exit", "quit"]:
                console.print("[danger]Shutting down Hypervisor. Terminating background sessions...[/danger]")
                logger.info("[SHUTDOWN] User requested exit. Terminating Hypervisor.")
                break
            if not user_input.strip():
                continue

            if user_input.lower().strip() == "/reset":
                current_thread_id = str(uuid.uuid4())
                console.print(f"[warning]Memory Wiped. New Operation Thread Initialized: {current_thread_id[:8]}[/warning]")
                logger.info(f"[SESSION RESET] User initiated /reset. New thread ID: {current_thread_id}")
                continue

            logger.info(f"[HUMAN INPUT] Objective Received: {user_input}")
            logger.info("[STATE INIT] Initializing Hypervisor State with {HumanMessage} and active_agent: Selection_Agent")

            # Initial State Vector
            inputs = {
                "messages": [HumanMessage(content=user_input)],
                "sender": "User",
                "active_agent": "Selection_Agent"
            }

            console.print("\n[info]Engaging Hypervisor Mesh...[/info]\n")

            config = {
                "recursion_limit": 15000,
                "configurable": {"thread_id": current_thread_id}
            }
            
            status = Status("[magenta]Selection_Agent is analyzing objective...[/magenta]", spinner="bouncingBar", console=console)
            status.start()

            try:
                async for event in app.astream(inputs, config=config):
                    for node_name, state_update in event.items():
                        
                        # 1. Handle Memory Compression Node
                        if node_name == "Memory_Manager":
                            status.stop()
                            new_summary = state_update.get("episodic_summary", "")
                            console.print(Panel(
                                Markdown(new_summary),
                                title="[bold magenta]🧠 EPISODIC MEMORY COMPRESSED (CONTEXT SAVED)[/bold magenta]",
                                border_style="magenta"
                            ))
                            status.update("[magenta]Memory engine re-syncing context...[/magenta]")
                            status.start()
                            continue

                        # 2. Handle Tool Execution Node
                        if node_name == "call_tool":
                            status.stop()
                            messages = state_update.get("messages", [])
                            if messages and isinstance(messages[-1], ToolMessage):
                                tool_msg = messages[-1]
                                console.print(format_tool_result(tool_msg.content))

                                logger.info(f"[TOOL NODE] Executed tool '{tool_msg.name}'. Appended {{ToolMessage}} to State.")
                            
                            # Update status for the agent that receives the tool output
                            status.update(f"[cyan]Analyzing tool output...[/cyan]")
                            status.start()
                            continue

                        # 3. Handle Agent Nodes
                        if "messages" in state_update and state_update["messages"]:
                            last_msg = state_update["messages"][-1]
                            
                            # Stop the spinner to print
                            status.stop()
                            
                            # Assign colors based on agent role
                            color = "cyan"
                            if "Red" in node_name or "Replay" in node_name: color = "red"
                            elif "Blue" in node_name or "DFIR" in node_name: color = "blue"
                            elif "Selection" in node_name: color = "magenta"
                            elif "Reporter" in node_name: color = "green"
                            elif "Bug" in node_name: color = "yellow"

                            # If the agent wants to call a tool/handoff
                            if isinstance(last_msg, AIMessage) and last_msg.tool_calls:
                                # Print agent's reasoning if any exists before the tool call
                                if last_msg.content:
                                    console.print(Panel(
                                        Markdown(last_msg.content),
                                        title=f"[bold {color}]🤖 {node_name} (Thought Process)[/bold {color}]",
                                        border_style=color
                                    ))
                                
                                # Print the tool calls beautifully
                                for tcall in last_msg.tool_calls:
                                    console.print(format_tool_call(tcall["name"], tcall["args"]))
                                    
                                    # If it's a handoff, update status distinctly
                                    if tcall["name"].startswith("transfer_to_"):
                                        target = tcall["name"].replace("transfer_to_", "")
                                        status.update(f"[bold magenta]Routing context to {target.upper()}...[/bold magenta]")
                                    else:
                                        status.update(f"[yellow]Executing {tcall['name']}...[/yellow]")
                            
                            # If the agent just replied with text (End of chain or human interaction)
                            elif last_msg.content:
                                console.print(Panel(
                                    Markdown(last_msg.content),
                                    title=f"[bold {color}]🤖 {node_name}[/bold {color}]",
                                    border_style=color
                                ))
                                status.update(f"[cyan]{node_name} is thinking...[/cyan]")

                            # Restart status for the next cycle
                            status.start()

                status.stop()
                console.print("\n[bold green]✓ Execution Chain Completed.[/bold green]")
                logger.info("[EXECUTION COMPLETE] Graph traversal finished for current objective.")

            except Exception as graph_err:
                status.stop()
                # Instead of completely crashing, catch the graph execution error, display it, and allow the user to continue the session or pivot.
                console.print(f"\n[bold red]⚠️  AGENTIC FAULT RECOVERED:[/bold red] The LLM produced an invalid format, hallucinated a token, or exceeded context limits.")
                console.print(f"[dim]Technical Details: {graph_err}[/dim]")
                console.print("[yellow]The Hypervisor caught the crash. You can issue a new command to redirect the agents or check background sessions.[/yellow]")
                logger.error(f"[SYSTEM FAULT] Caught Graph Execution Error: {graph_err}")

        except (KeyboardInterrupt, asyncio.exceptions.CancelledError):
            status.stop()
            console.print("\n[danger]User Interrupt (Ctrl+C). Halting current execution chain...[/danger]")
            continue
        except Exception as e:
            status.stop()
            console.print(f"\n[danger]System Error Exception: {e}[/danger]")
            logger.error(f"[FATAL ERROR] System Exception: {e}")

if __name__ == "__main__":
    # Ensure Windows compatibility for asyncio if needed
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())