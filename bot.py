import os
import time
import random
from collections import deque
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Automatically strip any accidental spaces, newlines, or quotes from GitHub Secrets
CLIENT_ID = "".join(os.environ.get("YT_CLIENT_ID", "").split()).strip('"\'')
CLIENT_SECRET = "".join(os.environ.get("YT_CLIENT_SECRET", "").split()).strip('"\'')
REFRESH_TOKEN = "".join(os.environ.get("YT_REFRESH_TOKEN", "").split()).strip('"\'')
VIDEO_ID_OR_URL = os.environ.get("VIDEO_ID", "").strip()

TARGET_HANDLE = "@T1RANJHA"

# Sent ONLY ONCE when the bot first joins the stream
WELCOME_MESSAGE = "I am back in the stream yo"

# Commands sent periodically every 6 to 9 messages
COMMANDS = ["!points", "!top"]

# Only emojis, dots, and "yo yo"
SAFE_MESSAGES = [
    "🍿",
    "💯",
    "yo yo",
    "..",
    ".",
    "🔥",
    "👀",
    "...",
    "⚡",
    "✌️",
    "😎"
]


def check_credentials_format():
    print(f"Checking secrets... ID length: {len(CLIENT_ID)}, Secret length: {len(CLIENT_SECRET)}, Token length: {len(REFRESH_TOKEN)}")
    if not CLIENT_ID or not CLIENT_SECRET or not REFRESH_TOKEN:
        raise ValueError("One or more GitHub Secrets are completely empty! Check Settings -> Secrets -> Actions.")


def extract_video_id(input_str):
    if "v=" in input_str:
        return input_str.split("v=")[1].split("&")[0]
    elif "youtu.be/" in input_str:
        return input_str.split("youtu.be/")[1].split("?")[0]
    elif "/live/" in input_str:
        return input_str.split("/live/")[1].split("?")[0]
    return input_str.strip()


def get_youtube_client():
    check_credentials_format()
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


def choose_next_message(recent_history, msg_counter, next_cmd_check, cmd_index):
    if msg_counter >= next_cmd_check:
        cmd = COMMANDS[cmd_index % len(COMMANDS)]
        if cmd not in recent_history:
            return cmd, True

    available = [m for m in SAFE_MESSAGES if m not in recent_history]
    if not available:
        available = SAFE_MESSAGES

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
    next_cmd_check = random.randint(6, 9)
    cmd_index = 0
    start_time = time.time()
    sent_welcome = False

    # Runs for up to 4.5 hours (16200s) to cover a 3.5-hour stream
    while time.time() - start_time < 16200:
        live_chat_id = get_live_chat_id(youtube, video_id, target_channel_id)
        if not live_chat_id:
            print("Stream ended. Stopping bot safely.")
            break

        # Send the greeting message ONLY ONCE at the very start of the stream
        if not sent_welcome:
            msg = WELCOME_MESSAGE
            is_cmd = False
            sent_welcome = True
        else:
            msg, is_cmd = choose_next_message(
                recent_history, msg_counter, next_cmd_check, cmd_index
            )

        if send_chat_message(youtube, live_chat_id, msg):
            recent_history.append(msg)
            if is_cmd:
                msg_counter = 0
                next_cmd_check = random.randint(6, 9)
                cmd_index += 1
            else:
                msg_counter += 1

        sleep_time = random.randint(75, 140)
        print(f"Waiting {sleep_time} seconds before next message...")
        time.sleep(sleep_time)


if __name__ == "__main__":
    main()
                     
