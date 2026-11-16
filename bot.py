import os
import re
import time
import random
import urllib.request
from collections import deque
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

CLIENT_ID = "".join(os.environ.get("YT_CLIENT_ID", "").split()).strip('"\'')
CLIENT_SECRET = "".join(os.environ.get("YT_CLIENT_SECRET", "").split()).strip('"\'')
REFRESH_TOKEN = "".join(os.environ.get("YT_REFRESH_TOKEN", "").split()).strip('"\'')
VIDEO_ID_OR_URL = os.environ.get("VIDEO_ID", "").strip()

TARGET_HANDLE = "@T1RANJHA"
TARGET_CHANNEL_ID = "UCcxrFIi2FidgaUcNj2R-lUw"

# Pure dots and safe emojis only (No commands, no welcome messages)
SAFE_MESSAGES = [
    "🍿",
    "💯",
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


def scrape_channel_live_video_ids(channel_id):
    urls = [
        f"https://www.youtube.com/channel/{channel_id}/live",
        "https://www.youtube.com/@T1RANJHA/live",
        "https://www.youtube.com/@T1RANJHA/streams"
    ]
    found_ids = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }
    for url in urls:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            canon = re.findall(r'rel="canonical"\s+href="https://www\.youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})"', html)
            for vid in canon:
                if vid not in found_ids:
                    found_ids.append(vid)
            vids = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', html)
            for vid in vids[:10]:
                if vid not in found_ids:
                    found_ids.append(vid)
        except Exception as e:
            print(f"Direct page check warning ({url}): {e}", flush=True)
    return found_ids


def find_active_stream(youtube, channel_id):
    candidate_ids = scrape_channel_live_video_ids(channel_id)

    uploads_id = "UU" + channel_id[2:] if channel_id.startswith("UC") else None
    if uploads_id:
        try:
            pl_res = youtube.playlistItems().list(
                part="contentDetails",
                playlistId=uploads_id,
                maxResults=5
            ).execute()
            for item in pl_res.get("items", []):
                vid = item.get("contentDetails", {}).get("videoId")
                if vid and vid not in candidate_ids:
                    candidate_ids.append(vid)
        except Exception:
            pass

    if candidate_ids:
        try:
            v_res = youtube.videos().list(
                part="liveStreamingDetails,snippet",
                id=",".join(candidate_ids[:20])
            ).execute()
            for v in v_res.get("items", []):
                snippet = v.get("snippet", {})
                live_details = v.get("liveStreamingDetails", {})
                chat_id = live_details.get("activeLiveChatId")
                if snippet.get("channelId") == channel_id and chat_id and not live_details.get("actualEndTime"):
                    vid = v["id"]
                    title = snippet.get("title", "Live Stream")
                    print(f"LOCKED ONTO LIVE STREAM: {title} ({vid})", flush=True)
                    return vid, chat_id
        except Exception as e:
            print(f"Video verification warning: {e}", flush=True)

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


def choose_next_message(recent_history):
    available = [m for m in SAFE_MESSAGES if m not in recent_history]
    if not available:
        available = SAFE_MESSAGES
    return random.choice(available)


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


def main():
    youtube = get_youtube_client()
    target_channel_id = TARGET_CHANNEL_ID
    print(f"Locked onto Target Channel: {TARGET_HANDLE} ({target_channel_id})", flush=True)

    video_id = None
    live_chat_id = None

    if VIDEO_ID_OR_URL:
        video_id = extract_video_id(VIDEO_ID_OR_URL)
        live_chat_id = get_live_chat_id(youtube, video_id, target_channel_id)
    else:
        # STANDBY MODE: Check every 3 minutes for up to 90 minutes (30 attempts)
        for attempt in range(1, 31):
            video_id, live_chat_id = find_active_stream(youtube, target_channel_id)
            if video_id and live_chat_id and live_chat_id != "RETRY":
                break
            print(f"[Standby {attempt}/30] @T1RANJHA not live yet. Waiting 3 minutes to re-check...", flush=True)
            time.sleep(180)

    if not video_id or not live_chat_id or live_chat_id == "RETRY":
        print("@T1RANJHA did not go live during the 90-minute standby window. Exiting cleanly.", flush=True)
        return

    print(f"Connected to @T1RANJHA Live Chat ID: {live_chat_id}", flush=True)

    recent_history = deque(maxlen=4)
    consecutive_failures = 0
    start_time = time.time()

    # Farm for up to 5 hours (18000s) after stream starts
    while time.time() - start_time < 18000:
        try:
            msg = choose_next_message(recent_history)
            result = send_chat_message(youtube, live_chat_id, msg)

            if result == "ENDED":
                print("Live chat officially ended. Stopping bot safely.", flush=True)
                break
            elif result is True:
                consecutive_failures = 0
                recent_history.append(msg)
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
