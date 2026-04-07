from langchain_core.tools import tool
import shlex
import json
from invoke import Context, exceptions as invoke_exc
import jc

@tool
def network_scan_nmap(target: str, arguments: str = "-F"):
    """
    Performs a network scan using Nmap.
    Automatically parses the raw terminal output into STRUCTURED JSON for accurate agent reasoning.

    NOTE: If root is required and fails, retry with unprivileged flags (remove -O or -sS).
    Use generic_linux_command with background=True for long scans (like full port -p-).
    """
    safe_target = shlex.quote(target)
    if ";" in arguments or "|" in arguments:
        return "Security Error: Illegal characters in arguments."

    command = f"nmap {arguments} {safe_target}"
    #command = f"nmap {arguments} -oX - {safe_target}"
    
    try:
        ctx = Context()
        result = ctx.run(command, warn=True, hide=True, timeout=900, pty=False)
        
        if result.return_code != 0 and not result.stdout.strip():
            return f"Nmap Failed (Code {result.return_code}):\n{result.stderr}\nTip: Try removing privileged flags like -O or -sS if not running as root."
        
        # JSON CONVERTER LAYER (jc)
        try:
            parsed_data = jc.parse('nmap', result.stdout)
            return json.dumps(parsed_data, indent=2)
            
        except Exception as parse_err:
            return f"Nmap Output (Raw Fallback):\n{result.stdout}"
            
    except invoke_exc.CommandTimedOut:
        return "Error: Scan timed out after 15 Minutes. Please use execute_shell_command with background=True for this heavy scan."
    except Exception as e:
        return f"Execution Error: {e}"


@tool
def check_port_listener(port: int):
    """
    Checks if a local port is listening. Useful to verify if reverse shells bound correctly.
    Returns structured JSON data.
    """
    command = "netstat -tuln"
    try:
        ctx = Context()
        result = ctx.run(command, warn=True, hide=True, timeout=30, pty=False)
        
        try:
            parsed_data = jc.parse('netstat', result.stdout)
            
            target_port_str = str(port)
            listening_sockets =[
                entry for entry in parsed_data 
                if target_port_str in str(entry.get('local_port', '')) or target_port_str in str(entry.get('local_address', ''))
            ]
            
            if listening_sockets:
                return json.dumps(listening_sockets, indent=2)
            return f"No service found listening on port {port}"
            
        except Exception:
            fallback_cmd = f"netstat -tuln | grep :{port}"
            fallback_res = ctx.run(fallback_cmd, warn=True, hide=True)
            return fallback_res.stdout if fallback_res.stdout else f"No service found listening on port {port}"
            
    except Exception as e:
        return str(e)