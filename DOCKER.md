# Docker Deployment

## Quick Start

### Using Docker Compose

```bash
docker-compose up --build
```

On first run, the script will display an OAuth authorization link in the terminal. Open the link in your browser to authorize access, and the `token.pickle` will be created in the `./data/` volume.

### Using Docker Compose YAML directly

Paste this into your Docker Compose interface:

```yaml
version: '3.8'

services:
  youtube-auto-watch-later:
    build:
      context: https://github.com/Noahffiliation/auto-watch-later.git
      dockerfile: Dockerfile
    container_name: youtube-auto-watch-later
    volumes:
      - ./data:/data
    stdin_open: true
    tty: true
    restart: unless-stopped
```

Docker will automatically clone the repository, build the image, and run the container.

## Data Structure

```
./data/
├── client_secrets.json      (created after OAuth)
├── token.pickle             (created after OAuth)
└── last_check_time.txt      (created after first run)

./logs/
└── YYYY-MM-DD_HH-MM-SS.txt
```

## First Run

The script will display:
```
Please visit this URL to authorize:
https://accounts.google.com/o/oauth2/device?...
```

Open this URL in your browser → authorize → `token.pickle` is saved.

## Subsequent Runs

```bash
docker-compose up
```

The token is loaded from `./data/token.pickle`, videos are added directly.

## Container Management

### Stop container
```bash
docker-compose down
```

### View logs
```bash
docker-compose logs -f
```

### View last 50 lines
```bash
docker-compose logs --tail=50
```

## Troubleshooting

**"client_secrets.json not found"**
- Create it from Google Cloud Console (the script will show you the instructions)

**"Token expired or invalid"**
- Delete `./data/token.pickle` and run again to re-authenticate

**No videos added**
- Check logs: `docker-compose logs -f`
- Verify you authorized the correct YouTube account

**API Quota exceeded**
- Reduce the frequency of executions
- Request a quota increase from Google Cloud Console

## Environment Variables (Optional)

You can customize behavior by adding environment variables to `docker-compose.yml`:

```yaml
environment:
  - TZ=UTC
  - PYTHONUNBUFFERED=1
  - INCLUDE_SHORTS=true
  - INCLUDE_TEASERS=true
```
