# -*- coding: utf-8 -*-
#
#  plugin.audio.mp3streams-remastered — default.py  PATCH DOCUMENT
#  ─────────────────────────────────────────────────────────────────
#
#  This file documents every change needed in default.py.
#  It is NOT a runnable script.  Apply each numbered section in order.
#
#  Each section shows:
#    LOCATION   → the function name and approximate original line number
#    WHY        → root-cause explanation
#    BEFORE     → the original code (exact, ready to search-and-replace)
#    AFTER      → the replacement code
#
#  Tip: use your editor's "Replace in file" on the BEFORE block to be safe.
#  ─────────────────────────────────────────────────────────────────────────


# ══════════════════════════════════════════════════════════════════════════════
# PATCH 1 — Module-level import of playerMP3
#
# LOCATION : Top of file, line 4 (the import block)
#
# WHY : playerMP3 is currently imported inside three separate functions
#       (play_album ~985, play_song ~1115, and the mode-999 dispatcher ~2295).
#       Inline imports are not wrong, but importing once at module level is
#       cleaner, avoids repeated import overhead, and makes the dependency
#       immediately visible to anyone reading the file.
# ══════════════════════════════════════════════════════════════════════════════

# ── BEFORE ───────────────────────────────────────────────────────────────────
"""
import urllib.request, urllib.error, urllib.parse, re
import xbmcplugin, xbmcgui, xbmcvfs, os, xbmc, sys
import settings, time
import requests
from bs4 import BeautifulSoup
from threading import Thread
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3
"""

# ── AFTER ────────────────────────────────────────────────────────────────────
"""
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from threading import Thread

import requests
import xbmc
import xbmcgui
import xbmcplugin
import xbmcvfs
from bs4 import BeautifulSoup
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3

import playerMP3          # ← moved from three inline imports to module level
import settings
"""

# ── ALSO REMOVE the three inline imports that become redundant: ───────────────
#   Line  985:  import playerMP3   (inside play_album)
#   Line 1115:  import playerMP3   (inside play_song)
#   Line 2295:  import playerMP3   (inside the mode == 999 dispatch block)


# ══════════════════════════════════════════════════════════════════════════════
# PATCH 2 — GET_url()
#
# LOCATION : ~line 84
#
# WHY (3 separate bugs):
#   1. User-Agent is the literal placeholder string "AppleWebKit/<WebKit Rev>"
#      — a template that was never filled in.  The musicmp3.ru server receives
#      this string and may reject scraping requests or return unexpected HTML.
#
#   2. The Accept header for the musicmp3 branch contains a typo:
#      "udio/wav" instead of "audio/wav".
#
#   3. The Referer for the musicmp3 branch uses plain http:// instead of
#      https://.  Modern servers redirect or block bare-HTTP referrers.
# ══════════════════════════════════════════════════════════════════════════════

# ── BEFORE ───────────────────────────────────────────────────────────────────
"""
def GET_url(url):
    header_dict = {}
    if "musicmp3" in url:
        header_dict["Accept"] = (
            "audio/webm,audio/ogg,udio/wav,audio/*;q=0.9,application/ogg;q=0.7,video/*;q=0.6,*/*;q=0.5"
        )
        header_dict["User-Agent"] = "AppleWebKit/<WebKit Rev>"
        header_dict["Host"] = "musicmp3.ru"
        header_dict["Referer"] = "http://musicmp3.ru/"
        header_dict["Connection"] = "keep-alive"
    if "goldenmp3" in url:
        header_dict["Accept"] = (
            "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        )
        header_dict["User-Agent"] = ua
        header_dict["Host"] = "www.goldenmp3.ru"
        header_dict["Referer"] = "http://www.goldenmp3.ru/compilations/events/albums"
        header_dict["Connection"] = "keep-alive"

    # link = net.http_GET(url, headers=header_dict).content.encode("utf-8").rstrip()
    return requests.get(url, headers=header_dict, timeout=10).text
"""

# ── AFTER ────────────────────────────────────────────────────────────────────
"""
def GET_url(url):
    \"\"\"
    Fetch a musicmp3.ru or goldenmp3.ru page and return its HTML as a string.

    Headers are matched to the site being requested so that both CDNs
    recognise the client as a normal browser request.
    \"\"\"
    header_dict = {}

    if "musicmp3" in url:
        header_dict["Accept"] = (
            # Fixed typo: "udio/wav" → "audio/wav"
            "audio/webm,audio/ogg,audio/wav,audio/*;q=0.9,"
            "application/ogg;q=0.7,video/*;q=0.6,*/*;q=0.5"
        )
        # Fixed: was the literal placeholder string "AppleWebKit/<WebKit Rev>"
        header_dict["User-Agent"] = ua
        header_dict["Host"]       = "musicmp3.ru"
        # Fixed: was "http://" — changed to "https://"
        header_dict["Referer"]    = "https://musicmp3.ru/"
        header_dict["Connection"] = "keep-alive"

    if "goldenmp3" in url:
        header_dict["Accept"] = (
            "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        )
        header_dict["User-Agent"] = ua
        header_dict["Host"]       = "www.goldenmp3.ru"
        # Fixed: was "http://" — changed to "https://"
        header_dict["Referer"]    = "https://www.goldenmp3.ru/compilations/events/albums"
        header_dict["Connection"] = "keep-alive"

    return requests.get(url, headers=header_dict, timeout=10).text
"""


