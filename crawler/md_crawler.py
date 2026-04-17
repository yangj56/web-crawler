from __future__ import annotations

import json
import re
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urldefrag, urljoin, urlparse, urlunparse

import httpx


_WS_RE = re.compile(r"[ \t]+\n")


def _canonical_host(host: str) -> str:
    h = (host or "").strip().lower()
    return h[4:] if h.startswith("www.") else h


def _normalize_url(url: str) -> str | None:
    if not url:
        return None
    try:
        u, _frag = urldefrag(url.strip())
        p = urlparse(u)
        if p.scheme not in ("http", "https"):
            return None
        if not p.netloc:
            return None
        path = p.path or "/"
        return urlunparse((p.scheme, p.netloc, path, p.params, p.query, ""))
    except Exception:
        return None


def _slugify(segment: str) -> str:
    s = (segment or "").strip().lower()
    s = re.sub(r"[^a-z0-9._-]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "page"


def _extract_links(html: str, base_url: str) -> list[str]:
    links: list[str] = []
    for m in re.finditer(r"""<a\s+[^>]*href=["']([^"']+)["']""", html, flags=re.I):
        href = m.group(1).strip()
        if not href or href.startswith(("mailto:", "javascript:", "tel:")):
            continue
        abs_url = urljoin(base_url, href)
        n = _normalize_url(abs_url)
        if n:
            links.append(n)
    return links


def _html_to_md_text(html: str) -> str:
    text = re.sub(r"(?is)<script.*?>.*?</script>", "", html)
    text = re.sub(r"(?is)<style.*?>.*?</style>", "", text)
    text = re.sub(r"(?is)<!--.*?-->", "", text)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</p\s*>", "\n\n", text)
    text = re.sub(r"(?is)<[^>]+>", "", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WS_RE.sub("\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


@dataclass(frozen=True)
class CrawlSetting:
    url: str
    check_other_sites: bool = False
    max_depth: int = 2
    max_pages: int = 50
    max_links_per_page: int = 50
    timeout_seconds: float = 20.0


def _load_settings(obj: dict[str, Any]) -> list[CrawlSetting]:
    defaults = obj.get("defaults") or {}
    max_depth_d = int(defaults.get("maxDepth") or 2)
    max_pages_d = int(defaults.get("maxPages") or 50)
    max_links_d = int(defaults.get("maxLinksPerPage") or 50)
    timeout_d = float(defaults.get("timeoutSeconds") or 20)

    settings: list[CrawlSetting] = []
    for raw in (obj.get("settings") or []):
        if not isinstance(raw, dict):
            continue
        url = _normalize_url(str(raw.get("url") or ""))
        if not url:
            continue
        settings.append(
            CrawlSetting(
                url=url,
                check_other_sites=bool(raw.get("checkOtherSites")),
                max_depth=int(raw.get("maxDepth") or max_depth_d),
                max_pages=int(raw.get("maxPages") or max_pages_d),
                max_links_per_page=int(raw.get("maxLinksPerPage") or max_links_d),
                timeout_seconds=float(raw.get("timeoutSeconds") or timeout_d),
            )
        )
    return settings


def _page_output_path(out_root: Path, url: str, parent_md_path: Path | None) -> tuple[Path, Path]:
    p = urlparse(url)
    host = _canonical_host(p.hostname or "site")
    segments = [s for s in (p.path or "/").split("/") if s]
    leaf = segments[-1] if segments else "index"
    leaf = _slugify(leaf)

    if parent_md_path is None:
        base_dir = out_root / host
        md_path = base_dir / (leaf if leaf != "index" else "index")
        md_path = md_path.with_suffix(".md")
        child_dir = base_dir / md_path.stem
        return md_path, child_dir

    parent_child_dir = parent_md_path.parent / parent_md_path.stem
    md_path = parent_child_dir / f"{leaf}.md"
    child_dir = parent_child_dir / leaf
    return md_path, child_dir


def run_from_settings_file(settings_path: Path, out_dir: Path) -> None:
    obj = json.loads(settings_path.read_text(encoding="utf-8"))
    settings = _load_settings(obj)
    if not settings:
        raise SystemExit(f"No valid settings found in {settings_path}")

    out_dir.mkdir(parents=True, exist_ok=True)
    for s in settings:
        _crawl_one_setting(s, out_dir)


def _crawl_one_setting(setting: CrawlSetting, out_dir: Path) -> None:
    seed = setting.url
    seed_host = _canonical_host(urlparse(seed).hostname or "")

    visited: set[str] = set()
    # url -> markdown file path; kept for future enhancements (indexing, cross-links)
    q: deque[tuple[str, int, Path | None]] = deque()
    q.append((seed, 0, None))

    limits_pages = max(1, setting.max_pages)
    limits_depth = max(0, setting.max_depth)
    max_links = max(0, setting.max_links_per_page)

    with httpx.Client(
        follow_redirects=True,
        timeout=httpx.Timeout(setting.timeout_seconds),
        headers={
            "User-Agent": "makancrawler/1.0 (+markdown export)",
            "Accept": "text/html,application/xhtml+xml",
        },
    ) as client:
        pages_crawled = 0
        while q and pages_crawled < limits_pages:
            url, depth, parent_md = q.popleft()
            if url in visited:
                continue
            if depth > limits_depth:
                continue

            host = _canonical_host(urlparse(url).hostname or "")
            if not setting.check_other_sites and host != seed_host and not host.endswith("." + seed_host):
                continue

            visited.add(url)

            try:
                r = client.get(url)
                r.raise_for_status()
                ctype = (r.headers.get("content-type") or "").lower()
                if "text/html" not in ctype and "application/xhtml" not in ctype and "<html" not in r.text.lower():
                    continue
            except Exception:
                continue

            html = r.text or ""
            title_match = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
            title = re.sub(r"\s+", " ", (title_match.group(1) if title_match else "")).strip()

            md_path, _child_dir = _page_output_path(out_dir, url, parent_md)
            md_path.parent.mkdir(parents=True, exist_ok=True)

            body_md = _html_to_md_text(html)
            md = "\n".join(
                [
                    f"# {title or url}",
                    "",
                    f"- Source: {url}",
                    "",
                    body_md,
                    "",
                ]
            ).strip() + "\n"
            md_path.write_text(md, encoding="utf-8")
            pages_crawled += 1

            if depth == limits_depth:
                continue

            links = _extract_links(html, url)
            if max_links:
                links = links[:max_links]

            for link in links:
                if link in visited:
                    continue
                q.append((link, depth + 1, md_path))

