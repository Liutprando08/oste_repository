import sys
import os
from urllib.parse import parse_qsl, urlencode


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))

import yt_dlp
import xbmcaddon
import xbmcgui
import xbmcplugin

ADDON = xbmcaddon.Addon()
BASE_URL = sys.argv[0]
HANDLE = int(sys.argv[1])

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
    ]
    for label, params in items:
        url = BASE_URL + "?" + urlencode(params)
        li = xbmcgui.ListItem(label)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, isFolder=True)
    xbmcplugin.endOfDirectory(HANDLE)


def search():
    query = xbmcgui.Dialog().input("Search")
    if not query:
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        return

    try:
        opts = ydl_opts_base()
        with yt_dlp.YoutubeDL(opts) as ydl:
            result = ydl.extract_info(f"ytsearch20:{query}", download=False)
            entries = result.get("entries", [])
        listVideos(entries)
    except Exception as e:
        xbmcgui.Dialog().notification("Search error", str(e)[:100])
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)


def trending():
    try:
        country = get_country()
        opts = ydl_opts_base()
        with yt_dlp.YoutubeDL(opts) as ydl:
            result = ydl.extract_info(
                f"ytsearch15:trending in {country} ",
                download=False,
            )
            entries = result.get("entries", [])
        listVideos(entries)
    except Exception as e:
        xbmcgui.Dialog().notification("Trending error", str(e)[:100])
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)


def listVideos(entries):
    quality = get_quality()
    for v in entries:
        vid_id = v.get("id") or v.get("url", "").split("v=")[-1]
        title = v.get("title") or v.get("ie_key", "Unknown")
        thumb = v.get("thumbnail") or (v.get("thumbnails") or [{}])[0].get("url", "")

        if not vid_id or vid_id.startswith("http"):
            continue

        params = {"action": "play", "id": vid_id, "quality": quality}
        url = BASE_URL + "?" + urlencode(params)

        li = xbmcgui.ListItem(title)
        li.setArt({"thumb": thumb, "fanart": thumb})
        li.setInfo("video", {"title": title})
        li.setProperty("IsPlayable", "true")
        xbmcplugin.addDirectoryItem(HANDLE, url, li, isFolder=False)

    xbmcplugin.endOfDirectory(HANDLE)


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


def router():
    params = dict(parse_qsl(sys.argv[2].lstrip("?")))
    action = params.get("action")

    if not action:
        mainMenu()
    elif action == "search":
        search()
    elif action == "trending":
        trending()
    elif action == "play":
        play(params["id"], params.get("quality", "720"))


router()
