# Finalization Plan: llms.txt Generator

## Current State vs Brief — Gap Analysis

The existing codebase is a **well-structured Apify Actor** (~400 LOC, strong tests, CI/CD) that crawls a website using BeautifulSoup/Crawlee and mechanically organises URLs into directory-based sections to produce a basic `llms.txt` file. It works, but it is missing the **core intelligence layer** and several key features described in the brief.

### What's Built (working)

| Component | Status | Notes |
|-----------|--------|-------|
| BeautifulSoup crawler | Done | Follows links, domain filtering, configurable depth/pages |
| HTML extraction | Done | Title (H1 fallback to `<title>`), meta description |
| Section organisation | Done | Directory-path-based grouping, small-section merging |
| Markdown renderer | Done | Spec-compliant output formatting |
| Type system | Done | Full TypedDict definitions |
| Tests | Done | 30+ unit tests, 93% test-to-code ratio |
| CI/CD | Done | GitHub Actions: lint, type-check, test |
| Docker deployment | Done | Apify Actor containerised |

### What's Missing (gaps from brief)

#### Tier 1 — Critical (core functionality the brief centres on)

| # | Gap | Brief Reference | Impact |
|---|-----|----------------|--------|
| 1 | **No LLM integration** | "Call the Anthropic API (Claude Sonnet) to analyse crawled content and generate the llms.txt output" | The main differentiator. Without it, output is a mechanical directory listing rather than an intelligently curated, contextual llms.txt |
| 2 | **No sitemap.xml parsing** | Step 1: "GET {domain}/sitemap.xml — extract all listed URLs" | Misses discoverable pages that aren't linked from the homepage |
| 3 | **No robots.txt parsing** | Step 1: "GET {domain}/robots.txt — parse for sitemap location, disallowed paths" | Misses sitemap hints, may crawl disallowed paths |
| 4 | **No existing llms.txt check** | Step 1: "GET {domain}/llms.txt — check if one already exists" | User has no idea if the domain already has one |
| 5 | **No body text extraction** | Step 3: "Extract first 500 chars of body text" | LLM has almost no content to work with — only titles and meta descriptions |
| 6 | **No URL categorisation** | Step 2: Categorise into About, Products, Docs, Support, Blog, Legal buckets | Sections are just path directories, not semantic categories |
| 7 | **No business model detection** | Step 4: "Infer business model, content types, monetisation signals" | LLM prompt can't be contextualised without this |
| 8 | **No spec validator** | Validation Rules table: H1 check, link format, URL resolution, file size, etc. | No way to verify output quality |

#### Tier 2 — Important (user-facing quality)

| # | Gap | Brief Reference |
|---|-----|----------------|
| 9 | **No tone option** | "Defensive (restrictive, brand-safe) vs Open (permissive, discovery-friendly)" |
| 10 | **No focus/vertical option** | "Auto-detect OR user-selected: SaaS/API Docs, E-commerce, Professional Services, Publisher/Blog, Corporate" |
| 11 | **No progress reporting** | UI: "Status: Crawling sitemap... (12/47 pages) ████░░ 34%" |
| 12 | **No validation report output** | "file size, link count, section count, spec compliance check" |

#### Tier 3 — Nice-to-have (edge cases and polish)

| # | Gap | Brief Reference |
|---|-----|----------------|
| 13 | No diff view against existing llms.txt | "Show it alongside generated version, offer diff" |
| 14 | No broken link detection | "HTTP HEAD check returns 200" |
| 15 | No SPA detection warning | "Warn that crawl may be incomplete" |
| 16 | No language detection | "Detect language, generate in that language" |
| 17 | No subdomain prompt | "Ask if subdomains should be included" |
| 18 | No WAF/retry logic | "Implement retry with backoff" |

### Architecture Note

The brief describes a **standalone web app** (React + Express/Flask). The current implementation is an **Apify Actor**. The Apify platform already provides an input UI, output display, key-value store for downloads, and proxy infrastructure. Rather than rebuilding as a standalone app, the plan below enhances the existing Actor to incorporate the brief's intelligence features. A standalone frontend can be built later as a thin wrapper over the Actor API if needed.

