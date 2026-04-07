import logging
import os
import subprocess
import uuid
import threading
import time
import glob
import json
from langchain_core.tools import tool
from config import WORKSPACE_DIR, INTERNAL_TARGET_RANGES
from invoke import Context, Responder, exceptions as invoke_exc
from fabric import Connection, Config
import jc
import binascii
import base64
import itertools
import math
from collections import Counter
import string
import re

logger = logging.getLogger("HypervisorTrace")
ABS_WORKSPACE = os.path.abspath(WORKSPACE_DIR)
ACTIVE_SESSIONS = {}
DYNAMIC_VHOSTS =[]

def sanitize_output(raw_text: str) -> str:
    """Removes null bytes and non-UTF-8 characters"""
    if not raw_text: return ""
    return raw_text.encode('utf-8', 'ignore').decode('utf-8').replace('\x00', '')

def handle_large_output(output: str, command: str, exit_code: int) -> str:
    """
    Core logic for Context Management. 
    Intercepts large outputs, writes them to disk, and returns a System Notice to the LLM.
    """
    if not output.strip():
        return f"Command executed successfully (No output). Exit code: {exit_code}"

    if len(output) <= 30000:
        return output

    file_id = uuid.uuid4().hex[:8]
    filepath = f"/tmp/agent_buffer_{file_id}.log"
    
    with open(filepath, "w", encoding="utf-8", errors="replace") as f:
        f.write(output)
    
    lines = output.splitlines()
    total_lines = len(lines)
    
    head = "\n".join(lines[:8])
    tail = "\n".join(lines[-5:]) if total_lines > 13 else ""
    
    notice = f"""⚠️ Output Truncated for Context Management
Command: {command}
Status: Completed (Exit Code: {exit_code})
Total Lines: {total_lines} | File Path: {filepath}

Output Preview (Head):
{head}

... [ {total_lines - 13} lines hidden ] ...

Output Preview (Tail):
{tail}

Action Required: The output is too large for the current window.
1. Use grep_file(file_path="{filepath}", pattern="<regex>", context_lines=3) to find specific data.
2. Use read_file_lines(file_path="{filepath}", start_line=X, end_line=Y) to paginate blocks.
"""
#3. Use wc_file(file_path="{filepath}") to verify data volume."""
    
    return notice

def is_safe_path(file_path: str) -> bool:
    """Ensures tools only read from the Workspace or temporary agent buffers."""
    if file_path.startswith("/tmp/agent_buffer_"):
        return True
    normalized_path = os.path.normpath(file_path).lstrip(os.sep)
    abs_requested = os.path.abspath(os.path.join(ABS_WORKSPACE, normalized_path))
    return abs_requested.startswith(ABS_WORKSPACE)

def get_sanitized_env(command: str) -> dict:
    """Creates an environment isolated from proxies if targeting local lab IPs."""
    global DYNAMIC_VHOSTS
    env = os.environ.copy()
    all_internal_targets = INTERNAL_TARGET_RANGES + DYNAMIC_VHOSTS
    is_internal = any(target in command for target in all_internal_targets)
    
    if is_internal:
        proxy_vars = [
            'http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY',
            'all_proxy', 'ALL_PROXY', 'no_proxy', 'NO_PROXY'
        ]
        for var in proxy_vars:
            env.pop(var, None)
        logger.info(f"[PROXY GUARD] Environment isolated for internal target.")
    return env

# JSON DATA CONVERTER
def try_jc_parse(command: str, raw_output: str) -> str:
    """Attempts to convert standard Linux terminal output into structured JSON."""
    base_cmd = command.strip().split()[0]
    jc_supported =["ls", "ps", "netstat", "ifconfig", "id", "uname", "env", "df", "mount", "whoami", "route"]
    
    if base_cmd in jc_supported:
        try:
            parsed = jc.parse(base_cmd, raw_output)
            return json.dumps(parsed, indent=2)
        except Exception:
            return raw_output
    return raw_output

