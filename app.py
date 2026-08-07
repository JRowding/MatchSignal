from flask import Flask, send_from_directory

app = Flask(__name__)


@app.get("/")
def home():
    return send_from_directory(".", "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}
