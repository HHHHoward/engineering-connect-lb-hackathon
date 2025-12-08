from flask import Flask, jsonify
import sys

app = Flask(__name__)

PORT = sys.argv[1] if len(sys.argv) > 1 else 5001

@app.route("/")
def home():
    return jsonify({
        "message": "Hello from backend server!",
        "server_port": PORT
    })

if __name__ == "__main__":
    app.run(port=int(PORT))