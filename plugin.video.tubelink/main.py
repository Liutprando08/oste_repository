import sys
import os
from urllib.parse import parse_qsl, urlencode


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))
import re
import yt_dlp
import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmc
import json
import xbmcvfs

ADDON = xbmcaddon.Addon()
BASE_URL = sys.argv[0]
HANDLE = int(sys.argv[1])

recent_queued_ids = []
MAX_RECENT = 10
SKIP_WORDS = {
    "official",
    "video",
    "audio",
    "lyrics",
    "lyric",
    "hd",
    "hq",
    "mv",
    "music",
    "remix",
    "cover",
    "live",
    "version",
    "ft",
    "feat",
    "full",
    "extended",
    "explicit",
    "clean",
}
QUALITIES = ["360", "480", "720", "1080"]
COUNTRY = [
    "United States",
    "United Kingdom",
    "Canada",
    "Australia",
    "Germany",
    "France",
    "Italy",
    "Spain",
    "Japan",
    "China",
    "India",
    "Brazil",
    "Mexico",
    "Russia",
    "South Korea",
    "Netherlands",
    "Sweden",
    "Norway",
    "Denmark",
    "Finland",
    "Poland",
    "Turkey",
    "South Africa",
    "Argentina",
    "Egypt",
    "Saudi Arabia",
    "UAE",
    "Singapore",
    "Thailand",
    "Vietnam",
    "Philippines",
    "Indonesia",
    "Malaysia",
    "New Zealand",
    "Ireland",
    "Portugal",
    "Greece",
    "Belgium",
    "Austria",
    "Switzerland",
    "Czech Republic",
    "Romania",
    "Hungary",
    "Israel",
    "Nigeria",
    "Kenya",
    "Morocco",
    "Pakistan",
    "Bangladesh",
    "Sri Lanka",
    "Chile",
    "Colombia",
    "Peru",
    "Venezuela",
    "Ukraine",
]


def get_country():
    try:
        return COUNTRY[int(ADDON.getSetting("country"))]
    except (ValueError, IndexError):
        return "United States"


def get_quality():
    try:
        return QUALITIES[int(ADDON.getSetting("quality"))]
    except (ValueError, IndexError):
        return "720"


def get_save_path():
    save_dir = "special://userdata/addon_data/plugin.video.tubelink/"
    xbmcvfs.mkdirs(save_dir)
    return f"{save_dir}saved_videos.json"


def load_save():
    save = get_save_path()
    if not xbmcvfs.exists(save):
        return []
    try:
        with xbmcvfs.File(save, "r") as f:
            content = f.read()
        return json.loads(content) if content.strip() else []
    except (json.JSONDecodeError, Exception):
        return []


def save_saved(videos):
    save = get_save_path()
    try:
        with xbmcvfs.File(save, "w") as f:
            f.write(json.dumps(videos, indent=2))
    except Exception:
        pass


def ydl_opts_base():
    return {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
    }


def mainMenu():
    items = [
        ("Search", {"action": "search"}),
        ("Trending", {"action": "trending"}),
        ("Saved videos", {"action": "saved_videos"}),
    ]
    for label, params in items:
        url = BASE_URL + "?" + urlencode(params)
        li = xbmcgui.ListItem(label)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, isFolder=True)
    xbmcplugin.endOfDirectory(HANDLE)


def search(query=None, page=1):
    if not query:
        query = xbmcgui.Dialog().input("Search")
        if not query:
            xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
            return
    try:
        offset = (page - 1) * 20
        search_query = (
            f"ytsearch20:start{offset}:{query}" if offset > 0 else f"ytsearch20:{query}"
        )
        opts = ydl_opts_base()
        with yt_dlp.YoutubeDL(opts) as ydl:
            result = ydl.extract_info(search_query, download=False)
            entries = result.get("entries", [])
        listVideos(entries, mode="search", query=query, page=page)
    except Exception as e:
        xbmcgui.Dialog().notification("Search error", str(e)[:100])
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)


def trending(page=1):
    try:
        country = get_country()
        offset = (page - 1) * 20
        trend_query = f"ytsearch20:start{offset}:trending in {country}"
        opts = ydl_opts_base()
        with yt_dlp.YoutubeDL(opts) as ydl:
            result = ydl.extract_info(
                trend_query,
                download=False,
            )
            entries = result.get("entries", [])
        listVideos(entries, mode="trending", page=page)
    except Exception as e:
        xbmcgui.Dialog().notification("Trending error", str(e)[:100])
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)


