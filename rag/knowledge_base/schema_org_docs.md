# Schema.org Structured Data

## Purpose
Schema.org vocabulary, embedded via JSON-LD, microdata, or RDFa, lets a page
describe its own content in a structured, machine-readable way (products,
articles, events, organizations, FAQs, etc.).

## Why it helps agents
Instead of parsing visual layout or inferring meaning from CSS classes, an
agent can read structured fields directly: price, availability, author, date,
steps in a how-to, and so on. This reduces ambiguity and token usage.

## What good implementation looks like
- JSON-LD blocks in the page `<head>` or body, using appropriate schema.org
  types (`Product`, `Article`, `FAQPage`, `Organization`, `BreadcrumbList`).
- Required properties for each type filled in accurately (e.g. `price`,
  `availability` for `Product`; `datePublished`, `author` for `Article`).
- Consistency between the structured data and the visible page content — an
  agent that detects mismatches should treat the source as less reliable.
- Nested/linked entities where relevant (e.g. an `Organization` referenced from
  a `Product`'s `brand` field).

## Common gaps
- No structured data at all, forcing an agent to parse raw HTML/DOM.
- Structured data present but incomplete (missing required fields) or stale
  relative to the actual page content.
- Structured data duplicated inconsistently across formats (JSON-LD says one
  price, microdata says another).

## Scoring considerations
- Rich, accurate, validated structured data: strong comprehension score.
- Partial or generic structured data: moderate score.
- Absent: agent must fall back to full-page HTML parsing, lower score.