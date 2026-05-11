import sys
import os
from urllib.parse import parse_qsl, urlencode
from collections import deque


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))
import yt_dlp
import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmc
import json
import xbmcvfs
import threading

ADDON = xbmcaddon.Addon()
BASE_URL = sys.argv[0]
HANDLE = int(sys.argv[1])
recent_queued_ids = deque(maxlen=10)
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

_queue_stop_event = threading.Event()
_queue_lock = threading.Lock()


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
        li.getVideoInfoTag().setTitle(title)
        if duration is not None:
            li.getVideoInfoTag().setDuration(duration)
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
        li.getVideoInfoTag().setTitle(title)
        duration = v.get("duration")
        if duration:
            li.getVideoInfoTag().setDuration(duration)
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
        f"best[height<={quality}][fps<=30][ext=mp4][acodec!=none][vcodec!=none]"
        f"/best[height<={quality}][ext=mp4][acodec!=none][vcodec!=none]"
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
            "socket_timeout": 15,
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


def queue_item(next_id, title="", quality="720"):
    params = {"action": "play", "id": next_id, "quality": quality, "title": title}
    plugin_url = BASE_URL + "?" + urlencode(params)

    li = xbmcgui.ListItem(label=title or next_id, path=plugin_url)
    li.setProperty("IsPlayable", "true")

    playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
    playlist.add(url=plugin_url, listitem=li)

    with _queue_lock:
        recent_queued_ids.append(next_id)


def _ytsearch_fallback(vid_id, title, count):
    query = f"ytsearch{count}:{title} similar"
    search_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": True,
        "socket_timeout": 15,
    }
    try:
        with yt_dlp.YoutubeDL(search_opts) as ydl:
            result = ydl.extract_info(query, download=False)
        entries = result.get("entries", [])
    except Exception:
        return []
    with _queue_lock:
        current_queued = list(recent_queued_ids)
    candidates = [
        entry
        for entry in entries
        if entry.get("id")
        and entry["id"] not in current_queued
        and entry["id"] != vid_id
    ]
    return candidates


def queue_related_videos(vid_id, quality="720", count=3, title=""):
    flat_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": True,
        "socket_timeout": 15,
    }
    try:
        with yt_dlp.YoutubeDL(flat_opts) as ydl:
            info = ydl.extract_info(
                f"https://www.youtube.com/watch?v={vid_id}&list=RD{vid_id}",
                download=False,
            )
        with _queue_lock:
            current_queued = list(recent_queued_ids)
        candidates = [
            entry
            for entry in info.get("entries", [])[1:]
            if "id" in entry and entry["id"] not in current_queued
        ]
    except Exception:
        candidates = _ytsearch_fallback(vid_id, title, count)
        if not candidates:
            return

    queued = 0
    for entry in candidates:
        if _queue_stop_event.is_set():
            break
        if queued >= count:
            break
        try:
            next_id = entry["id"]
            title = entry.get("title", next_id)
            queue_item(next_id, title=title, quality=quality)
            queued += 1
        except Exception:
            continue

    if queued > 0:
        msg = f"{queued} related video{'s' if queued > 1 else ''} queued"
        xbmcgui.Dialog().notification("TubeLink", msg, xbmcgui.NOTIFICATION_INFO, 3000)


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
        _queue_stop_event.clear()
        threading.Thread(
            target=queue_related_videos,
            args=(
                params["id"],
                params.get("quality", "720"),
                3,
                params.get("title", ""),
            ),
            daemon=True,
        ).start()


router()
