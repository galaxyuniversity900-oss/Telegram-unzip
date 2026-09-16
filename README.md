# TuzsBot — Telegram Universal Archive Extractor

TuzsBot is an open-source Telegram archive service. Send an archive file or a direct HTTP(S) archive URL; the bot downloads it, inspects it, applies limits, extracts it, indexes the result, and lets you browse/download files from the same Telegram conversation.

## Implemented now

- Telegram document and direct HTTP(S) URL input
- ZIP, RAR, 7Z, TAR, GZ, BZ2 and XZ via 7-Zip
- Magic-byte detection for extensionless downloads
- Archive metadata inspection before extraction
- Download/output/file-count/ratio limits
- Path traversal and unsafe-link protection
- SSRF protection with redirect re-validation
- Bounded URL streaming
- Interactive paginated file browser
- Ordered staged extraction with validation after every batch
- Background extraction workers
- **Durable Redis-backed job queue**
- **Independent Bot Gateway and Worker processes**
- **Redis processing-list acknowledgement model**
- Docker Compose with Redis + bot + worker
- Automatic restart policies
- Unit tests and GitHub Actions CI

## Architecture

```text
                         Telegram
                            │
                            ▼
                    ┌───────────────┐
                    │  Bot Gateway  │
                    │  Polling/API  │
                    └───────┬───────┘
                            │
                            ▼
                    ┌───────────────┐
                    │ Redis Queue   │
                    │ durable jobs  │
                    └───────┬───────┘
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
          Worker #1      Worker #2      Worker #N
              │             │             │
              └─────────────┼─────────────┘
                            ▼
                  Staged Extraction Engine
                            │
                            ▼
                     Shared Job Volume
                            │
                            ▼
                    Telegram File Browser
```

The Bot Gateway runs with `python -m app`. Workers run independently with `python -m app.worker_main`. Redis stores job metadata and the durable ready/processing queues.

See [`docs/REDIS_ARCHITECTURE.md`](docs/REDIS_ARCHITECTURE.md) for the worker protocol and scaling model.

## 24/7 VPS mode

The Docker Compose stack now contains three services:

- `redis` — persistent Redis queue
- `tuzsbot` — Telegram gateway
- `worker` — independent archive extraction worker

Start everything with:

```bash
cp .env.example .env
# Set TELEGRAM_BOT_TOKEN in .env
docker compose up -d --build
docker compose ps
docker compose logs -f --tail=200
```

The stack uses `restart: unless-stopped`, persistent volumes, bounded processes and rotating logs. Systemd deployment is available through `deploy/tuzsbot.service` and `deploy/install-vps.sh`.

## Large archive engine

Very large archives are processed as deterministic ordered batches:

```text
Archive
  │
  ▼
Inspect + validate members
  │
  ▼
Ordered extraction plan
  │
  ├── Batch 001 → validate → usable
  ├── Batch 002 → validate → usable
  ├── Batch 003 → validate → usable
  └── Batch N   → validate → usable
  │
  ▼
Indexed workspace
```

Earlier validated stages remain available while later stages run. Staging improves reliability and resource management; it does not guarantee faster decompression for solid archives.

## Configuration

| Variable | Default | Purpose |
|---|---:|---|
| `REDIS_URL` | `redis://redis:6379/0` | Redis backend |
| `MAX_DOWNLOAD_MB` | `200` | Maximum input/download size |
| `MAX_EXTRACTED_MB` | `500` | Maximum extracted bytes |
| `MAX_FILES` | `5000` | Maximum extracted files |
| `MAX_RATIO` | `100` | Maximum declared compression ratio |
| `MAX_ARCHIVE_DEPTH` | `2` | Archive recursion setting |
| `EXTRACTION_TIMEOUT_SECONDS` | `180` | Extraction stage timeout |
| `DOWNLOAD_TIMEOUT_SECONDS` | `60` | URL request timeout |
| `MAX_CONCURRENT_JOBS` | `2` | Worker concurrency |
| `MAX_JOBS_PER_USER` | `1` | Active jobs per user |
| `JOB_TTL_SECONDS` | `900` | Job metadata/workspace lifetime |
| `EXTRACTION_BATCH_SIZE` | `100` | Files per extraction stage |
| `WORK_DIR` | `/tmp/tuzsbot` | Job workspace |

## Development

```bash
pip install -r requirements.txt
pytest -q
python -m app
python -m app.worker_main
```

## Roadmap

### Phase 1 — Core
- [x] Secure archive detection and inspection
- [x] Staged extraction
- [x] Telegram gateway
- [x] Durable Redis queue
- [x] Independent workers

### Phase 2 — Telegram UX
- [x] Paginated browsing
- [x] Page-based downloads
- [ ] Search inside extracted tree
- [ ] Cancellation UI
- [ ] Password entry flow
- [ ] Repack selected files
- [ ] Resume interrupted stage plan

### Phase 3 — Platform
- [ ] Processing-lease/heartbeat reaper
- [ ] Shared object-storage backend
- [ ] Database-backed job history
- [ ] Webhook deployment
- [ ] REST API
- [ ] CLI/SDK
- [ ] Plugin extraction engines
- [ ] Format-specific parallel block workers
- [ ] Optional malware scanning
- [ ] Metrics/observability
- [ ] Windows worker adapter

## License

MIT
