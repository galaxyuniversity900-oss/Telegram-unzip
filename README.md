# TuzsBot — Telegram Universal Archive Extractor

TuzsBot is an open-source Telegram archive service. Send an archive file or a direct HTTP(S) archive URL; the bot downloads it, inspects it, applies safety limits, extracts it, indexes the result, and lets you browse/download files from the same Telegram conversation.

## Implemented now

- Telegram document input
- Direct HTTP(S) URL input
- ZIP, RAR, 7Z, TAR and common GZ/BZ2/XZ formats through 7-Zip
- Magic-byte archive detection for extensionless downloads
- Pre-extraction archive inspection
- Maximum compressed download size
- Maximum extracted size
- Maximum entry/file count
- Compression-ratio protection
- Path traversal protection
- Symlink rejection
- SSRF protection for URL downloads, including redirect re-validation
- Bounded URL streaming
- Per-user active-job limit
- Global concurrent-job limit
- Automatic job cleanup/TTL
- Interactive file browsing with pagination
- Download-by-page instead of flooding a chat with thousands of files
- Non-root Docker runtime
- Unit tests and GitHub Actions CI

## Architecture

```text
Telegram / URL
      │
      ▼
   Bot Gateway
      │
      ▼
 Download + URL Security
      │
      ▼
 Archive Detector / Inspector
      │
      ▼
 Secure Extraction Worker
      │
      ▼
 File Index + Job Store
      │
      ▼
 Interactive Telegram Browser
```

The extraction engine is deliberately separated from Telegram-facing code so it can later become a reusable library/API/CLI.

## Run locally

1. Install Python 3.12+ and 7-Zip.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and set a **new** Telegram bot token.
4. Start:

```bash
python -m app
```

## Docker

```bash
docker build -t tuzsbot .
docker run --rm \
  -e TELEGRAM_BOT_TOKEN='YOUR_NEW_TOKEN' \
  -v tuzsbot-data:/tmp/tuzsbot \
  tuzsbot
```

## Configuration

| Variable | Default | Purpose |
|---|---:|---|
| `MAX_DOWNLOAD_MB` | `200` | Maximum input/download size |
| `MAX_EXTRACTED_MB` | `500` | Maximum extracted bytes |
| `MAX_FILES` | `5000` | Maximum extracted entries |
| `MAX_RATIO` | `100` | Maximum declared compression ratio |
| `MAX_ARCHIVE_DEPTH` | `2` | Reserved recursion safety setting |
| `EXTRACTION_TIMEOUT_SECONDS` | `180` | Extraction wall-clock timeout |
| `DOWNLOAD_TIMEOUT_SECONDS` | `60` | URL request timeout |
| `MAX_CONCURRENT_JOBS` | `2` | Global extraction concurrency |
| `MAX_JOBS_PER_USER` | `1` | Active jobs per Telegram user |
| `JOB_TTL_SECONDS` | `900` | Workspace lifetime |
| `WORK_DIR` | `/tmp/tuzsbot` | Temporary job storage |

## Security model

TuzsBot treats every uploaded/downloaded archive as untrusted input. The current implementation validates archive metadata before extraction, rejects unsafe filesystem links/paths, limits output size and entry count, blocks local/private URL targets, re-checks redirect destinations, uses extraction timeouts, and runs the Docker process as a non-root user.

For public deployment, add host/container resource limits and an optional malware scanner before accepting untrusted files at scale.

**Never commit a Telegram bot token.** Configure `TELEGRAM_BOT_TOKEN` through the deployment environment or secret manager. Any token previously exposed in chat should be revoked and regenerated before production use.

## Development

Run the test suite with:

```bash
pytest -q
```

CI also runs Python compilation checks and the unit tests on pushes and pull requests targeting `main`.

## Roadmap

### Phase 1 — Secure extraction core
- [x] Archive detection
- [x] Metadata inspection
- [x] Safety limits
- [x] Secure extraction
- [x] Job lifecycle

### Phase 2 — Telegram UX
- [x] File/URL intake
- [x] Interactive browsing
- [x] Paginated delivery
- [ ] Search inside extracted tree
- [ ] Cancellation/progress UI
- [ ] Password entry flow
- [ ] Repack selected files

### Phase 3 — Platform
- [ ] Persistent queue/worker backend
- [ ] Storage abstraction
- [ ] Database-backed jobs
- [ ] Webhook deployment
- [ ] REST API
- [ ] CLI/SDK
- [ ] Plugin-based extraction engines
- [ ] Optional malware scanning
- [ ] Metrics/observability

## License

MIT
