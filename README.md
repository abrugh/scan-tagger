# scan-tagger

Watches a directory for new scanned documents, sends the first page to an LLM vision model for classification, and renames the file to a human-readable format:

```
{GUID}.pdf  →  2025-03-25_Car_Insurance_Declaration.pdf
```

Built for network scanners that dump files with useless names like `0127_200327140748_001.pdf` into an SMB share. Works with OpenAI, Azure OpenAI, or any OpenAI-compatible API.

## Quick Start

1. Copy `.env.example` to `.env` and add your API key
2. Edit `docker-compose.yml` — update the volume mount to your scans directory
3. Run:

```bash
docker compose up -d
```

That's it. Drop a file in the watched directory and it gets renamed.

## Configuration

Edit `config.yaml` or override with environment variables:

### LLM Settings

| Setting | Env Var | Default | Description |
|---|---|---|---|
| `llm_provider` | `LLM_PROVIDER` | `openai` | `openai` or `azure` |
| `openai_api_key` | `OPENAI_API_KEY` | — | OpenAI API key |
| `openai_model` | `OPENAI_MODEL` | `gpt-4o` | Model name |
| `openai_base_url` | `OPENAI_BASE_URL` | — | Custom endpoint (e.g. ollama) |
| `azure_openai_endpoint` | `AZURE_OPENAI_ENDPOINT` | — | Azure endpoint URL |
| `azure_openai_api_key` | `AZURE_OPENAI_API_KEY` | — | Azure API key |
| `azure_openai_deployment` | `AZURE_OPENAI_DEPLOYMENT` | `gpt-4o` | Azure deployment name |

### Watcher Settings

| Setting | Env Var | Default | Description |
|---|---|---|---|
| `watch_path` | `WATCH_PATH` | `/scans` | Directory to monitor |
| `stabilization_delay` | `STABILIZATION_DELAY` | `3.0` | Seconds between size checks |
| `stabilization_checks` | `STABILIZATION_CHECKS` | `3` | Stable checks before processing |
| `max_summary_words` | `MAX_SUMMARY_WORDS` | `4` | Max words in filename |
| `process_existing` | `PROCESS_EXISTING` | `false` | Rename existing files on startup |

### Notifications (optional)

| Setting | Env Var | Default | Description |
|---|---|---|---|
| `discord_webhook_url` | `DISCORD_WEBHOOK_URL` | — | Discord webhook for alerts |
| `signal_recipient` | `SIGNAL_RECIPIENT` | — | Signal phone number for alerts |
| `signal_port` | `SIGNAL_PORT` | `7583` | signal-cli daemon port |
| `notify_on_success` | `NOTIFY_ON_SUCCESS` | `true` | Notify on every rename |
| `daily_summary_hour` | `DAILY_SUMMARY_HOUR` | `20` | Hour (0-23) for daily digest |

## Supported File Types

PDF, JPG, JPEG, PNG, TIFF, TIF

## How It Works

1. **Watchdog** monitors the directory for new files
2. **Stabilization** — waits for the file write to finish (file size stops changing), important for network/SMB shares
3. **PDF → Image** — converts the first page to PNG via poppler
4. **LLM Vision** — sends the image for document classification
5. **Rename** — applies `YYYY-MM-DD_Summary.ext` format using the file's modification time, with collision handling (`_2`, `_3`, etc.)
6. **Notify** — sends success/failure alerts via Discord and/or Signal
7. **Daily digest** — summary of the day's renames at a configurable hour

## License

MIT