# BACKGROUND SESSION MANAGER
class ShellSession:
    """Manages background shell processes to prevent the AI from hanging on interactive commands."""
    def __init__(self, command, cwd, env):
        self.id = str(uuid.uuid4())[:8]
        self.command = command
        self.process = subprocess.Popen(
            command, shell=True, cwd=cwd, env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, universal_newlines=True, errors='replace'
        )
        self.output_buffer =[]
        self.running = True
        self.reader_thread = threading.Thread(target=self._read_output, daemon=True)
        self.reader_thread.start()

    def _read_output(self):
        for line in iter(self.process.stdout.readline, ''):
            self.output_buffer.append(sanitize_output(line))
            if len(self.output_buffer) > 1000:
                self.output_buffer = self.output_buffer[-1000:]
        self.running = False

    def get_output(self):
        if not self.output_buffer and self.running:
            time.sleep(3) 

        out = "".join(self.output_buffer)
        self.output_buffer.clear()
        
        if not self.running and not out:
            return f"[Session {self.id} Terminated. Exit code: {self.process.poll()}]"
        
        return handle_large_output(out, self.command, self.process.poll() or 0)

    def send_input(self, text):
        if self.process.poll() is None:
            self.process.stdin.write(text + "\n")
            self.process.stdin.flush()
            return f"Input sent to session {self.id}."
        return f"Cannot send input. Session {self.id} is dead."

    def kill(self):
        self.process.terminate()
        self.running = False
        return f"Session {self.id} terminated."

@tool
def execute_shell_command(command: str = "", background: bool = False, session_action: str = "", session_id: str = ""):
    """Executes a Linux shell command or manages background sessions."""
    global ACTIVE_SESSIONS

    # --- SESSION MANAGEMENT LOGIC ---
    if session_action == "list":
        if not ACTIVE_SESSIONS: return "No active sessions."
        return "Active Sessions:\n" + "\n".join([f"- {sid}: {sess.command} (Running: {sess.process.poll() is None})" for sid, sess in ACTIVE_SESSIONS.items()])

    if session_action == "output":
        if session_id not in ACTIVE_SESSIONS: return f"Error: Session {session_id} not found."
        return ACTIVE_SESSIONS[session_id].get_output()

    if session_action == "send":
        if session_id not in ACTIVE_SESSIONS: return f"Error: Session {session_id} not found."
        return ACTIVE_SESSIONS[session_id].send_input(command)

    if session_action == "kill":
        if session_id not in ACTIVE_SESSIONS: return f"Error: Session {session_id} not found."
        res = ACTIVE_SESSIONS[session_id].kill()
        del ACTIVE_SESSIONS[session_id]
        return res

    # --- EXECUTION LOGIC ---
    if not command: return "Error: Command cannot be empty unless managing a session."

    # 1. ROE Guardrails
    forbidden =["rm -rf /", ":(){ :|:& };:", "mkfs"] 
    if any(f in command for f in forbidden):
        return "SECURITY ALERT: Command blocked by Hypervisor's Guardrails."
    
    if command.strip().startswith("ssh ") or command.strip().startswith("sshpass "):
        return (
            "SYSTEM ERROR: You are strictly forbidden from using 'ssh' or 'sshpass' "
            "via execute_shell_command. You MUST use the 'ssh_interactive_exec' tool "
            "to prevent terminal hanging and correctly handle sudo interactions."
        )
    
    execution_env = get_sanitized_env(command)

    if background:
        sess = ShellSession(command, ABS_WORKSPACE, execution_env)
        ACTIVE_SESSIONS[sess.id] = sess
        return f"Started background session. ID: {sess.id}. Use session_action='output' to read it."

    # INVOKE LOCAL EXECUTION LAYER WITH RESPONDERS
    try:
        ctx = Context()
        
        yes_responder = Responder(pattern=r"Are you sure you want to continue connecting \(yes/no/\[fingerprint\]\)\?", response="yes\n")
        general_y_responder = Responder(pattern=r"\[Y/n\]", response="y\n")

        with ctx.cd(ABS_WORKSPACE):
            result = ctx.run(
                command, 
                env=execution_env, 
                warn=True, 
                hide=True, 
                timeout=900, 
                watchers=[yes_responder, general_y_responder],
                pty=False
            )
        
        raw_output = sanitize_output(result.stdout + result.stderr)        
        parsed_output = try_jc_parse(command, raw_output)

        return handle_large_output(parsed_output, command, result.return_code)

    except invoke_exc.CommandTimedOut:
        return "Error: Command timed out after 15 Minutes. It likely trapped the console waiting for user input. If it requires long execution, run it with background=True."
    except Exception as e:
        return f"System Execution Error: {str(e)}"

