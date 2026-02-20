#!/usr/bin/env python3
import os
import time
import uuid
import sqlite3
from flask import Flask, request, jsonify, render_template
import openai
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__)

limiter = Limiter(get_remote_address, app=app)

try:
    openai_client = openai.OpenAI()
except Exception as e:
    openai_client = None
    print(f"Warning: OpenAI client failed to initialize: {e}")

MESSAGE_TTL = 7 * 24 * 60 * 60  # 7 days
MAX_LENGTH = 280

DATABASE_URL = os.environ.get("DATABASE_URL")  # set by Render automatically
DB_PATH = os.path.join(os.path.dirname(__file__), "wall.db")

# Render gives postgres:// but psycopg2 needs postgresql://
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)


def get_db():
    if DATABASE_URL:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(DATABASE_URL)
        return conn, "%s"  # PostgreSQL placeholder
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn, "?"   # SQLite placeholder


def init_db():
    conn, ph = get_db()
    try:
        if DATABASE_URL:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    text TEXT NOT NULL,
                    timestamp REAL NOT NULL
                )
            """)
            conn.commit()
            cur.close()
        else:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS messages (
                        id TEXT PRIMARY KEY,
                        text TEXT NOT NULL,
                        timestamp REAL NOT NULL
                    )
                """)
    finally:
        conn.close()


try:
    init_db()
except Exception as e:
    print(f"Warning: DB init failed: {e}")


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
    if not openai_client:
        return jsonify({"error": "OpenAI not configured"}), 503

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": message}],
        )
        return jsonify({"reply": response.choices[0].message.content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route("/clear", methods=["POST"])
def clear():
    return jsonify({"status": "ok"})


@app.route("/image/generate", methods=["POST"])
@limiter.limit("5 per minute")
def generate_image():
    data = request.json
    prompt = data.get("prompt", "").strip()
    if not prompt:
        return jsonify({"error": "No prompt provided"}), 400
    if not openai_client:
        return jsonify({"error": "OpenAI not configured"}), 503

    try:
        response = openai_client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            n=1,
        )
        return jsonify({"url": response.data[0].url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/messages", methods=["GET"])
def get_messages():
    now = time.time()
    cutoff = now - MESSAGE_TTL
    conn, ph = get_db()
    try:
        if DATABASE_URL:
            cur = conn.cursor()
            cur.execute(f"DELETE FROM messages WHERE timestamp < {ph}", (cutoff,))
            cur.execute("SELECT id, text, timestamp FROM messages ORDER BY timestamp DESC")
            rows = cur.fetchall()
            conn.commit()
            cur.close()
            return jsonify([{
                "id": r[0], "text": r[1], "timestamp": r[2],
                "expires_in": max(0, int(MESSAGE_TTL - (now - r[2])))
            } for r in rows])
        else:
            with conn:
                conn.execute(f"DELETE FROM messages WHERE timestamp < {ph}", (cutoff,))
                rows = conn.execute("SELECT * FROM messages ORDER BY timestamp DESC").fetchall()
                return jsonify([{
                    "id": r["id"], "text": r["text"], "timestamp": r["timestamp"],
                    "expires_in": max(0, int(MESSAGE_TTL - (now - r["timestamp"])))
                } for r in rows])
    finally:
        conn.close()


@app.route("/messages", methods=["POST"])
@limiter.limit("5 per minute")
def post_message():
    data = request.json
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "Message is empty"}), 400
    if len(text) > MAX_LENGTH:
        return jsonify({"error": f"Max {MAX_LENGTH} characters"}), 400

    conn, ph = get_db()
    try:
        if DATABASE_URL:
            cur = conn.cursor()
            cur.execute(
                f"INSERT INTO messages (id, text, timestamp) VALUES ({ph}, {ph}, {ph})",
                (str(uuid.uuid4()), text, time.time())
            )
            conn.commit()
            cur.close()
        else:
            with conn:
                conn.execute(
                    f"INSERT INTO messages (id, text, timestamp) VALUES ({ph}, {ph}, {ph})",
                    (str(uuid.uuid4()), text, time.time())
                )
    finally:
        conn.close()
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(debug=debug)
