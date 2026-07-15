# Oste Repository

A custom Kodi add-on repository containing media streaming plugins.

## Add-ons

| Add-on | Description | Version |
|--------|-------------|---------|
| `repository.oste` | Repository installer - adds this repo to Kodi | 2.5.3 |
| `plugin.video.tubelink` | YouTube without API key (via yt-dlp) | 2.0.6 |
| `plugin.video.onepace` | One Pace - fan-edited One Piece anime | 1.0.0 |
| `plugin.audio.mp3streams-remastered` | Music streaming and downloading | 2025.0.1 |

## Installation

1. In Kodi, go to **Settings > File Manager > Add source**
2. Enter the following URL:
   ```
   https://raw.githubusercontent.com/Liutprando08/oste_repository/main/zips/
   ```
3. Give it a name (e.g. "Oste Repository") and click OK
4. Go to **Settings > Add-ons > Install from zip file** and select the source you just added
5. Install `repository.oste` from the listed files
6. After installation, you can install individual add-ons from **Install from repository > Oste Repository**

## Dependencies

The following Kodi module dependencies are required (usually pre-installed or auto-installed):

- `xbmc.python 3.0.0` (Kodi 19+)
- `script.module.mutagen` (for MP3 Streams)
- `script.module.requests` (for MP3 Streams)
- `script.module.beautifulsoup4` (for MP3 Streams)

## Development

### Adding or updating add-ons

1. Edit the add-on source in its respective `plugin.*` or `repository.*` directory
2. Update the version in `addon.xml`
3. Run the build script to regenerate ZIPs and the repository catalog:

```bash
./build.sh
```

### Build script

The `build.sh` script runs `create_repository.py` to:
- Create ZIP archives for each add-on
- Generate `zips/addons.xml` (the repository catalog)
- Generate MD5 checksums for all files

### Repository structure

```
.
├── repository.oste/          # Repository installer add-on
├── plugin.video.tubelink/    # YouTube plugin (includes vendored yt-dlp)
├── plugin.video.onepace/     # One Pace anime plugin
├── plugin.audio.mp3streams-remastered/  # Music streaming plugin
├── zips/                     # Distribution ZIPs and addons.xml
├── create_repository.py      # Build tool (by Chad Parry)
└── build.sh                  # Build wrapper script
```

## License

This project is licensed under the GPL v3 - see [LICENSE](LICENSE) for details.

Individual add-ons may have their own licenses (see respective directories).
