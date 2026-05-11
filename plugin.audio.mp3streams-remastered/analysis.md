# Comprehensive Codebase Analysis: `plugin.audio.mp3streams-remastered`

## 1. Executive Summary

**MP3 Streams** (v2025.0.1, provider "Jon Bovi") is a Kodi audio addon that streams MP3 music from Russian web sources — primarily `musicmp3.ru`, `goldenmp3.ru`, and `officialcharts.com`. It allows browsing by artist, album, genre, and chart, with search, download, favourites, and instant-mix features. The codebase is ~3,300 lines of Python 3, split into three source files (`default.py`, `playerMP3.py`, `settings.py`) plus supporting XML config, artwork, and a static URL list.

---

## 2. Architecture Overview

### 2.1 Component Model

The addon uses two Kodi extension points declared in `addon.xml`:

| Extension Point | File | Role |
|---|---|---|
| `xbmc.python.pluginsource` | `default.py` | Main UI plugin — generates Kodi directory listings and handles user interaction |
| `xbmc.service` | `playerMP3.py` | Background service — pre-caches MP3 data to local storage and resolves playback URLs |

`settings.py` acts as a thin facade over Kodi's `xbmcaddon.Addon` settings API.

### 2.2 Data Flow

```
User browses menu
        |
        v
default.py ----> HTTP GET ----> musicmp3.ru / goldenmp3.ru / officialcharts.com
        |                        |
        |                   HTML response
        |                        |
        v                        v
  Kodi ListItems           BeautifulSoup / regex parse
  (titles, art,                    |
   plugin:// URLs)          Extract track URLs,
        |                   artist names, album art
        |                        |
        v                        v
  User selects track ----> plugin:// URL with mode=999
        |
        v
  playerMP3.py.play()
        |
        +-- Cache hit?  ----> Serve cached .mp3 file
        |
        +-- Cache miss? ----> Build header-augmented CDN URL
                            ----> Start downloader thread
                            ----> Stream 8KB chunks to cache
                            ----> Serve from cache when threshold met
```

### 2.3 Technology Stack

| Layer | Technology |
|---|---|
| Platform | Kodi 19+ (Matrix) / Python 3.x |
| HTTP | `requests` library (no connection pooling reuse) |
| Parsing | `beautifulsoup4` + `re` (regex) |
| Audio Tagging | `mutagen` (ID3v2 tags on downloaded files) |
| IPC | Kodi `Window(10000)` properties (cross-thread signalling) |
| Cache | Filesystem: `special://temp/` + addon profile data dir |
| Settings | Kodi `xml`-based settings system |

---

## 3. Feature Breakdown

### 3.1 Main Menu Navigation

The root menu in `CATEGORIES` (default.py:131-175) presents:

| Menu Item | Handler | Data Source |
|---|---|---|
| Artists | `artists()` | musicmp3.ru |
| Top Albums | `all_top_albums()` | musicmp3.ru |
| New Albums | `all_new_albums()` | musicmp3.ru |
| Compilations | `compilations_menu()` | goldenmp3.ru |
| Billboard Charts | `charts()` | officialcharts.com |
| Search | `search()` | musicmp3.ru |
| Favourites | 3 sub-menus | Local flat-file storage |
| Instant Mix | 2 sub-menus | Favourites + playlist |

### 3.2 Billboard Charts (default.py:180-448)

The charts system scrapes `officialcharts.com` for 22 chart categories (Billboard 200, Hot 100 Singles, genre-specific album charts, UK charts, etc.). It uses `BeautifulSoup` to find `<audio>` tags with `data-title` and `data-artist` attributes. **Notable**: There is dead code (lines ~218-273) still present from an earlier `billboard.com` scraping approach that is never reached due to being gated behind `CHART_SOURCE == '0'` while the live code path uses `CHART_SOURCE == '1'`.

### 3.3 Artist & Album Browsing (default.py:451-877)

Artists are scraped from `musicmp3.ru/artists/` using regex patterns to extract artist names from HTML anchor tags. The approach is brittle — it relies on hardcoded patterns like `r'artist[^>]*>([^<]+)<'` which will break if the upstream site changes its HTML structure.

Album browsing supports:
- **Genre hierarchy**: Top-level genres -> subgenres -> album listings -> track listings
- **Pagination**: `album_list()` handles page numbers via query parameter `?page=N`
- **Compilations**: A separate source (`goldenmp3.ru`) with its own scraping logic

### 3.4 Search (default.py:715-815)

Uses Kodi's `xbmc.Keyboard()` dialog for text input. Performs three search types:
- **Artists**: Searches `musicmp3.ru/search/artist/`
- **Albums**: Searches `musicmp3.ru/search/album/`
- **Songs**: Searches `musicmp3.ru/search/songs/`

