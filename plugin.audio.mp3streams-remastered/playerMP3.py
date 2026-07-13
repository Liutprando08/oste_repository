# -*- coding: utf-8 -*-
#
#  plugin.audio.mp3streams-remastered — playerMP3.py
#
#  Copyright (C) 2014-2015
#  This Program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2, or (at your option)
#  any later version.
#
#  http://www.gnu.org/copyleft/gpl.html
#

# ──────────────────────────────────────────────────────────────────────────────
# Standard library
# ──────────────────────────────────────────────────────────────────────────────

import os
import threading
import urllib.parse
import urllib.request
import urllib.error

from contextlib import closing
from hashlib import md5

# ──────────────────────────────────────────────────────────────────────────────
# Third-party
# ──────────────────────────────────────────────────────────────────────────────

import requests
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3

# ──────────────────────────────────────────────────────────────────────────────
# Kodi API
# ──────────────────────────────────────────────────────────────────────────────

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs


# ══════════════════════════════════════════════════════════════════════════════
# Add-on identity
# ══════════════════════════════════════════════════════════════════════════════

ADDON_ID = "plugin.audio.mp3streams-remastered"
ADDON = xbmcaddon.Addon(ADDON_ID)
TITLE = ADDON.getAddonInfo("name")
VERSION = ADDON.getAddonInfo("version")
HOME = xbmcvfs.translatePath(ADDON.getAddonInfo("path"))
PROFILE = ADDON.getAddonInfo("profile")
ICON = os.path.join(HOME, "icon.png")
TEMP = xbmcvfs.translatePath(os.path.join(PROFILE, "temp_dl"))


# ══════════════════════════════════════════════════════════════════════════════
# Kodi version detection
# ══════════════════════════════════════════════════════════════════════════════


def _get_kodi_version():
    """Return (major, minor) integers for the running Kodi build."""
    version = xbmc.getInfoLabel("System.BuildVersion")
    try:
        parts = version.split(".")
        return int(parts[0]), int(parts[1])
    except (IndexError, ValueError):
        return 21, 0  # safe modern fallback


MAJOR, MINOR = _get_kodi_version()
FRODO = (MAJOR == 12) and (MINOR < 9)


# ══════════════════════════════════════════════════════════════════════════════
# Logging
# ══════════════════════════════════════════════════════════════════════════════

DEBUG = False  # Set True to promote log output from LOGDEBUG to the default level.


def log(text):
    """Write a prefixed message to kodi.log."""
    try:
        message = "%s V%s : %s" % (TITLE, VERSION, str(text))
        level = xbmc.LOGNONE if DEBUG else xbmc.LOGDEBUG
        xbmc.log(message, level)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
# Stream headers — single source of truth
#
# listen.musicmp3.ru enforces access control via HTTP headers.  Every request
# to that CDN — whether made by the Downloader thread or by Kodi's internal
# player — must include all three of Host, Referer, and User-Agent.
#
# Previously these headers were copy-pasted into several functions (with two
# of those copies using a literal placeholder "AppleWebKit/<WebKit Rev>" and
# one copy omitting Referer entirely).  The canonical definition here is used
# everywhere, guaranteeing consistency.
# ══════════════════════════════════════════════════════════════════════════════

STREAM_HEADERS = {
    "Host": "listen.musicmp3.ru",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; WOW64; rv:44.0) Gecko/20100101 Firefox/44.0"
    ),
    "Accept": (
        "audio/webm,audio/ogg,audio/wav,audio/*;q=0.9,"
        "application/ogg;q=0.7,video/*;q=0.6,*/*;q=0.5"
    ),
    "Referer": "https://musicmp3.ru/",
}


