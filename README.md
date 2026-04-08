# Hypervisor: Autonomous Multi-Agent Mesh for Cybersecurity Orchestration

**Hypervisor** is a stateful, autonomous Agentic Mesh designed to execute complex cybersecurity kill-chains. Built on **LangGraph**, it moves beyond simple ReAct loops into a specialized mesh architecture capable of reasoning, pivoting, and managing massive forensic data without context collapse.

## The Engineering Challenge
Most AI Agents fail in real-world environments because of **Context Window Explosion** and **Cognitive Drift**. Hypervisor solves this using three architectural innovations:

### 1. Forensic Buffer Protocol
Instead of flooding the LLM with raw tool outputs (e.g., a 100MB Nmap scan or Tshark dump), Hypervisor intercepts large data, offloads it to a virtualized workspace, and provides the agent with an autonomous **Pagination & Grep Interface**. This keeps the context window lean and reasoning sharp.

### 2. Recursive Episodic Memory
Using a custom LangGraph reducer, Hypervisor monitors token usage. When a threshold is met, it triggers a **Summarization Cycle**—extracting critical IPs, credentials, and state—wiping the raw history and injecting a compressed "Technical Ledger" back into the system prompt.

### 3. Multi-Agent OODA Orchestration
A mesh of 10 specialized agents (RedTeam, BlueTeam, DFIR, Reverse Engineering) orchestrated by a **Mission Commander**. Each agent follows a strict **OODA (Observe, Orient, Decide, Act)** flow, preventing infinite loops and ensuring strategic pivoting.

## Technical Stack
- **Orchestration:** LangGraph (StateGraph)
- **Framework:** LangChain / Python
- **Environment:** Headless Kali Linux (Dockerized)
- **Data Parsing:** JSON-native conversion via `jc`

## Getting Started
1. Clone the repo.
2. Setup `.env` (Use `.env.example`).
3. Run `docker build -t hypervisor .`
4. Execute `python main.py`.
