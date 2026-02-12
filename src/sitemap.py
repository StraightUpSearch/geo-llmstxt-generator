"""Sitemap and robots.txt fetching and parsing."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from typing import Any

import httpx

logger = logging.getLogger(__name__)

SITEMAP_NS = 'http://www.sitemaps.org/schemas/sitemap/0.9'
REQUEST_TIMEOUT = 15.0
STATUS_OK = 200


async def fetch_robots_txt(domain: str, client: httpx.AsyncClient) -> dict[str, Any]:
    """Fetch and parse robots.txt for sitemap locations and disallow rules."""
    sitemap_urls: list[str] = []
    disallow_rules: list[str] = []
    raw: str | None = None

    try:
        resp = await client.get(f'{domain}/robots.txt', timeout=REQUEST_TIMEOUT)
        if resp.status_code != STATUS_OK:
            logger.info(f'No robots.txt at {domain} (status {resp.status_code})')
            return {'sitemap_urls': sitemap_urls, 'disallow_rules': disallow_rules, 'raw': None}

        raw = resp.text
        for line in raw.splitlines():
            stripped = line.strip()
            lower = stripped.lower()
            if lower.startswith('sitemap:'):
                url = stripped.split(':', 1)[1].strip()
                if url:
                    sitemap_urls.append(url)
            elif lower.startswith('disallow:'):
                rule = stripped.split(':', 1)[1].strip()
                if rule:
                    disallow_rules.append(rule)

    except httpx.HTTPError as e:
        logger.warning(f'Failed to fetch robots.txt: {e}')

    return {'sitemap_urls': sitemap_urls, 'disallow_rules': disallow_rules, 'raw': raw}


async def fetch_sitemap_urls(
    url: str,
    client: httpx.AsyncClient,
    max_urls: int = 500,
) -> list[str]:
    """Fetch and parse a sitemap XML, returning all discovered page URLs.

    Handles both sitemap index files and regular sitemaps.
    """
    urls: list[str] = []

    try:
        resp = await client.get(url, timeout=REQUEST_TIMEOUT)
        if resp.status_code != STATUS_OK:
            logger.info(f'No sitemap at {url} (status {resp.status_code})')
            return urls

        root = ET.fromstring(resp.text)  # noqa: S314
        ns = {'ns': SITEMAP_NS}

        # Check for sitemap index (contains links to other sitemaps)
        sitemap_locs = root.findall('.//ns:sitemap/ns:loc', ns)
        if not sitemap_locs:
            sitemap_locs = root.findall('.//sitemap/loc')

        if sitemap_locs:
            for loc in sitemap_locs[:10]:
                if loc.text and len(urls) < max_urls:
                    nested = await fetch_sitemap_urls(loc.text.strip(), client, max_urls - len(urls))
                    urls.extend(nested)
            return urls[:max_urls]

        # Regular sitemap — extract page URLs
        page_locs = root.findall('.//ns:url/ns:loc', ns)
        if not page_locs:
            page_locs = root.findall('.//url/loc')

        for loc in page_locs:
            if loc.text:
                urls.append(loc.text.strip())
            if len(urls) >= max_urls:
                break

    except ET.ParseError:
        logger.warning(f'Failed to parse sitemap XML at {url}')
    except httpx.HTTPError as e:
        logger.warning(f'Failed to fetch sitemap {url}: {e}')

    return urls


async def fetch_existing_llms_txt(domain: str, client: httpx.AsyncClient) -> str | None:
    """Check if the domain already has an llms.txt file."""
    try:
        resp = await client.get(f'{domain}/llms.txt', timeout=REQUEST_TIMEOUT)
        if resp.status_code == STATUS_OK:
            text = resp.text.strip()
            if text.startswith('#'):
                return text
    except httpx.HTTPError:
        pass
    return None


async def gather_site_info(domain: str, client: httpx.AsyncClient) -> dict[str, Any]:
    """Gather pre-crawl intelligence: robots.txt, sitemap, existing llms.txt."""
    robots = await fetch_robots_txt(domain, client)

    # Collect sitemap URLs from robots.txt hints + default location
    sitemap_sources = list(robots['sitemap_urls'])
    default_sitemap = f'{domain}/sitemap.xml'
    if default_sitemap not in sitemap_sources:
        sitemap_sources.append(default_sitemap)

    all_sitemap_urls: list[str] = []
    for source in sitemap_sources:
        found = await fetch_sitemap_urls(source, client)
        all_sitemap_urls.extend(found)

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_urls: list[str] = []
    for u in all_sitemap_urls:
        if u not in seen:
            seen.add(u)
            unique_urls.append(u)

    existing = await fetch_existing_llms_txt(domain, client)

    return {
        'domain': domain,
        'robots': robots,
        'sitemap_urls': unique_urls,
        'existing_llms_txt': existing,
    }
