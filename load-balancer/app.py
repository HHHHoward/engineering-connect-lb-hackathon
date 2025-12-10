from flask import Flask, request, Response
import logging
from logging.handlers import RotatingFileHandler
import os
import requests
from threading import Lock
import time
import yaml

app = Flask(__name__)

LISTENER_PORT = int(os.getenv("LISTENER_PORT", 80))
CONNECTION_TIMEOUT = int(os.getenv("CONNECTION_TIMEOUT", 2))
LOAD_BALANCING_ALGORITHM = os.getenv("LOAD_BALANCING_ALGORITHM", "Sticky")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
CONFIG_FILE = os.getenv("CONFIG_FILE", "config.yml")
WEIGHT = os.getenv("Weight",[3,1,2])
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
print("test12111")

TARGET_GROUPS = {
    group["name"]: [
        f"http://{target['hostname']}:{target['port']}"
        for target in group["targets"]
    ] for group in config["target_groups"]
}

logger.debug(f"Target Groups loaded: {TARGET_GROUPS}")

def cleanup_expired_sessions():
    current_time = time.time() *1000
    expired_clients = [ client_id for client_id, session in STICKY_SESSIONS.items() if session['expires_at'] < current_time]
    for client_id in expired_clients:
        logger.info(f"Session expired for client {client_id}, removing from sticky map")
        del STICKY_SESSIONS[client_id]
    return len(expired_clients)

# ---------------------------
#  ROUND ROBIN SERVER PICKER
# ---------------------------

def get_next_server(target_group_name):
    match LOAD_BALANCING_ALGORITHM:
      case "Round Robin":
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
#  WEIGHTED SERVER PICKER
# ---------------------------
      case "Weighted":
        global current
        ## get an array for the weight of 3 backends
        weight = [config["Algorithom"][0]["weight"]["backend1"],config["Algorithom"][0]["weight"]["backend2"],config["Algorithom"][0]["weight"]["backend3"]]
        
        if target_group_name not in TARGET_GROUPS:
            logger.warning(f"Target group {target_group_name} not found.")
            return None
        
        healthy_servers = TARGET_GROUPS[target_group_name]
        if not healthy_servers:
            logger.warning(f"No healthy servers in target group '{target_group_name}'.")
            return None
        
        ##repeat the backend for the weighted times in the target group
        server_weight_assigned = [i for i, count in zip(healthy_servers, weight) for _ in range(count)] 
        ##server = healthy_servers[current]
        ##logger.info(f"Selected server {server} from target group '{target_group_name}'.")
        ##current = (current + 1) % len(healthy_servers)
        server = server_weight_assigned[current]
        logger.info(f"Selected server {server} from target group '{target_group_name}'.")
        current = (current + 1) % len(healthy_servers)
        return server

# ---------------------------
#  STICKY SERVER PICKER
# ---------------------------
      case "Sticky":
        global STICKY_SESSIONS, STICKY_COUNTERS, STICKY_LOCK

        if 'STICKY_SESSIONS' not in globals():
            STICKY_SESSIONS = {} 

        if 'STICKY_COUNTERS' not in globals():
            STICKY_COUNTERS = {}  

        if 'STICKY_LOCK' not in globals():
            STICKY_LOCK = Lock()
        
        with STICKY_LOCK:
            cleanup_expired_sessions()
            
            if target_group_name not in TARGET_GROUPS:
                logger.warning(f"Target group {target_group_name} not found.")
                return None
            
            healthy_servers = TARGET_GROUPS[target_group_name]
            if not healthy_servers:
                logger.warning(f"No healthy servers in target group '{target_group_name}'.")
                return None

            client_id = request.remote_addr
            if not client_id:
                logger.warning(f"Sticky algorithm requires client IP address")
                return None

            session_ttl = None
            for tg in config.get("target_groups", []):
                if tg.get("name") == target_group_name:
                    session_ttl = tg.get("session_ttl")
                    break
            
            if session_ttl is None:
                logger.warning(f"No session_ttl configured for target group '{target_group_name}'")
                return None
            
            current_time = time.time() * 1000  # Convert to milliseconds
            
            if client_id in STICKY_SESSIONS:
                session = STICKY_SESSIONS[client_id]

                if session['target_group'] != target_group_name:
                    logger.info(f"Client {client_id} switching target groups, creating new session")
                    del STICKY_SESSIONS[client_id]

                elif session['expires_at'] < current_time:
                    logger.info(f"Session expired for client {client_id}, creating new session")
                    del STICKY_SESSIONS[client_id]

                elif session['server'] not in healthy_servers:
                    logger.warning(f"Assigned server {session['server']} is no longer healthy for client {client_id}, creating new session")
                    del STICKY_SESSIONS[client_id]
                else:
                    logger.info(f"Returning sticky server {session['server']} for client {client_id} (expires in {int((session['expires_at'] - current_time) / 1000)}s)")
                    return session['server']

            if target_group_name not in STICKY_COUNTERS:
                STICKY_COUNTERS[target_group_name] = 0

            counter = STICKY_COUNTERS[target_group_name]
            server = healthy_servers[counter % len(healthy_servers)]
            STICKY_COUNTERS[target_group_name] = (counter + 1) % len(healthy_servers)

            expires_at = current_time + session_ttl
            STICKY_SESSIONS[client_id] = {
                'server': server,
                'expires_at': expires_at,
                'target_group': target_group_name
            }
            
            logger.info(f"Created new session for client {client_id} -> server {server} in target group '{target_group_name}' (TTL: {session_ttl}ms)")
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
