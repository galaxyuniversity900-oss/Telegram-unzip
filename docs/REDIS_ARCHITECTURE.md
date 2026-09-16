# Redis-backed worker architecture

The project now separates Telegram polling from archive extraction.

```text
Telegram
   |
   v
Bot Gateway
   |
   +--> downloads archive to shared job volume
   |
   v
Redis durable queue
   |
   +--> Worker 1
   +--> Worker 2
   +--> Worker N
           |
           v
     staged 7-Zip extraction
           |
           v
      shared job volume
           |
           v
     Telegram delivery
```

## Processes

### Bot gateway

Run with:

```bash
python -m app
```

Responsibilities:

- Telegram polling
- archive/URL intake
- download
- job creation
- Redis enqueue
- result browsing
- file delivery

### Worker

Run with:

```bash
python -m app.worker_main
```

Responsibilities:

- claim queued jobs
- staged extraction
- progress state updates
- result notification
- queue acknowledgement

## Redis semantics

Jobs are stored under `tuzsbot:job:<job_id>` and queued in `tuzsbot:jobs`.
A claimed job is moved to `tuzsbot:jobs:processing` before extraction. The worker acknowledges it only after processing completes or fails. This separates queue ownership from Telegram polling and prevents ordinary worker restarts from losing a job immediately after dequeue.

The next hardening step is a lease/heartbeat reaper that returns stale entries from the processing list to the ready queue after a worker disappears mid-extraction.

## Scaling

Increase `MAX_CONCURRENT_JOBS` and run multiple worker containers. The bot gateway remains a separate service. Redis provides the shared coordination layer while the job volume must be shared by all workers that process the same job.

For a multi-host deployment, replace the local Docker volume with shared object storage or a network filesystem and keep only job metadata/path references in Redis.