def build_stream_url(url):
    """
    Append the required HTTP headers to a listen.musicmp3.ru URL using
    Kodi's pipe-separated header syntax, so PAPlayer can open the URL
    directly without receiving a 403 Forbidden response.

    Non-musicmp3 URLs are returned unchanged.  The Range header is omitted
    from the appended block because Kodi's player manages byte-range
    requests internally.

    Example:
        "https://listen.musicmp3.ru/abc123"
        → "https://listen.musicmp3.ru/abc123|Host=listen.musicmp3.ru&..."
    """
    if "listen.musicmp3.ru" not in url:
        return url

    player_headers = {k: v for k, v in STREAM_HEADERS.items() if k != "Range"}
    header_string = "&".join(
        "%s=%s" % (k, urllib.parse.quote_plus(v)) for k, v in player_headers.items()
    )
    return url + "|" + header_string


PROPERTY = "MP3_DOWNLOADER_STATE_%d"
RESOLVING = "MP3_RESOLVING"
MAX_DOWNLOADERS = 2


def getFreeSlot():
    """Return the index of the first idle downloader slot, or -1 if all busy."""
    for i in range(MAX_DOWNLOADERS):
        if not xbmcgui.Window(10000).getProperty(PROPERTY % i):
            return i
    return -1


def getNmrDownloaders():
    """Return the number of currently active downloader threads."""
    return sum(
        1
        for i in range(MAX_DOWNLOADERS)
        if xbmcgui.Window(10000).getProperty(PROPERTY % i)
    )


def stopDownloaders():
    """
    Signal every active downloader to stop, then block until they have
    all released their slots.
    """
    log("stopDownloaders: signalling all active slots")

    for i in range(MAX_DOWNLOADERS):
        if xbmcgui.Window(10000).getProperty(PROPERTY % i):
            xbmcgui.Window(10000).setProperty(PROPERTY % i, "Signal")

    # Reset the scan index each time a slot is still occupied so that a newly
    # freed slot is not missed if a thread exits out of order.
    i = 0
    while i < MAX_DOWNLOADERS:
        if xbmcgui.Window(10000).getProperty(PROPERTY % i):
            xbmc.sleep(100)
            i = 0
        else:
            i += 1

    log("stopDownloaders: all slots clear")


# ══════════════════════════════════════════════════════════════════════════════
# File utilities
# ══════════════════════════════════════════════════════════════════════════════


def deleteFile(filename):
    """
    Delete *filename* via xbmcvfs, suppressing all errors.

    Previously this function was called throughout the module but was never
    defined, causing a NameError at runtime whenever a download was cancelled
    or a cached file needed removing.
    """
    if not filename:
        return
    try:
        xbmcvfs.delete(filename)
        log("deleteFile: removed %s" % filename)
    except Exception as e:
        log("deleteFile: could not remove %s — %s" % (filename, e))


def createMD5(url):
    """Return the hex MD5 digest of *url* (used as a cache-safe filename)."""
    return md5(url.encode("utf-8")).hexdigest()


# Characters that are illegal in file or folder names on Windows and Linux.
_ILLEGAL_CHARS = str.maketrans({c: "" for c in r'/\:*?"<>|'})


def clean(text):
    """Strip characters that are illegal in file or folder names."""
    return text.translate(_ILLEGAL_CHARS).strip()


def createFilename(title, artist, album, url):
    """
    Build the local path where a track will be cached or permanently stored.

    - keep_downloads == "false" → MD5 hash filename inside TEMP (self-cleaning)
    - keep_downloads == "true"  → organised under the user's chosen music
                                  directory, using the configured folder
                                  structure setting.
    """
    if ADDON.getSetting("keep_downloads") == "false":
        return os.path.join(TEMP, createMD5(url))

    title = clean(title)
    artist = clean(artist)
    album = clean(album)

    use_custom = ADDON.getSetting("custom_directory") == "true"
    folder = ADDON.getSetting("music_dir") if use_custom else TEMP

    if ADDON.getSetting("folder_structure") == "0":
        base = os.path.join(folder, artist, album)
    else:
        base = os.path.join(folder, "%s - %s" % (artist, album))

    try:
        xbmcvfs.mkdirs(base)
    except Exception as e:
        log("createFilename: could not create directory %s — %s" % (base, e))

    return os.path.join(base, title + ".mp3")


