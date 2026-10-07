import re
from dataclasses import dataclass
from html import unescape

from app.core.config import get_settings
from app.listings.normalize import normalize_url
from app.photos.fetch import PhotoFetchError, fetch_bytes

TITLE_MAX = 140
NOTES_MAX = 2000
_USER_AGENT = "Mozilla/5.0 (compatible; Dwellings/1.0; +https://dwellings.rtech.cloud)"
_POSTING = re.compile(
    r"^https://[a-z0-9-]+\.craigslist\.org/(?:[a-z]{3}/)?[a-z]{3}/d/[a-z0-9-]+/\d+\.html$"
)
_TITLE = re.compile(r"""id=["']titletextonly["'][^>]*>(.*?)</span>""", re.IGNORECASE | re.DOTALL)
_BODY = re.compile(r"""id=["']postingbody["'][^>]*>(.*?)</section>""", re.IGNORECASE | re.DOTALL)
_PRINT = re.compile(
    r"""<div[^>]+class=["'][^"']*print-information[^"']*["'][^>]*>.*?</div>""",
    re.IGNORECASE | re.DOTALL,
)
_TAGS = re.compile(r"<[^>]+>")
_GONE = re.compile(
    r"posting has been deleted|posting has expired|this posting has been flagged|"
    r"""class=["'][^"']*\bremoved\b""",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Posting:
    title: str
    body: str
    gone: bool


def is_posting_url(raw: object) -> bool:
    if not isinstance(raw, str):
        return False
    url = normalize_url(raw)
    return url is not None and _POSTING.match(url) is not None


def fold(value: str) -> str:
    text = unescape(value).replace("\xa0", " ")
    text = text.replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    return re.sub(r"\s+", " ", text).strip().casefold()


def _plain(fragment: str) -> str:
    without_print = _PRINT.sub(" ", fragment)
    return fold(_TAGS.sub(" ", without_print))


def parse_posting(html: str) -> Posting:
    title_match = _TITLE.search(html)
    body_match = _BODY.search(html)
    title = _plain(title_match.group(1)) if title_match else ""
    body = _plain(body_match.group(1)) if body_match else ""
    return Posting(title=title, body=body, gone=_GONE.search(html) is not None)


def _same(stored: str | None, page: str, limit: int) -> bool:
    if not stored or not page:
        return False
    left = fold(stored)
    right = fold(page)
    if len(right) > limit:
        right = right[:limit].rstrip()
    return left == right


def judge(
    url: str,
    title: str,
    notes: str | None,
    posting: Posting | None,
    fetch_error: str | None,
) -> tuple[bool, str | None]:
    if not is_posting_url(url):
        return False, "not a craigslist posting link"
    if fetch_error:
        return False, "the Craigslist link did not open"
    if posting is None or posting.gone:
        return False, "the Craigslist post is gone"
    if not posting.title:
        return False, "the Craigslist post has no title"
    if not _same(title, posting.title, TITLE_MAX):
        shown = posting.title[:80]
        return False, f'title does not match the Craigslist post ("{shown}")'
    if not posting.body:
        return False, "the Craigslist post has no description"
    if not _same(notes, posting.body, NOTES_MAX):
        return False, "description does not match the Craigslist post"
    return True, None


def _craigslist_host(hostname: str) -> bool:
    return hostname == "craigslist.org" or hostname.endswith(".craigslist.org")


def load_posting(url: str) -> tuple[Posting | None, str | None]:
    if not is_posting_url(url):
        return None, "not a craigslist posting link"
    try:
        data, content_type = fetch_bytes(
            url,
            get_settings().photo_fetch_timeout,
            user_agent=_USER_AGENT,
            host_ok=_craigslist_host,
        )
    except PhotoFetchError:
        return None, "the Craigslist link did not open"
    if "html" not in content_type:
        return None, "the Craigslist link did not open"
    return parse_posting(data[:1_000_000].decode("utf-8", errors="ignore")), None
