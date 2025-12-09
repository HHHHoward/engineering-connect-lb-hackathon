from flask import Flask, jsonify
import os
import socket

app = Flask(__name__)

HOSTNAME = socket.gethostname()
PORT = int(os.getenv("PORT", 5000))

@app.route("/")
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
    app.run(host='0.0.0.0', port=int(PORT), debug=True)