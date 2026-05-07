# Codebase Deep Analysis — `plugin.audio.mp3streams`

## 1. Executive Overview

This is a **Kodi audio addon** (`plugin.audio.mp3streams`) that streams MP3 music from two Russian websites (`musicmp3.ru`, `goldenmp3.ru`) and scrapes chart data from `officialcharts.com`. It targets Kodi 19+ users who want on-demand music browsing, search, playlist pre-caching, and offline downloads without a subscription service. The architectural philosophy is a **monolithic Kodi plugin + background service**: `default.py` handles UI navigation and scraping, while `playerMP3.py` runs as a Kodi service providing background pre-caching of upcoming playlist tracks. The codebase is a ~2011-era fork from the `t0mm0` common library, patched incrementally over a decade with no systematic refactoring, resulting in severe technical debt.

---

## 2. Architecture & Structure

### High-Level Architecture

**Monolithic Kodi addon** with two entry points:
1. **Plugin source** (`default.py`, 1457 lines) — invoked when the user navigates the addon; responsible for all menu rendering, HTTP scraping, search, downloads, and favourites management.
2. **Service** (`playerMP3.py`, 720 lines) — registered as `<extension point="xbmc.service">`, runs as a background service that detects when music starts playing and pre-caches subsequent tracks via a pool of `Downloader` threads.

### Directory Map

| Path | Responsibility |
|---|---|
| `default.py` | All UI, scraping, download, favourites, search, navigation logic |
| `playerMP3.py` | Pre-caching service, background downloading, ID3 tagging |
| `settings.py` | Thin wrapper around Kodi settings API + path/folder helpers |
| `addon.xml` | Addon manifest, dependency declarations, entry points |
| `advancedsettings.xml` | Override Kodi audio player to `dvdplayer` |
| `lists/mp3url.list` | Hardcoded mapping of 29 track-number-to-musicmp3.ru URL prefixes |
| `resources/settings.xml` | 10 Kodi settings definitions (pre-cache amount, queue, directories) |
| `resources/language/english/strings.xml` | English localization strings |
| `art/` | ~150 pre-bundled icon images for genres, subgenres, billboard charts |
| `t0mm0/common/addon.py` | Reusable Kodi addon helper library (URL building, dialogs, pickling) — **fully dead code** |
| `t0mm0/common/net.py` | HTTP networking wrapper with cookie support — partially used, partially broken |

### Design Patterns

- **Scraper pattern**: BeautifulSoup + regex-based HTML scraping from remote sites — the primary data access pattern throughout
- **Thread pool**: `playerMP3.py` maintains 3 concurrent `Downloader` threads for pre-caching, coordinated via Kodi Window properties (a makeshift IPC)
- **Observer (Kodi-driven)**: The service loop polls `xbmc.Monitor().abortRequested` and `xbmc.Player().isPlaying()` to determine when to start pre-caching
- **Repository (crude)**: Favourites are stored as flat text files, split/joined on `<>` delimiter

### Architectural Violations

| Violation | Location | Impact |
|---|---|---|
| Two competing HTTP stacks used inconsistently | `default.py:75-78`, `net.py`, `default.py:152` | Cookies set in one stack are ignored by the other; requests bypass cookie handling |
| Massive regex duplication with commented-out alternatives | Lines 329-330, 365-366, 387-388, 422-423, 425-426, 428, 653 | Dead comments hide which pattern is actually active |
| `settings.py` duplicates `create_directory`/`create_file` | `settings.py:83-99` = `default.py:1136-1152` | Exact verbatim copy; changes must be made in both places |

---

## 3. Tech Stack & Dependencies