def resetCache():
    """Delete every file in the temporary download directory."""
    log("resetCache: clearing %s" % TEMP)
    if not xbmcvfs.exists(TEMP):
        try:
            xbmcvfs.mkdirs(TEMP)
        except Exception:
            pass
        return

    _dirs, files = xbmcvfs.listdir(TEMP)
    for name in files:
        deleteFile(os.path.join(TEMP, name))


# ══════════════════════════════════════════════════════════════════════════════
# File size verification
# ══════════════════════════════════════════════════════════════════════════════


def _file_is_unavailable(filename):
    """
    Return True when the downloaded bytes are actually an HTML error page
    from the server (e.g. a 212-byte "Track unavailable" response).
    """
    try:
        with xbmcvfs.File(filename, "r") as f:
            content = f.read().lower()
        if "unavailable" in content:
            log("_file_is_unavailable: server error page detected in %s" % filename)
            return True
    except Exception:
        pass
    return False


def verifyFileSize(filename):
    """
    Poll until the cached file grows past the precache threshold (KB setting).

    Returns True as soon as the threshold is crossed, False on timeout or
    if an exception flag is set by the Downloader thread.

    Maximum wait: 100 × 500 ms = 50 seconds.
    """
    if not filename:
        return True

    precache_kb = int(ADDON.getSetting("pre-cache").replace("K", ""))
    translated = xbmcvfs.translatePath(filename)

    log("verifyFileSize: waiting for %s (threshold %d KB)" % (translated, precache_kb))

    for attempt in range(100, 0, -1):
        # Check whether the Downloader signalled an unrecoverable error.
        if xbmcgui.Window(10000).getProperty(translated) == "EXCEPTION":
            xbmcgui.Window(10000).clearProperty(translated)
            log("verifyFileSize: exception flag set — aborting wait")
            return False

        if xbmcvfs.exists(translated):
            size = xbmcvfs.File(translated).size()
            log("verifyFileSize: attempt %d — %d bytes on disk" % (attempt, size))

            if size == 212 and _file_is_unavailable(translated):
                return False

            if size > precache_kb * 1024:
                log("verifyFileSize: threshold reached (%d bytes)" % size)
                return True

        xbmc.sleep(500)

    log("verifyFileSize: timed out waiting for %s" % translated)
    return False


# ══════════════════════════════════════════════════════════════════════════════
# Download orchestration
# ══════════════════════════════════════════════════════════════════════════════


def startFile(title, artist, album, track, url, filename):
    """
    Spawn a Downloader thread and block until the precache threshold is met.
    Attempts the download twice before giving up.
    """
    log("startFile: %s → %s" % (url, filename))

    for attempt in range(1, 3):
        log("startFile: attempt %d of 2" % attempt)
        downloader = Downloader(title, artist, album, track, url, filename)
        downloader.start()

        if verifyFileSize(filename):
            return

        log("startFile: attempt %d failed — cleaning up before retry" % attempt)
        stopDownloaders()
        deleteFile(xbmcvfs.translatePath(filename))

    log("startFile: all attempts exhausted for %s" % filename)


def fetchFile(title, artist, album, track, url, filename):
    """
    Start a background download for the current track.  Stops existing
    downloaders if the pool is almost full (reserving one free slot for
    the next track's pre-fetch via fetchNext).
    """
    log("fetchFile: %s" % filename)

    if getNmrDownloaders() >= MAX_DOWNLOADERS - 1:
        stopDownloaders()

    local = xbmcvfs.translatePath(filename)
    if xbmcvfs.exists(local) and xbmcvfs.File(local).size() > 250 * 1024:
        log("fetchFile: %s already cached and above minimum size" % local)
        return

    log("fetchFile: initiating download for %s" % filename)
    startFile(title, artist, album, track, url, filename)


