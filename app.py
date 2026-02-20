#!/usr/bin/env python3
import os
import time
import urllib.request
import datetime
from flask import Flask, request, jsonify, render_template, send_from_directory
import openai
import anthropic

app = Flask(__name__)

openai_client = openai.OpenAI()
anthropic_client = anthropic.Anthropic()

IMAGES_DIR = os.path.join(os.path.dirname(__file__), "static", "images")
os.makedirs(IMAGES_DIR, exist_ok=True)

IMAGE_TTL_SECONDS = 30 * 60  # 30 minutes


def cleanup_old_images():
    now = time.time()
    for filename in os.listdir(IMAGES_DIR):
        filepath = os.path.join(IMAGES_DIR, filename)
        if os.path.isfile(filepath) and now - os.path.getmtime(filepath) > IMAGE_TTL_SECONDS:
            os.remove(filepath)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/static/images/<path:filename>")
def serve_image(filename):
    return send_from_directory(IMAGES_DIR, filename)


@app.route("/chat/gpt", methods=["POST"])
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


@app.route("/cleanup", methods=["POST"])
def cleanup():
    cleanup_old_images()
    return jsonify({"status": "ok"})


@app.route("/clear", methods=["POST"])
def clear_all():
    for filename in os.listdir(IMAGES_DIR):
        filepath = os.path.join(IMAGES_DIR, filename)
        if os.path.isfile(filepath):
            os.remove(filepath)
    return jsonify({"status": "ok"})


@app.route("/image/generate", methods=["POST"])
def generate_image():
    cleanup_old_images()
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
    url = response.data[0].url
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"image_{timestamp}.png"
    filepath = os.path.join(IMAGES_DIR, filename)
    urllib.request.urlretrieve(url, filepath)

    return jsonify({"url": f"/static/images/{filename}"})


if __name__ == "__main__":
    app.run(debug=True)
