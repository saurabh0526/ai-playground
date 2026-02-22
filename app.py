#!/usr/bin/env python3
import os
import time
import uuid
import sqlite3
import requests
import re
from urllib.parse import urlparse
from flask import Flask, request, jsonify, render_template
import openai
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from bs4 import BeautifulSoup
from better_profanity import profanity

app = Flask(__name__)

limiter = Limiter(get_remote_address, app=app)

# Initialize profanity filter
try:
    profanity.load_censor_words()
except Exception as e:
    print(f"Warning: Profanity filter initialization: {e}")

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
            cur.execute("ALTER TABLE messages ADD COLUMN IF NOT EXISTS image_url TEXT")
            cur.execute("ALTER TABLE messages ADD COLUMN IF NOT EXISTS is_ai BOOLEAN DEFAULT FALSE")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY,
                    message_id TEXT NOT NULL,
                    reason TEXT,
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
                try:
                    conn.execute("ALTER TABLE messages ADD COLUMN image_url TEXT")
                except Exception:
                    pass  # column already exists
                try:
                    conn.execute("ALTER TABLE messages ADD COLUMN is_ai BOOLEAN DEFAULT FALSE")
                except Exception:
                    pass  # column already exists
                try:
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS reports (
                            id TEXT PRIMARY KEY,
                            message_id TEXT NOT NULL,
                            reason TEXT,
                            timestamp REAL NOT NULL
                        )
                    """)
                except Exception:
                    pass  # table already exists
    finally:
        conn.close()


try:
    init_db()
except Exception as e:
    print(f"Warning: DB init failed: {e}")


def fetch_link_preview(url):
    """Fetch metadata from a URL for preview"""
    try:
        # Validate URL format
        parsed = urlparse(url)
        if not parsed.scheme:
            url = "https://" + url
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, "html.parser")
        
        # Extract metadata from Open Graph tags
        og_title = soup.find("meta", property="og:title")
        og_desc = soup.find("meta", property="og:description")
        og_image = soup.find("meta", property="og:image")
        
        # Fallback to regular meta tags
        if not og_title:
            title_tag = soup.find("title")
            og_title = title_tag.string if title_tag else None
        else:
            og_title = og_title.get("content")
            
        if not og_desc:
            desc_tag = soup.find("meta", attrs={"name": "description"})
            og_desc = desc_tag.get("content") if desc_tag else None
        else:
            og_desc = og_desc.get("content")
            
        og_image = og_image.get("content") if og_image else None
        
        return {
            "title": og_title or "Link Preview",
            "description": og_desc or "",
            "image": og_image,
            "url": url
        }
    except Exception as e:
        return {"error": str(e)}


def is_content_abusive(text):
    """Check if content contains abusive/inappropriate elements"""
    if not text or len(text) < 1:
        return False
    
    # Check for profanity
    if profanity.contains_profanity(text):
        return True
    
    # Check for excessive caps (>80% uppercase letters)
    letters = [c for c in text if c.isalpha()]
    if letters:
        caps_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        if caps_ratio > 0.8 and len(letters) > 5:
            return True
    
    # Check for repeated characters (more than 4 same chars in a row = spam)
    for i in range(len(text) - 4):
        if len(set(text[i:i+5])) == 1:
            return True
    
    # Check for excessive repeated words
    words = text.lower().split()
    if len(words) > 5:
        word_counts = {}
        for word in words:
            word_counts[word] = word_counts.get(word, 0) + 1
        if any(count > len(words) * 0.5 for count in word_counts.values()):
            return True
    
    return False


def fetch_top_news(count=2):
    """Fetch top trending news/articles from HackerNews"""
    try:
        # Fetch top stories from HackerNews API
        response = requests.get("https://hacker-news.firebaseio.com/v0/topstories.json", timeout=5)
        story_ids = response.json()[:30]  # Get top 30 IDs
        
        articles = []
        for story_id in story_ids:
            story_response = requests.get(
                f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json",
                timeout=3
            )
            story = story_response.json()
            
            if story.get("url") and story.get("title"):
                articles.append({
                    "title": story["title"],
                    "url": story["url"]
                })
            
            if len(articles) >= count:
                break
        
        return articles[:count]
    except Exception as e:
        print(f"Error fetching news: {e}")
        return []


def post_news_to_wall():
    """Post top news articles to wall if not already posted"""
    try:
        articles = fetch_top_news(2)
        conn, ph = get_db()
        
        for article in articles:
            try:
                title = article.get("title", "")[:300]  # Limit title length
                url = article.get("url", "")
                
                if not title or not url:
                    continue
                
                # Check if this URL is already posted
                if DATABASE_URL:
                    cur = conn.cursor()
                    cur.execute(f"SELECT id FROM messages WHERE text LIKE {ph}", (f"%{url}%",))
                    if cur.fetchone():
                        cur.close()
                        continue
                else:
                    result = conn.execute(f"SELECT id FROM messages WHERE text LIKE {ph}", (f"%{url}%",)).fetchone()
                    if result:
                        continue
                
                # Create post text with title and URL
                post_text = f"📰 {title}\n{url}"
                
                # Post to wall
                if DATABASE_URL:
                    cur = conn.cursor()
                    cur.execute(
                        f"INSERT INTO messages (id, text, timestamp, image_url, is_ai) VALUES ({ph}, {ph}, {ph}, {ph}, {ph})",
                        (str(uuid.uuid4()), post_text, time.time(), None, True)
                    )
                    conn.commit()
                    cur.close()
                else:
                    conn.execute(
                        f"INSERT INTO messages (id, text, timestamp, image_url, is_ai) VALUES ({ph}, {ph}, {ph}, {ph}, {ph})",
                        (str(uuid.uuid4()), post_text, time.time(), None, True)
                    )
                    conn.commit()
            except Exception as e:
                print(f"Error posting article: {e}")
                continue
        
        conn.close()
    except Exception as e:
        print(f"Error in post_news_to_wall: {e}")


@app.route("/")
def index():
    # Fetch and post top news in background
    try:
        post_news_to_wall()
    except Exception as e:
        print(f"Warning: Failed to post news on index load: {e}")
    return render_template("index.html")


@app.route("/fetch-news", methods=["POST"])
@limiter.limit("3 per minute")
def fetch_news_endpoint():
    """Endpoint to manually trigger news fetching"""
    try:
        post_news_to_wall()
        return jsonify({"status": "ok", "message": "News fetched and posted"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/link-preview", methods=["POST"])
@limiter.limit("10 per minute")
def link_preview():
    data = request.json
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    
    preview = fetch_link_preview(url)
    return jsonify(preview)


@app.route("/chat/gpt", methods=["POST"])
@limiter.limit("30 per minute")
def chat_gpt():
    data = request.json
    message = data.get("message", "").strip()
    if not message:
        return jsonify({"error": "No message provided"}), 400
    if not openai_client:
        return jsonify({"error": "OpenAI not configured"}), 503

    image = data.get("image")
    if image:
        img_url = image.get("url") or f"data:{image['mime']};base64,{image['b64']}"
        content = [{"type": "text", "text": message},
                   {"type": "image_url", "image_url": {"url": img_url}}]
    else:
        content = message

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": content}],
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
            cur.execute("SELECT id, text, timestamp, image_url, is_ai FROM messages ORDER BY timestamp DESC")
            rows = cur.fetchall()
            conn.commit()
            cur.close()
            return jsonify([{
                "id": r[0], "text": r[1], "timestamp": r[2],
                "image_url": r[3], "is_ai": bool(r[4]) if r[4] is not None else False,
                "expires_in": max(0, int(MESSAGE_TTL - (now - r[2])))
            } for r in rows])
        else:
            with conn:
                conn.execute(f"DELETE FROM messages WHERE timestamp < {ph}", (cutoff,))
                rows = conn.execute("SELECT * FROM messages ORDER BY timestamp DESC").fetchall()
                return jsonify([{
                    "id": r["id"], "text": r["text"], "timestamp": r["timestamp"],
                    "image_url": r["image_url"], "is_ai": bool(r.get("is_ai", False)),
                    "expires_in": max(0, int(MESSAGE_TTL - (now - r["timestamp"])))
                } for r in rows])
    finally:
        conn.close()


@app.route("/messages", methods=["POST"])
@limiter.limit("5 per minute")
@limiter.limit("100 per day")
def post_message():
    data = request.json
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "Message is empty"}), 400
    if len(text) > MAX_LENGTH:
        return jsonify({"error": f"Max {MAX_LENGTH} characters"}), 400
    
    # Check for abusive content
    if is_content_abusive(text):
        return jsonify({"error": "Your message contains inappropriate content and cannot be posted. Please review our community guidelines."}), 400
    
    image_url = data.get("image_url", "").strip() or None

    conn, ph = get_db()
    try:
        if DATABASE_URL:
            cur = conn.cursor()
            cur.execute(
                f"INSERT INTO messages (id, text, timestamp, image_url) VALUES ({ph}, {ph}, {ph}, {ph})",
                (str(uuid.uuid4()), text, time.time(), image_url)
            )
            conn.commit()
            cur.close()
        else:
            with conn:
                conn.execute(
                    f"INSERT INTO messages (id, text, timestamp, image_url) VALUES ({ph}, {ph}, {ph}, {ph})",
                    (str(uuid.uuid4()), text, time.time(), image_url)
                )
    finally:
        conn.close()
    return jsonify({"status": "ok"})


@app.route("/messages/<message_id>", methods=["DELETE"])
def delete_message(message_id):
    conn, ph = get_db()
    try:
        if DATABASE_URL:
            cur = conn.cursor()
            cur.execute(f"DELETE FROM messages WHERE id = {ph}", (message_id,))
            conn.commit()
            cur.close()
        else:
            with conn:
                conn.execute(f"DELETE FROM messages WHERE id = {ph}", (message_id,))
    finally:
        conn.close()
    return jsonify({"status": "ok"})


@app.route("/messages/<message_id>/report", methods=["POST"])
@limiter.limit("5 per minute")
def report_message(message_id):
    data = request.json or {}
    reason = data.get("reason", "").strip()
    
    conn, ph = get_db()
    try:
        if DATABASE_URL:
            cur = conn.cursor()
            cur.execute(
                f"INSERT INTO reports (id, message_id, reason, timestamp) VALUES ({ph}, {ph}, {ph}, {ph})",
                (str(uuid.uuid4()), message_id, reason or None, time.time())
            )
            conn.commit()
            cur.close()
        else:
            with conn:
                conn.execute(
                    f"INSERT INTO reports (id, message_id, reason, timestamp) VALUES ({ph}, {ph}, {ph}, {ph})",
                    (str(uuid.uuid4()), message_id, reason or None, time.time())
                )
    finally:
        conn.close()
    return jsonify({"status": "ok"})


@app.route("/ai-post", methods=["POST"])
@limiter.limit("5 per minute")
def ai_post():
    """Generate and post AI agent message to the wall"""
    if not openai_client:
        return jsonify({"error": "AI not configured"}), 503
    
    try:
        # Generate an interesting post about news, tech, or general knowledge
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": "Generate a single short, interesting social media post (max 150 chars) about technology news, scientific discovery, or thought-provoking insight. Make it engaging and suitable for a public wall. No hashtags."
            }],
            max_tokens=50
        )
        
        text = response.choices[0].message.content.strip()
        if not text or len(text) > MAX_LENGTH:
            text = "Did you know? Technology is evolving faster than ever. What's your take on AI?"
        
        # Post the AI-generated message
        conn, ph = get_db()
        try:
            if DATABASE_URL:
                cur = conn.cursor()
                cur.execute(
                    f"INSERT INTO messages (id, text, timestamp, image_url, is_ai) VALUES ({ph}, {ph}, {ph}, {ph}, {ph})",
                    (str(uuid.uuid4()), text, time.time(), None, True)
                )
                conn.commit()
                cur.close()
            else:
                with conn:
                    conn.execute(
                        f"INSERT INTO messages (id, text, timestamp, image_url, is_ai) VALUES ({ph}, {ph}, {ph}, {ph}, {ph})",
                        (str(uuid.uuid4()), text, time.time(), None, True)
                    )
        finally:
            conn.close()
        
        return jsonify({"status": "ok", "text": text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(debug=debug)
