#!/usr/bin/env python3
import os
from flask import Flask, request, jsonify, render_template
import openai
import anthropic

app = Flask(__name__)

openai_client = openai.OpenAI()
anthropic_client = anthropic.Anthropic()


@app.route("/")
def index():
    return render_template("index.html")


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


@app.route("/clear", methods=["POST"])
def clear_all():
    return jsonify({"status": "ok"})


@app.route("/image/generate", methods=["POST"])
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
    app.run(debug=True)