| Dependency | Version (declared) | Purpose | Assessment |
|---|---|---|---|
| `xbmc.python` | 3.0.0 | Kodi Python API (Python 3 binding) | Current for Kodi 19+ |
| `script.module.future` | unspecified | Python 2/3 compatibility layer | **Only needed by vendored t0mm0 library** — can be removed if t0mm0 is removed |
| `script.module.mutagen` | unspecified | ID3 tag reading/writing via `EasyID3` | Standard, but no version pin — risk of API breakage |
| `script.module.requests` | unspecified | HTTP library | **Misused** — headers passed as query params (Bug #1) |
| `script.module.beautifulsoup4` | unspecified | HTML parsing | Undersized — only used in one function (`chart_lists`) while regex is used everywhere else |
| `t0mm0.common` (bundled) | ~2011 | Addon helper | **Severely outdated**. Python 2 patterns, `pickle` serialization, no connection pooling |

### Dependency Issues

1. **No version pinning** on `script.module.future`, `mutagen`, `requests`, or `beautifulsoup4` — future Kodi repo changes could break the addon silently.
2. **`script.module.future` is only needed for t0mm0**. If the library were removed, this dependency could go.
3. **`requests` is badly misused** (see Bug #1).

---

## 4. Core Functionality — Feature by Feature

### Feature 1: Browsing (Artists, Genres, Albums, Compilations)

**What it does**: Presents a hierarchical menu: main categories → genres → artists → albums → songs.

**How it works**:
1. `CATEGORIES()` (line 89) populates the root menu with `addDir()` calls. Each call stores a mode number.
2. When the user selects an item, `default.py`'s mode dispatch (lines 1313-1457) routes to the appropriate function.
3. `artists()` (line 210) fetches `http://musicmp3.ru/artists.html`, regex-extracts subgenre URLs from `<li class="menu_sub__item">` elements.
4. `all_artists()` (line 219) fetches a paginated artist list, extracts from `<li class="small_list__item">` regex.
5. `genres()` (line 243), `sub_dir()` (line 236), `genre_sub_dir()` (line 263) all follow the same pattern: `GET_url` → regex → `addDir`.

**Inputs**: Hardcoded musicmp3.ru URLs, user navigation clicks.
**Outputs**: Kodi directory listings with icons, context menus.

**Edge cases handled**: Pagination (`>> Next page`), `&amp;` → `&`/`and` replacement, artist icon caching.

**Edge cases NOT handled**:
- **Site structure changes**: All scraping depends on fragile regex patterns over HTML. If musicmp3.ru changes CSS classes, every function breaks silently (empty listings).
- **Network errors**: `GET_url()` has a 10-second timeout but no retry logic. If the first request fails, the user sees an empty list.
- **Unicode normalization**: Icon filename generation (`title.replace(' ','').replace('&amp;','_').lower()`) doesn't handle non-ASCII characters (e.g., `José` → `josé`, icon lookup fails).

---

### Feature 2: Chart Scraping

**What it does**: Shows Top 20/40/50/100 chart listings from officialcharts.com.

**How it works**: `charts()` (line 107) adds 22 chart items. When one is selected, `chart_lists()` (line 148) uses BeautifulSoup to find `<div class="chart-image">` elements containing `<audio data-title="..." data-artist="...">` tags.

**Inputs**: Chart URL from menu selection.
**Outputs**: Directory listing of chart entries.

**Edge cases handled**: Checks for `'singles' in name.lower()` vs `'albums'` to decide routing.

**Edge cases NOT handled**:
- **Dead code paths**: The entire `elif "billboard.com"` branch (line 179) and `else` branch (line 192) are unreachable since all menu items point to `officialcharts.com`.
- **No HTTP error handling**: Uses raw `urllib.request.urlopen` (line 152) with no timeout, no retry, no status-code checking.
- **officialcharts.com HTML changes**: Any change to `class="chart-image"` will silently produce empty results.

---

### Feature 3: Search

**What it does**: Searches musicmp3.ru for artists, albums, or songs.

**How it works**: `search()` (line 300) shows a Kodi keyboard dialog, then routes to `search_artists()`, `search_albums()`, or `search_songs()`.

**Inputs**: User keyboard input.
**Outputs**: Directory listing (artists/albums) or playlist (songs).

**Edge cases handled**: Replaces ` - ` with space, handles `Various Artist` HTML workaround (lines 328, 341).

**Edge cases NOT handled**:
- **`search_songs()` URL construction at line 339**: `query.replace(' ', '+')` after other replacements. If user types `artist FT song`, it becomes `artistFTsong` because `FT ` was replaced first.
- **`search_songs()` at line 338, 349-354**: Creates a `playlist` list and `xbmcgui.ListItem` objects that are never used — dead code.

---

### Feature 4: Album Playback with Pre-caching

**What it does**: Plays an album by adding each song to the Kodi playlist and pre-caching upcoming tracks via `playerMP3.py`.

**How it works**:
1. `play_album()` (line 411) is entered via mode 5/6/7.
2. If `browse` mode, it shows songs as a listing (line 486) and returns.
3. Otherwise, it fetches the album page, regex-extracts track data, builds playlist items via `playerMP3.getListItem()`.
4. `getListItem()` (playerMP3.py:385) creates a `plugin://` URL with mode=999 pointing back to the addon with pre-cache parameters.
5. When the track is about to play, Kodi calls the addon with mode 999, invoking `playerMP3.play()` (line 539).
6. `play()` fetches the current file, then calls `fetchNext()` to start pre-caching the following track.
7. `Downloader` threads download MP3 data into `TEMP` directory.
8. `verifyFileSize()` polls until the file reaches the pre-cache threshold or times out after 50 seconds.

**Inputs**: Album URL, artist name, icon image.
**Outputs**: Kodi playlist populated with pre-cached songs.

**Edge cases handled**: Already-downloaded files (line 539), distribution lock via window properties (MAX_DOWNLOADERS=3), signal mechanism to stop downloaders.

**Edge cases NOT handled**:
- **Regex dependency**: The entire pipeline depends on `rel=` being present in song HTML (line 446). Missing `rel=` triggers a silently different regex.
- **`verifyFileSize()` (playerMP3.py:205)**: 0-byte files are polled for 50 seconds then silently failed.
- **All 3 downloader slots full**: `fetchNext()` (line 441) silently does nothing — next track is never pre-cached.
- **GOTHAM_FIX fallback (line 500-510)**: References `myfreemp3.eu` (dead since ~2018). Bare `except:` swallows the error.

---

### Feature 5: Downloads

**What it does**: Downloads individual songs or full albums to the user's music directory.

**How it works**: `download_song()` (line 593) and `download_album()` (line 632) stream MP3 data via `requests.get(url, headers=headers, stream=True)` and write chunks to disk.

**Inputs**: Song/album URL, metadata.
**Outputs**: MP3 files on disk + entry in DOWNLOAD_LIST for ID3 tagging.

**Edge cases handled**: Album download lock (prevents concurrent album downloads), notification updates per track.

**Edge cases NOT handled**:
- **Race condition**: Lock checked at line 644, created at line 676 (inside loop). Between these, another download can slip through.
- **No partial download recovery**: Failed downloads leave partial files on disk with no cleanup.
- **Network error**: `requests.get()` at line 678 has no timeout and no error handling. A connection drop mid-album crashes the function, leaving the lock file in place permanently.
- **Memory buffer**: `iter_content()` uses no `timeout` on the request, so a stalled server hangs the UI.

---

### Feature 6: Favourites System

**What it does**: Saves favourite artists, albums, and songs to flat text files with optional grouping.

**How it works**: All favourites are stored as `<>`-delimited flat files. Adding/removing parses the entire file, checks for duplicates, and rewrites it.

**Inputs**: User context menu selection, group name.
**Outputs**: Text file entries.

**Edge cases handled**: Group selection with "Add New Group", duplicate prevention via `find_list()`.

**Edge cases NOT handled**:
- **Concurrent write race**: `add_to_list()` reads entire file, modifies, writes back. Two concurrent operations cause one to clobber the other.
- **No file size limit**: Hundreds of favourites → O(n) scan on every add/remove.
- **No `<>` delimiter escaping**: If any metadata naturally contains `<>`, the file format breaks.
- **Prepend vs. append**: New entries are prepended (line 1057), so favourites display in reverse chronological order — likely unintentional.

---

### Feature 7: ID3 Tagging

**What it does**: Applies ID3 tags (title, artist, album, track number) to downloaded MP3 files.

**How it works**: `Getid3Thread` (line 702) reads `downloads.list`, applies tags via mutagen `EasyID3`, removes the entry. In `playerMP3.py`, `Downloader.applyID3()` (line 645) does the same for pre-cache files kept (`keep_downloads=true`).

**Edge cases**: Skips files where `track < 1`, handles non-existent files gracefully.

**Edge cases NOT handled**:
- **Inefficiency in `applyID3()` (playerMP3.py:656-684)**: Copies file to temp, edits temp, deletes original, copies back. Doubles I/O for every pre-cached file. On a Raspberry Pi, this is painful.
- **Empty tag writes**: Lines 676-677 set `audio["date"] = ""` and `audio["genre"] = ""` — writes empty tags that are unnecessary.

---

## 5. Bug Report

### 🐛 Bug #1 — `GET_url()` passes headers as query parameters

- **Location**: `default.py` — line 77
- **Severity**: Critical
- **Type**: Logic Error
- **Description**: `requests.get(url, header_dict, timeout=10).text` passes `header_dict` as the second positional argument. In the `requests` library API, `requests.get(url, params=None, **kwargs)`. The second positional arg is `params` (query parameters), NOT `headers`. This means all custom headers (Accept, User-Agent, Host, Referer, Connection) are silently appended as URL query parameters like `?Accept=audio%2Fwebm...`. The actual HTTP request has no custom headers. This breaks server-specific behavior especially for goldenmp3.ru.
- **Reproduction**: Set `GOLDEN_PATH = True` or browse goldenmp3.ru compilations. The server may reject the request or return different content without the proper Referer header.
- **Proposed Fix**:
  ```python
  def GET_url(url):
      header_dict = {}
      if 'musicmp3' in url:
          header_dict['Accept'] = 'audio/webm,audio/ogg,audio/wav,audio/*;q=0.9,application/ogg;q=0.7,video/*;q=0.6,*/*;q=0.5'
          header_dict['User-Agent'] = 'AppleWebKit/<WebKit Rev>'
          header_dict['Host'] = 'musicmp3.ru'
          header_dict['Referer'] = 'http://musicmp3.ru/'
          header_dict['Connection'] = 'keep-alive'
      if 'goldenmp3' in url:
          header_dict['Accept'] = 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
          header_dict['User-Agent'] = ua
          header_dict['Host'] = 'www.goldenmp3.ru'
          header_dict['Referer'] = 'http://www.goldenmp3.ru/compilations/events/albums'
          header_dict['Connection'] = 'keep-alive'
      return requests.get(url, headers=header_dict, timeout=10).text
  ```

### 🐛 Bug #2 — Cookie cross-contamination between HTTP libraries

- **Location**: `default.py` — lines 75-78 and `t0mm0/common/net.py`
- **Severity**: High
- **Type**: Logic Error
- **Description**: `GET_url()` calls `net.set_cookies(cookie_jar)` (line 75, loading cookies into `t0mm0.net`'s `CookieJar`) but then fetches with `requests.get()` (line 77, which uses `requests`'s own session). Then `net.save_cookies(cookie_jar)` (line 78) saves `t0mm0.net`'s cookies — but the `requests` call may have set/updated cookies that are never saved. Conversely, cookies loaded into `t0mm0.net` are never sent with the `requests` call. Cookies are silently lost.
- **Reproduction**: Any flow that calls `GET_url()` twice. The first request's Set-Cookie headers are stored in `requests`'s internal session but never persisted. The second request doesn't send them.
- **Proposed Fix**: Use `requests.Session()` with proper cookie persistence, or use `t0mm0.net` consistently. Better:
  ```python
  import requests
  from http.cookiejar import LWPCookieJar
  
  _session = requests.Session()
  _cj = LWPCookieJar(settings.cookie_jar())
  try:
      _cj.load(ignore_discard=True)
  except:
      pass
  _session.cookies.update({c.name: c.value for c in _cj})  # simplistic; a full conversion needs cookiejar_from_dict
  ```

### 🐛 Bug #3 — Unreachable/dead `billboard.com` code in `chart_lists()`

- **Location**: `default.py` — lines 179-208
- **Severity**: Medium
- **Type**: Dead Code
- **Description**: The `elif "billboard.com" in url:` branch (line 179) and `else:` branch (line 192) are never reached because all chart menu items in `charts()` point exclusively to `officialcharts.com` URLs. The code is dead.
- **Reproduction**: Not triggered by any current menu path.
- **Proposed Fix**: Remove lines 179-208 entirely.

### 🐛 Bug #4 — Bare `except:` masks `KeyboardInterrupt` and `SystemExit`

- **Location**: Multiple locations in `default.py` — lines 186, 199, 202, 362, 385, 567, 710-712, 748-753, 865-877, etc.
- **Severity**: Medium
- **Type**: Error Handling
- **Description**: Bare `except:` (without specifying an exception type) catches `KeyboardInterrupt`, `SystemExit`, and `GeneratorExit`, making the addon unkillable via Ctrl+C in development and masking critical errors.
- **Reproduction**: Trigger any error in a try block (e.g., regex match failure at line 186). It's silently caught.
- **Proposed Fix**: Replace every bare `except:` with `except Exception:` (or more specific types).

### 🐛 Bug #5 — SSL verification disabled

- **Location**: `playerMP3.py` — line 618
- **Severity**: High
- **Type**: Security Vulnerability
- **Description**: `requests.get(self.url, headers=headers, stream=True, verify=False)` disables SSL/TLS certificate validation. All HTTPS music downloads are vulnerable to MitM attacks.
- **Reproduction**: Any playback that routes through pre-caching (mode 999 flow).
- **Proposed Fix**: Remove `verify=False`:
  ```python
  requests.get(self.url, headers=headers, stream=True)
  ```

### 🐛 Bug #6 — Duplicate `PROFILE` assignment

- **Location**: `playerMP3.py` — lines 157-158
- **Severity**: Low
- **Type**: Dead Code
- **Description**: Line 157 assigns `PROFILE = xbmcvfs.translatePath(...)`. Line 158 immediately overwrites it with the untranslated path. Line 157 is wasted work.
- **Proposed Fix**: Remove line 157.

### 🐛 Bug #7 — `add_to_list()` shadowing built-in `list` + prepend semantics

- **Location**: `default.py` — lines 400, 710, 743, 764, 817, 849, 867, 885, 906, 924, 961, 999, 1056-1059
- **Severity**: Medium
- **Type**: Code Quality
- **Description**: The variable name `list` shadows Python's built-in `list` in at least 13 locations. In `add_to_list()` (line 1049), the new item is **prepended** (line 1057), not appended — so favourites lists are built in reverse chronological order.
- **Proposed Fix**: Rename all `list` variables to `entry`, `item`, or `line`. Change prepend to append.

### 🐛 Bug #8 — `download_album()` creates lock file inside loop

- **Location**: `default.py` — lines 644, 676, 690-691
- **Severity**: High
- **Type**: Race Condition
- **Description**: The download lock `downloading.txt` is created at line 676 **inside** the per-track loop. If an error occurs between the HTTP GET (line 648) and creating the lock file (line 676), no lock exists and a concurrent album download can start.
- **Reproduction**: Start an album download. While the first track is downloading, start another — it may be allowed to proceed.
- **Proposed Fix**: Move lock file creation to before the HTTP request:
  ```python
  def download_album(url, name, iconimage):
      download_lock_file = create_file(MUSIC_DIR, "downloading.txt")
      # ... rest of function
  ```

### 🐛 Bug #9 — Potential infinite loop in `stopDownloaders()`

- **Location**: `playerMP3.py` — lines 259-266
- **Severity**: Low
- **Type**: Logic Error (edge case)
- **Description**: `stopDownloaders()` resets `i = 0` whenever it finds a non-empty property. If a downloader thread crashes without clearing its property, the loop becomes infinite. In practice, `Downloader.run()` clears it at line 705, but a violent thread kill (e.g., Kodi shutdown) could leave it set.
- **Proposed Fix**: Add a maximum iteration guard:
  ```python
  def stopDownloaders():
      for i in range(MAX_DOWNLOADERS):
          xbmcgui.Window(10000).setProperty(PROPERTY % i, "Signal")
      for _ in range(200):  # max 20 seconds
          all_clear = True
          for i in range(MAX_DOWNLOADERS):
              if xbmcgui.Window(10000).getProperty(PROPERTY % i):
                  all_clear = False
                  break
          if all_clear:
              return
          xbmc.sleep(100)
  ```

### 🐛 Bug #10 — `search_songs()` builds unused playlist list

- **Location**: `default.py` — lines 338, 349-354
- **Severity**: Low
- **Type**: Dead Code
- **Description**: A `playlist` list is created at line 338 and appended to at line 354, but never returned, passed, or used for playback.
- **Proposed Fix**: Remove lines 338 and 349-354.

### 🐛 Bug #11 — `len` variable shadows built-in

- **Location**: `playerMP3.py` — line 452
- **Severity**: High
- **Type**: Code Quality
- **Description**: `len = playlist.size()` shadows the built-in `len()` function. Line 454: `if posn >= len:` uses the shadowed variable. Any code below that needs `len()` for its real purpose will break.
- **Proposed Fix**: Rename to `pl_size` or `length`.

### 🐛 Bug #12 — Misspelled MIME type

- **Location**: `default.py` — line 64
- **Severity**: Low
- **Type**: Typo (may cause server misinterpretation)
- **Description**: `'audio/webm,audio/ogg,udio/wav,audio/*;q=0.9'` — `udio/wav` is missing the leading `a`. Should be `audio/wav`. This means the server may deprioritize WAV responses.
- **Proposed Fix**: Change to `audio/wav`.

### 🐛 Bug #13 — `get_params()` URL truncation logic error

- **Location**: `default.py` — lines 1114-1115
- **Severity**: Low
- **Type**: Off-by-one
- **Description**: `if (params[len(params)-1] == '/'): params = params[0:len(params)-2]` — if the last char is `/`, it strips 2 chars instead of 1. This is a latent bug that would manifest if Kodi ever passes a trailing-slash URL. The correctly stripped URL would lose its last character.
- **Proposed Fix**: Change `-2` to `-1`.

---

## 6. Security Analysis

### 🔴 Critical — SSL Verification Disabled

- **Location**: `playerMP3.py` line 618
- **Risk**: All HTTPS music downloads are vulnerable to MitM attacks. An attacker on the network can substitute arbitrary content.
- **Impact**: Complete compromise of downloaded audio content. Could inject malware disguised as MP3 files.
- **Fix**: Remove `verify=False`.

### 🟡 Medium — Hardcoded User-Agent Strings

- **Location**: `default.py` lines 41, 65, 83; `playerMP3.py` lines 608-610
- **Risk**: Multiple distinct User-Agent strings hardcoded (Chrome OS, AppleWebKit, Firefox 44). `requests` library has no default UA set by the code.
- **Impact**: Low — primarily fingerprinting and potential blocking by CDNs.
- **Fix**: Consolidate to one modern UA string and use it consistently.

### 🟡 Medium — No Input Sanitization in Notification

- **Location**: `default.py` line 1106
- **Risk**: `xbmc.executebuiltin("XBMC.notication(" + title + "," + message + "," + ms + "," + nart + ")")` — if `title`, `message`, or `nart` contain special characters like `)` or `,`, they could break out of the builtin command and inject arbitrary Kodi builtins.
- **Impact**: Low in practice (Kodi's parser is strict, and notification data comes from scraped sources, not user input). But it's a code injection vector in theory.
- **Fix**: Use `xbmcgui.Dialog().notification()` instead:
  ```python
  def notification(title, message, ms, nart):
      xbmcgui.Dialog().notification(title, message, nart, int(ms.replace('000', '')))
  ```

### 🟢 Low — Cookie File in Plaintext

- **Location**: `settings.py` line 9
- **Risk**: Cookies stored in `cookiejar.lwp` in plaintext.
- **Impact**: Negligible for music streaming site cookies.

---

## 7. Performance Assessment

### 🔴 Bottleneck — Double I/O in ID3 Tagging

- **Location**: `playerMP3.py` lines 656-684
- **Issue**: `applyID3()` copies the MP3 to temp, edits temp, deletes original, copies back. For a 5MB MP3, that's 10MB of writes + a delete per track. A 12-track album = 120MB of write I/O.
- **Fix**: Edit ID3 tags in-place using mutagen. Investigate and fix whatever locking issue motivated the copy-delete-copyback pattern.

### 🟡 Medium — No Connection Reuse

- **Location**: `default.py` lines 53, 77; `playerMP3.py` line 618
- **Issue**: Every HTTP request creates a new TCP connection. Loading an album page with 12 tracks = 13 TCP handshakes. No connection pooling.
- **Fix**: Use `requests.Session()` throughout. It maintains connection pools and cookie jars automatically.

### 🟡 Medium — Regex on Large HTML Strings

- **Location**: Multiple regex calls throughout `default.py` (lines 213, 221, 239, 249, 258, 266, 274, 288, 316, etc.)
- **Issue**: Each regex compiles on-the-fly and operates on full HTML. Python's backtracking regex engine can exhibit catastrophic backtracking on the 200+ character patterns in lines 422, 425, 428, 653 when given malformed HTML.
- **Fix**: Use BeautifulSoup consistently for all HTML parsing.

### 🟢 Low — Polling-Based Service Loop

- **Location**: `playerMP3.py` lines 117-122
- **Issue**: 1-second polling is standard for Kodi services. Acceptable.

---

## 8. Code Quality & Maintainability

### Readability Issues

| Issue | Severity | Location |
|---|---|---|
| Variable `list` shadows built-in 13+ times | High | `default.py` lines 400, 710, 743, 764, 817, 849, 867, 885, 906, 924, 961, 999, 1301 |
| `len` shadows built-in | High | `playerMP3.py:452` |
| All constants are global mutable state | Medium | `default.py` lines 15-41 — values set at import, stale on setting change |
| Magic mode numbers everywhere | High | `default.py` lines 1317-1455 — 40-branch `if/elif` ladder using opaque ints |
| Hardcoded date in string match | Medium | `default.py:188`: `'Best Songs of 2014'` — 12 years past |
| Commented-out code | Medium | Lines 54-59, 76, 104-105, 130-146, 288-289, 329-330, 365-366, 387-388, 422-423, 425-426, 428, 608-631, 669, 685 |
| Opaque variable names | Medium | `std`, `alt`, `trn`, `d1`, `nartist`, `nalbum`, `origurl` in `play_album()` |
| Unescaped regex metacharacters | Medium | `default.py:1154` — `from_string` and `to_string` concatenated directly into regex without `re.escape()` |
| Typo in MIME type | Low | `default.py:64`: `udio/wav` vs `audio/wav` |

### Dead Code Inventory

| Function/Variable | Location | Reason Dead |
|---|---|---|
| `get_cookie()` | `default.py:81-87` | Never called (line 1315 commented out) |
| `addLink()` | `default.py:1169-1175` | Never called |
| `playlist` list in `search_songs()` | `default.py:338,354` | Built and appended, never used |
| `DownloadMusicThread` (commented class) | `default.py:609-631` | Commented out |
| All `billboard.com` branch | `default.py:179-208` | Unreachable — all chart URLs are officialcharts.com |
| `GOTHAM_FIX` path | `default.py:500-510` | References `myfreemp3.eu` (dead domain) |
| `FRODO` compatibility | `playerMP3.py:32,402` | Kodi 12 (2013) — addon claims Kodi 19+ support |
| `t0mm0/addon.py` (792 lines) | Full file | `Addon` class is imported at `default.py:9` but never instantiated. Fully dead. |

### Duplicate Code

| Duplication | Locations | Notes |
|---|---|---|
| `create_directory()` and `create_file()` | `settings.py:83-99` AND `default.py:1136-1152` | Exact verbatim copy |
| Album track extraction regex patterns | Lines 422, 425, 428, 653, 655 | Nearly identical, written inline 3+ times |
| Favourites group selection UI | 4 copies in lines 862-881, 900-919, 955-970, 994-1009 | Minor variation per file |
| URL construction pattern | Lines 1190, 1234, 1196, 1201, etc. | Repeated verbatim in context menu builders |

### Test Coverage

**Zero.** No test files, no test framework dependency, no test harness. Every function depends on Kodi runtime globals (`xbmc`, `xbmcgui`, `xbmcplugin`, `sys.argv`), making testing impossible without full Kodi emulation. The module-level side effects at import (creating files, reading settings, calling `xbmc.getInfoLabel`) mean you cannot even import `default.py` outside Kodi.

---

## 9. Risks & Technical Debt

### Risk Matrix

| Risk | Likelihood | Impact | Priority |
|---|---|---|---|
| `musicmp3.ru` / `goldenmp3.ru` change HTML structure | High (inevitable) | Critical — entire addon becomes non-functional | Highest |
| `officialcharts.com` changes CSS classes | Medium (periodic redesigns) | High — chart listings break silently | High |
| `listen.musicmp3.ru` switches to HTTPS-only | Medium | Critical — all playback URLs use `http://` | High |
| `myfreemp3.eu` fallback creates confusing error path | Already happening | Low — `except:` silently swallows DNS failure | Low |
| SSL disabled makes MitM trivial | Low (targeted attack) | Critical — audio content integrity | High |

### Technical Debt Register

1. **Regex-based HTML parsing** — The single biggest source of fragility. Every scraping function is one CSS class rename away from breaking. BeautifulSoup is already a dependency but only used in `chart_lists()`. **Cost to fix**: Moderate.

2. **Dual HTTP stack** — `t0mm0.net` and `requests` both used, with broken cookie sharing between them. **Cost to fix**: Low.

3. **Magic numbers** — 40+ modes (5, 6, 7, 10, 11, 18, 21...) scattered across `addDir()` calls and `if/elif` dispatch. **Cost to fix**: Low.

4. **Vendored `t0mm0` library** — 1123 lines of Python 2-era code, only 331 lines (`net.py`) actually used. `addon.py` (792 lines) is fully dead. Future compatibility risk. **Cost to fix**: Low.

5. **Flat-file favourites storage** — `<>`-delimited text files with zero write concurrency protection. **Cost to fix**: Low.

6. **Module-level side effects** — `default.py` cannot be imported without a running Kodi instance. No testing possible. **Cost to fix**: High (architectural).

---

## 10. Recommendations — Priority Action Plan

### P0 — Critical (fix now)

1. **Fix header-params bug in `GET_url()`** (`default.py:77`) — change `requests.get(url, header_dict, ...)` → `requests.get(url, headers=header_dict, ...)`. Fixes all header-dependent scraping.

2. **Fix cookie handling** — Replace `t0mm0.net` cookie management with `requests.Session()` throughout. Fixes cookie persistence across requests.

3. **Remove `verify=False`** (`playerMP3.py:618`). Closes MitM attack vector on all MP3 downloads.

### P1 — High (fix this cycle)

4. **Replace all regex-based HTML scraping with BeautifulSoup** — Every scraping function. BeautifulSoup is already a dependency. Dramatically reduces fragility against site HTML changes.

5. **Replace magic number dispatch with a dict** (`default.py:1317-1455`):
   ```python
   MODE_DISPATCH = {
       5: lambda: play_album(...),
       6: lambda: play_album(...),
       ...
   }
   handler = MODE_DISPATCH.get(mode)
   if handler: handler()
   ```

6. **Fix bare `except:` clauses** — All ~20 instances: `except:` → `except Exception:`.

7. **Fix `notification()` function** (`default.py:1106`) — Use `xbmcgui.Dialog().notification()` instead of `xbmc.executebuiltin()`.

### P2 — Medium (this quarter)

8. **Standardize on one HTTP library** — Remove `t0mm0/common/net.py` dependency. Use single `requests.Session()`.

9. **Remove `t0mm0/common/addon.py`** (792 lines of dead code). Remove `script.module.future` dependency from `addon.xml`.

10. **Fix `download_album()` lock race** — Move lock file creation before HTTP GET.

11. **Fix `applyID3()` double I/O** (`playerMP3.py:656-684`) — Edit ID3 tags in-place.

12. **Fix `len` variable shadowing** (`playerMP3.py:452`).

### P3 — Low (nice to have)

13. **Rename all `list` variables** to `entry`, `item`, or `line`.

14. **Rewrite favourites storage** to JSON with atomic writes (write to temp, rename).

15. **Clean up all commented-out code** — ~30 locations.

16. **Add error handling for network failures** — `requests.ConnectionError`, `requests.Timeout` → user-friendly dialog.

17. **Fix `get_params()` trailing-slash off-by-one** (`default.py:1114-1115`): `-2` → `-1`.

### P4 — Architectural (next major version)

18. **Split `default.py` into modules**: `navigation.py`, `scraper.py`, `downloader.py`, `favourites.py`, `search.py`, `utils.py`.

19. **Replace flat-file storage** with JSON with atomic writes.

20. **Remove all t0mm0 code** — replace with thin `requests.Session()` wrapper.

### P5 — Stretch

21. **Add fallback music source** (Internet Archive, Jamendo, Free Music Archive) to eliminate single-source dependency.

22. **Implement proper error handling throughout** — every network call should have a user-visible error dialog.

23. **Add settings refresh mechanism** — read settings from `ADDON.getSetting()` on each operation instead of using stale module-level globals.

24. **Audit and update `lists/mp3url.list`** — change `http://` to `https://`, verify all 29 URL prefixes still resolve.

---

### Closing Assessment

This addon works today through luck more than design. The core streaming functionality depends on a decade of patches over an unsalvageable scraping layer. The two critical bugs (Bug #1 and Bug #2) mean header-dependent requests silently fail in ways that may already be causing intermittent failures attributed to "site changes."

The good news: the fixes are mostly mechanical and low-risk. There are no deep algorithm problems, no architectural dead ends that require a rewrite. A disciplined engineer could bring this codebase to a maintainable state in **2-3 focused sprints**:

- **Sprint 1** (P0 + P1): Fix critical bugs, standardize HTTP, replace regex with BeautifulSoup, fix notification injection, remove dead code.
- **Sprint 2** (P2): Split monolith, rewrite storage to JSON, fix races, remove t0mm0 dependency.
- **Sprint 3** (P3-P4): Error handling, settings refresh, testing harness, fallback sources.
