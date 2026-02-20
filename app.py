#!/usr/bin/env python3
import os
import time
import uuid
import threading
from flask import Flask, request, jsonify, render_template
import openai
import anthropic
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__)

limiter = Limiter(get_remote_address, app=app)

openai_client = openai.OpenAI()
anthropic_client = anthropic.Anthropic()

MESSAGE_TTL = 3 * 60 * 60  # 3 hours
MAX_LENGTH = 280

messages = []
messages_lock = threading.Lock()


def get_active_messages():
    now = time.time()
    with messages_lock:
        messages[:] = [m for m in messages if now - m["timestamp"] < MESSAGE_TTL]
        return sorted(messages, key=lambda m: m["timestamp"], reverse=True)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/chat/gpt", methods=["POST"])
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


@app.route("/image/generate", methods=["POST"])
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


@app.route("/messages", methods=["GET"])
def get_messages():
    now = time.time()
    active = get_active_messages()
    return jsonify([{
        "id": m["id"],
        "text": m["text"],
        "timestamp": m["timestamp"],
        "expires_in": max(0, int(MESSAGE_TTL - (now - m["timestamp"])))
    } for m in active])


@app.route("/messages", methods=["POST"])
@limiter.limit("5 per minute")
def post_message():
    data = request.json
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "Message is empty"}), 400
    if len(text) > MAX_LENGTH:
        return jsonify({"error": f"Max {MAX_LENGTH} characters"}), 400

    msg = {"id": str(uuid.uuid4()), "text": text, "timestamp": time.time()}
    with messages_lock:
        messages.append(msg)

    return jsonify({"status": "ok"})


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(debug=debug)