@tool
def ssh_interactive_exec(target_ip: str, username: str, password: str, command: str, use_sudo: bool = False):
    """
    Executes a command via SSH with a PTY. Automatically handles sudo password prompts
    by injecting the provided password when requested by the remote system.
    """
    forbidden_ranges =["10.0.", "192.168.100."]
    if any(target_ip.startswith(r) for r in forbidden_ranges):
        return "🛑 SCOPE VIOLATION: SSH attempt blocked by Hypervisor's Guardrails."
    
    try:
        sudo_responder = Responder(pattern=r"\[sudo\] password for", response=f"{password}\n")
        generic_pass_responder = Responder(pattern=r"assword:", response=f"{password}\n")
        ssh_responder = Responder(pattern=r"Are you sure you want to continue connecting", response="yes\n")

        config = Config(overrides={'run': {'pty': True}, 'sudo': {'password': password}})
        conn = Connection(
            host=target_ip, 
            user=username, 
            connect_kwargs={"password": password, "timeout": 15}, 
            config=config
        )

        watchers =[sudo_responder, generic_pass_responder, ssh_responder]

        if use_sudo:
            result = conn.sudo(command, watchers=watchers, warn=True, hide=True, timeout=60)
        else:
            result = conn.run(command, watchers=watchers, warn=True, hide=True, timeout=60)

        raw_output = sanitize_output(result.stdout + result.stderr)
        parsed_output = try_jc_parse(command, raw_output)
        
        conn.close()

        return handle_large_output(parsed_output.strip(), f"ssh@{target_ip}: {command}", result.return_code)

    except invoke_exc.CommandTimedOut:
        return "SSH Error: Remote command timed out after 60 seconds."
    except Exception as e:
        return f"SSH Fabric Execution Failed: {str(e)}"

@tool
def execute_code(python_code: str):
    """Writes and executes Python code dynamically."""
    script_path = os.path.join(ABS_WORKSPACE, f"temp_script_{uuid.uuid4().hex[:6]}.py")
    try:
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(python_code)
        
        result = subprocess.run(
            ["python3", script_path], capture_output=True, text=True, cwd=ABS_WORKSPACE, timeout=300, errors='replace'
        )
        output = sanitize_output(result.stdout + result.stderr)
        
        # Uses the new Context Management Strategy
        return handle_large_output(output, "Custom Python Script", result.returncode)
    except Exception as e:
        return f"Python Execution Error: {str(e)}"
    finally:
        if os.path.exists(script_path):
            os.remove(script_path)

@tool
def map_vhost(ip_address: str, hostname: str):
    """
    CRITICAL FOR WEB RECON: Maps a discovered Virtual Host (domain name) to an IP address.
    This writes to /etc/hosts so tools can resolve the domain. Use this IMMEDIATELY if you 
    discover a domain name (like 'earth.local' or 'terratest.earth.local').
    """
    global DYNAMIC_VHOSTS
    
    try:
        # 1. Add to the proxy bypass list so tools can hit it directly without timing out
        if hostname not in DYNAMIC_VHOSTS:
            DYNAMIC_VHOSTS.append(hostname)
            
        # 2. Write to the container's /etc/hosts file securely
        with open("/etc/hosts", "r") as f:
            hosts_content = f.read()
            
        entry = f"{ip_address}\t{hostname}\n"
        if entry not in hosts_content:
            with open("/etc/hosts", "a") as f:
                f.write(entry)
                
        return f"SUCCESS: Hostname '{hostname}' mapped to IP '{ip_address}'. You MUST now use http://{hostname} for your web tools instead of the raw IP."
        
    except Exception as e:
        return f"System Error mapping VHost: {str(e)}"