def fetchNext(posn):
    """
    Pre-fetch the next unresolved playlist entry at or after *posn*.

    Walks forward through the playlist, skipping any item that does not
    belong to this plugin or is not a mode=999 playback URL, until it
    either finds an item to pre-cache or reaches the end of the playlist.
    """
    log("fetchNext: scanning playlist from position %d" % posn)

    if getNmrDownloaders() > 0 or posn == 0:
        return

    playlist = xbmc.PlayList(xbmc.PLAYLIST_MUSIC)
    if posn >= playlist.size():
        log("fetchNext: reached end of playlist")
        return

    url = playlist[posn].getPath()

    if not url.startswith("plugin://plugin.audio.mp3streams"):
        return

    params = _parse_query(url)

    try:
        mode = int(urllib.parse.unquote_plus(params["mode"]))
    except (KeyError, ValueError):
        return

    if mode != 999:
        return fetchNext(posn + 1)

    try:
        title = urllib.parse.unquote_plus(params["title"])
        artist = urllib.parse.unquote_plus(params["artist"])
        album = urllib.parse.unquote_plus(params["album"])
        track = urllib.parse.unquote_plus(params["track"])
        url = urllib.parse.unquote_plus(params["url"])
        filename = urllib.parse.unquote_plus(params["filename"])

    except KeyError as missing:
        log("fetchNext: missing required param %s at position %d" % (missing, posn))
        return

    local = xbmcvfs.translatePath(filename)
    if xbmcvfs.exists(local):
        try:
            if xbmcvfs.File(local).size() > 50 * 1024:
                log("fetchNext: '%s' already cached — skipping" % title)
                return
        except:
            return

    log("fetchNext: pre-fetching '%s' → %s" % (title, filename))
    Downloader(title, artist, album, track, url, filename).start()


# ══════════════════════════════════════════════════════════════════════════════
# URL / query string helpers
# ══════════════════════════════════════════════════════════════════════════════


def _parse_query(url):
    """
    Parse the query string of a plugin:// URL into a {key: value} dict.

    Internal helper; external callers should use the public alias getParams()
    for backwards compatibility.
    """
    if len(url) < 2:
        return {}
    query = url.split("?", 1)[-1]
    params = {}
    for pair in query.split("&"):
        parts = pair.split("=", 1)
        if len(parts) == 2:
            params[parts[0]] = parts[1]
    return params


# Public alias kept for backwards compatibility with callers in default.py.
getParams = _parse_query


# ══════════════════════════════════════════════════════════════════════════════
# ListItem factory
# ══════════════════════════════════════════════════════════════════════════════


def getListItem(
    title,
    artist,
    album,
    track,
    image,
    duration,
    url,
    fanart,
    isPlayable,
    useDownload,
    block=True,
):
    resolved_url = url

    if "listen.musicmp3.ru" in url:
        if useDownload:
            filename = createFilename(title, artist, album, url)
            local = xbmcvfs.translatePath(filename)
            Downloader(title, artist, album, track, url, filename).start()
            if block:
                if verifyFileSize(filename):
                    log(
                        "getListItem: pre-cache threshold met — "
                        "serving cached '%s'" % title
                    )
                    resolved_url = local
                else:
                    log(
                        "getListItem: pre-cache timed out — "
                        "falling back to URL for '%s'" % title
                    )
                    resolved_url = build_stream_url(url)
            else:
                resolved_url = build_stream_url(url)
        else:
            resolved_url = build_stream_url(url)

    liz = xbmcgui.ListItem(title)
    liz.setArt({"icon": image, "thumb": image})
    liz.setInfo(
        "music",
        {"Title": title, "Artist": artist, "Album": album, "Duration": duration},
    )
    liz.setProperty("mimetype", "audio/mpeg")
    liz.setProperty("fanart_image", fanart)
    liz.setProperty("IsPlayable", isPlayable)

    return resolved_url, liz


