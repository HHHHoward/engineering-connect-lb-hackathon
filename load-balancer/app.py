from flask import Flask, request, Response
import logging
from logging.handlers import RotatingFileHandler
import os
import requests
import socket
import threading
import time
import yaml

app = Flask(__name__)

CONFIG_FILE = os.getenv("CONFIG_FILE", "config.yml")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

LISTENER_PORT = int(os.getenv("LISTENER_PORT", 80))
CONNECTION_TIMEOUT = int(os.getenv("CONNECTION_TIMEOUT", 2))
LOAD_BALANCING_ALGORITHM = os.getenv("LOAD_BALANCING_ALGORITHM", "ROUND_ROBIN").upper()

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
    logger.debug(f"Loading configuration from {CONFIG_FILE}")
    try:
        with open("config.yml", "r") as file:
            return yaml.safe_load(file)

    except Exception as e:
        logger.debug(f"Failed to load configuration: {e}")
        return {"target_groups": [], "listeners": []}

config = load_config()

LISTENERS = config["listeners"]

logger.debug(f"Listeners loaded: {LISTENERS}")

def resolve_hostname(hostname):
    """Resolve a hostname to a list of IP addresses."""
    try:
        return [addr[4][0] for addr in socket.getaddrinfo(hostname, None, family=socket.AF_INET)]
    except socket.gaierror as e:
        logger.debug(f"Failed to resolve hostname '{hostname}': {e}")
        return []
    
def load_target_groups():
    logger.debug("Loading target groups from configuration")
    target_groups = {}
    for target_group in config["target_groups"]:
        targets = []
        for target in target_group["targets"]:
            healthcheck = target.get("healthcheck", {"path": "/", "status_code": [200], "timeout": 2})
            healthcheck["path"] = healthcheck.get("path", "/")
            healthcheck["status_code"] = healthcheck.get("status_code", [200])
            healthcheck["timeout"] = healthcheck.get("timeout", 2)

            logger.debug(f"Loading server healthcheck: {healthcheck}")

            target_hostname = target["hostname"].replace("http://", "").replace("https://", "").replace("/", "")
            # Resolve the hostname to IP addresses
            resolved_ips = resolve_hostname(target_hostname)
            if not resolved_ips:
                logger.debug(f"Skipping target '{target_hostname}:{target['port']}' due to DNS resolution failure.")
                continue

            for ip in resolved_ips:
                server = {
                    "hostname": f"http://{ip}:{target['port']}",
                    "weight": target.get("weight", 1),
                    "healthcheck": healthcheck
                }
                targets.append(server)
                logger.debug(f"Added resolved target: {server}")
        
        target_groups[target_group["name"]] = {
            "servers": targets,
            "current_index": 0,
            "healthy_servers": targets.copy()
        }
    return target_groups

TARGET_GROUPS = load_target_groups()

logger.debug(f"Target Groups loaded: {TARGET_GROUPS}")


def get_next_server(target_group_name):
    if target_group_name not in TARGET_GROUPS:
        logger.debug(f"Target group {target_group_name} not found.")
        return None
    
    target_group = TARGET_GROUPS[target_group_name]
    healthy_servers = target_group["healthy_servers"]

    if not healthy_servers:
        logger.debug(f"No healthy servers in target group '{target_group_name}'.")
        return None
    
    current = target_group["current_index"]

    match LOAD_BALANCING_ALGORITHM:
      case "ROUND_ROBIN":        
        server = healthy_servers[current]
        logger.debug(f"Selected server {server} from target group '{target_group_name}' using ROUND_ROBIN.")
        target_group["current_index"] = (current + 1) % len(healthy_servers)
        return server

      case "WEIGHTED":         
        weights = [
            server.get("weight", 1)
            for server in healthy_servers
        ]        

        server_weight_assigned = [
            server for server, weight in zip(healthy_servers, weights) for _ in range(weight)
        ] 

        server = server_weight_assigned[current]
        logger.debug(f"Selected server {server} from target group '{target_group_name}' using WEIGHTED.")
        
        target_group["current_index"] = (current + 1) % len(server_weight_assigned)
        return server

    logger.debug(f"Unknown load balancing algorithm: {LOAD_BALANCING_ALGORITHM}")
    return None