@tool
def analyze_entropy(data_string: str):
    """
    CRITICAL RECON TOOL: Calculates the Shannon Entropy and identifies Hash Signatures.
    Determines if a string is a Hash (needs cracking), Encrypted (needs crypto_analyzer), 
    or Encoded (Base64/Hex). Use immediately on unexplained, random-looking text.
    Use this immediately when you find unexplained, random-looking text.
    """
    # Clean the string of whitespace and newlines
    data_string = ''.join(data_string.split())
    if not data_string:
        return "Error: Empty string provided."

    report = f"--- DATA ANALYSIS REPORT ---\n"
    report += f"Length: {len(data_string)} characters\n"

    # 1. HASH SIGNATURE DETECTION
    hash_signatures = {
        "MD5 or NTLM": r"^[a-fA-F0-9]{32}$",
        "SHA-1": r"^[a-fA-F0-9]{40}$",
        "SHA-256": r"^[a-fA-F0-9]{64}$",
        "SHA-512": r"^[a-fA-F0-9]{128}$",
        "Bcrypt": r"^\$2[aby]\$[0-9]{2}\$[./A-Za-z0-9]{53}$",
        "MD5-Crypt (Linux)": r"^\$1\$[./A-Za-z0-9]{1,8}\$[./A-Za-z0-9]{22}$",
        "SHA256-Crypt (Linux)": r"^\$5\$[./A-Za-z0-9]{1,16}\$[./A-Za-z0-9]{43}$",
        "SHA512-Crypt (Linux)": r"^\$6\$[./A-Za-z0-9]{1,16}\$[./A-Za-z0-9]{86}$"
    }

    identified_hashes =[]
    for hash_name, pattern in hash_signatures.items():
        if re.match(pattern, data_string):
            identified_hashes.append(hash_name)

    if identified_hashes:
        report += f"Format Detected: PASSWORD HASH ({', '.join(identified_hashes)})\n\n"
        report += "🛑 SYSTEM DIRECTIVE: HASHING IS ONE-WAY. Do NOT use `crypto_analyzer`.\n"
        report += "ACTION REQUIRED: Save this string to a file (e.g., `hash.txt`) and use `execute_shell_command` to run `john --wordlist=/usr/share/wordlists/rockyou.txt hash.txt` to crack it."
        return report
    
    # 1. Calculate Shannon Entropy
    p, lns = Counter(data_string), float(len(data_string))
    entropy = -sum(count/lns * math.log2(count/lns) for count in p.values())
    report += f"Shannon Entropy: {entropy:.3f} (Scale: 0.0 - 8.0)\n"

    # 2. Heuristic Checks
    is_hex = all(c in string.hexdigits for c in data_string) and len(data_string) % 2 == 0
    is_b64 = data_string.endswith('=') or (all(c.isalnum() or c in '+/' for c in data_string) and len(data_string) > 20)

    # # 3. Decision Matrix
    # report = f"--- ENTROPY ANALYSIS REPORT ---\n"
    # report += f"Length: {len(data_string)} characters\n"
    # report += f"Shannon Entropy: {entropy:.3f} (Scale: 0.0 - 8.0)\n\n"

    is_candidate = False
    if is_hex:
        report += "Format Detected: HEXADECIMAL CIPHERTEXT / ENCODING\n"
        is_candidate = True
    elif is_b64 and entropy > 4.0:
        report += "Format Detected: BASE64 CIPHERTEXT / ENCODING\n"
        is_candidate = True
    elif entropy > 5.0:
        report += "Format Detected: HIGH ENTROPY (Likely Encrypted/Compressed)\n"
        is_candidate = True
    else:
        report += "Format Detected: PLAINTEXT / LOW ENTROPY\n"

    if is_candidate:
        report += "\n🛑 SYSTEM DIRECTIVE: is_cryptographic_candidate = TRUE.\n"
        report += "ACTION REQUIRED: This is Two-Way Encryption. Search your asset ledger for a Potential Key (e.g., a text file or secret string). Once found, execute the `crypto_analyzer` tool."
    else:
        report += "\n🟢 SYSTEM DIRECTIVE: is_cryptographic_candidate = FALSE.\n"
        report += "Proceed with standard enumeration."

    return report

