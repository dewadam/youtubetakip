#!/usr/bin/env python3
"""YouTube kanal istatistiklerini çeker ve docs/data/stats.json'a kaydeder."""
import json, os, re, sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parent.parent
CHANNELS_FILE = ROOT / "channels.json"
STATS_FILE = ROOT / "docs" / "data" / "stats.json"
API_BASE = "https://www.googleapis.com/youtube/v3"
API_KEY = os.environ.get("YOUTUBE_API_KEY")
MAX_VIDEOS_PER_CHANNEL = 20
HISTORY_LIMIT = 700

def api_get(endpoint, **params):
    params["key"] = API_KEY
    url = f"{API_BASE}/{endpoint}?{urlencode(params)}"
    try:
        with urlopen(url, timeout=30) as r:
            return json.load(r)
    except HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()}", file=sys.stderr)
        raise

def resolve_channel(identifier):
    m = re.search(r"youtube\.com/@([\w.\-]+)", identifier)
    if m: identifier = "@" + m.group(1)
    m = re.search(r"channel/(UC[\w\-]+)", identifier)
    if m: identifier = m.group(1)
    if identifier.startswith("UC") and len(identifier) > 20:
        res = api_get("channels", part="snippet,statistics,contentDetails", id=identifier)
    elif identifier.startswith("@"):
        res = api_get("channels", part="snippet,statistics,contentDetails", forHandle=identifier)
    else:
        s = api_get("search", part="snippet", type="channel", q=identifier, maxResults=1)
        if not s.get("items"): return None
        cid = s["items"][0]["id"]["channelId"]
        res = api_get("channels", part="snippet,statistics,contentDetails", id=cid)
    items = res.get("items") or []
    return items[0] if items else None

def fetch_channel_videos(uploads_playlist_id, max_results=20):
    pl = api_get("playlistItems", part="contentDetails",
                 playlistId=uploads_playlist_id, maxResults=max_results)
    video_ids = [i["contentDetails"]["videoId"] for i in pl.get("items", [])]
    if not video_ids: return []
    vids = api_get("videos", part="snippet,statistics", id=",".join(video_ids))
    out = []
    for v in vids.get("items", []):
        st = v.get("statistics", {}); sn = v.get("snippet", {})
        out.append({
            "videoId": v["id"], "title": sn.get("title", ""),
            "published": sn.get("publishedAt", ""),
            "thumbnail": sn.get("thumbnails", {}).get("medium", {}).get("url", ""),
            "views": int(st.get("viewCount", 0)),
            "likes": int(st.get("likeCount", 0)),
            "comments": int(st.get("commentCount", 0)),
        })
    return out

def load_json(path, default):
    if path.exists():
        try: return json.loads(path.read_text(encoding="utf-8"))
        except Exception: return default
    return default

def main():
    if not API_KEY:
        print("HATA: YOUTUBE_API_KEY yok.", file=sys.stderr); sys.exit(1)
    config = load_json(CHANNELS_FILE, {"channels": []})
    identifiers = config.get("channels", [])
    if not identifiers:
        print("channels.json boş."); return
    stats = load_json(STATS_FILE, {"channels": {}, "videos": [], "lastUpdated": None})
    stats.setdefault("channels", {}); stats.setdefault("videos", [])
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for ident in identifiers:
        try:
            ch = resolve_channel(ident)
            if not ch:
                print(f"UYARI: {ident} bulunamadı"); continue
            cid = ch["id"]; sn = ch["snippet"]; st = ch["statistics"]
            uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
            entry = stats["channels"].get(cid, {
                "id": cid, "title": sn["title"],
                "thumbnail": sn["thumbnails"]["default"]["url"], "history": []
            })
            entry["title"] = sn["title"]
            entry["thumbnail"] = sn["thumbnails"]["default"]["url"]
            snap = {"ts": now_iso,
                    "subs": int(st.get("subscriberCount", 0)),
                    "views": int(st.get("viewCount", 0)),
                    "videos": int(st.get("videoCount", 0))}
            entry["lastSnapshot"] = snap
            entry["history"].append(snap)
            if len(entry["history"]) > HISTORY_LIMIT:
                entry["history"] = entry["history"][-HISTORY_LIMIT:]
            stats["channels"][cid] = entry
            vids = fetch_channel_videos(uploads, MAX_VIDEOS_PER_CHANNEL)
            stats["videos"] = [v for v in stats["videos"] if v.get("channelId") != cid]
            for v in vids:
                v["channelId"] = cid; v["channelTitle"] = sn["title"]
                stats["videos"].append(v)
            print(f"OK {sn['title']}: {len(vids)} video")
        except Exception as e:
            print(f"HATA {ident}: {e}", file=sys.stderr)
    stats["lastUpdated"] = now_iso
    STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATS_FILE.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Kaydedildi: {STATS_FILE}")

if __name__ == "__main__":
    main()