---

## Proposed Implementation Plan

### Phase 1: Enhanced Crawl Intelligence

**Goal**: Make the crawler gather the data the LLM needs to produce quality output.

#### 1.1 Add sitemap.xml + robots.txt fetching (`src/sitemap.py`)
- Fetch `{domain}/robots.txt`, parse for `Sitemap:` directives and `Disallow:` rules
- Fetch `{domain}/sitemap.xml` (and any nested sitemaps), extract all `<loc>` URLs
- Merge sitemap URLs with link-discovered URLs, deduplicate
- Filter out disallowed paths from robots.txt
- Fall back gracefully if either file is missing (404)

#### 1.2 Add existing llms.txt check
- Fetch `{domain}/llms.txt` before crawling
- If found, store its content for later comparison/diff
- Flag to user in output metadata

#### 1.3 Enhance content extraction in crawler (`src/crawler.py`)
- Extract first 500 characters of visible body text (strip nav, footer, scripts)
- Extract `<h1>` tags (already done)
- Add extraction of all `<h2>` headings for page structure understanding
- Store richer `CrawledPage` with `body_text` and `headings` fields

#### 1.4 Add URL categorisation (`src/analyser.py`)
- Classify crawled URLs into semantic buckets based on URL patterns and page content:
  - About/Company, Products/Services, Documentation/API, Support/Help, Blog/Content, Legal/Policy
- Prioritise category landing pages over deep content pages
- Detect business model signals (pricing pages, checkout, API docs, etc.)

### Phase 2: LLM Integration

**Goal**: Use Claude to generate intelligently curated llms.txt output instead of mechanical directory listings.

#### 2.1 Anthropic API integration (`src/generator.py`)
- Add `anthropic` Python SDK as a dependency
- Accept API key via Actor input or environment variable
- Construct the structured prompt from the brief:
  - System prompt with spec rules, tone, British English, etc.
  - User prompt with: domain, detected business type, tone, crawled page data
- Call Claude Sonnet with the assembled prompt
- Parse the response as the llms.txt content

#### 2.2 Prompt construction
- Build the system prompt exactly as specified in the brief
- Build the user prompt with:
  - Domain and detected business type
  - Homepage title, description, H1
  - Categorised URL list with titles and descriptions
  - Key page extracts (URL, title, description, H1, body text snippet)
  - robots.txt directives
- Handle token limits: if crawled data exceeds context window, prioritise by category importance

#### 2.3 Fallback mode
- If no API key is provided, fall back to the current mechanical generation (enhanced with better categorisation from Phase 1)
- Log a warning that LLM-enhanced output requires an API key

### Phase 3: Spec Validator

**Goal**: Validate generated output against the llms.txt spec before presenting it.

#### 3.1 Implement validator (`src/validator.py`)
Validation checks from the brief:

| Rule | Implementation |
|------|---------------|
| Starts with single H1 | Regex: `^# .+` on first non-empty line |
| Blockquote after H1 | Check for `> ` line after H1 |
| No H1 duplicates | Count `# ` occurrences (not `##`) |
| Sections use H2 only | No `###` or deeper headings |
| Links in correct format | Regex: `- \[.+\]\(.+\)(: .+)?` |
| File size under 15KB | `len(output.encode('utf-8'))` |
| No HTML tags | Regex: `<[^>]+>` |
| No YAML frontmatter | File doesn't start with `---` |
| Optional section last | `## Optional` appears after all other H2s |

#### 3.2 Validation report output
- Return validation results as structured metadata alongside the llms.txt output
- Include: pass/fail per rule, file size, link count, section count
- Push to dataset alongside the llms.txt content

### Phase 4: Input Options & Configuration

**Goal**: Expose the tone, focus, and depth options from the brief.