The search results are parsed with regex for artists and albums, and BeautifulSoup for songs. The song search function builds a playlist but **never uses it** (the `playlist` variable is assigned but never passed to any consumer — a dead-code bug).

### 3.5 Playback System

#### 3.5.1 Album Playback (`play_album`, default.py:895-1127)

This is the most complex function in the codebase. It:
1. Fetches the album HTML page
2. Parses tracks using regex (`track_id_pattern`) to extract track IDs
3. Resolves `mp3url.list` mappings for CDN URLs (if `GOTHAM_FIX` is enabled)
4. For each track, creates a `plugin://` URL with `mode=999`
5. Calls `playerMP3.getListItem()` to create a Kodi `ListItem` with optional pre-caching
6. Adds tracks to a Kodi `PlayList` and starts playback

**Mode parameter handling** (lines 1060-1127):
- `mode=''` (default): Plays all tracks sequentially, launches Kodi player
- `mode='browse'`: Returns directory listing of album tracks (no playback)
- `mode='queue'`: Queues all tracks without starting playback
- `mode='mix'`: Used by Instant Mix — plays from a shuffled subset

#### 3.5.2 Single Song Playback (`play_song`, default.py:1137-1177)

Simpler than album playback — resolves one track URL, creates a single-item playlist, and starts playing. Uses Kodi's `xbmc.Player().play()` directly.

### 3.6 Pre-Cache System (playerMP3.py)

The background service runs a continuous loop (lines 796-845) that:
1. Waits for Kodi playback to start
2. Monitors the playlist for upcoming tracks
3. Pre-fetches the next 3 tracks into local cache (`special://temp/`)
4. Clears old cache entries after 25 seconds of playback (to prevent disk bloat)

The cache system uses **3 concurrent downloader slots**, tracked via Kodi `Window(10000)` properties — a primitive but functional IPC mechanism. Each downloader thread:
- Streams data in 8KB chunks
- Checks threshold (`PRE_CACHE` setting, default 500KB)
- Applies ID3 tags on completion (for downloads, not cache)
- Respects a stop-flag via `Window(10000).setProperty('StopDownload', ...)`

### 3.7 Download System (default.py:1180-1347)

Users can download individual songs or full albums:
- **Single download**: `download_song()` — streams URL directly, saves to configured music directory, applies ID3 tags in a background thread
- **Album download**: `download_album()` — iterates over album tracks, streams each sequentially, saves with album-specific naming

Both use `urllib.request.urlopen()` with a custom `_fileobj` context manager, writing in 8192-byte chunks. A **lock file** mechanism (`album_download.lock`) prevents concurrent album downloads but has a race condition — the lock is checked but not atomically created.

### 3.8 ID3 Tagging (default.py:1356-1387)

A background `Getid3Thread` class applies ID3v2 tags to downloaded files using `mutagen`. It:
1. Reads the original URL from `song-info.txt`
2. Fetches the album page again to re-parse metadata
3. Applies artist, title, album, genre, year, track number, and album art tags
4. Renames the file to `Artist - Title.mp3`

**Performance concern**: This re-fetches and re-parses the entire album page for each individual track download, rather than passing metadata through. If downloading a 12-track album, 12 separate HTTP requests + parses are made.

### 3.9 Favourites System (default.py:1520-1741)

A flat-file storage system with three data files:
- `favourites_artists.txt` — `<>` delimited: `Artist<>Url`
- `favourites_albums.txt` — `<>` delimited: `Album<>Artist<>Url<>Thumb`
- `favourites_songs.txt` — `<>` delimited: `Song<>Artist<>Url<>Album<>Thumb<>TrackNr`

Supports grouping through "Add New Group" and "Ungrouped" pseudo-items. Groups are delimited by `*<groupname>*` in the file. The file I/O functions (`read_from_file`, `write_to_file`, `add_to_list`, `remove_from_list`) use Python's `open()` without explicit encoding — relying on system default (ASCII on Linux, potentially causing UnicodeDecodeErrors with Cyrillic metadata).

### 3.10 Instant Mix (default.py:1399-1505)

Creates a shuffled playlist from favourites:
- **From Songs**: Collects all favourite songs, shuffles, prompts for count (via keyboard), plays the first N
- **From Albums**: Selects a random subset of favourite albums, then randomly selects 1-3 tracks per album

Uses `random.shuffle()` and `random.sample()`. The `ShuffleAlbumThread` runs UI updates in a background thread, which is racy — it calls `xbmcplugin.addDirectoryItems()` from a non-main thread.

