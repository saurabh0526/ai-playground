#!/usr/bin/env python3
import os
from functools import wraps
from flask import Flask, request, jsonify, render_template, session
import openai
import anthropic
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24))

limiter = Limiter(get_remote_address, app=app)

openai_client = openai.OpenAI()
anthropic_client = anthropic.Anthropic()

APP_PASSWORD = os.environ.get("APP_PASSWORD", "")


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if APP_PASSWORD and not session.get("authenticated"):
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


@app.route("/")
def index():
    return render_template("index.html", authenticated=not APP_PASSWORD or session.get("authenticated", False))


@app.route("/login", methods=["POST"])
@limiter.limit("10 per minute")
def login():
    if request.json.get("password") == APP_PASSWORD:
        session["authenticated"] = True
        return jsonify({"status": "ok"})
    return jsonify({"error": "Wrong password"}), 401


@app.route("/chat/gpt", methods=["POST"])
@login_required
@limiter.limit("30 per minute")
def chat_gpt():
    data = request.json
    message = data.get("message", "").strip()
    if not message:
        return jsonify({"error": "No message provided"}), 400

    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": message}],
    )
    return jsonify({"reply": response.choices[0].message.content})


@app.route("/chat/claude", methods=["POST"])
@login_required
@limiter.limit("30 per minute")
def chat_claude():
    data = request.json
    message = data.get("message", "").strip()
    if not message:
        return jsonify({"error": "No message provided"}), 400

    response = anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": message}],
    )
    return jsonify({"reply": response.content[0].text})


@app.route("/clear", methods=["POST"])
@login_required
def clear_all():
    return jsonify({"status": "ok"})


@app.route("/image/generate", methods=["POST"])
@login_required
@limiter.limit("5 per minute")
def generate_image():
    data = request.json
    prompt = data.get("prompt", "").strip()
    if not prompt:
        return jsonify({"error": "No prompt provided"}), 400

    response = openai_client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size="1024x1024",
        n=1,
    )
    return jsonify({"url": response.data[0].url})


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(debug=debug)
