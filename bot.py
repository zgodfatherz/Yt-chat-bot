import os
import time
import random
from collections import deque
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

CLIENT_ID = "".join(os.environ.get("YT_CLIENT_ID", "").split()).strip('"\'')
CLIENT_SECRET = "".join(os.environ.get("YT_CLIENT_SECRET", "").split()).strip('"\'')
REFRESH_TOKEN = "".join(os.environ.get("YT_REFRESH_TOKEN", "").split()).strip('"\'')
VIDEO_ID_OR_URL = os.environ.get("VIDEO_ID", "").strip()

TARGET_HANDLE = "@T1RANJHA"

# Sent ONLY ONCE when the bot first joins the stream
WELCOME_MESSAGE = "I am back in the stream yo"

# Commands sent periodically to check your points & hours in logs
COMMANDS = ["!points", "!top", "!tophours"]

# Clean emojis, dots, and "yo yo"
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


def get_youtube_client():
    if not CLIENT_ID or not CLIENT_SECRET or not REFRESH_TOKEN:
        raise ValueError("One or more GitHub Secrets are empty!")
    creds = Credentials(
        None,
        refresh_token=REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET
    )
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def get_target_channel_id(youtube):
    res = youtube.channels().list(
        part="id,snippet",
        forHandle=TARGET_HANDLE
    ).execute()
    items = res.get("items", [])
    if not items:
        return None
    ch_id = items[0]["id"]
    print(f"Locked onto Target Channel: {items[0]['snippet']['title']} ({ch_id})", flush=True)
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
    print(f"Auto-detected live stream: {items[0]['snippet']['title']} ({video_id})", flush=True)
    return video_id


def get_live_chat_id(youtube, video_id, target_channel_id):
    try:
        res = youtube.videos().list(
            part="liveStreamingDetails,snippet",
            id=video_id
        ).execute()
        items = res.get("items", [])
        if not items:
            return None
        video_channel_id = items[0].get("snippet", {}).get("channelId")
        if target_channel_id and video_channel_id != target_channel_id:
            return None
        return items[0].get("liveStreamingDetails", {}).get("activeLiveChatId")
    except Exception as e:
        print(f"Network glitch checking stream status: {e}", flush=True)
        return "RETRY"


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
        print(f"Sent message: {text}", flush=True)
        return True
    except Exception as e:
        err_str = str(e)
        print(f"Error sending message: {err_str}", flush=True)
        if "liveChatEnded" in err_str or "liveChatDisabled" in err_str:
            return "ENDED"
        return False


def log_streamlabs_reply(youtube, live_chat_id):
    try:
        time.sleep(6)
        res = youtube.liveChatMessages().list(
            liveChatId=live_chat_id,
            part="snippet,authorDetails",
            maxResults=15
        ).execute()
        items = res.get("items", [])
        print("--- Checking Chat for @Streamlabs Reply ---", flush=True)
        for item in items[-8:]:
            author = item.get("authorDetails", {}).get("displayName", "Unknown")
            text = item.get("snippet", {}).get("displayMessage", "")
            print(f"  [Chat] {author}: {text}", flush=True)
        print("-------------------------------------------", flush=True)
    except Exception as e:
        print(f"Could not read chat reply: {e}", flush=True)


def main():
    youtube = get_youtube_client()
    target_channel_id = get_target_channel_id(youtube)
    if not target_channel_id:
        return

    video_id = find_active_stream_for_channel(youtube, target_channel_id)
    if not video_id:
        print("@T1RANJHA is not live right now. Exiting check cleanly.", flush=True)
        return

    live_chat_id = get_live_chat_id(youtube, video_id, target_channel_id)
    if not live_chat_id or live_chat_id == "RETRY":
        print("No active live chat found.", flush=True)
        return

    print(f"Connected to @T1RANJHA Live Chat ID: {live_chat_id}", flush=True)

    recent_history = deque(maxlen=4)
    msg_counter = 0
    next_cmd_check = random.randint(6, 9)
    cmd_index = 0
    consecutive_failures = 0
    start_time = time.time()
    sent_welcome = False

    # Runs for up to 5.5 hours (19800s) continuously
    while time.time() - start_time < 19800:
        try:
            if not sent_welcome:
                msg = WELCOME_MESSAGE
                is_cmd = False
                sent_welcome = True
            else:
                msg, is_cmd = choose_next_message(
                    recent_history, msg_counter, next_cmd_check, cmd_index
                )

            result = send_chat_message(youtube, live_chat_id, msg)

            if result == "ENDED":
                print("Live chat officially ended. Stopping bot safely.", flush=True)
                break
            elif result is True:
                consecutive_failures = 0
                recent_history.append(msg)
                if is_cmd:
                    log_streamlabs_reply(youtube, live_chat_id)
                    msg_counter = 0
                    next_cmd_check = random.randint(6, 9)
                    cmd_index += 1
                else:
                    msg_counter += 1
            else:
                consecutive_failures += 1
                print(f"Retry {consecutive_failures}/6 - Rebuilding YouTube client...", flush=True)
                youtube = get_youtube_client()
                if consecutive_failures >= 6:
                    check = get_live_chat_id(youtube, video_id, target_channel_id)
                    if not check:
                        print("Stream confirmed offline after 6 retries. Exiting.", flush=True)
                        break
                    else:
                        if check != "RETRY":
                            live_chat_id = check
                        consecutive_failures = 0

        except Exception as loop_err:
            print(f"Recovered from unexpected loop error: {loop_err}", flush=True)
            time.sleep(15)
            try:
                youtube = get_youtube_client()
            except Exception:
                pass

        # 65 to 110 seconds guarantees we never miss a 5-minute Streamlabs point tick!
        sleep_time = random.randint(65, 110)
        print(f"Waiting {sleep_time} seconds before next message...", flush=True)
        time.sleep(sleep_time)


if __name__ == "__main__":
    main()
        
