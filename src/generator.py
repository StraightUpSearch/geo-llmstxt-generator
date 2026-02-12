"""LLM-powered llms.txt generation using the Anthropic API."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import anthropic

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    'You are an llms.txt generation engine. Your sole output is a production-ready '
    'llms.txt file following the spec at llmstxt.org.\n\n'
    'Rules:\n'
    '- Output ONLY the llms.txt file content. No explanations, no commentary, no code fences.\n'
    '- Use British English.\n'
    '- H1: Site/project name (required) — use the brand name, not the domain.\n'
    '- Blockquote: 1-3 sentence summary capturing business model, key offerings, and differentiators.\n'
    '- Optional body text: Only if critical context is needed.\n'
    '- H2 sections: Group links by category. Use clear section names.\n'
    '- Each link: [Page Title](URL): One-line description of what the page contains.\n'
    '- Include a ## Optional section for secondary/nice-to-have content.\n'
    '- Keep total file under 10KB (roughly 200-400 lines max).\n'
    '- Prefer landing pages and category pages over individual blog posts or product items.\n'
    '- Never include login-gated, user-generated, or dynamically personalised pages.\n'
    '- Never include promotional or marketing superlatives in descriptions.\n'
    '- Descriptions should be factual and neutral.\n'
    '- If the site has API docs or developer resources, these get priority placement.\n'
    '- Do not invent or fabricate URLs. Only use URLs from the provided data.'
)

EXPLAINER_SYSTEM_PROMPT = (
    'You are a GEO (Generative Engine Optimisation) and SEO expert. Given a generated '
    'llms.txt file and information about the site it was created for, write a clear, concise '
    'explanation of the strategic decisions made.\n\n'
    'Cover:\n'
    '1. Why certain pages were prioritised and included\n'
    '2. How the section structure establishes topical authority and expertise\n'
    '3. How descriptions were crafted for AI consumption and understanding\n'
    '4. What GEO principles were applied\n'
    "5. How this file improves the site's visibility in AI-powered search\n\n"
    'Keep the tone professional but accessible. Use 3-5 short paragraphs. Use British English.'
)


def _build_user_prompt(
    domain: str,
    business_type: str,
    tone: str,
    pages: list[dict[str, Any]],
    categories: dict[str, list[dict[str, Any]]],
    robots_raw: str | None,
) -> str:
    """Construct the user prompt with crawled site data."""
    # Homepage data
    homepage = next(
        (p for p in pages if p['url'].rstrip('/') == domain.rstrip('/')),
        None,
    )
    homepage_title = homepage['title'] if homepage else 'Unknown'
    homepage_desc = (homepage.get('description', '') or '') if homepage else ''

    parts = [
        f'Domain: {domain}',
        f'Business type: {business_type}',
        f'Tone: {tone}',
        '',
        f'Homepage title: {homepage_title}',
        f'Homepage meta description: {homepage_desc}',
        '',
    ]

    # Categorised URL list
    parts.append(f'Sitemap URLs ({len(pages)} total, categorised):')
    for category, cat_pages in sorted(categories.items()):
        parts.append(f'\n### {category}')
        for page in cat_pages:
            desc = page.get('description', '') or ''
            parts.append(f'- {page["url"]} — {page["title"]}: {desc}')
    parts.append('')

    # Key page extracts
    parts.append('Key page extracts:')
    for page in pages[:50]:
        body = page.get('body_text', '') or ''
        headings = ', '.join(page.get('headings', [])[:5])
        parts.append(f'\nURL: {page["url"]}')
        parts.append(f'Title: {page["title"]}')
        if page.get('description'):
            parts.append(f'Description: {page["description"]}')
        if headings:
            parts.append(f'H2 headings: {headings}')
        if body:
            parts.append(f'Body excerpt: {body}')
    parts.append('')

    # Robots.txt
    if robots_raw:
        parts.append('Existing robots.txt directives:')
        parts.append(robots_raw[:1000])
        parts.append('')

    parts.append('Generate the llms.txt file now.')
    return '\n'.join(parts)


async def generate_llms_txt(
    domain: str,
    pages: list[dict[str, Any]],
    categories: dict[str, list[dict[str, Any]]],
    business_type: str,
    tone: str,
    robots_raw: str | None,
    api_key: str,
) -> str:
    """Generate llms.txt content using Claude."""
    client = anthropic.AsyncAnthropic(api_key=api_key)
    user_prompt = _build_user_prompt(domain, business_type, tone, pages, categories, robots_raw)

    message = await client.messages.create(
        model='claude-sonnet-4-20250514',
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{'role': 'user', 'content': user_prompt}],
    )

    content = message.content[0].text

    # Strip any accidental code fences the model might add
    if content.startswith('```'):
        lines = content.split('\n')
        lines = lines[1:]
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        content = '\n'.join(lines)

    return content.strip()


async def generate_explainer(
    domain: str,
    llms_txt: str,
    business_type: str,
    api_key: str,
) -> str:
    """Generate a GEO/SEO explainer for the llms.txt decisions."""
    client = anthropic.AsyncAnthropic(api_key=api_key)

    user_prompt = (
        f'Domain: {domain}\n'
        f'Detected business type: {business_type}\n\n'
        f'Generated llms.txt:\n\n{llms_txt}\n\n'
        f'Explain the GEO and SEO strategy behind this llms.txt file.'
    )

    message = await client.messages.create(
        model='claude-sonnet-4-20250514',
        max_tokens=1500,
        system=EXPLAINER_SYSTEM_PROMPT,
        messages=[{'role': 'user', 'content': user_prompt}],
    )

    return message.content[0].text.strip()


def generate_fallback_llms_txt(
    domain: str,
    pages: list[dict[str, Any]],
    categories: dict[str, list[dict[str, Any]]],
) -> str:
    """Generate a basic llms.txt without LLM — mechanical fallback."""
    hostname = urlparse(domain).hostname or domain
    lines = [f'# {hostname}\n']

    # Homepage description as blockquote
    homepage = next(
        (p for p in pages if p['url'].rstrip('/') == domain.rstrip('/')),
        None,
    )
    if homepage and homepage.get('description'):
        lines.append(f'> {homepage["description"]}\n')

    lines.append('')

    # Sections by category
    for category in sorted(categories):
        if not categories[category]:
            continue
        lines.append(f'## {category}\n')
        for page in categories[category]:
            link = f'- [{page["title"]}]({page["url"]})'
            if page.get('description'):
                link += f': {page["description"]}'
            lines.append(link)
        lines.append('')

    return '\n'.join(lines)


FALLBACK_EXPLAINER = (
    'This llms.txt file was generated using structural analysis of the site '
    'without AI enhancement. The pages were categorised by URL patterns and '
    'organised into semantic sections to help AI systems understand the '
    "site's content hierarchy.\n\n"
    'For a more nuanced, AI-crafted output with better descriptions and '
    'strategic page selection, provide an Anthropic API key. The AI-enhanced '
    'version analyses page content, detects the business model, and crafts '
    'descriptions optimised for generative engine visibility.\n\n'
    'Even in its current form, this file establishes a clear content hierarchy '
    'that helps AI crawlers and generative search engines understand what the '
    'site offers and where to find key information. This is the foundation of '
    "Generative Engine Optimisation (GEO) \u2014 making your site's expertise "
    'and authority legible to AI systems.'
)
