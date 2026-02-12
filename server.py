"""FastAPI web server for the llms.txt generator."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from src.analyser import analyse_site
from src.generator import (
    FALLBACK_EXPLAINER,
    generate_explainer,
    generate_fallback_llms_txt,
    generate_llms_txt,
)
from src.sitemap import gather_site_info
from src.validator import validate_llms_txt
from src.web_crawler import crawl_site

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title='llms.txt Generator')

# Serve static files
PUBLIC_DIR = Path(__file__).parent / 'public'
if PUBLIC_DIR.exists():
    app.mount('/static', StaticFiles(directory=str(PUBLIC_DIR)), name='static')


@app.get('/')
async def index() -> FileResponse:
    """Serve the frontend."""
    return FileResponse(str(PUBLIC_DIR / 'index.html'))


@app.post('/api/generate')
async def generate(request: Request) -> StreamingResponse:
    """Generate llms.txt for a domain. Returns SSE stream with progress."""
    body = await request.json()
    url = body.get('url', '').strip().rstrip('/')
    tone = body.get('tone', 'open')
    focus = body.get('focus', 'auto')
    max_pages = min(int(body.get('maxPages', 50)), 100)
    api_key = body.get('apiKey', '') or os.environ.get('ANTHROPIC_API_KEY', '')

    if not url:
        return StreamingResponse(
            _error_stream('Please enter a valid URL'),
            media_type='text/event-stream',
        )

    # Ensure URL has scheme
    if not url.startswith('http'):
        url = f'https://{url}'

    async def event_stream() -> AsyncIterator[str]:
        """Stream progress events as SSE."""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (compatible; LlmsTxtGenerator/1.0)',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            }
            async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
                # Step 1: Check for existing llms.txt
                yield _sse(
                    {
                        'step': 'checking',
                        'message': 'Checking for existing llms.txt...',
                        'progress': 5,
                    }
                )

                site_info = await gather_site_info(url, client)
                existing = site_info['existing_llms_txt']
                if existing:
                    yield _sse(
                        {
                            'step': 'checking',
                            'message': f'Found existing llms.txt ({len(existing)} chars)',
                            'progress': 8,
                            'existing': True,
                        }
                    )

                # Step 2: robots.txt + sitemap
                sitemap_count = len(site_info['sitemap_urls'])
                robots_status = 'found' if site_info['robots']['raw'] else 'not found'
                yield _sse(
                    {
                        'step': 'sitemap',
                        'message': f'robots.txt {robots_status} \u2022 {sitemap_count} sitemap URLs',
                        'progress': 15,
                    }
                )

                # Step 3: Crawl pages
                yield _sse(
                    {
                        'step': 'crawling',
                        'message': 'Starting page crawl...',
                        'progress': 20,
                    }
                )

                pages = await crawl_site(
                    domain=url,
                    sitemap_urls=site_info['sitemap_urls'],
                    disallow_rules=site_info['robots']['disallow_rules'],
                    client=client,
                    max_pages=max_pages,
                )

                yield _sse(
                    {
                        'step': 'crawling',
                        'message': f'Crawled {len(pages)} pages successfully',
                        'progress': 60,
                    }
                )

                if not pages:
                    yield _sse_error(
                        'No pages could be crawled. The site may be blocking requests or the URL may be invalid.'
                    )
                    return

                # Step 4: Analyse
                yield _sse(
                    {
                        'step': 'analysing',
                        'message': 'Analysing site structure...',
                        'progress': 65,
                    }
                )
                analysis = analyse_site(pages)

                business_type = focus if focus != 'auto' else analysis['business_model']
                cat_count = analysis['signals']['category_count']
                yield _sse(
                    {
                        'step': 'analysing',
                        'message': f'Detected: {business_type} \u2022 {cat_count} categories',
                        'progress': 70,
                    }
                )

                # Step 5: Generate
                llms_txt = ''
                explainer = ''

                if api_key:
                    yield _sse(
                        {
                            'step': 'generating',
                            'message': 'Generating llms.txt with AI...',
                            'progress': 75,
                        }
                    )
                    try:
                        llms_txt = await generate_llms_txt(
                            domain=url,
                            pages=analysis['prioritised_pages'],
                            categories=analysis['categories'],
                            business_type=business_type,
                            tone=tone,
                            robots_raw=site_info['robots']['raw'],
                            api_key=api_key,
                        )

                        yield _sse(
                            {
                                'step': 'explainer',
                                'message': 'Writing GEO strategy explainer...',
                                'progress': 88,
                            }
                        )
                        explainer = await generate_explainer(
                            domain=url,
                            llms_txt=llms_txt,
                            business_type=business_type,
                            api_key=api_key,
                        )
                    except Exception as e:
                        logger.warning(f'LLM generation failed, using fallback: {e}')
                        yield _sse(
                            {
                                'step': 'generating',
                                'message': 'AI failed, using structural fallback...',
                                'progress': 80,
                            }
                        )
                        llms_txt = generate_fallback_llms_txt(
                            url,
                            pages,
                            analysis['categories'],
                        )
                        explainer = FALLBACK_EXPLAINER
                else:
                    yield _sse(
                        {
                            'step': 'generating',
                            'message': 'No API key \u2014 structural generation...',
                            'progress': 75,
                        }
                    )
                    llms_txt = generate_fallback_llms_txt(
                        url,
                        pages,
                        analysis['categories'],
                    )
                    explainer = FALLBACK_EXPLAINER

                # Step 6: Validate
                yield _sse(
                    {
                        'step': 'validating',
                        'message': 'Validating against spec...',
                        'progress': 92,
                    }
                )
                validation = validate_llms_txt(llms_txt)

                yield _sse(
                    {
                        'step': 'validating',
                        'message': 'Validation complete',
                        'progress': 95,
                    }
                )

                # Final result
                yield _sse(
                    {
                        'step': 'complete',
                        'progress': 100,
                        'message': 'Done!',
                        'data': {
                            'llms_txt': llms_txt,
                            'explainer': explainer,
                            'validation': validation,
                            'existing_llms_txt': existing,
                            'business_type': business_type,
                            'pages_crawled': len(pages),
                            'sitemap_urls_found': sitemap_count,
                        },
                    }
                )

        except Exception as e:
            logger.exception('Generation pipeline failed')
            yield _sse_error(f'An error occurred: {e!s}')

    return StreamingResponse(event_stream(), media_type='text/event-stream')


def _sse(data: dict[str, Any]) -> str:
    """Format a dict as an SSE event."""
    return f'data: {json.dumps(data)}\n\n'


def _sse_error(message: str) -> str:
    """Format an error SSE event."""
    return f'data: {json.dumps({"step": "error", "message": message})}\n\n'


async def _error_stream(message: str) -> AsyncIterator[str]:
    """Yield a single error event."""
    yield _sse_error(message)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', '3000'))
    logger.info(f'Starting llms.txt generator on http://localhost:{port}')
    uvicorn.run(app, host='0.0.0.0', port=port)  # noqa: S104
