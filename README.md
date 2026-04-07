# Hypervisor: Autonomous Multi-Agent Mesh for Cybersecurity Orchestration

**Hypervisor** is a stateful, autonomous Agentic Mesh designed to execute complex cybersecurity kill-chains. Built on **LangGraph**, it moves beyond simple ReAct loops into a specialized mesh architecture capable of reasoning, pivoting, and managing massive forensic data without context collapse.

## 🚀 The Engineering Challenge
Most AI Agents fail in real-world environments because of **Context Window Explosion** and **Cognitive Drift**. Hypervisor solves this using three architectural innovations:

### 1. Forensic Buffer Protocol
Instead of flooding the LLM with raw tool outputs (e.g., a 100MB Nmap scan or Tshark dump), Hypervisor intercepts large data, offloads it to a virtualized workspace, and provides the agent with an autonomous **Pagination & Grep Interface**. This keeps the context window lean and reasoning sharp.

### 2. Recursive Episodic Memory
Using a custom LangGraph reducer, Hypervisor monitors token usage. When a threshold is met, it triggers a **Summarization Cycle**—extracting critical IPs, credentials, and state—wiping the raw history and injecting a compressed "Technical Ledger" back into the system prompt.

### 3. Multi-Agent OODA Orchestration
A mesh of 10 specialized agents (RedTeam, BlueTeam, DFIR, Reverse Engineering) orchestrated by a **Mission Commander**. Each agent follows a strict **OODA (Observe, Orient, Decide, Act)** flow, preventing infinite loops and ensuring strategic pivoting.

## 🛠️ Technical Stack
- **Orchestration:** LangGraph (StateGraph)
- **Framework:** LangChain / Python
- **Environment:** Headless Kali Linux (Dockerized)
- **Data Parsing:** JSON-native conversion via `jc`

## 🤖 The Mesh: Agent Registry
Hypervisor utilizes a multi-agent routing topology. The Selection Agent acts as the router, delegating execution to isolated domain experts.
Agent Persona	Specialty Domain	Tooling Arsenal
- Selection_Agent	Strategic routing and campaign design.	Routing Logic Only
- Network_Analyzer	Reconnaissance and High Value Target (HVT) identification.	nmap, JSON port evaluation
- Bug_Bounter	Web application fuzzing, VHost mapping, and logic bypass.	Advanced HTTP, OSINT
- RedTeam_Agent	Exploitation, Privilege Escalation, and Shell acquisition.	SUID tracing, SSH Fabric
- BlueTeam_Agent	Precision remediation, configuration auditing, and hardening.	Zero-disruption patching
- DFIR_Agent	Forensic timeline reconstruction and IOC extraction.	Massive log pagination
- Reverse_Engineering	Headless binary dissection and malware static analysis.	r2pipe, Python instrumentation
- Memory_Analysis	Runtime secrets extraction and process hooking.	Headless gdb, frida
- Replay_Attack	PCAP analysis, session hijacking, and wire manipulation.	Headless tshark filtering
- Reporter	Aggregates findings into definitive HTML security assessments.	Report Synthesis

## 🏁 Getting Started
1. Clone the repo.
2. Setup `.env` (Use `.env.example`).
3. Run `docker build -t hypervisor .`
4. Execute `python main.py`.
