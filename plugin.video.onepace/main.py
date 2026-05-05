import sys
import xbmcplugin
import xbmcgui
import xbmc
import urllib.request
import urllib.parse
import json

ADDON_ID = "plugin.video.onepace"
ARC_DATA = {
    "romance-dawn": {"title": "1. Romance Dawn", "list_id": "At73d5SH"},
    "orange-town": {"title": "2. Orange Town", "list_id": "WEJNxGhq"},
    "syrup-village": {"title": "3. Syrup Village", "list_id": "wZSPLqpA"},
    "gaimon": {"title": "4. Gaimon", "list_id": "GSCf3j5A"},
    "baratie": {"title": "5. Baratie", "list_id": "JR7mF2uG"},
    "arlong-park": {"title": "6. Arlong Park", "list_id": "UyNWVSbD"},
    "buggy-crew": {"title": "7. The Adventures of Buggy's Crew", "list_id": "E1QXSY7a"},
    "loguetown": {"title": "8. Loguetown", "list_id": "sng6aHYQ"},
    "reverse-mountain": {"title": "9. Reverse Mountain", "list_id": "gehq5RGo"},
    "whisky-peak": {"title": "10. Whisky Peak", "list_id": "5d4WRz1y"},
    "koby-meppo": {"title": "11. The Trials of Koby-Meppo", "list_id": "81KWfWcq"},
    "little-garden": {"title": "12. Little Garden", "list_id": "89ocLnCv"},
    "drum-island": {"title": "13. Drum Island", "list_id": "4juJksu7"},
    "alabasta": {"title": "14. Alabasta", "list_id": "m6uYD3ir"},
    "jaya": {"title": "15. Jaya", "list_id": "P6mnmZpN"},
    "skypiea": {"title": "16. Skypiea", "list_id": "q4HPAiL4"},
    "long-ring-long-land": {"title": "17. Long Ring Long Land", "list_id": "opsghUMA"},
    "water-seven": {"title": "18. Water Seven", "list_id": "o8YkGt9i"},
    "enies-lobby": {"title": "19. Enies Lobby", "list_id": "543jMNry"},
    "post-enies-lobby": {"title": "20. Post-Enies Lobby", "list_id": "upyN5vVk"},
    "thriller-bark": {"title": "21. Thriller Bark", "list_id": "Cq9faLGv"},
    "sabaody": {"title": "22. Sabaody Archipelago", "list_id": "jhpKUqF8"},
    "amazon-lily": {"title": "23. Amazon Lily", "list_id": "Bsr9gKsn"},
    "impel-down": {"title": "24. Impel Down", "list_id": "y5ywnHdF"},
    "straw-hat-adventures": {
        "title": "25. If You Could Go Anywhere...",
        "list_id": "cnjWovN9",
    },
    "marineford": {"title": "26. Marineford", "list_id": "uFuFpnpi"},
    "post-war": {"title": "27. Post-War", "list_id": "7EANMSA7"},
    "return-sabaody": {"title": "28. Return to Sabaody", "list_id": "igysH62b"},
    "fishman-island": {"title": "29. Fishman Island", "list_id": "o6ZzNwzp"},
    "punk-hazard": {"title": "30. Punk Hazard", "list_id": "wJoipMZu"},
    "dressrosa": {"title": "31. Dressrosa", "list_id": "DMuj2Pqe"},
    "zou": {"title": "32. Zou", "list_id": "nSkEY2Cq"},
    "whole-cake-island": {"title": "33. Whole Cake Island", "list_id": "phsTwRmF"},
    "reverie": {"title": "34. Reverie", "list_id": "FnBXXzXi"},
    "wano": {"title": "35. Wano", "list_id": "Fje5h8U7"},
    "egghead": {"title": "36. Egghead", "list_id": "uA4CjnkS"},
    "fan-letter": {"title": "Special: One Piece Fan Letter", "list_id": "cTvXTid9"},
}
_HANDLE = int(sys.argv[1])


def arc_image(arc_id):
    return f"special://home/addons/{ADDON_ID}/resources/posters/{arc_id}.jpg"


def fetch_pixeldrain_list(list_id):
    url = "https://pixeldrain.com/api/list/" + list_id
    try:
        req = urllib.request.urlopen(url, timeout=10)
        data = req.read().decode("utf-8")
        req.close()
        return json.loads(data)
    except Exception as e:
        xbmc.log("One Pace: Failed to fetch list " + list_id + ": " + str(e))
        return {"success": False, "files": []}


def get_params():
    params = sys.argv[2]
    if not params:
        return {}
    args = {}
    for param in params[1:].split("&"):
        if "=" in param:
            key, value = param.split("=", 1)
            args[key] = urllib.parse.unquote(value)
    return args


def show_root():

    xbmcplugin.setContent(_HANDLE, "tvshows")
    xbmcplugin.addSortMethod(_HANDLE, xbmcplugin.SORT_METHOD_NONE)
    xbmcplugin.setPluginCategory(_HANDLE, "One Pace")

    i = 1
    for arc_id, arc_data in ARC_DATA.items():
        list_item = xbmcgui.ListItem(label=arc_data["title"], offscreen=True)
        image = arc_image(i)
        list_item.setArt({"thumb": image})
        url = sys.argv[0] + "?action=arc&arc_id=" + arc_id
        xbmcplugin.addDirectoryItem(
            handle=int(sys.argv[1]), url=url, listitem=list_item, isFolder=True
        )
        i = i + 1
    xbmcplugin.endOfDirectory(_HANDLE, cacheToDisc=True)


def show_arc(arc_id):
    arc_data = ARC_DATA.get(arc_id, {})
    list_id = arc_data.get("list_id", "")

    if not list_id:
        xbmcgui.Dialog().ok("One Pace", "No list ID for this arc.")
        return

    list_data = fetch_pixeldrain_list(list_id)

    if not list_data.get("success"):
        xbmcgui.Dialog().ok("One Pace", "Failed to fetch episodes from Pixeldrain")
        return

    files = list_data.get("files", [])
    for f in files:
        file_id = f.get("id", "")
        name = f.get("name", "Unknown")
        size_mb = f.get("size", 0) / (1024 * 1024)
        title = name + " (" + str(int(size_mb)) + "MB)"
        video_url = "https://pixeldrain.com/api/file/" + file_id + "?download"
        list_item = xbmcgui.ListItem(label=title)
        list_item.setInfo("video", {"title": name})
        list_item.setProperty("IsPlayable", "true")
        list_item.setProperty("mimetype", "video/mp4")
        url = sys.argv[0] + "?action=play&url=" + urllib.parse.quote(video_url)
        xbmcplugin.addDirectoryItem(
            handle=_HANDLE, url=url, listitem=list_item, isFolder=False
        )
    xbmcplugin.endOfDirectory(_HANDLE)


def play_video(url):
    if not url:
        xbmcgui.Dialog().ok("One Pace", "No URL available")
        return
    list_item = xbmcgui.ListItem(label="One Pace")
    list_item.setProperty("IsPlayable", "true")
    list_item.setPath(url)
    xbmcplugin.setResolvedUrl(handle=_HANDLE, succeeded=True, listitem=list_item)


def run():
    params = get_params()
    action = params.get("action", "root")

    if action == "root":
        show_root()
    elif action == "arc":
        arc_id = params.get("arc_id", "")
        show_arc(arc_id)
    elif action == "play":
        url = params.get("url", "")
        play_video(url)
    else:
        show_root()


if __name__ == "__main__":
    run()