# ══════════════════════════════════════════════════════════════════════════════
# PATCH 3 — download_song()
#
# LOCATION : ~line 1157
#
# WHY (3 bugs):
#   1. User-Agent is the same "AppleWebKit/<WebKit Rev>" placeholder.
#   2. The Referer header is entirely absent.  listen.musicmp3.ru requires it
#      to serve audio; without it the server returns 403 Forbidden even for
#      direct download requests.
#   3. iter_content() is called without chunk_size, which defaults to 1 byte
#      per iteration — extremely slow for multi-megabyte audio files.
#
#   The fix replaces the hand-written header dict with playerMP3.STREAM_HEADERS,
#   which is the single authoritative definition used by the Downloader class.
#   This guarantees all three are always in sync.
# ══════════════════════════════════════════════════════════════════════════════

# ── BEFORE ───────────────────────────────────────────────────────────────────
"""
def download_song(url, name, songname, artist, album, iconimage):
    track = songname[: songname.find(".")]
    artist_path = create_directory(MUSIC_DIR, artist)
    album_path = create_directory(artist_path, album)
    list_data = "%s<>%s<>%s<>%s<>%s%s" % (
        album_path,
        artist,
        album,
        track,
        songname,
        ".mp3",
    )
    local_filename = album_path + "/" + songname + ".mp3"
    headers = {
        "Host": "listen.musicmp3.ru",
        "Range": "bytes=0-",
        "User-Agent": "AppleWebKit/<WebKit Rev>",
        "Accept": "audio/webm,audio/ogg,audio/wav,audio/*;q=0.9,application/ogg;q=0.7,video/*;q=0.6,*/*;q=0.5",
    }
    r = requests.get(url, headers=headers, stream=True)
    with open(local_filename, "wb") as f:
        for chunk in r.iter_content():  # chunk_size=1024
            if chunk:
                f.write(chunk)
                f.flush()
    # urllib.urlretrieve(url, local_filename)
    add_to_list(list_data, DOWNLOAD_LIST, False)
"""

# ── AFTER ────────────────────────────────────────────────────────────────────
"""
def download_song(url, name, songname, artist, album, iconimage):
    \"\"\"
    Download a single track to the permanent music library directory.

    Uses playerMP3.STREAM_HEADERS — the canonical header definition — so that
    Host, User-Agent, Accept, and Referer are always correct and consistent
    with every other request made to listen.musicmp3.ru.
    \"\"\"
    track       = songname[: songname.find(".")]
    artist_path = create_directory(MUSIC_DIR, artist)
    album_path  = create_directory(artist_path, album)

    list_data = "%s<>%s<>%s<>%s<>%s%s" % (
        album_path, artist, album, track, songname, ".mp3"
    )
    local_filename = os.path.join(album_path, songname + ".mp3")

    try:
        response = requests.get(
            url,
            headers=playerMP3.STREAM_HEADERS,   # ← single source of truth
            stream=True,
            verify=True,
            timeout=30,
        )
        response.raise_for_status()             # surface 4xx/5xx immediately

        with open(local_filename, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):  # ← was 1 byte/iter
                if chunk:
                    f.write(chunk)
                    f.flush()

    except requests.HTTPError as e:
        xbmc.log(
            "download_song: HTTP %d for %s — %s"
            % (e.response.status_code, url, e),
            xbmc.LOGERROR,
        )
        return
    except Exception as e:
        xbmc.log("download_song: unexpected error — %s" % e, xbmc.LOGERROR)
        return

    add_to_list(list_data, DOWNLOAD_LIST, False)
"""


# ══════════════════════════════════════════════════════════════════════════════
# PATCH 4 — play_song()
#
# LOCATION : ~line 1114
#
# WHY :
#   The 403 error for this function is fixed entirely by PATCH 1 in
#   playerMP3.py (getListItem now returns a header-augmented URL instead
#   of the raw CDN URL).  No URL-resolution change is needed here.
#
#   This patch:
#   - Removes the inline "import playerMP3" (replaced by the module-level
#     import from PATCH 1 of this document).
#   - Removes ~15 lines of dead commented-out code that was never re-enabled.
#   - Adds a guard against overwriting the ListItem's path after getListItem
#     already resolved it: the liz object's path must be kept in sync with
#     the url variable when a stored local file is used, otherwise Kodi plays
#     the stored file but the ListItem metadata still references the remote URL.
# ══════════════════════════════════════════════════════════════════════════════

