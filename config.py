import os
from dotenv import load_dotenv
load_dotenv()

MODEL_PLANNER = os.getenv("MODEL_PLANNER")
MODEL_EXECUTOR = os.getenv("MODEL_EXECUTOR")
LLM_BASE_URL = os.getenv("LLM_BASE_URL")
LLM_API_KEY = os.getenv("LLM_API_KEY")
INTERNAL_TARGET_RANGES =["192.168.", "10.0.", "172.16.", "localhost", "127.0.0.1"]

# Sandbox Configuration
ALLOW_DANGEROUS_COMMANDS = False 
WORKSPACE_DIR = "./workspace"

if not os.path.exists(WORKSPACE_DIR):
    os.makedirs(WORKSPACE_DIR)