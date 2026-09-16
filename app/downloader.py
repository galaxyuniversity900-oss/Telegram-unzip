from __future__ import annotations

import ipaddress
import socket
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import httpx

from .archive import detect_archive


def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only HTTP(S) URLs are supported.")
    host = parsed.hostname
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise ValueError("URL host could not be resolved.") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise ValueError("Private or local network URLs are not allowed.")


def filename_from_url(url: str) -> str:
    name = Path(unquote(urlparse(url).path)).name
    return name or "download"


async def download_url(url: str, destination_dir: Path, max_bytes: int, timeout_seconds: int) -> tuple[Path, int]:
    current = url
    headers = {"User-Agent": "TuzsBot/1.0 (+https://github.com/galaxyuniversity900-oss/Telegram-unzip)"}
    timeout = httpx.Timeout(timeout_seconds, connect=15)
    async with httpx.AsyncClient(follow_redirects=False, timeout=timeout, headers=headers) as client:
        for _ in range(5):
            _validate_url(current)
            async with client.stream("GET", current, follow_redirects=False) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise ValueError("URL redirect has no destination.")
                    current = urljoin(current, location)
                    continue
                response.raise_for_status()
                length = response.headers.get("content-length")
                if length and int(length) > max_bytes:
                    raise ValueError("Download exceeds the configured limit.")
                name = filename_from_url(current)
                content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                destination = destination_dir / name
                total = 0
                try:
                    with destination.open("wb") as handle:
                        async for chunk in response.aiter_bytes(1024 * 1024):
                            total += len(chunk)
                            if total > max_bytes:
                                raise ValueError("Download exceeds the configured limit.")
                            handle.write(chunk)
                except Exception:
                    destination.unlink(missing_ok=True)
                    raise
                if detect_archive(destination) is None:
                    destination.unlink(missing_ok=True)
                    raise ValueError(f"The URL did not return a supported archive (content-type: {content_type or 'unknown'}).")
                return destination, total
    raise ValueError("Too many redirects.")
