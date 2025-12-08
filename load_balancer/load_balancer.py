from flask import Flask, request, Response
import requests
import threading
import time

app = Flask(__name__)

# List of backend servers
SERVERS = [
    "http://127.0.0.1:5001",
    "http://127.0.0.1:5002",
    "http://127.0.0.1:5003"
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


if __name__ == "__main__":
    print("Load balancer running on port 8000...")
    app.run(port=8000)