from flask import Flask, jsonify
import os
import socket

app = Flask(__name__)

HOSTNAME = socket.gethostname()
PORT = int(os.getenv("PORT", 5000))
DEBUG = True if os.getenv("DEBUG", "True") == "True" else False

@app.route("/v1")
def home():
    """Return message with hostname and port."""

    return jsonify({
        "message": "Hello from backend server!",
        "hostname": HOSTNAME,
        "server_port": PORT
    })

@app.route("/health")
def healthcheck():
    """Healthcheck endpoint."""

    return jsonify({
        "status": "ok",
    }), 200

if __name__ == "__main__":
    print(f"Backend {HOSTNAME} running on port {PORT}...")
    app.run(host='0.0.0.0', port=PORT, debug=False)