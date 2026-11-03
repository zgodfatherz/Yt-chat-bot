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

# Strictly locked to T1 Ranjha Live (@T1RANJHA)
TARGET_HANDLE = "@T1RANJHA"

CASUAL_MESSAGES = [
    ".",
    "🍿",
    "👀",
    "gg",
    "nice",
    "op",
    "🔥",
    "badiya",
    "..",
    "💯",
    "op gameplay",
    "clutch",
    "⚡",
    "mast"
]

HYPE_MESSAGES = ["gg", "op", "🔥", "nice", "clutch", "💯", "op भाई", "⚡"]
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


def get_target_channel_id(youtube):
    res = youtube.channels().list(
        part="id,snippet",
        forHandle=TARGET_HANDLE
    ).execute()
    items = res.get("items", [])
    if not items:
        print(f"Could not find channel for {TARGET_HANDLE}")
        return None
    ch_id = items[0]["id"]
    ch_title = items[0]["snippet"]["title"]
    print(f"Locked onto Target Channel: {ch_title} ({ch_id})")
    return ch_id


def find_active_stream_for_channel(youtube, channel_id):
    res = youtube.search().list(
        part="id,snippet",
        channelId=channel_id,
        eventType="live",
        type="video",
        maxResults=1
    ).execute()
    items = res.get("items", [])
    if not items:
        return None
    video_id = items[0]["id"]["videoId"]
    title = items[0]["snippet"]["title"]
    print(f"Auto-detected live stream: {title} ({video_id})")
    return video_id


def get_live_chat_id(youtube, video_id, target_channel_id):
    res = youtube.videos().list(
        part="liveStreamingDetails,snippet",
        id=video_id
    ).execute()
    items = res.get("items", [])
    if not items:
        return None

    video_channel_id = items[0].get("snippet", {}).get("channelId")
    if target_channel_id and video_channel_id != target_channel_id:
        print("Safety Lock: Stream does not belong to @T1RANJHA! Aborting.")
        return None

    details = items[0].get("liveStreamingDetails", {})
    return details.get("activeLiveChatId")


def analyze_chat_mood(youtube, live_chat_id):
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

        hype_words = ["gg", "op", "nice", "clutch", "w", "fire", "badiya", "mast", "insane"]
        dot_count = sum(1 for t in recent_texts if t in [".", ".."])
        hype_count = sum(1 for t in recent_texts if any(w in t for w in hype_words))

        if hype_count >= 2:
            return "hype"
        elif dot_count >= 2:
            return "quiet"
        return "normal"
    except Exception:
        return "normal"


def choose_next_message(recent_history, msg_counter, next_points_check, mood):
    if msg_counter >= next_points_check and "!points" not in recent_history:
        return "!points", True

    if mood == "hype":
        pool = HYPE_MESSAGES
    elif mood == "quiet":
        pool = QUIET_MESSAGES
    else:
        pool = CASUAL_MESSAGES

    available = [m for m in pool if m not in recent_history]
    if not available:
        available = [m for m in CASUAL_MESSAGES if m not in recent_history]

    return random.choice(available), False


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
    youtube = get_youtube_client()
    target_channel_id = get_target_channel_id(youtube)

    if VIDEO_ID_OR_URL:
        video_id = extract_video_id(VIDEO_ID_OR_URL)
    else:
        if not target_channel_id:
            return
        video_id = find_active_stream_for_channel(youtube, target_channel_id)

    if not video_id:
        print("@T1RANJHA is not live right now. Exiting check cleanly.")
        return

    live_chat_id = get_live_chat_id(youtube, video_id, target_channel_id)
    if not live_chat_id:
        print("No active live chat found.")
        return

    print(f"Connected to @T1RANJHA Live Chat ID: {live_chat_id}")

    recent_history = deque(maxlen=4)
    msg_counter = 0
    next_points_check = random.randint(5, 8)
    start_time = time.time()

    # Runs for up to 4.5 hours (16200s) to easily cover a 3.5-hour stream
    while time.time() - start_time < 16200:
        live_chat_id = get_live_chat_id(youtube, video_id, target_channel_id)
        if not live_chat_id:
            print("Stream ended. Stopping bot safely.")
            break

        mood = analyze_chat_mood(youtube, live_chat_id)
        msg, is_points_cmd = choose_next_message(
            recent_history, msg_counter, next_points_check, mood
        )

        if send_chat_message(youtube, live_chat_id, msg):
            recent_history.append(msg)
            if is_points_cmd:
                msg_counter = 0
                next_points_check = random.randint(6, 9)
            else:
                msg_counter += 1

        sleep_time = random.randint(75, 140)
        print(f"Waiting {sleep_time} seconds before next message...")
        time.sleep(sleep_time)


if __name__ == "__main__":
    main()
        
