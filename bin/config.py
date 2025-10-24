SERVER_IP      = "192.168.86.72"
RESOLVER_PORT  = 8094
CC_PORT        = 5589

def resolver_base():
    return f"http://{SERVER_IP}:{RESOLVER_PORT}"

def cc_base():
    # ChromeCapture schema
    return f"chrome://{SERVER_IP}:{CC_PORT}/stream?url="
