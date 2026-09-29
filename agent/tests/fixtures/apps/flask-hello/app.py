import os
import ssl
from flask import Flask

GREETING = os.environ.get("GREETING", "hello")
app = Flask(__name__)


@app.get("/health")
def health():
    return "ok"


@app.get("/")
def index():
    return f"{GREETING} over {ssl.OPENSSL_VERSION.split()[0]}"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