@tool
def crypto_analyzer(ciphertext: str, key_string: str, algorithm: str = "xor", is_hex: bool = True):
    """
    The 'CyberChef' Tool. Decrypts a ciphertext using a provided key.
    Args:
        ciphertext: The encrypted string (e.g., "37090b5903...").
        key_string: The plaintext key (e.g., content of testdata.txt).
        algorithm: Currently supports "xor".
        is_hex: Set to True if ciphertext is hex, False if Base64.
    """
    try:
        # 1. Clean inputs
        ciphertext = ''.join(ciphertext.split())
        key_string = key_string.strip()
        
        # 2. Decode Ciphertext
        if is_hex:
            cipher_bytes = binascii.unhexlify(ciphertext)
        else:
            cipher_bytes = base64.b64decode(ciphertext)
            
        key_bytes = key_string.encode('utf-8')
        
        if algorithm.lower() == "xor":
            # --- LENGTH-AGNOSTIC XOR LOGIC ---
            if len(key_bytes) > len(cipher_bytes):
                working_key = key_bytes[:len(cipher_bytes)]
            else:
                working_key = (key_bytes * (len(cipher_bytes) // len(key_bytes) + 1))[:len(cipher_bytes)]
            
            decrypted_bytes = bytes([a ^ b for a, b in zip(cipher_bytes, working_key)])
            # -------------------------------------------------
            
            try:
                plaintext = decrypted_bytes.decode('utf-8')
                return f"✅ SUCCESS: Decrypted Plaintext:\n{plaintext}"
            except UnicodeDecodeError:
                return f"⚠️ PARTIAL SUCCESS (Non-UTF8 chars found - wrong key?):\n{repr(decrypted_bytes)}"
        else:
            return f"Error: Algorithm '{algorithm}' not supported."
            
    except Exception as e:
        return f"Cryptographic Analysis Failed: {str(e)}"
@tool
def grep_file(file_path: str, pattern: str, context_lines: int = 3):
    """
    Searches for a regex pattern in a file and returns matching lines with context.
    Crucial for analyzing large truncated logs or buffer files.
    
    Returns line numbers so you can follow up with read_file_lines for pagination.
    """
    # 1. Security Check
    if not is_safe_path(file_path):
        return "Error: Access denied. Path is outside allowed workspace or buffers."

    # 2. Consistent Path Resolution
    if file_path.startswith("/tmp/agent_buffer_"):
        full_path = file_path
    else:
        normalized = os.path.normpath(file_path).lstrip(os.sep)
        full_path = os.path.abspath(os.path.join(ABS_WORKSPACE, normalized))
    
    if not os.path.exists(full_path):
        return f"Error: File '{file_path}' not found."
    
    try:
        cmd = ["grep", "-a","-i", "-E", "-n", "-C", str(context_lines), pattern, full_path]
        
        res = subprocess.run(cmd, capture_output=True, text=True, errors='replace')
        
        if res.returncode == 1:
            return (
                f"No matches found for '{pattern}' in {file_path}. "
                "HINT: Try a more generic keyword, check for case sensitivity, "
                "or use 'read_file_lines' to manually inspect a chunk of the file."
            )
        
        if res.returncode >= 2:
            return (
                f"SYSTEM ERROR: Grep failed (Code {res.returncode}). "
                f"The pattern '{pattern}' might be a malformed regex. "
                f"Details: {res.stderr.strip()}"
            )
        
        output = sanitize_output(res.stdout)
        
        return handle_large_output(output, f"grep '{pattern}' on {file_path}", res.returncode)
        
    except Exception as e:
        return f"Grep execution error: {str(e)}"

@tool
def read_file_lines(file_path: str, start_line: int, end_line: int):
    """
    Reads a specific range of lines from a file (1-based indexing).
    Use this to 'page' through large files or buffer logs identified by wc_file.
    
    Example: To read the first 100 lines, use start_line=1, end_line=100.
    """
    # 1. Security Check
    if not is_safe_path(file_path):
        return "Error: Access denied. Path is outside allowed workspace or buffers."

    # 2. Consistent Path Resolution
    if file_path.startswith("/tmp/agent_buffer_"):
        full_path = file_path
    else:
        normalized = os.path.normpath(file_path).lstrip(os.sep)
        full_path = os.path.abspath(os.path.join(ABS_WORKSPACE, normalized))
        
    if not os.path.exists(full_path):
        return f"Error: File '{file_path}' not found."
        
    try:
        lines = []
        # 3. Memory-efficient reading (Streaming line by line)
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                current_line_num = i + 1
                if current_line_num >= start_line:
                    lines.append(line.rstrip("\n"))
                if current_line_num >= end_line:
                    break
                    
        if not lines:
            return f"No lines found in range {start_line}-{end_line} for file {file_path}."

        content = "\n".join(lines)
        summary = f"--- Reading {file_path} (Lines {start_line} to {start_line + len(lines) - 1}) ---\n"
        
        # 4. Recursive protection:
        return handle_large_output(summary + content, f"read_file_lines {start_line}-{end_line}", 0)
        
    except Exception as e:
        return f"Error reading file lines: {str(e)}"

@tool
def wc_file(file_path: str):
    """
    Returns the total number of lines, words, and characters in a file.
    Use this to determine the 'end_line' when using read_file_lines for pagination.
    """
    # 1. Security Check
    if not is_safe_path(file_path):
        return "Error: Access denied. Path is outside allowed workspace or buffers."

    # 2. Consistent Path Resolution
    if file_path.startswith("/tmp/agent_buffer_"):
        full_path = file_path
    else:
        # Resolve relative to workspace
        normalized = os.path.normpath(file_path).lstrip(os.sep)
        full_path = os.path.abspath(os.path.join(ABS_WORKSPACE, normalized))
    
    if not os.path.exists(full_path):
        return f"Error: File '{file_path}' not found."
    
    try:
        res = subprocess.run(["wc", full_path], capture_output=True, text=True, errors='replace')
        
        if res.returncode != 0:
            return f"Error executing wc: {res.stderr}"

        parts = res.stdout.strip().split()
        if len(parts) >= 3:
            lines, words, chars = parts[0], parts[1], parts[2]
            return f"File: {file_path}\nLines: {lines}\nWords: {words}\nBytes: {chars}"
            
        return sanitize_output(res.stdout.strip())
        
    except Exception as e:
        return f"Error counting file: {str(e)}"

@tool
def list_files(path: str = "."):
    """
    Lists files and directories within the workspace.
    Supports subdirectories (e.g., 'scans/nmap').
    
    Returns: A formatted list showing [DIR] or [FILE] with sizes.
    """
    # 1. Security Check
    if not is_safe_path(path):
        return "Error: Access denied. You can only list files within the workspace."

    # 2. Resolve Path
    normalized = os.path.normpath(path).lstrip(os.sep)
    if not normalized or normalized == "":
        normalized = "."
        
    full_path = os.path.abspath(os.path.join(ABS_WORKSPACE, normalized))

    try:
        if not os.path.exists(full_path):
            return f"Error: Path '{path}' does not exist."

        if not os.path.isdir(full_path):
            return f"Error: '{path}' is a file, not a directory. Use read_file to view it."

        items = os.listdir(full_path)
        if not items:
            return f"The directory '{path}' is empty."

        # 3. Enriched Output (Helping the agent decide what to do next)
        output = [f"Contents of directory '{path}':"]
        for item in sorted(items):
            item_path = os.path.join(full_path, item)
            if os.path.isdir(item_path):
                output.append(f"  [DIR]  {item}/")
            else:
                size = os.path.getsize(item_path)
                # Display size in KB for readability if larger than 1KB
                size_str = f"{size} bytes" if size < 1024 else f"{size/1024:.1f} KB"
                output.append(f"  [FILE] {item} ({size_str})")

        return "\n".join(output)

    except Exception as e:
        return f"Error listing directory: {str(e)}"

@tool
def read_file(file_path: str):
    """
    Reads the full content of a file.
    Use this for:
    1. Files you created in the workspace (including subdirectories).
    2. Buffer files from truncated outputs (e.g., /tmp/agent_buffer_...).
    
    Note: If the file is extremely large, this tool will trigger the truncation protocol.
    """
    # 1. Using the centralized safety checker
    if not is_safe_path(file_path):
        return "Error: Access denied. You can only read files within the workspace or agent buffers."

    # 2. Resolving the actual path
    if file_path.startswith("/tmp/agent_buffer_"):
        full_path = file_path
    else:
        # ing relative to workspace, but allow subdirectories
        normalized = os.path.normpath(file_path).lstrip(os.sep)
        full_path = os.path.abspath(os.path.join(ABS_WORKSPACE, normalized))

    try:
        if not os.path.exists(full_path):
            return f"Error: File '{file_path}' not found."

        if os.path.isdir(full_path):
            return f"Error: '{file_path}' is a directory. Use list_files to see contents."

        with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
            # 3. Pass through handle_large_output to prevent context blowout
            return handle_large_output(content, f"read_file {file_path}", 0)
            
    except Exception as e:
        return f"Error reading file: {str(e)}"

@tool
def write_file(file_path: str, content: str):
    """
    Writes content to a file. 
    Supports writing to subdirectories within the workspace.
    
    CRITICAL: Do not attempt to write to system directories. 
    Use relative paths like 'findings.txt' or 'recon/notes.log'.
    """
    # 1. Block writing to agent buffers (buffers are read-only logs)
    if file_path.startswith("/tmp/agent_buffer_"):
        return "Error: Agent buffers are read-only system logs. Write to the workspace instead."

    # 2. Useing the centralized safety checker
    if not is_safe_path(file_path):
        return "Error: Access denied. You can only write files within the workspace."

    # 3. Resolve the path safely
    normalized = os.path.normpath(file_path).lstrip(os.sep)
    full_path = os.path.abspath(os.path.join(ABS_WORKSPACE, normalized))

    try:
        # 4. Automatically create subdirectories if they don't exist
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
            
        relative_path = os.path.relpath(full_path, ABS_WORKSPACE)
        return f"SUCCESS: File saved to {relative_path}"
        
    except Exception as e:
        return f"Error writing file: {str(e)}"
    
@tool
def submit_final_report(executive_summary: str, threat_score: int, remediation_command: str, final_html_report: str = ""):
    """
    CRITICAL: This is the final tool in the kill chain.
    Calling this triggers the end of the engagement, kills all background processes,
    and cleans up temporary buffers.
    """
    global ACTIVE_SESSIONS

    # 1. PROCESS HYGIENE: Kill any orphaned background sessions
    if ACTIVE_SESSIONS:
        for session_id in list(ACTIVE_SESSIONS.keys()):
            try:
                ACTIVE_SESSIONS[session_id].kill()
                del ACTIVE_SESSIONS[session_id]
            except:
                pass

    # 2. FILE HYGIENE: Cleanup large output buffers
    buffer_files = glob.glob("/tmp/agent_buffer_*.log")
    for b_file in buffer_files:
        try:
            os.remove(b_file)
        except:
            pass

    # 3. PERSISTENCE: Save the final report content if provided
    if final_html_report:
        try:
            report_path = os.path.join(ABS_WORKSPACE, "final_assessment_report.html")
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(final_html_report)
        except:
            pass

    # 4. SIGNAL THE ROUTER: This exact string triggers 'END' in core/graph.py
    report = (
        f"### 🛑 ENGAGEMENT COMPLETE 🛑\n\n"
        f"**Threat Score:** {threat_score}/10\n\n"
        f"**Executive Summary:**\n{executive_summary}\n\n"
        f"**Proposed Remediation:**\n`{remediation_command}`\n\n"
        f"**Note:** All background sessions terminated. Large buffers purged."
    )
    return report

CORE_TOOLS =[
    execute_shell_command, execute_code, 
    list_files, read_file, write_file, 
    grep_file, read_file_lines, wc_file,
    ssh_interactive_exec, map_vhost, analyze_entropy, crypto_analyzer,
    submit_final_report
]