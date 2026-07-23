# src/logger.py - Système de logs professionnel

import time

RESET = "\033[0m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
WHITE = "\033[37m"
BOLD = "\033[1m"

def _timestamp():
    return time.strftime("%H:%M:%S")

def info(msg):
    print(f"{CYAN}[{_timestamp()}] [INFO]{RESET} {msg}")

def init(msg):
    print(f"{MAGENTA}[{_timestamp()}] [INIT]{RESET} {msg}")

def send(msg):
    print(f"{BLUE}[{_timestamp()}] [SEND]{RESET} {msg}")

def recv(msg):
    print(f"{CYAN}[{_timestamp()}] [RECV]{RESET} {msg}")

def ok(msg):
    print(f"{GREEN}[{_timestamp()}] [OK]{RESET} {msg}")

def err(msg):
    print(f"{RED}[{_timestamp()}] [ERR]{RESET} {msg}")

def warn(msg):
    print(f"{YELLOW}[{_timestamp()}] [WARN]{RESET} {msg}")

def db(msg):
    print(f"{MAGENTA}[{_timestamp()}] [DB]{RESET} {msg}")

def api(msg):
    print(f"{BLUE}[{_timestamp()}] [API]{RESET} {msg}")

def sep(char="-", length=60):
    print(f"{WHITE}{char * length}{RESET}")
