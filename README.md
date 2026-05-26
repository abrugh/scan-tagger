# scan-tagger

Watches a directory for new scanned documents (via SMB), sends the first page to Azure OpenAI vision for classification, and renames the file to a human-readable format:

```
{GUID}.pdf  →  2026-05-25_Car_Insurance_Declaration.pdf
```

## Quick Start

1. Copy `.env.example` to `.env` and set your Azure OpenAI API key
2. Edit `docker-compose.yml` — update the volume mount to your scans directory
3. Run:

```bash
docker compose up -d
```

## Configuration

Edit `config.yaml` or override with environment variables:

| Setting | Env Var | Default | Description |
|---|---|---|---|
| `watch_path` | `WATCH_PATH` | `/scans` | Directory to monitor |
| `azure_openai_endpoint` | `AZURE_OPENAI_ENDPOINT` | *(in config.yaml)* | Azure OpenAI endpoint |
| `azure_openai_deployment` | `AZURE_OPENAI_DEPLOYMENT` | `gpt-5.4` | Model deployment name |
| `azure_openai_api_key` | `AZURE_OPENAI_API_KEY` | — | API key (use env var) |
| `stabilization_delay` | `STABILIZATION_DELAY` | `3.0` | Seconds between size checks |
| `stabilization_checks` | `STABILIZATION_CHECKS` | `3` | Stable checks before processing |
| `max_summary_words` | `MAX_SUMMARY_WORDS` | `4` | Max words in filename |
| `process_existing` | `PROCESS_EXISTING` | `false` | Rename existing files on startup |
| `log_level` | `LOG_LEVEL` | `INFO` | Logging level |
| `discord_webhook_url` | `DISCORD_WEBHOOK_URL` | — | Discord webhook for alerts |
| `signal_recipient` | `SIGNAL_RECIPIENT` | — | Signal phone number for alerts |
| `signal_port` | `SIGNAL_PORT` | `7583` | signal-cli daemon port |
| `notify_on_success` | `NOTIFY_ON_SUCCESS` | `true` | Notify on every rename |
| `notify_on_startup` | `NOTIFY_ON_STARTUP` | `true` | Notify when service starts |
| `daily_summary_hour` | `DAILY_SUMMARY_HOUR` | `20` | Hour (0-23) for daily digest |

## Supported File Types

PDF, JPG, JPEG, PNG, TIFF, TIF

## How It Works

1. **Watchdog** monitors the directory for new files
2. **Stabilization** — waits for SMB write to finish (file size stops changing)
3. **PDF → Image** — converts the first page to PNG via poppler
4. **Azure OpenAI Vision** — sends the image for document classification
5. **Rename** — applies `YYYY-MM-DD_Summary.ext` format with collision handling
6. **Notify** — sends success/failure alerts via Discord and/or Signal
7. **Daily digest** — summary of the day's renames at a configurable hour