---

## 4. Code Quality Assessment

### 4.1 Structural Issues

**Monolithic design**: `default.py` is 2,342 lines of flat, procedural code with no classes, no separation of concerns, and heavy coupling between UI rendering, HTTP logic, parsing, file I/O, and threading. Functions routinely span 100-250 lines.

**Duplicate code**: `settings.py` re-implements `create_directory()` and `create_file()` identically to those in `default.py`. The URL-building logic in `GET_url()` is a near-duplicate of `open_url()`.

**Magic numbers**: Mode dispatch uses 40+ hardcoded numeric values (`mode=1` through `mode=999`) with zero documentation, no enum, and no constants. Understanding the routing requires tracing through the entire `if/elif` ladder (default.py:2147-2342).

### 4.2 Identified Bugs

1. **BROKEN — Headers passed as query params** (default.py:127):
   `requests.get(url, headers)` instead of `requests.get(url, headers=headers)`. The `headers` dict lands in the `params` positional parameter, causing all custom headers (User-Agent, Referer, etc.) to be appended as URL query parameters. **This means the addon likely presents a default Python `requests` User-Agent to target sites.**

2. **Cookie cross-contamination** (default.py:104):
   A single `cookiejar` from `requests.session()` is shared across all requests, including Kodi's fanart downloader. Cookies from `musicmp3.ru` could interfere with other sites.

3. **Dead billboard.com code** (default.py:218-273):
   ~55 lines of code gated behind `CHART_SOURCE == '0'`, but `CHART_SOURCE` is hardcoded to `'1'`. This code paths through `billboard.py` entirely via dead `try/except` blocks.

4. **Bare `except:` masks** (multiple locations):
   Several `try/except` blocks use bare `except:` which catches `KeyboardInterrupt` and `SystemExit`, making the addon impossible to terminate cleanly in some states.

5. **SSL verification disabled** (playerMP3.py:481,492,497):
   `urllib.request.urlopen(req, context=ssl._create_unverified_context())` — disables certificate validation, a **critical security vulnerability**.

6. **Duplicate `PROFILE` assignment** (default.py:44,49):
   `PROFILE` is set twice via `xbmc.translatePath`, with the second overwriting the first.

7. **`list` variable shadowing** (default.py:1772):
   `def find_list(string, list):` shadows Python's built-in `list` type.

8. **Lock file race condition** (default.py:1259):
   `os.path.exists(lock)` followed by `open(lock, 'w')` is not atomic — concurrent instances can both pass the existence check.

9. **Potential infinite loop** (playerMP3.py:188):
   `stopDownloaders()` uses `while getNmrDownloaders() > 0: ...` with `xbmc.sleep(100)` but no timeout guard.

10. **Unused variable** (default.py:805):
    `playlist = xbmc.PlayList(xbmc.PLAYLIST_MUSIC)` is created but never used in `search_songs`.

11. **`len` shadows built-in** (default.py:1754):
    `def write_to_file(string, len):` shadows the built-in `len()`.

12. **Typo in MIME type** (default.py:831):
    `'Content-Type': 'application/octet-stream'` — should be `octet-stream`.

13. **Off-by-one in `get_params`** (default.py:1859):
    The parameter parser skips the first character of parameter values. For example, `?mode=5&name=foo` would parse `name` as `oo`.

### 4.3 Error Handling

Error handling is inconsistent:
- Some HTTP calls check status codes; others don't
- Network failures often produce cryptic Kodi popups ("Unknown error")
- Bare `except:` clauses swallow all exceptions silently
- No retry logic on transient failures (except in the downloader which has 2 retries)
- No logging framework — uses `xbmc.log()` with mixed severity levels throughout

---

## 5. Security Analysis

| Severity | Issue | Location |
|---|---|---|
| **CRITICAL** | SSL certificate verification disabled | playerMP3.py:481,492,497 |
| MEDIUM | No input sanitization on search queries | default.py:758 — user input passed directly to URL |
| MEDIUM | No path traversal protection in downloads | default.py:1212 — filename constructed from URL metadata |
| LOW | Hardcoded HTTP URLs in mp3url.list | lists/mp3url.list — all 29 entries use `http://` |

The SSL disabling is particularly concerning — it makes the addon vulnerable to man-in-the-middle attacks on the MP3 stream data and any metadata returned alongside it.

---

## 6. Performance Assessment

