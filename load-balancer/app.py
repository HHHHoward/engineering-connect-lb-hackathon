from flask import Flask, request, Response
import os
import requests
import threading
import time

app = Flask(__name__)

LISTENER_PORT = int(os.getenv("LISTENER_PORT", 80))
CONNECTION_TIMEOUT = int(os.getenv("CONNECTION_TIMEOUT", 2))
LOAD_BALANCING_ALGORITHM = os.getenv("LOAD_BALANCING_ALGORITHM", "ROUND_ROBIN")
DEBUG = True if os.getenv("DEBUG", "True") == "True" else False

# List of backend servers
SERVERS = [
    "http://backend1:5000",
    "http://backend2:5000",
    "http://backend3:5000"
]

HEALTHY_SERVERS = SERVERS.copy()
current = 0

# ---------------------------
#  ROUND ROBIN SERVER PICKER
# ---------------------------
def get_next_server():
    global current
    if not HEALTHY_SERVERS:
        return None
    server = HEALTHY_SERVERS[current]
    current = (current + 1) % len(HEALTHY_SERVERS)
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


def health_check_loop():
    """Background thread that checks every server every 3 seconds."""
    global HEALTHY_SERVERS

    while True:
        new_healthy = []

        for server in SERVERS:
            if check_server(server):
                new_healthy.append(server)

        HEALTHY_SERVERS = new_healthy

        print("Health check:", HEALTHY_SERVERS)
        time.sleep(3)


# Start checker thread
threading.Thread(target=health_check_loop, daemon=True).start()


# ---------------------------
#          PROXY
# ---------------------------
@app.route("/", methods=["GET", "POST"])
def proxy():
    target = get_next_server()

    if not target:
        return {"error": "No healthy backend servers available"}, 503

    try:
        resp = requests.request(
            method=request.method,
            url=target,
            headers={k: v for k, v in request.headers if k != 'Host'},
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=False,
            timeout=2
        )

        return Response(resp.content, resp.status_code, resp.headers.items())

    except requests.exceptions.RequestException:
        return {"error": f"Server {target} unreachable"}, 502

@app.route("/targets", methods=["GET"])
def get_targets():
    """Return the list of backend servers and their health status."""
    return {
        "servers": SERVERS,
        "healthy_servers": HEALTHY_SERVERS
    }

if __name__ == "__main__":
    print(f"Load balancer running on port {LISTENER_PORT}...")
    app.run(host='0.0.0.0', port=LISTENER_PORT, debug=DEBUG)