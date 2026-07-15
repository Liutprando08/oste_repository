# MP3 Streams (Remastered)

Kodi audio addon for streaming and downloading music. Based on the original MP3 Streams plugin, remastered for Kodi 19+ (Matrix) and later.

## Features

- Browse and stream music from online sources
- Download full albums or individual tracks
- Billboard Charts integration
- Artist and album search
- Favourite artists, albums, and songs
- Instant Mix (shuffle and play)
- ID3 tag writing for downloaded music
- Compilations browsing

## Requirements

- Kodi 19 (Matrix) or later
- Python 3
- The following Kodi addon modules (usually pre-installed):
  - `script.module.requests`
  - `script.module.beautifulsoup4`
  - `script.module.mutagen`

## Installation

### From zip file

1. Download the latest release zip from the [Releases](https://github.com/) page
2. In Kodi, go to **Add-ons** > **Install from zip file**
3. Browse to the downloaded zip and select it
4. The addon will appear under **Music Add-ons**

### Manual installation

1. Clone or download this repository
2. Copy the `plugin.audio.mp3streams-remastered` folder to your Kodi addons directory:
   - Linux: `~/.kodi/addons/`
   - macOS: `~/Library/Application Support/Kodi/addons/`
   - Windows: `%APPDATA%\Kodi\addons\`
3. Restart Kodi

## Settings

After installation, configure the addon via **Add-ons** > **MP3 Streams** > **Settings**:

- **Music Directory**: Choose where to save downloaded music (default: addon data folder)
- **Folder Structure**: `Artist/Album` or `Artist - Album`
- **Keep Downloads**: Whether to keep downloaded files after playback
- **Queue Albums/Songs**: Enable queue mode instead of immediate playback

## License

This project is licensed under the GNU General Public License v2.0 - see the [LICENSE](LICENSE) file for details.
