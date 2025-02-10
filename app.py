from flask import Flask, jsonify, render_template
import os

app = Flask(__name__)

# get the port from the environment or use 3000
port = os.getenv("APP_PORT", 3000)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api")
def api():
    return jsonify({"message": "Hello, Flask!"})

if __name__ == "__main__":
    port = int(port)
    app.run(host='0.0.0.0', port=port, debug=True)
