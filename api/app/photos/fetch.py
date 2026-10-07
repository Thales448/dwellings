import ipaddress
import re
import socket
from urllib.parse import urljoin, urlparse

import httpx

MAX_BYTES = 12_000_000
_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_OG = re.compile(
    r"""<meta[^>]+(?:property|name)=["'](?:og:image|twitter:image)(?::src)?["'][^>]*>""",
    re.IGNORECASE,
)
_CONTENT = re.compile(r"""content=["']([^"']+)["']""", re.IGNORECASE)


class PhotoFetchError(Exception):
    pass


def _blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def is_public_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
        return False
    host = parsed.hostname.strip(".").lower()
    if host in {"localhost", "metadata", "metadata.google.internal"} or host.endswith(".local"):
        return False
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        try:
            infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except socket.gaierror:
            return False
        addresses = []
        for info in infos:
            try:
                addresses.append(ipaddress.ip_address(info[4][0]))
            except ValueError:
                return False
    return bool(addresses) and all(not _blocked(ip) for ip in addresses)


def fetch_bytes(
    url: str,
    timeout: int,
    *,
    user_agent: str = "Dwellings/1.0",
    host_ok: object | None = None,
) -> tuple[bytes, str]:
    current = url
    headers = {"user-agent": user_agent}
    allowed = host_ok if callable(host_ok) else None
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        for _ in range(4):
            if not is_public_url(current):
                raise PhotoFetchError("blocked url")
            hostname = (urlparse(current).hostname or "").lower().removeprefix("www.")
            if allowed is not None and not allowed(hostname):
                raise PhotoFetchError("unexpected host")
            response = client.get(current, headers=headers)
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if not location:
                    raise PhotoFetchError("redirect without a location")
                current = urljoin(current, location)
                continue
            if response.status_code != 200:
                raise PhotoFetchError(f"status {response.status_code}")
            data = response.content
            if len(data) > MAX_BYTES:
                raise PhotoFetchError("image is too large")
            ctype = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            return data, ctype
    raise PhotoFetchError("too many redirects")


def image_urls_from_html(html: str, page_url: str) -> list[str]:
    found: list[str] = []
    for tag in _OG.findall(html):
        match = _CONTENT.search(tag)
        if match is None:
            continue
        absolute = urljoin(page_url, match.group(1).strip())
        if absolute not in found:
            found.append(absolute)
        if len(found) >= 8:
            break
    return found


def looks_like_image(data: bytes, content_type: str) -> bool:
    if content_type in _IMAGE_TYPES:
        return True
    return data.startswith((b"\x89PNG", b"\xff\xd8\xff", b"GIF8", b"RIFF"))