# ══════════════════════════════════════════════════════════════════════════════
# Plugin URL resolver  (mode = 999)
# ══════════════════════════════════════════════════════════════════════════════


def play(sys, params):
    """
    Resolve a mode=999 plugin URL to a playable path and hand it to Kodi.

    Resolution order (same as getListItem):
        1. Local cached file if *filename* param is present and the file exists.
        2. Blocking pre-cache — wait for the background Downloader to reach
           the pre-cache threshold, then serve from the local file.
        3. Header-augmented remote URL as a last-resort fallback.

    A try/finally block guarantees that the RESOLVING window property is always
    cleared, even if an unexpected exception occurs during resolution.
    """
    log("play: resolving track")
    xbmcgui.Window(10000).setProperty(RESOLVING, RESOLVING)

    try:
        title = urllib.parse.unquote_plus(params["title"])
        artist = urllib.parse.unquote_plus(params["artist"])
        album = urllib.parse.unquote_plus(params["album"])
        duration = urllib.parse.unquote_plus(params["duration"])
        image = urllib.parse.unquote_plus(params["image"])
        url = urllib.parse.unquote_plus(params["url"])
        filename = urllib.parse.unquote_plus(params.get("filename", ""))

        # Determine the best available path for this track.
        if filename:
            local = xbmcvfs.translatePath(filename)
            if not xbmcvfs.exists(local) or xbmcvfs.File(local).size() <= 100 * 1024:
                track_param = urllib.parse.unquote_plus(params.get("track", "0"))
                Downloader(title, artist, album, track_param, url, filename).start()
            if xbmcvfs.exists(local) and xbmcvfs.File(local).size() > 100 * 1024:
                log("play: cache hit — serving '%s' from %s" % (title, local))
                resolved_url = local
            else:
                log("play: cache miss — waiting for pre-cache on '%s'" % title)
                if verifyFileSize(filename):
                    log("play: pre-cache threshold met — serving cached '%s'" % title)
                    resolved_url = local
                else:
                    log(
                        "play: pre-cache timed out — "
                        "using header-augmented URL for '%s'" % title
                    )
                    resolved_url = build_stream_url(url)
        else:
            resolved_url = build_stream_url(url)

        liz = xbmcgui.ListItem(title, path=resolved_url)
        liz.setArt(
            {
                "icon": image,
                "thumb": image,
                "poster": image,
                "fanart": image,
            }
        )
        liz.setInfo(
            "music",
            {"Title": title, "Artist": artist, "Album": album, "Duration": duration},
        )
        liz.setProperty("mimetype", "audio/mpeg")
        liz.setProperty("IsPlayable", "true")

        log("play: setResolvedUrl → %s" % resolved_url)
        xbmcplugin.setResolvedUrl(int(sys.argv[1]), True, liz)

    except Exception as e:
        log("play: error during resolution — %s" % e)
        xbmcplugin.setResolvedUrl(int(sys.argv[1]), False, xbmcgui.ListItem())

    finally:
        xbmcgui.Window(10000).clearProperty(RESOLVING)
        log("play: RESOLVING property cleared")


# ══════════════════════════════════════════════════════════════════════════════
# Downloader thread
# ══════════════════════════════════════════════════════════════════════════════


