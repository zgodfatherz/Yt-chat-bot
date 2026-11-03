import os
import time
import random
from collections import deque
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

CLIENT_ID = os.environ.get("YT_CLIENT_ID")
CLIENT_SECRET = os.environ.get("YT_CLIENT_SECRET")
REFRESH_TOKEN = os.environ.get("YT_REFRESH_TOKEN")
VIDEO_ID_OR_URL = os.environ.get("VIDEO_ID", "").strip()

# Natural viewer messages (no duplicates allowed in recent history)
CASUAL_MESSAGES = [
    ".",
    "🍿",
    "👀",
    "gg",
    "nice",
    "op",
    "🔥",
    "let's go",
    "..",
    "💯",
    "solid gameplay",
    "clutch",
    "⚡"
]

HYPE_MESSAGES = ["gg", "op", "🔥", "nice", "clutch", "💯", "👀"]
QUIET_MESSAGES = [".", "🍿", "👀", "..", "gg", "🔥"]


def extract_video_id(input_str):
    if "v=" in input_str:
        return input_str.split("v=")[1].split("&")[0]
    elif "youtu.be/" in input_str:
        return input_str.split("youtu.be/")[1].split("?")[0]
    elif "/live/" in input_str:
        return input_str.split("/live/")[1].split("?")[0]
    return input_str.strip()


def get_youtube_client():
    creds = Credentials(
        None,
        refresh_token=REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET
    )
    return build("youtube", "v3", credentials=creds)


def get_live_chat_id(youtube, video_id):
    res = youtube.videos().list(
        part="liveStreamingDetails,snippet",
        id=video_id
    ).execute()
    items = res.get("items", [])
    if not items:
        print("Video not found. Check your Video ID or URL.")
        return None
    title = items[0].get("snippet", {}).get("title", "Unknown Stream")
    print(f"Found Stream: {title}")
    details = items[0].get("liveStreamingDetails", {})
    return details.get("activeLiveChatId")


def analyze_chat_mood(youtube, live_chat_id):
    """Reads recent chat messages to match the current stream situation."""
    try:
        res = youtube.liveChatMessages().list(
            liveChatId=live_chat_id,
            part="snippet",
            maxResults=20
        ).execute()
        items = res.get("items", [])
        if not items:
            return "quiet"

        recent_texts = [
            item["snippet"].get("displayMessage", "").lower().strip()
            for item in items[-10:]
        ]

        hype_words = ["gg", "op", "nice", "clutch", "w", "fire", "insane", "lol", "haha"]
        dot_count = sum(1 for t in recent_texts if t in [".", ".."])
        hype_count = sum(1 for t in recent_texts if any(w in t for w in hype_words))

        if hype_count >= 2:
            return "hype"
        elif dot_count >= 2:
            return "quiet"
        return "normal"
    except Exception as e:
        print(f"Could not read chat mood: {e}")
        return "normal"


def choose_next_message(recent_history, msg_counter, next_points_check, mood):
    # Check "!points" periodically without repeating it back-to-back
    if msg_counter >= next_points_check and "!points" not in recent_history:
        return "!points", True

    if mood == "hype":
        pool = HYPE_MESSAGES
    elif mood == "quiet":
        pool = QUIET_MESSAGES
    else:
        pool = CASUAL_MESSAGES

    # Filter out any message sent in the last 4 turns to prevent spam strikes
    available = [m for m in pool if m not in recent_history]
    if not available:
        available = [m for m in CASUAL_MESSAGES if m not in recent_history]

    chosen = random.choice(available)
    return chosen, False


def send_chat_message(youtube, live_chat_id, text):
    try:
        youtube.liveChatMessages().insert(
            part="snippet",
            body={
                "snippet": {
                    "liveChatId": live_chat_id,
                    "type": "textMessageEvent",
                    "textMessageDetails": {"messageText": text}
                }
            }
        ).execute()
        print(f"Sent message: {text}")
        return True
    except Exception as e:
        print(f"Error sending message: {e}")
        return False


def main():
    if not VIDEO_ID_OR_URL:
        print("Error: Please enter the Stream Video ID or URL when starting the workflow.")
        return

    video_id = extract_video_id(VIDEO_ID_OR_URL)
    youtube = get_youtube_client()
    live_chat_id = get_live_chat_id(youtube, video_id)

    if not live_chat_id:
        print("No active live chat found (stream might have ended or not started yet).")
        return

    print(f"Successfully connected to Live Chat ID: {live_chat_id}")

    # Keep track of the last 4 messages so it never repeats 2 or 3 times
    recent_history = deque(maxlen=4)
    msg_counter = 0
    next_points_check = random.randint(5, 8)
    start_time = time.time()

    # Run up to 5.5 hours (GitHub Actions max job duration)
    while time.time() - start_time < 19800:
        # Check if stream is still live and read the room
        live_chat_id = get_live_chat_id(youtube, video_id)
        if not live_chat_id:
            print("Stream ended. Stopping bot safely.")
            break

        mood = analyze_chat_mood(youtube, live_chat_id)
        msg, is_points_cmd = choose_next_message(
            recent_history, msg_counter, next_points_check, mood
        )

        success = send_chat_message(youtube, live_chat_id, msg)
        if success:
            recent_history.append(msg)
            if is_points_cmd:
                msg_counter = 0
                next_points_check = random.randint(6, 9)
            else:
                msg_counter += 1

        # Human-like random delay between 75 and 140 seconds
        sleep_time = random.randint(75, 140)
        print(f"Waiting {sleep_time} seconds before next message...")
        time.sleep(sleep_time)


if __name__ == "__main__":
    main()
  