def check_server(server):
    """Send a GET request to the healthcheck endpoint; healthy if status matches."""
    try:
        healthcheck = server.get("healthcheck", {"path": "/", "status_code": [200], "timeout": 2})
        healthcheck_path = f"{server['hostname']}{healthcheck['path']}"
        
        logger.debug(f"Performing health check for {healthcheck_path} with timeout {healthcheck['timeout']}")

        r = requests.get(healthcheck_path, timeout=healthcheck["timeout"])
        logger.debug(f"Health check response from {healthcheck_path}: {r.status_code}")

        return r.status_code in healthcheck["status_code"]
    
    except requests.exceptions.Timeout:
        logger.debug(f"Health check for {server['hostname']} timed out.")
        return False
    except Exception as e:
        logger.debug(f"Health check failed for {server['hostname']}: {e}")
        return False


def health_check_loop():
    """Background thread that checks every server every 3 seconds."""
    while True:
        for group_name, group_data in TARGET_GROUPS.items():
            logger.debug(f"Performing health checks for target group '{group_name}'")

            new_healthy_servers = [
                server for server in group_data["servers"] if check_server(server)
            ]

            if new_healthy_servers != group_data["healthy_servers"]:
                logger.debug(f"Health status changed for target group '{group_name}'. Healthy servers: {new_healthy_servers}")

            group_data["healthy_servers"] = new_healthy_servers
        time.sleep(3)


threading.Thread(target=health_check_loop, daemon=True).start()


@app.route("/", defaults={"subpath": ""}, methods=["GET", "POST"])
@app.route("/<path:subpath>", methods=["GET", "POST"])
def proxy(subpath):
    full_path = f"/{subpath}"

    listener_rule = next(
        (rule for rule in LISTENERS if full_path.startswith(rule["path_prefix"])),
        None
    )
    
    logger.debug(f"Incoming request path: {full_path}")

    if not listener_rule:
        logger.debug(f"No matching listener found for path '{full_path}'")
        return Response("Not found", status=404)

    logger.debug(f"Matched listener: {listener_rule}")

    target_group_name = listener_rule["target_group"]
    target_group = TARGET_GROUPS.get(target_group_name)

    if not target_group or not target_group["healthy_servers"]:
        logger.debug(f"No healthy backend servers available for target group '{target_group_name}'")
        return Response("Service unavailable", status=503)

    try:
        logger.debug(f"Forwarding request to {target_group_name}")   
        upstream_server = get_next_server(target_group_name)
        if not upstream_server:
            logger.debug(f"No server available for target group '{target_group_name}'")
            return Response("Service unavailable", status=503)
        
        rewritten_path = full_path.replace(listener_rule.get("path_prefix", ""), listener_rule.get("path_rewrite", ""), 1)
        
        upstream_url = f"{upstream_server['hostname']}{rewritten_path}"
        logger.debug(f"Forwarding request to {upstream_url}")

        response = requests.request(
            method=request.method,
            url=upstream_url,
            headers={k: v for k, v in request.headers if k != 'Host'},
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=False,
            timeout=CONNECTION_TIMEOUT
        )

        return Response(
            response.content, 
            status=response.status_code, 
            headers=dict(response.headers)
        )

    except requests.exceptions.Timeout:
        logger.debug(f"Request to {upstream_server} timed out")
        return Response("Gateway timeout", status=504)

    except requests.exceptions.RequestException as e:
        logger.debug(f"Connection error while forwarding request to {upstream_server}: {e}")
        return Response("Bad gateway", status=502)

if __name__ == "__main__":
    print(f"Load balancer running on port {LISTENER_PORT}...")
    app.run(host='0.0.0.0', port=LISTENER_PORT, debug=False)