def listVideos(entries, mode=None, query=None, page=1):
    quality = get_quality()
    for v in entries:
        vid_id = v.get("id") or v.get("url", "").split("v=")[-1]
        title = v.get("title") or v.get("ie_key", "Unknown")
        thumb = v.get("thumbnail") or (v.get("thumbnails") or [{}])[0].get("url", "")
        duration = v.get("duration")

        if not vid_id or vid_id.startswith("http"):
            continue

        if duration is not None and isinstance(duration, (int, float)):
            duration = int(duration)
            hrs = duration // 3600
            mins = (duration % 3600) // 60
            secs = duration % 60
            if hrs > 0:
                duration_str = f"[{hrs:02d}:{mins:02d}:{secs:02d}] "
            else:
                duration_str = f"[{mins:02d}:{secs:02d}] "
            title = duration_str + title

        params = {"action": "play", "id": vid_id, "quality": quality, "title": title}
        url = BASE_URL + "?" + urlencode(params)

        li = xbmcgui.ListItem(title)
        li.setArt({"thumb": thumb, "fanart": thumb})
        info = {"title": title}
        if duration is not None:
            info["duration"] = duration
        li.setInfo("video", info)
        li.setProperty("IsPlayable", "true")
        save_params = {
            "action": "save_video",
            "id": vid_id,
            "title": title,
            "thumb": thumb,
            "duration": str(duration) if duration is not None else "",
        }
        save_url = BASE_URL + "?" + urlencode(save_params)
        li.addContextMenuItems([("Save to Favorites", f"RunPlugin({save_url})")])
        xbmcplugin.addDirectoryItem(HANDLE, url, li, isFolder=False)
    if entries and mode:
        next_params = {"action": mode, "page": str(page + 1)}
        if query:
            next_params["query"] = query
        next_url = BASE_URL + "?" + urlencode(next_params)
        next_li = xbmcgui.ListItem("--- Next Page ---")
        xbmcplugin.addDirectoryItem(HANDLE, next_url, next_li, isFolder=True)
    xbmcplugin.endOfDirectory(HANDLE)


def save_video(vid_id, title, thumb, duration_str):
    videos = load_save()
    videos.append(
        {
            "id": vid_id,
            "title": title,
            "thumb": thumb,
            "duration": int(duration_str) if duration_str.isdigit() else 0,
        }
    )
    save_saved(videos)


def list_saved_videos():
    videos = load_save()
    quality = get_quality()

    for idx, v in enumerate(videos):
        vid_id = v.get("id")
        title = v.get("title", "Unknown")
        thumb = v.get("thumb", "")

        params = {"action": "play", "id": vid_id, "quality": quality, "title": title}
        url = BASE_URL + "?" + urlencode(params)

        li = xbmcgui.ListItem(title)
        li.setArt({"thumb": thumb, "fanart": thumb})
        duration = v.get("duration")
        info = {"title": title}
        if duration:
            info["duration"] = duration
        li.setInfo("video", info)
        li.setProperty("IsPlayable", "true")
        remove_params = {"action": "remove_saved", "index": str(idx)}
        remove_url = BASE_URL + "?" + urlencode(remove_params)
        li.addContextMenuItems([("Remove from Saved", f"RunPlugin({remove_url})")])
        xbmcplugin.addDirectoryItem(HANDLE, url, li, isFolder=False)
    xbmcplugin.endOfDirectory(HANDLE)


def remove_saved(index_str):
    videos = load_save()
    try:
        idx = int(index_str)
        if 0 <= idx < len(videos):
            videos.pop(idx)
            save_saved(videos)
    except ValueError:
        pass


def play(vid_id, quality):
    yt_url = f"https://www.youtube.com/watch?v={vid_id}"

    fmt = (
        f"best[height<={quality}][ext=mp4][acodec!=none][vcodec!=none]"
        f"/best[ext=mp4][acodec!=none][vcodec!=none]"
        f"/best[ext=mp4]"
        f"/best"
    )

    try:
        opts = {
            "quiet": True,
            "no_warnings": True,
            "format": fmt,
            "skip_download": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(yt_url, download=False)

        stream_url = info.get("url")

        if not stream_url:
            formats = info.get("formats", [])
            progressive = [
                f
                for f in formats
                if f.get("ext") == "mp4"
                and f.get("acodec") not in (None, "none")
                and f.get("vcodec") not in (None, "none")
            ]
            if progressive:
                stream_url = progressive[-1]["url"]
            elif formats:
                stream_url = formats[-1]["url"]

        if not stream_url:
            raise ValueError("No playable stream found")

        li = xbmcgui.ListItem(path=stream_url)
        li.setMimeType("video/mp4")
        li.setProperty("IsPlayable", "true")
        xbmcplugin.setResolvedUrl(HANDLE, True, li)

    except Exception as e:
        xbmcgui.Dialog().notification("Playback error", str(e)[:100])
        xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())


