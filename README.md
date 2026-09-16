# TuzsBot — Telegram Universal Archive Extractor

A production-oriented Telegram bot that accepts archive files or direct file URLs, safely extracts supported archives, and delivers or browses the extracted contents inside Telegram.

## Current status

🚧 Architecture and implementation foundation.

## Core roadmap

- Telegram file and direct URL input
- ZIP, RAR, 7Z, TAR, GZ, BZ2 and XZ support
- Password-protected archives
- Secure isolated extraction
- Path traversal and symlink protection
- Archive-bomb/decompression-ratio limits
- File indexing and interactive browsing
- Background jobs and progress reporting
- Per-user limits and automatic cleanup
- Docker deployment
- Automated tests and CI

## Security

Never commit a Telegram bot token. Configure `TELEGRAM_BOT_TOKEN` as an environment variable or deployment secret.

The bot token previously pasted in chat must be revoked/regenerated before production use because it is no longer secret.

## License

MIT
