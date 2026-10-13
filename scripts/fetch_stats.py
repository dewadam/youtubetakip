#!/usr/bin/env python3
"""YouTube kanal istatistiklerini çeker ve docs/data/stats.json'a kaydeder."""
import json, os, re, sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, unquote, urlparse
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
        body = e.read().decode("utf-8", errors="replace")
        print(f"YouTube API HTTP {e.code} ({endpoint}): {body}", file=sys.stderr)
        raise

def normalize_channel_identifier(identifier):
    """Kanal URL'sini, kanal kimliğini veya @handle değerini normalize eder."""
    value = unquote(str(identifier or "").strip())
    if not value:
        return ""

    # Hem www.youtube.com hem youtube.com URL'lerini destekle.
    if "youtube.com" in value.lower():
        parsed = urlparse(value if "://" in value else "https://" + value)
        path = parsed.path.rstrip("/")
        match = re.match(r"^/channel/(UC[\w-]+)", path, re.IGNORECASE)
        if match:
            return match.group(1)
        match = re.match(r"^/@([^/]+)", path)
        if match:
            return "@" + match.group(1).lstrip("@")
        match = re.match(r"^/(?:c|user)/([^/]+)", path)
        if match:
            return match.group(1)
        # URL beklenmeyen biçimdeyse query olarak kullanmak yerine açık hata ver.
        raise ValueError(f"Desteklenmeyen YouTube kanal URL'si: {identifier}")

    match = re.search(r"(?:^|/)channel/(UC[\w-]+)", value)
    if match:
        return match.group(1)
    if value.startswith("@"):
        return value
    if value.startswith("UC") and len(value) >= 20:
        return value
    return value

def resolve_channel(identifier):
    normalized = normalize_channel_identifier(identifier)
    if not normalized:
        return None

    common = dict(part="snippet,statistics,contentDetails")
    if normalized.startswith("UC") and len(normalized) >= 20:
        res = api_get("channels", **common, id=normalized)
    elif normalized.startswith("@"):
        # YouTube Data API v3 forHandle parametresi @ işaretiyle birlikte verilir.
        res = api_get("channels", **common, forHandle=normalized)
    else:
        # Eski /c/ ve /user/ URL'leri handle değildir; aramayla çözümle.
        s = api_get("search", part="snippet", type="channel",
                    q=normalized, maxResults=5)
        items = s.get("items") or []
        if not items:
            return None
        channel_ids = [i.get("id", {}).get("channelId") for i in items]
        channel_ids = [cid for cid in channel_ids if cid]
        if not channel_ids:
            return None
        res = api_get("channels", **common, id=",".join(channel_ids))

    items = res.get("items") or []
    return items[0] if items else None

def fetch_channel_videos(uploads_playlist_id, max_results=20):
    pl = api_get("playlistItems", part="contentDetails",
                 playlistId=uploads_playlist_id, maxResults=max_results)
    video_ids = [i["contentDetails"]["videoId"] for i in pl.get("items", [])
                 if i.get("contentDetails", {}).get("videoId")]
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
    failures = 0
    for ident in identifiers:
        try:
            ch = resolve_channel(ident)
            if not ch:
                failures += 1
                print(f"UYARI: Kanal bulunamadı: {ident}", file=sys.stderr)
                continue
            cid = ch["id"]; sn = ch.get("snippet", {}); st = ch.get("statistics", {})
            uploads = ch.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
            if not uploads:
                raise ValueError("Kanalın yüklemeler oynatma listesi bulunamadı")

            entry = stats["channels"].get(cid, {
                "id": cid, "title": sn.get("title", cid),
                "thumbnail": sn.get("thumbnails", {}).get("default", {}).get("url", ""),
                "history": []
            })
            entry["title"] = sn.get("title", cid)
            entry["thumbnail"] = sn.get("thumbnails", {}).get("default", {}).get("url", "")
            snap = {"ts": now_iso,
                    "subs": int(st.get("subscriberCount", 0)),
                    "views": int(st.get("viewCount", 0)),
                    "videos": int(st.get("videoCount", 0))}
            entry["lastSnapshot"] = snap
            entry.setdefault("history", []).append(snap)
            if len(entry["history"]) > HISTORY_LIMIT:
                entry["history"] = entry["history"][-HISTORY_LIMIT:]
            stats["channels"][cid] = entry

            vids = fetch_channel_videos(uploads, MAX_VIDEOS_PER_CHANNEL)
            stats["videos"] = [v for v in stats["videos"] if v.get("channelId") != cid]
            for v in vids:
                v["channelId"] = cid
                v["channelTitle"] = sn.get("title", cid)
                stats["videos"].append(v)
            print(f"OK {sn.get('title', cid)} ({cid}): {len(vids)} video")
        except Exception as e:
            failures += 1
            print(f"HATA {ident}: {type(e).__name__}: {e}", file=sys.stderr)

    # En az bir kanal başarıyla çekildiyse güncelleme zamanını yaz.
    if len(stats["channels"]) > 0:
        stats["lastUpdated"] = now_iso
        STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATS_FILE.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Kaydedildi: {STATS_FILE}")
    if failures:
        print(f"UYARI: {failures} kanal işlenemedi.", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