class Downloader(threading.Thread):
    """
    Background thread that streams a single MP3 from listen.musicmp3.ru
    to a local file and optionally applies ID3 tags on completion.

    Lifecycle
    ---------
    - ``run()``        — thread entry point; acquires a free slot then delegates.
    - ``_download()``  — streams the remote file in chunks, honouring stop signals.
    - ``_apply_id3()`` — writes metadata tags after a successful download.
    - ``signal()``     — called from another thread to request a clean abort.

    Stop signalling uses two channels:
        1. The ``PROPERTY % slot`` window property being set to ``"Signal"``
           (checked inside the download loop via ``_check_signal()``).
        2. The internal ``_signal`` flag (set by ``signal()`` or by
           ``_check_signal()``; checked after each chunk write).
    """

    def __init__(self, title, artist, album, track, url, filename):
        super().__init__(daemon=True)
        self._signal = False
        self.title = title
        self.artist = artist
        self.album = album
        self.track = int(track) if str(track).isdigit() else 0
        self.url = url
        self.filename = xbmcvfs.translatePath(filename)
        self.slot = -1
        self.complete = False
        self.slot_released = False

    # ── Stop signalling ───────────────────────────────────────────────────────

    def signal(self):
        """Request a clean abort.  Thread-safe."""
        self._signal = True

    def _check_signal(self):
        """
        Return True if a stop has been requested via either channel.
        Promotes the window-property signal to the internal flag so that
        subsequent checks do not need to read the window property again.
        """
        if xbmcgui.Window(10000).getProperty(PROPERTY % self.slot) == "Signal":
            log("Downloader[%d]: stop signal received via window property" % self.slot)
            self._signal = True
        return self._signal

    # ── Download ──────────────────────────────────────────────────────────────

    def _download(self):
        """
        Stream the remote audio file to disk in 8 KB chunks.

        Uses the canonical STREAM_HEADERS constant so that the Host, Referer,
        User-Agent, and Accept values are always correct and consistent with
        every other request made by this module.

        Raises an HTTP error immediately (via raise_for_status) rather than
        silently writing error HTML to disk, which was the previous behaviour.
        """
        log("Downloader[%d]: starting — %s" % (self.slot, self.url))
        xbmcgui.Window(10000).setProperty(PROPERTY % self.slot, "Downloading")
        precache_kb = int(ADDON.getSetting("pre-cache").replace("K", ""))
        precache_bytes = precache_kb * 1024
        bytes_written = 0
        f = None
        try:
            with closing(
                requests.get(
                    self.url,
                    headers=STREAM_HEADERS,
                    stream=True,
                    verify=True,
                    timeout=30,
                )
            ) as response:
                response.raise_for_status()  # immediately surface 4xx / 5xx errors

                f = open(self.filename, "wb")
                for chunk in response.iter_content(chunk_size=8192):
                    if self._check_signal():
                        log("Downloader[%d]: aborted mid-stream" % self.slot)
                        return
                    if chunk:
                        f.write(chunk)
                        f.flush()
                        bytes_written += len(chunk)
                        if not self.slot_released and bytes_written >= precache_bytes:
                            xbmcgui.Window(10000).clearProperty(PROPERTY % self.slot)
                            self.slot_released = True
                            log(
                                "Downloader[%d]: slot released after %d bytes"
                                % (self.slot, bytes_written)
                            )
            f.flush()
            self.complete = True
            log("Downloader[%d]: complete — %s" % (self.slot, self.filename))

        except requests.HTTPError as e:
            log("Downloader[%d]: HTTP %d — %s" % (self.slot, e.response.status_code, e))
            xbmcgui.Window(10000).setProperty(self.filename, "EXCEPTION")

        except Exception as e:
            log("Downloader[%d]: unexpected error — %s" % (self.slot, e))
            xbmcgui.Window(10000).setProperty(self.filename, "EXCEPTION")

        finally:
            if not self.slot_released:
                xbmcgui.Window(10000).clearProperty(PROPERTY % self.slot)
            if f is not None:
                try:
                    f.close()
                except Exception:
                    pass

    # ── ID3 tagging ───────────────────────────────────────────────────────────

    def _apply_id3(self):
        """
        Write ID3 tags to the downloaded file.

        Skipped silently when:
        - keep_downloads is disabled (temp files are deleted after playback anyway)
        - the track number is unknown (track < 1)
        - the file no longer exists on disk
        """
        if ADDON.getSetting("keep_downloads") == "false":
            return
        if self.track < 1 or not xbmcvfs.exists(self.filename):
            return

        log("Downloader[%d]: applying ID3 tags to '%s'" % (self.slot, self.title))

        basename = self.filename.rsplit(os.sep, 1)[-1]
        temp = os.path.join(TEMP, basename)
        do_copy = self.filename != temp

        try:
            if do_copy:
                xbmcvfs.copy(self.filename, temp)

            # Strip the leading "N. " track-number prefix from the displayed title
            # so that ID3 title and track-number tags do not duplicate information.
            tag_title = self.title
            dot_pos = self.title.find(". ")
            if dot_pos != -1:
                tag_title = self.title[dot_pos + 2 :]

            audio = MP3(temp, ID3=EasyID3)
            audio["title"] = tag_title
            audio["artist"] = self.artist
            audio["album"] = self.album
            audio["tracknumber"] = str(self.track)
            audio["date"] = ""
            audio["genre"] = ""
            audio.save(v1=2)
            log("Downloader[%d]: tags saved — %s" % (self.slot, audio.pprint()))

            if do_copy:
                del audio  # release mutagen's file handle before moving
                deleteFile(self.filename)
                xbmcvfs.copy(temp, self.filename)
                deleteFile(temp)

        except Exception as e:
            log("Downloader[%d]: ID3 tagging failed — %s" % (self.slot, e))

    # ── Thread entry point ────────────────────────────────────────────────────

    def run(self):
        # Short-circuit if the file was already cached by a previous session.
        if xbmcvfs.exists(self.filename):
            log("Downloader: '%s' already cached at %s" % (self.title, self.filename))
            self.complete = True
            return

        self.slot = getFreeSlot()
        if self.slot < 0:
            log("Downloader: no free slot — skipping '%s'" % self.title)
            return

        log(
            "Downloader[%d]: title='%s'  url=%s  file=%s"
            % (self.slot, self.title, self.url, self.filename)
        )

        try:
            self._download()
        finally:
            if not self.slot_released:
                xbmcgui.Window(10000).clearProperty(PROPERTY % self.slot)

        if self.complete:
            log("Downloader[%d]: '%s' finished" % (self.slot, self.title))
            self._apply_id3()
        else:
            log(
                "Downloader[%d]: '%s' cancelled — removing partial file"
                % (self.slot, self.title)
            )
            deleteFile(self.filename)