# ── BEFORE ───────────────────────────────────────────────────────────────────
"""
def play_song(url, name, songname, artist, album, iconimage, dur, clear):
    import playerMP3

    try:
        track = int(name[: name.find(".")])
    except:
        track = 0
    url, liz = playerMP3.getListItem(
        songname,
        artist,
        album,
        track,
        iconimage,
        dur,
        url,
        fanart,
        "true",
        GOTHAM_FIX_2,
    )
    title = name
    if FOLDERSTRUCTURE == "0":
        stored_path = os.path.join(MUSIC_DIR, artist, album, title + ".mp3")
    else:
        stored_path = os.path.join(MUSIC_DIR, artist + " - " + album, title + ".mp3")
    # if xbmc.Player().isPlayingAudio():
    # xbmc.Player().stop()
    if os.path.exists(stored_path):
        url = stored_path
    pl = get_XBMCPlaylist(clear)
    pl.add(url, liz)
    xbmc.Player().play(pl)
    # if clear or (not xbmc.Player().isPlayingAudio()):
    # xbmc.Player().play(pl)
    # playlist.append((newurl, liz))
    # for blob ,liz in playlist:
    #    try:
    #        if blob:
    #            pl.add(blob,liz)
    #    except:
    #        pass
    # newPlay(pl, clear)
"""

# ── AFTER ────────────────────────────────────────────────────────────────────
"""
def play_song(url, name, songname, artist, album, iconimage, dur, clear):
    \"\"\"
    Resolve a single track URL and hand it to Kodi's music player.

    getListItem() (in playerMP3) returns either a locally cached file path
    or a header-augmented CDN URL.  Both are safe to pass directly to Kodi's
    PAPlayer; no bare listen.musicmp3.ru URLs reach the player.
    \"\"\"
    try:
        track = int(name[: name.find(".")])
    except (ValueError, TypeError):
        track = 0

    # getListItem resolves to local cache or header-augmented URL automatically.
    resolved_url, liz = playerMP3.getListItem(
        songname, artist, album, track,
        iconimage, dur, url, fanart,
        "true", GOTHAM_FIX_2,
    )

    # Override with a permanently stored file if keep_downloads is on and the
    # file was saved from a previous session.  Also update the ListItem path so
    # that Kodi's player and the metadata are always in sync.
    if FOLDERSTRUCTURE == "0":
        stored_path = os.path.join(MUSIC_DIR, artist, album, name + ".mp3")
    else:
        stored_path = os.path.join(MUSIC_DIR, artist + " - " + album, name + ".mp3")

    if os.path.exists(stored_path):
        resolved_url = stored_path
        liz.setPath(stored_path)   # ← keep ListItem path in sync

    pl = get_XBMCPlaylist(clear)
    pl.add(resolved_url, liz)
    xbmc.Player().play(pl)
"""


# ══════════════════════════════════════════════════════════════════════════════
# PATCH 5 — play_album() — stored_path override (same liz.setPath fix)
#
# LOCATION : ~line 1086 (inside the playlist-building loop in play_album)
#
# WHY : play_album builds a (url, liz) playlist list.  After getListItem()
#       sets both the url and the ListItem path, the stored_path check can
#       override url but forgets to call liz.setPath(), leaving the ListItem
#       pointing at the remote CDN while Kodi is told to play the local file.
#       This causes a mismatch in Now Playing metadata.
# ══════════════════════════════════════════════════════════════════════════════

# ── BEFORE ───────────────────────────────────────────────────────────────────
"""
        if os.path.exists(stored_path):
            url = stored_path
        playlist.append((url, liz))
"""

# ── AFTER ────────────────────────────────────────────────────────────────────
"""
        if os.path.exists(stored_path):
            url = stored_path
            liz.setPath(stored_path)   # ← keep ListItem path in sync
        playlist.append((url, liz))
"""


# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY OF ALL CHANGES
# ══════════════════════════════════════════════════════════════════════════════
#
#  Patch | File        | Function          | Bug fixed
#  ──────┼─────────────┼───────────────────┼──────────────────────────────────
#    1   | default.py  | (imports)         | Move playerMP3 import to module level
#    2   | default.py  | GET_url()         | Placeholder UA; Accept typo; http Referer
#    3   | default.py  | download_song()   | Placeholder UA; missing Referer; chunk_size=1
#    4   | default.py  | play_song()       | Dead code; liz/url path sync
#    5   | default.py  | play_album()      | liz/url path sync after stored_path override
#  ──────┼─────────────┼───────────────────┼──────────────────────────────────
#  (see playerMP3.py for the primary 403 fix and the deleteFile definition)
