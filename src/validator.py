"""Spec compliance validation for generated llms.txt files."""

from __future__ import annotations

import re
from typing import Any

WARN_SIZE_BYTES = 10_000
ERROR_SIZE_BYTES = 15_000

# Regex for valid link lines: - [text](url) or - [text](url): description
LINK_PATTERN = re.compile(r'^- \[.+\]\(https?://.+\)(: .+)?$')
HTML_TAG_PATTERN = re.compile(r'<[a-zA-Z/][^>]*>')


def validate_llms_txt(content: str) -> dict[str, Any]:
    """Validate a generated llms.txt file against the spec.

    Returns a ValidationReport dict with checks, stats, and overall pass/fail.
    """
    lines = content.split('\n')
    non_empty = [line for line in lines if line.strip()]
    checks: list[dict[str, Any]] = []

    # 1. Starts with single H1
    first_content = non_empty[0] if non_empty else ''
    h1_ok = first_content.startswith('# ') and not first_content.startswith('## ')
    checks.append(
        {
            'rule': 'Starts with H1',
            'passed': h1_ok,
            'message': 'File starts with a valid H1 heading' if h1_ok else 'Must start with H1 (# Title)',
        }
    )

    # 2. Blockquote after H1 (recommended, not required)
    has_blockquote = len(non_empty) > 1 and non_empty[1].startswith('> ')
    checks.append(
        {
            'rule': 'Blockquote after H1',
            'passed': has_blockquote,
            'message': 'Summary blockquote present' if has_blockquote else 'Recommended: add > blockquote after H1',
        }
    )

    # 3. No duplicate H1s
    h1_count = sum(1 for line in lines if re.match(r'^# [^#]', line))
    checks.append(
        {
            'rule': 'No duplicate H1',
            'passed': h1_count == 1,
            'message': 'Single H1 heading found' if h1_count == 1 else f'{h1_count} H1 headings found (only 1 allowed)',
        }
    )

    # 4. Sections use H2 only (no H3 or deeper)
    deep_headings = [line for line in lines if re.match(r'^#{3,}\s', line)]
    checks.append(
        {
            'rule': 'Sections use H2 only',
            'passed': len(deep_headings) == 0,
            'message': 'All sections use H2' if not deep_headings else f'{len(deep_headings)} headings deeper than H2',
        }
    )

    # 5. Links in correct format
    link_lines = [line for line in lines if line.strip().startswith('- [')]
    bad_links = [line for line in link_lines if not LINK_PATTERN.match(line.strip())]
    checks.append(
        {
            'rule': 'Links in correct format',
            'passed': len(bad_links) == 0,
            'message': f'All {len(link_lines)} links correctly formatted'
            if not bad_links
            else f'{len(bad_links)} invalid',
        }
    )

    # 6. File size
    size_bytes = len(content.encode('utf-8'))
    size_ok = size_bytes <= ERROR_SIZE_BYTES
    size_warn = size_bytes > WARN_SIZE_BYTES
    if size_ok and not size_warn:
        size_msg = f'{size_bytes:,} bytes (under 10KB)'
    elif size_ok and size_warn:
        size_msg = f'{size_bytes:,} bytes (over 10KB limit, under 15KB max)'
    else:
        size_msg = f'{size_bytes:,} bytes (exceeds 15KB maximum)'
    checks.append({'rule': 'File size', 'passed': size_ok, 'message': size_msg})

    # 7. No HTML tags
    html_lines = [line for line in lines if HTML_TAG_PATTERN.search(line)]
    checks.append(
        {
            'rule': 'No HTML tags',
            'passed': len(html_lines) == 0,
            'message': 'No HTML tags found' if not html_lines else f'HTML on {len(html_lines)} lines',
        }
    )

    # 8. No YAML frontmatter
    starts_with_yaml = content.strip().startswith('---')
    checks.append(
        {
            'rule': 'No YAML frontmatter',
            'passed': not starts_with_yaml,
            'message': 'No frontmatter' if not starts_with_yaml else 'Starts with YAML (---)',
        }
    )

    # 9. Optional section is last
    h2_sections = [line.strip() for line in lines if re.match(r'^## ', line)]
    optional_ok = True
    if any('optional' in s.lower() for s in h2_sections):
        optional_idx = next(i for i, s in enumerate(h2_sections) if 'optional' in s.lower())
        optional_ok = optional_idx == len(h2_sections) - 1
    checks.append(
        {
            'rule': '## Optional section last',
            'passed': optional_ok,
            'message': 'Optional is last' if optional_ok else 'Optional must be last H2',
        }
    )

    # Stats
    link_count = len(link_lines)
    section_count = len(h2_sections)
    is_valid = all(c['passed'] for c in checks)

    return {
        'checks': checks,
        'file_size_bytes': size_bytes,
        'link_count': link_count,
        'section_count': section_count,
        'is_valid': is_valid,
    }
