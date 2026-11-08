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


def extract_video_id(input_str):
    if "v=" in input_str:
        return input_str.split("v=")[1].split("&")[0]
    elif "youtu.be/" in input_str:
        return input_str.split("youtu.be/")[1].split("?")[0]
    elif "/live/" in input_str:
        return input_str.split("/live/")[1].split("?")[0]
    return input_str.strip()


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


def get_target_channel_info(youtube):
    res = youtube.channels().list(
        part="id,snippet,contentDetails",
        forHandle=TARGET_HANDLE
    ).execute()
    items = res.get("items", [])
    if not items:
        return None, None
    ch_id = items[0]["id"]
    uploads_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    print(f"Locked onto Target Channel: {items[0]['snippet']['title']} ({ch_id})", flush=True)
    return ch_id, uploads_id


def find_active_stream(youtube, channel_id, uploads_playlist_id):
    """
    Method 1: Instant check via Channel Uploads Playlist (Zero YouTube search lag, 1-second detection).
    Method 2: Fallback to YouTube Search API if needed.
    """
    # Method 1: Check latest 5 videos in the channel's Uploads playlist
    if uploads_playlist_id:
        try:
            pl_res = youtube.playlistItems().list(
                part="contentDetails,snippet",
                playlistId=uploads_playlist_id,
                maxResults=5
            ).execute()
            video_ids = [
                item["contentDetails"]["videoId"]
                for item in pl_res.get("items", [])
                if "contentDetails" in item and "videoId" in item["contentDetails"]
            ]
            if video_ids:
                v_res = youtube.videos().list(
                    part="liveStreamingDetails,snippet",
                    id=",".join(video_ids)
                ).execute()
                for v in v_res.get("items", []):
                    live_details = v.get("liveStreamingDetails", {})
                    chat_id = live_details.get("activeLiveChatId")
                    # Ensure the stream is actively live right now (has active chat and hasn't ended)
                    if chat_id and not live_details.get("actualEndTime"):
                        vid = v["id"]
                        title = v["snippet"]["title"]
                        print(f"Instant-detected live stream via Uploads: {title} ({vid})", flush=True)
                        return vid, chat_id
        except Exception as e:
            print(f"Uploads playlist check warning: {e}", flush=True)

    # Method 2: Fallback to YouTube Search API
    try:
        res = youtube.search().list(
            part="id,snippet",
            channelId=channel_id,
            eventType="live",
            type="video",
            maxResults=1
        ).execute()
        items = res.get("items", [])
        if items:
            vid = items[0]["id"]["videoId"]
            title = items[0]["snippet"]["title"]
            chat_id = get_live_chat_id(youtube, vid, channel_id)
            if chat_id and chat_id != "RETRY":
                print(f"Auto-detected live stream via Search: {title} ({vid})", flush=True)
                return vid, chat_id
    except Exception as e:
        print(f"Search fallback warning: {e}", flush=True)

    return None, None


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
    target_channel_id, uploads_playlist_id = get_target_channel_info(youtube)
    if not target_channel_id:
        return

    if VIDEO_ID_OR_URL:
        video_id = extract_video_id(VIDEO_ID_OR_URL)
        live_chat_id = get_live_chat_id(youtube, video_id, target_channel_id)
    else:
        video_id, live_chat_id = find_active_stream(youtube, target_channel_id, uploads_playlist_id)

    if not video_id or not live_chat_id or live_chat_id == "RETRY":
        print("@T1RANJHA is not live right now. Exiting check cleanly.", flush=True)
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

        sleep_time = random.randint(65, 110)
        print(f"Waiting {sleep_time} seconds before next message...", flush=True)
        time.sleep(sleep_time)


if __name__ == "__main__":
    main()
            
