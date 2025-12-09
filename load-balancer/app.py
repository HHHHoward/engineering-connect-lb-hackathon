from flask import Flask, request, Response
import logging
from logging.handlers import RotatingFileHandler
import os
import requests
import threading
import time
import yaml

app = Flask(__name__)

LISTENER_PORT = int(os.getenv("LISTENER_PORT", 80))
CONNECTION_TIMEOUT = int(os.getenv("CONNECTION_TIMEOUT", 2))
LOAD_BALANCING_ALGORITHM = os.getenv("LOAD_BALANCING_ALGORITHM", "ROUND_ROBIN")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
CONFIG_FILE = os.getenv("CONFIG_FILE", "config.yml")

current = 0

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format=os.getenv("LOG_FORMAT", "%(asctime)s - %(levelname)s - %(message)s"),
    handlers=[
        logging.StreamHandler(),  # Log to console
        logging.FileHandler(os.getenv("LOG_FILE", "load_balancer.log"))  # Log to file
    ]
)

logger = logging.getLogger(__name__)

file_handler = RotatingFileHandler("load_balancer.log", maxBytes=5 * 1024 * 1024, backupCount=3)
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(file_handler)

def load_config():
    logger.info(f"Loading configuration from {CONFIG_FILE}")
    try:
        with open("config.yml", "r") as file:
            return yaml.safe_load(file)

    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        return {"target_groups": [], "listeners": []}

config = load_config()

LISTENERS = config["listeners"]

logger.debug(f"Listeners loaded: {LISTENERS}")

TARGET_GROUPS = {
    group["name"]: [
        f"http://{target['hostname']}:{target['port']}"
        for target in group["targets"]
    ] for group in config["target_groups"]
}

logger.debug(f"Target Groups loaded: {TARGET_GROUPS}")

# ---------------------------
#  ROUND ROBIN SERVER PICKER
# ---------------------------
def get_next_server(target_group_name):
    global current
    if target_group_name not in TARGET_GROUPS:
        logger.warning(f"Target group {target_group_name} not found.")
        return None
    
    healthy_servers = TARGET_GROUPS[target_group_name]
    if not healthy_servers:
        logger.warning(f"No healthy servers in target group '{target_group_name}'.")
        return None
    
    server = healthy_servers[current]
    logger.info(f"Selected server {server} from target group '{target_group_name}'.")
    current = (current + 1) % len(healthy_servers)
    return server


# ---------------------------
#        HEALTH CHECKER
# ---------------------------
def check_server(server):
    """Send a GET / request; healthy if status < 400."""
    try:
        r = requests.get(server, timeout=1)
        return r.status_code < 400
    except Exception:
        return False


# def health_check_loop():
#     """Background thread that checks every server every 3 seconds."""
#     global HEALTHY_SERVERS

#     while True:
#         new_healthy = []

#         for server in SERVERS:
#             if check_server(server):
#                 new_healthy.append(server)

#         HEALTHY_SERVERS = new_healthy

#         print("Health check:", HEALTHY_SERVERS)
#         time.sleep(3)


# # Start checker thread
# threading.Thread(target=health_check_loop, daemon=True).start()


# ---------------------------
#          PROXY
# ---------------------------
@app.route("/", defaults={"subpath": ""}, methods=["GET", "POST"])
@app.route("/<path:subpath>", methods=["GET", "POST"])
def proxy(subpath):
    full_path = f"/{subpath}"
    # path = request.path
    listener = next((l for l in LISTENERS if full_path.startswith(l["path_prefix"])), None)
    
    logger.debug(f"Incoming request path: {full_path}")
    if not listener:
        logger.warning(f"No matching listener found for path '{full_path}'")
        return {"error": f"No matching listener found for path '{full_path}'"}, 404

    logger.debug(f"Matched listener: {listener}")

    target_group = listener["target_group"]
    target = get_next_server(target_group)

    if not target:
        logger.error(f"No healthy backend servers available for target group '{target_group}'")
        return {"error": "No healthy backend servers available"}, 503

    try:
        logger.debug(f"Forwarding request to {target}{full_path}")        
        url = target + full_path
    
        if "path_rewrite" in listener:
            logger.debug(f"Rewriting path from '{full_path}' to '{url.replace(listener['path_prefix'], listener['path_rewrite'])}'")
            url = url.replace(listener["path_prefix"], listener["path_rewrite"], 1)

        resp = requests.request(
            method=request.method,
            url=url,
            headers={k: v for k, v in request.headers if k != 'Host'},
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=False,
            timeout=CONNECTION_TIMEOUT
        )

        logger.debug(f"Request to {target} completed with status code {resp.status_code}")
        return Response(resp.content, resp.status_code, resp.headers.items())

    except requests.exceptions.RequestException as e:
        logger.error(f"Request to {target} failed: {e}")
        return {"error": f"Server {target} unreachable"}, 502

@app.route("/config", methods=["GET"])
def get_targets():
    """Return the list of backend servers and their health status."""
    return {
        "listeners": LISTENERS,
        "target_groups": TARGET_GROUPS
    }

if __name__ == "__main__":
    print(f"Load balancer running on port {LISTENER_PORT}...")
    app.run(host='0.0.0.0', port=LISTENER_PORT, debug=False)