"""
def title_similarity(a, b):
    def tokens(s):
        return set(re.sub(r"[^a-z0-9\s]", "", s.lower()).split())

    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta), len(tb))


def clean_title_for_search(title):
    title = re.sub(r"^\[\d+:\d+(?::\d+)?\]\s*", "", title)
    title = re.sub(r"[\(\[][^\)\]]*[\)\]]", "", title)
    title = re.sub(r"\bft\.?\b.*", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\bfeat\.?\b.*", "", title, flags=re.IGNORECASE)
    words = [w for w in title.split() if w.lower() not in SKIP_WORDS]
    return " ".join(words[:5]).strip()


def queue_item(params):
    try:
        vid_id = params["id"]
        title = params["title"]
        quality = params.get("quality", "720")

        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": False,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(
                f"https://www.youtube.com/watch?v={vid_id}", download=False
            )

        source_channel = info.get("channel_id") or info.get("uploader_id", "")
        related = info.get("related_videos", [])

        SIMILARITY_THRESHOLD = 0.4

        def is_acceptable(v, current_title, current_id):
            rid = v.get("id") or v.get("url", "").split("v=")[-1]
            if not rid or rid == current_id:
                return False
            if rid in recent_queued_ids:
                return False
            if source_channel and v.get("channel_id") == source_channel:
                return False
            if (
                title_similarity(current_title, v.get("title", ""))
                > SIMILARITY_THRESHOLD
            ):
                return False
            return True

        rel_vid = next((v for v in related if is_acceptable(v, title, vid_id)), None)

        if not rel_vid:
            clean_query = clean_title_for_search(title)
            search_query = f"ytsearch10:{clean_query} mix"
            with yt_dlp.YoutubeDL(ydl_opts_base()) as ydl:
                search_result = ydl.extract_info(search_query, download=False)
                candidates = search_result.get("entries", [])

            rel_vid = next(
                (v for v in candidates if is_acceptable(v, title, vid_id)), None
            )

        if not rel_vid:
            xbmcgui.Dialog().notification("Queue", "No suitable related video found")
            return

        rel_id = rel_vid.get("id") or rel_vid.get("url", "").split("v=")[-1]

        fmt = (
            f"best[height<={quality}][ext=mp4][acodec!=none][vcodec!=none]"
            f"/best[ext=mp4][acodec!=none][vcodec!=none]"
            f"/best[ext=mp4]/best"
        )
        with yt_dlp.YoutubeDL(
            {"quiet": True, "no_warnings": True, "format": fmt, "skip_download": True}
        ) as ydl:
            rel_info = ydl.extract_info(
                f"https://www.youtube.com/watch?v={rel_id}", download=False
            )

        stream_url = rel_info.get("url")
        if not stream_url:
            formats = rel_info.get("formats", [])
            progressive = [
                f
                for f in formats
                if f.get("ext") == "mp4"
                and f.get("acodec") not in (None, "none")
                and f.get("vcodec") not in (None, "none")
            ]
            stream_url = (
                progressive[-1]["url"]
                if progressive
                else (formats[-1]["url"] if formats else None)
            )

        if not stream_url:
            raise ValueError("No playable stream for related video")

        playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
        li = xbmcgui.ListItem(rel_vid.get("title", "Related Video"))
        li.setMimeType("video/mp4")
        li.setProperty("IsPlayable", "true")
        playlist.add(stream_url, li)
        xbmcgui.Dialog().notification("Queued", rel_vid.get("title", "")[:50])

        recent_queued_ids.append(rel_id)
        if len(recent_queued_ids) > MAX_RECENT:
            recent_queued_ids.pop(0)

        xbmcplugin.setResolvedUrl(HANDLE, True, li)

    except KeyError as e:
        xbmcgui.Dialog().notification("Queue Error", f"Missing parameter: {str(e)}")
    except Exception as e:
        xbmcgui.Dialog().notification("Queue Error", str(e)[:100])
"""


def router():
    params = dict(parse_qsl(sys.argv[2].lstrip("?")))
    action = params.get("action")

    if not action:
        mainMenu()
    elif action == "search":
        search(query=params.get("query"), page=int(params.get("page", "1")))
    elif action == "trending":
        trending(page=int(params.get("page", "1")))
    elif action == "saved_videos":
        list_saved_videos()
    elif action == "save_video":
        save_video(
            params.get("id"),
            params.get("title", ""),
            params.get("thumb", ""),
            params.get("duration", ""),
        )
    elif action == "remove_saved":
        remove_saved(params.get("index", "0"))
    elif action == "play":
        play(params["id"], params.get("quality", "720"))


#     queue_item(params=params)


router()