| Area | Assessment |
|---|---|
| **HTTP** | No connection pooling — new TCP/TLS handshake per request. `requests.Session` is instantiated but cookie-jar is the only reused component. |
| **Parsing** | Heavy regex usage on large HTML documents. The artist parsing regex runs across the entire page HTML. |
| **ID3 Tagging** | Re-fetches album page per track (N+1 problem for albums). |
| **Cache** | Filesystem-based, cleared every 25 seconds — reasonable for streaming, but no LRU eviction or size limits. |
| **Threading** | Each downloader thread creates a new `urllib.request` connection. Max 3 concurrent. No thread pool — created/destroyed per track. |
| **UI Responsiveness** | Some blocking HTTP calls happen on the main plugin thread, which can cause Kodi UI freezes during menu navigation. |

---

## 7. Maintainability Assessment

**Risk: Very High**. The codebase has:

- **Zero unit tests** — no test files, no test framework configured
- **No type hints** — all 3,300 lines are untyped Python
- **No consistent naming** — mixed `snake_case`, `camelCase`, and `PascalCase` for functions
- **No docstrings** — functions have no documentation beyond inline comments (which are sparse)
- **Tight coupling** — UI logic, HTTP, parsing, and threading are interleaved throughout
- **Vendor lock-in** — scraping HTML depends on specific DOM structures of 3 third-party websites that can change at any time
- **No dependency management** beyond `addon.xml` imports — no `requirements.txt`, no version pinning

---

## 8. Recommendations

### Priority 0 (Critical — Fix Immediately)

1. **Fix `GET_url` header passing**: Change `requests.get(url, headers)` to `requests.get(url, headers=headers)`.
2. **Enable SSL verification**: Remove `ssl._create_unverified_context()` usage. If certificates are truly problematic, implement proper certificate pinning instead.

### Priority 1 (High)

3. **Refactor mode dispatch**: Replace the 40+ branch `if/elif` ladder with a dictionary-based router. Map mode numbers to handler functions.
4. **Add timeouts to all HTTP calls**: `requests.get(url, timeout=10)` prevents UI hangs on network issues.
5. **Fix lock file race**: Use `os.open(lock, os.O_CREAT | os.O_EXCL)` for atomic lock acquisition.
6. **Add a logging system**: Replace scattered `xbmc.log()` calls with a proper logging facade.

### Priority 2 (Medium)

7. **Eliminate dead code**: Remove the `billboard.com` code path, unused `playlist` in `search_songs`, and duplicate functions.
8. **Introduce enums for modes**: Replace magic numbers with `IntEnum` or `StrEnum`.
9. **Add encoding to file operations**: Specify `encoding='utf-8'` on all `open()` calls.
10. **Fix `get_params` off-by-one**: Correct the parameter value parsing.

### Priority 3 (Low)

11. **Add types**: Introduce type hints for all public functions.
12. **Separate concerns**: Split `default.py` into modules (`browser.py`, `player.py`, `favourites.py`, `download.py`, `ui.py`).
13. **Connection pooling**: Reuse `requests.Session` properly across requests.
14. **Cache ID3 metadata**: Pass parsed metadata to tagger threads instead of re-fetching.

### Priority 4 (Cosmetic)

15. **Rename variables**: Replace `list`, `len` shadowing; fix `octet-stream` typo.
16. **Consistent formatting**: Adopt a formatter (e.g., `black` for Python).

---

## 9. Risk Matrix

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Site HTML structure changes | High | High — all scraping breaks | Add parsing resilience; consider API if available |
| musicmp3.ru goes offline | Medium | Critical — entire addon stops | Look for alternative sources |
| SSL MITM attack | Low | Critical — stream injection | Fix SSL immediately |
| Kodi API deprecation | Medium | Medium — playlist/view APIs | Track Kodi version support |
| Unicode encoding errors | Medium | Low — Cyrillic metadata fails | Add explicit UTF-8 encoding |

---

## 10. Conclusion

**MP3 Streams** is a functional but fragile Kodi audio addon that works primarily because the upstream sites have remained relatively stable. The architecture is typical of early Kodi addons — monolithic, procedural, and tightly coupled to screen-scraped HTML sources. The pre-cache system in `playerMP3.py` is actually the most architecturally interesting component, showing thoughtful design around concurrent download management and Kodi's unique `Window`-based IPC.

The critical bugs (broken HTTP headers, disabled SSL) need immediate attention. Beyond that, the codebase would benefit significantly from a structural refactor — even a modest investment in modularization, error handling, and type safety would dramatically improve maintainability. As a snapshot of a working Kodi addon from the "scrape-it-yourself" era, it's an interesting study in practical but rough-edged software engineering.

**Key numbers**: ~3,300 LOC across 3 source files, 3 external scraped sources, 150+ bundled artwork assets, 13 confirmed bugs, 1 critical security vulnerability, 0 tests.