#### 4.1 Update input schema (`.actor/input_schema.json`)
Add new input parameters:
- `tone`: enum — `"open"` (default) or `"defensive"`
- `focus`: enum — `"auto"`, `"saas"`, `"ecommerce"`, `"services"`, `"publisher"`, `"corporate"`
- `anthropicApiKey`: string (optional, for LLM-enhanced generation)
- Keep existing: `startUrl`, `maxCrawlDepth`, `maxCrawlPages`

#### 4.2 Wire options through to generator
- Pass tone and focus to the LLM prompt
- Use focus to weight URL categorisation priorities

### Phase 5: Output Enhancements

**Goal**: Richer output metadata and comparison features.

#### 5.1 Enhanced dataset output
- Push to dataset: `llms.txt` content, validation report, crawl stats
- If existing llms.txt was found: include it in output for comparison
- Status messages with progress (crawling, analysing, generating, validating)

#### 5.2 URL validation (optional/async)
- HTTP HEAD check on URLs in the generated output
- Warn on 3xx redirects, flag 4xx/5xx as errors
- Include in validation report

### Phase 6: Edge Case Handling

#### 6.1 SPA detection
- If most pages return identical or near-identical content, warn that the site may be JS-rendered

#### 6.2 Large site handling
- Cap at `maxCrawlPages` (already exists)
- Prioritise by URL depth and detected category when selecting which pages to crawl

#### 6.3 Clean up dead code
- Remove or repurpose `src/crawler_config.py` (currently unused)

---

## Updated File Structure

```
src/
├── __init__.py          # (existing)
├── __main__.py          # (existing) Entry point
├── main.py              # (existing, modified) Orchestrator — wire new components
├── crawler.py           # (existing, modified) Enhanced content extraction
├── sitemap.py           # (NEW) robots.txt + sitemap.xml parsing
├── analyser.py          # (NEW) URL categorisation + business model detection
├── generator.py         # (NEW) Anthropic API integration + prompt construction
├── validator.py         # (NEW) Spec compliance checking
├── renderer.py          # (existing) Fallback mechanical renderer
├── helpers.py           # (existing, minor updates) Utility functions
└── mytypes.py           # (existing, modified) Extended type definitions
```

## New/Updated Dependencies

```
anthropic>=0.40.0       # Anthropic Python SDK for Claude API
```

---

## Implementation Priority

The phases are ordered by impact and dependency:

1. **Phase 1** (Enhanced Crawl) — foundational; everything else depends on richer data
2. **Phase 2** (LLM Integration) — the core value-add from the brief
3. **Phase 3** (Validator) — quality assurance on output
4. **Phase 4** (Input Options) — user control over generation
5. **Phase 5** (Output Enhancements) — polish and metadata
6. **Phase 6** (Edge Cases) — robustness

Phases 3 and 4 can be developed in parallel with Phase 2. Phase 6 items can be sprinkled in throughout.

---

## What Stays Out of Scope (per brief)

- `.md` mirror page generation
- File deployment to user's server
- Monitoring/updating over time
- `llms-full.txt` or `llms-ctx.txt` files
- SEO advice
- Standalone React frontend (Apify UI serves this purpose for now)

---

## Tests to Add

Each new module needs corresponding tests:

- `tests/test_sitemap.py` — robots.txt parsing, sitemap XML parsing, URL deduplication, fallback on 404
- `tests/test_analyser.py` — URL categorisation accuracy, business model detection
- `tests/test_generator.py` — prompt construction (mock API calls), fallback mode, token limit handling
- `tests/test_validator.py` — each validation rule with passing and failing cases
- Update `tests/test_helpers.py` — any new helper functions
- Update `tests/test_renderer.py` — if renderer changes

---

## Summary

The current codebase is a solid foundation — well-tested, well-typed, clean architecture. The primary gap is the **intelligence layer**: the tool mechanically lists pages by directory instead of using an LLM to produce a curated, contextual llms.txt. Adding sitemap/robots.txt awareness, richer content extraction, URL categorisation, and Claude Sonnet integration will transform it from a basic directory lister into the tool described in the brief.
