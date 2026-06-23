<h1 align="center">Auto Watch Later</h1>

## 🚀 Quick Start

### Local (browser available)
```bash
pip install -r requirements.txt
python auto_watch_later.py
```
A browser window will open automatically for OAuth authentication.

### Docker / Headless server
```bash
docker-compose up --build
```
The script detects that no browser is available and switches to Device Flow: it displays a short URL and a code to validate from any device (phone, PC, etc.). No interaction needed in the terminal.

📖 See [DOCKER.md](DOCKER.md) for details.

## Table of Contents
- [About](#about)
- [Quick Start](#-quick-start)
- [Setup](#setup)
- [Quota management](#quota-management)
- [Docker](#docker)
- [Built Using](#built_using)
- [Authors](#authors)
- [Acknowledgments](#acknowledgement)

## Setup <a name = "setup"></a>

The script supports two authentication modes, detected automatically at runtime.

### Mode 1 — Local / Desktop (browser available)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project and enable **YouTube Data API v3**
3. Create OAuth 2.0 credentials → type **Desktop application**
4. Download the JSON file, rename it to `client_secrets.json` and place it next to the script
5. Run the script — a browser window opens automatically

### Mode 2 — Docker / Headless server (no browser)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project and enable **YouTube Data API v3**
3. Create OAuth 2.0 credentials → type **TVs and Limited Input devices**
4. Set the following environment variables (e.g. in `docker-compose.yml`):
   ```yaml
   environment:
     - YOUTUBE_CLIENT_ID=your_client_id
     - YOUTUBE_CLIENT_SECRET=your_client_secret
   ```
   Alternatively, place `client_secrets.json` in the working directory as a fallback.
5. Run the script — it displays a short URL and a code to validate from any device

> **Note:** The `token.pickle` file is saved after first authentication and reused on subsequent runs. Mount `./data` as a volume to persist it across container restarts.

### Content filters

By default, Shorts and teasers/trailers are excluded from the playlist. You can opt in via environment variables:

| Variable | Default | Description |
|---|---|---|
| `INCLUDE_SHORTS` | `false` | Include YouTube Shorts |
| `INCLUDE_TEASERS` | `false` | Include teasers and trailers (detected by title keywords) |

```yaml
environment:
  - INCLUDE_SHORTS=true
  - INCLUDE_TEASERS=true
```

These can be used in both local and Docker modes.

### Quota management

The YouTube Data API v3 has a daily limit of 10,000 units. The script logs quota consumption at the end of every run:

```
=== API Quota consumed ===
  playlistItems.insert: 53× (50 unit/call) = 2650 units 
  activities.list: 355× (1 unit/call) = 355 units 
  playlistItems.list: 265× (1 unit/call) = 265 units 
  channels.list: 1× (1 unit/call) = 1 units 
  Total : 3271 / 10000 units  (32.7% of daily quota)
```

If the quota is exceeded mid-run, the script saves its progress and resumes automatically on the next run — no videos are missed and no duplicate inserts occur. The following files are created in `./data` only when needed:

| File | Purpose |
|---|---|
| `pending_videos.json` | Videos found but not yet added to the playlist |
| `scan_progress.json` | Last channel index and Shorts cache for scan resume |
| `playlist_id.txt` | Cached playlist ID to avoid scanning all playlists every run |
| `subscriptions_cache.json` | Cached channel list (refreshed every 24h) |

## About <a name = "about"></a>
I watch YouTube on almost a daily basis, so I wanted a way to automatically add my subscriptions to a custom playlist so I can add them to the YouTube built-in Watch Later playlist. The YouTube Data API v3 doesn't let you mess with Watch Later directly, so I have to use a temp playlist and add all videos to Watch Later from there, which is just a "Add all to..." button in the playlist settings on the YouTube desktop website.

### Why? <a name = "why"></a>
Since I have over 200 subscriptions, I get a lot of video notifications on my phone, and Android will start removing older notifications from the same app once you get too many, and I'd rather not miss any videos.

The drawback is I'm getting every single video/livestream from all my subscriptions, whereas I used to be able to filter out anything I'm not interested in based on title/thumbnail/type. I don't mind clearing out videos from the playlist as I'm watching videos, I'll occasionally skip over a video anyways if I don't want to watch it, so I'll take this over missing videos.

### Note <a name = "note"></a>
I whipped this up by [vibe-coding](https://en.wikipedia.org/wiki/Vibe_coding) in [Claude](https://claude.ai/). I've heard anecdotally that Claude tends to do better at coding tasks than other LLMs, so this project was a way to see if that's true.

## Docker <a name = "docker"></a>

### Simple setup
```bash
docker-compose up --build
```

**First run:** The script detects the headless environment and switches to Device Flow. It displays a short URL (e.g. `https://www.google.com/device`) and a code to enter. Open the URL on any device (phone, PC), enter the code, and authorize access. The `token.pickle` will be saved in the `./data/` volume.

**Subsequent runs:** The token is persisted in the `./data/` volume — the script runs directly without requiring new authentication.


## Built Using <a name = "built_using"></a>
- [Python](https://www.python.org/)
- [Claude](https://claude.ai/)

## Authors <a name = "authors"></a>
- [@Noahffiliation](https://github.com/Noahffiliation) - Idea & Initial work

## Acknowledgements <a name = "acknowledgement"></a>
- YouTube