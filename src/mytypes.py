from __future__ import annotations

from typing import NotRequired, TypedDict


class LinkDict(TypedDict):
    """Dictionary representing a single link in the `llms.txt` file."""

    url: str
    title: str
    description: str | None


class SectionDict(TypedDict):
    """Dictionary representing a single section in the `llms.txt` file."""

    title: str
    links: list[LinkDict]


class LLMSData(TypedDict):
    """Dictionary representing the data structure of the `llms.txt` file."""

    title: str
    description: str | None
    details: str | None
    sections: dict[str, SectionDict]


class CrawledPage(TypedDict):
    """Dictionary representing the crawled pages."""

    url: str
    title: str
    description: str | None
    body_text: NotRequired[str]
    headings: NotRequired[list[str]]


class RobotsInfo(TypedDict):
    """Parsed robots.txt information."""

    sitemap_urls: list[str]
    disallow_rules: list[str]
    raw: str | None


class SiteInfo(TypedDict):
    """Pre-crawl information gathered about a site."""

    domain: str
    robots: RobotsInfo
    sitemap_urls: list[str]
    existing_llms_txt: str | None


class ValidationCheck(TypedDict):
    """Result of a single validation check."""

    rule: str
    passed: bool
    message: str


class ValidationReport(TypedDict):
    """Full validation report for generated llms.txt."""

    checks: list[ValidationCheck]
    file_size_bytes: int
    link_count: int
    section_count: int
    is_valid: bool
