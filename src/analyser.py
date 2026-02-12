"""URL categorisation and site analysis."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

# URL path patterns for each category bucket
CATEGORY_PATTERNS: dict[str, list[str]] = {
    'About & Company': [
        '/about',
        '/team',
        '/company',
        '/contact',
        '/careers',
        '/our-story',
        '/who-we-are',
        '/leadership',
        '/history',
        '/mission',
    ],
    'Products & Services': [
        '/products',
        '/services',
        '/solutions',
        '/pricing',
        '/plans',
        '/features',
        '/platform',
        '/offerings',
        '/packages',
    ],
    'Documentation & API': [
        '/docs',
        '/api',
        '/developers',
        '/reference',
        '/documentation',
        '/sdk',
        '/guide',
        '/tutorial',
        '/getting-started',
        '/quickstart',
    ],
    'Support & Help': [
        '/help',
        '/support',
        '/faq',
        '/knowledge-base',
        '/kb',
        '/troubleshoot',
        '/status',
        '/community',
    ],
    'Blog & Content': [
        '/blog',
        '/articles',
        '/news',
        '/resources',
        '/insights',
        '/press',
        '/media',
        '/updates',
        '/stories',
        '/case-stud',
    ],
    'Legal & Policy': [
        '/privacy',
        '/terms',
        '/cookies',
        '/legal',
        '/compliance',
        '/gdpr',
        '/policy',
        '/disclaimer',
    ],
}

# Signals for business model detection
BUSINESS_MODEL_SIGNALS: dict[str, list[str]] = {
    'SaaS / Software': [
        'pricing',
        'plans',
        'free trial',
        'sign up',
        'dashboard',
        'api',
        'documentation',
        'developers',
        'integrations',
        'sdk',
    ],
    'E-commerce': [
        'shop',
        'cart',
        'checkout',
        'product',
        'buy',
        'order',
        'shipping',
        'store',
        'catalog',
        'collection',
    ],
    'Professional Services': [
        'services',
        'consulting',
        'solutions',
        'clients',
        'portfolio',
        'case study',
        'testimonial',
        'contact us',
        'book a call',
    ],
    'Publisher / Blog': [
        'article',
        'author',
        'editorial',
        'subscribe',
        'newsletter',
        'category',
        'tag',
        'archive',
        'magazine',
    ],
    'Corporate / Enterprise': [
        'investor',
        'shareholder',
        'annual report',
        'governance',
        'sustainability',
        'corporate',
        'ir',
        'esg',
    ],
}


def categorise_url(url: str) -> str:
    """Assign a URL to a category based on path patterns."""
    path = urlparse(url).path.lower()

    for category, patterns in CATEGORY_PATTERNS.items():
        if any(pattern in path for pattern in patterns):
            return category

    return 'General'


def categorise_pages(pages: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group crawled pages into semantic categories."""
    categories: dict[str, list[dict[str, Any]]] = {}

    for page in pages:
        category = categorise_url(page['url'])
        if category not in categories:
            categories[category] = []
        categories[category].append(page)

    return categories


def detect_business_model(pages: list[dict[str, Any]]) -> str:
    """Detect the likely business model from crawled page content."""
    scores: dict[str, int] = dict.fromkeys(BUSINESS_MODEL_SIGNALS, 0)

    for page in pages:
        searchable = ' '.join(
            [
                page.get('url', ''),
                page.get('title', ''),
                page.get('description', '') or '',
                page.get('body_text', '') or '',
            ]
        ).lower()

        for model, signals in BUSINESS_MODEL_SIGNALS.items():
            for signal in signals:
                if signal in searchable:
                    scores[model] += 1

    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else 'General'


def prioritise_pages(pages: list[dict[str, Any]], max_pages: int = 50) -> list[dict[str, Any]]:
    """Prioritise pages for LLM context: landing pages first, deep content last."""

    def _priority_score(page: dict[str, Any]) -> tuple[int, int]:
        url = page.get('url', '')
        path = urlparse(url).path
        depth = path.rstrip('/').count('/')

        # Category landing pages get highest priority
        category = categorise_url(url)
        category_bonus = 0 if category == 'General' else -10  # lower = higher priority

        return (category_bonus, depth)

    sorted_pages = sorted(pages, key=_priority_score)
    return sorted_pages[:max_pages]


def analyse_site(pages: list[dict[str, Any]]) -> dict[str, Any]:
    """Full site analysis: categorise pages, detect business model, prioritise."""
    categories = categorise_pages(pages)
    business_model = detect_business_model(pages)
    prioritised = prioritise_pages(pages)

    # Detect content signals
    has_api_docs = 'Documentation & API' in categories
    has_pricing = any('pricing' in (p.get('url', '') + p.get('title', '')).lower() for p in pages)
    has_blog = 'Blog & Content' in categories

    return {
        'categories': categories,
        'business_model': business_model,
        'prioritised_pages': prioritised,
        'signals': {
            'has_api_docs': has_api_docs,
            'has_pricing': has_pricing,
            'has_blog': has_blog,
            'total_pages': len(pages),
            'category_count': len(categories),
        },
    }