# ══════════════════════════════════════════════════════════════════════════════
# Background service  (runs when this file is executed directly by Kodi)
# ══════════════════════════════════════════════════════════════════════════════

_COUNT = 0
_STARTED = False
_RETRIES = 25


def _service_clear():
    """
    Stop all active downloads, flush the temp cache, and reset counters.

    Skipped if the RESOLVING property is currently set (a track is mid-resolve)
    to avoid interrupting playback setup.
    """
    global _COUNT, _STARTED
    log("service: clearing state")

    if xbmcgui.Window(10000).getProperty(RESOLVING) != RESOLVING:
        stopDownloaders()
        resetCache()
    else:
        log("service: clear skipped — RESOLVING property is active")

    _COUNT = 0
    _STARTED = False


def _service_check():
    """
    Increment an idle counter while Kodi is not playing.  Trigger a full
    cache clear if the player has been idle for more than _RETRIES seconds.
    """
    global _COUNT

    if xbmc.Player().isPlaying():
        _COUNT = 0
    else:
        _COUNT += 1
        log("service: idle check %d / %d" % (_COUNT, _RETRIES))
        if _COUNT > _RETRIES:
            _service_clear()


if __name__ == "__main__":
    log("service: started")
    _service_clear()
    monitor = xbmc.Monitor()
    while not monitor.abortRequested():
        if not _STARTED:
            _STARTED = xbmc.Player().isPlaying()
        else:
            _service_check()
            player = xbmc.Player()
            if player.isPlaying():
                try:
                    playlist = xbmc.PlayList(xbmc.PLAYLIST_MUSIC)
                    cur = playlist.getposition()
                    if cur >= 0:
                        fetchNext(cur + 1)
                except:
                    pass
        xbmc.sleep(1000)

    log("service: abort requested — shutting down")
    _service_clear()
