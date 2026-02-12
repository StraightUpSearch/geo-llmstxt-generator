"""Standalone async web crawler using httpx + BeautifulSoup."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import bs4
import httpx

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

USER_AGENT = 'Mozilla/5.0 (compatible; LlmsTxtGenerator/1.0; +https://llmstxt.org)'
REQUEST_TIMEOUT = 15.0
BATCH_SIZE = 5
BATCH_DELAY = 0.5
BODY_TEXT_LIMIT = 500
STATUS_OK = 200


async def fetch_page(url: str, client: httpx.AsyncClient) -> dict[str, Any] | None:
    """Fetch a single page and extract rich content."""
    try:
        resp = await client.get(url, follow_redirects=True, timeout=REQUEST_TIMEOUT)
        if resp.status_code != STATUS_OK:
            logger.warning(f'Skipping {url} (status {resp.status_code})')
            return None

        soup = bs4.BeautifulSoup(resp.text, 'html.parser')

        # Remove non-content elements
        for tag in soup.find_all(['nav', 'footer', 'script', 'style', 'noscript', 'iframe']):
            tag.decompose()

        # Title: prefer H1, fall back to <title>
        h1_tag = soup.find('h1')
        title = h1_tag.get_text(strip=True) if h1_tag else None
        if not title and soup.title and soup.title.string:
            title = soup.title.string.strip()
        if not title:
            logger.info(f'No title found for {url}, skipping')
            return None

        # Meta description
        description = _extract_meta_description(soup)

        # H2 headings for structure understanding
        headings = [h2.get_text(strip=True) for h2 in soup.find_all('h2') if h2.get_text(strip=True)]

        # Body text: first 500 chars of main content
        body_el = soup.find('main') or soup.find('article') or soup.find('body')
        body_text = ''
        if body_el:
            body_text = body_el.get_text(separator=' ', strip=True)[:BODY_TEXT_LIMIT]

        return {
            'url': url,
            'title': title,
            'description': description,
            'body_text': body_text,
            'headings': headings[:10],
        }

    except httpx.HTTPError as e:
        logger.warning(f'HTTP error fetching {url}: {e}')
        return None
    except Exception as e:
        logger.warning(f'Unexpected error fetching {url}: {e}')
        return None


def _extract_meta_description(soup: bs4.BeautifulSoup) -> str | None:
    """Extract meta description from a BeautifulSoup object."""
    tag = soup.find('meta', {'name': 'description'}) or soup.find('meta', {'name': 'Description'})
    if tag is None:
        return None

    content = tag.get('content')
    if isinstance(content, list):
        content = ' '.join(content)
    if isinstance(content, str) and '\n' not in content:
        return content.strip() or None
    return None


def _extract_homepage_links(html: str, domain: str) -> list[str]:
    """Extract internal links from homepage HTML."""
    soup = bs4.BeautifulSoup(html, 'html.parser')
    parsed_domain = urlparse(domain)
    links: list[str] = []
    seen: set[str] = set()
    skip_extensions = ('.jpg', '.png', '.gif', '.svg', '.pdf', '.css', '.js', '.xml')

    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        if isinstance(href, list):
            href = href[0]

        # Normalise relative URLs
        if href.startswith('/'):
            href = f'{parsed_domain.scheme}://{parsed_domain.netloc}{href}'

        # Only keep same-domain links
        parsed = urlparse(href)
        if parsed.netloc != parsed_domain.netloc:
            continue

        clean = f'{parsed.scheme}://{parsed.netloc}{parsed.path}'.rstrip('/')
        if clean not in seen and not any(ext in parsed.path for ext in skip_extensions):
            seen.add(clean)
            links.append(clean)

    return links


async def crawl_site(
    domain: str,
    sitemap_urls: list[str],
    disallow_rules: list[str],
    client: httpx.AsyncClient,
    max_pages: int = 50,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[dict[str, Any]]:
    """Crawl a site: combine sitemap URLs with homepage links, fetch pages.

    Args:
        domain: The base domain URL (e.g. https://example.com)
        sitemap_urls: URLs discovered from sitemap.xml
        disallow_rules: Paths from robots.txt Disallow directives
        client: httpx async client
        max_pages: Maximum pages to crawl
        on_progress: Callback(crawled_count, total_count)
    """
    # Start with homepage to discover more links
    homepage_result = await fetch_page(domain, client)
    results: list[dict[str, Any]] = []
    if homepage_result:
        results.append(homepage_result)

    # Get homepage links as fallback/supplement to sitemap
    try:
        resp = await client.get(domain, follow_redirects=True, timeout=REQUEST_TIMEOUT)
        homepage_links = _extract_homepage_links(resp.text, domain) if resp.status_code == STATUS_OK else []
    except httpx.HTTPError:
        homepage_links = []

    # Merge sitemap + homepage links, deduplicate, filter disallowed
    all_urls = _merge_and_filter_urls(domain, sitemap_urls, homepage_links, disallow_rules)
    total = min(len(all_urls), max_pages - 1)

    if on_progress:
        on_progress(len(results), total + 1)

    # Crawl in batches to be respectful to the target server
    urls_to_crawl = all_urls[:total]
    for i in range(0, len(urls_to_crawl), BATCH_SIZE):
        batch = urls_to_crawl[i : i + BATCH_SIZE]
        tasks = [fetch_page(url, client) for url in batch]
        batch_results = await asyncio.gather(*tasks)

        results.extend(r for r in batch_results if r is not None)

        if on_progress:
            on_progress(len(results), total + 1)

        if i + BATCH_SIZE < len(urls_to_crawl):
            await asyncio.sleep(BATCH_DELAY)

    return results


def _merge_and_filter_urls(
    domain: str,
    sitemap_urls: list[str],
    homepage_links: list[str],
    disallow_rules: list[str],
) -> list[str]:
    """Merge URLs from sitemap and homepage, filter disallowed, deduplicate."""
    seen: set[str] = {domain.rstrip('/')}
    merged: list[str] = []
    parsed_domain = urlparse(domain)

    for url in [*sitemap_urls, *homepage_links]:
        parsed = urlparse(url)
        # Same domain only
        if parsed.netloc and parsed.netloc != parsed_domain.netloc:
            continue

        clean = url.rstrip('/')
        if clean in seen:
            continue

        # Check disallow rules
        path = parsed.path
        if any(path.startswith(rule) for rule in disallow_rules):
            continue

        seen.add(clean)
        merged.append(url)

    # Sort by URL depth (shallower pages first = more important)
    merged.sort(key=lambda u: urlparse(u).path.count('/'))
    return merged
