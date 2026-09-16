# Windows extraction worker

This directory is a deployment placeholder for a Windows worker host. The recommended topology is:

```text
Telegram Bot / VPS
       |
       v
Persistent Queue
       |
       +---- Linux worker(s)
       |
       +---- Windows worker(s)
                    |
                    v
             Extraction Engine
```

A Windows worker should run as a persistent service and consume jobs from the same durable queue rather than accepting RDP commands. Keep the worker implementation aligned with the repository's extraction contract before enabling it in production.

## Host requirements

- Windows 10/11 Pro or Windows Server
- Python 3.12+
- 7-Zip installed and available as `7z.exe`
- Git
- Network access to the queue/storage backend
- A service manager such as NSSM or Windows Service wrapper

The current repository's queue is intentionally in-process; therefore this worker folder does not pretend that a Windows machine can join the current queue yet. The next platform milestone is a Redis-backed durable queue and a worker protocol shared by Linux and Windows.
