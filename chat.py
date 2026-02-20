#!/usr/bin/env python3
import os
import urllib.request
import datetime
import openai
import anthropic

openai_client = openai.OpenAI()
anthropic_client = anthropic.Anthropic()

IMAGES_DIR = os.path.join(os.path.dirname(__file__), "images")
os.makedirs(IMAGES_DIR, exist_ok=True)

IMAGE_KEYWORDS = ("generate", "create", "draw", "make", "show", "image", "picture", "photo", "illustration")

def is_image_request(text):
    lower = text.lower()
    return any(kw in lower for kw in IMAGE_KEYWORDS)


def chat_gpt():
    print("Chatting with GPT-4o (type 'quit' to exit)\n")
    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("quit", "exit", "q"):
            break
        if not user_input:
            continue

        if is_image_request(user_input):
            print("(Looks like an image request — generating image...)")
            generate_image(prompt=user_input)
            continue

        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": user_input}],
        )
        print(f"GPT: {response.choices[0].message.content}\n")


def chat_claude():
    print("Chatting with Claude (type 'quit' to exit)\n")
    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("quit", "exit", "q"):
            break
        if not user_input:
            continue

        response = anthropic_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": user_input}],
        )
        print(f"Claude: {response.content[0].text}\n")


def generate_image(prompt=None):
    if prompt is None:
        prompt = input("Describe the image you want: ").strip()
    if not prompt:
        print("No prompt provided.")
        return

    print("Generating image...")
    response = openai_client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size="1024x1024",
        n=1,
    )
    url = response.data[0].url
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(IMAGES_DIR, f"image_{timestamp}.png")
    urllib.request.urlretrieve(url, filename)
    print(f"\nImage URL: {url}")
    print(f"Saved to:  {filename}\n")


def main():
    print("OpenAI Playground")
    print("1. Chat with GPT-4o (+ image generation)")
    print("2. Chat with Claude")
    print()
    choice = input("Choose (1/2): ").strip()

    if choice == "1":
        chat_gpt()
    elif choice == "2":
        chat_claude()
    else:
        print("Invalid choice.")


if __name__ == "__main__":
    main()
