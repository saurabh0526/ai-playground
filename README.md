# AI Playground

A simple web app to chat with GPT-4o, Claude, and generate images with DALL-E 3.

## Features

- **GPT-4o** — chat with OpenAI's GPT-4o
- **Claude** — chat with Anthropic's Claude
- **Image Gen** — generate images with DALL-E 3
- Generated images are automatically deleted after 30 minutes
- Clear all chats and images instantly with the "Clear all" button

## Setup

1. Clone the repo:
   ```bash
   git clone https://github.com/saurabh0526/ai-playground.git
   cd ai-playground
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set your API keys:
   ```bash
   export OPENAI_API_KEY=your_openai_key
   export ANTHROPIC_API_KEY=your_anthropic_key
   ```

4. Run the app:
   ```bash
   python app.py
   ```

5. Open `http://127.0.0.1:5000` in your browser.

## Deploy to Render

1. Push this repo to GitHub
2. Go to [render.com](https://render.com) → New → Web Service
3. Connect your GitHub repo
4. Set environment variables: `OPENAI_API_KEY` and `ANTHROPIC_API_KEY`
5. Build command: `pip install -r requirements.txt`
6. Start command: `gunicorn app:app`
