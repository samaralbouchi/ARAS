# General Agentic Web Readiness Practices

## llms.txt
An emerging convention where a site exposes a plain-text `/llms.txt` (and
sometimes `/llms-full.txt`) file summarizing its content and structure in a
format optimized for LLM consumption, similar in spirit to `robots.txt` but
aimed at language models rather than crawlers.

## robots.txt and sitemap.xml for agents
- `robots.txt` should clearly state which paths are crawlable and shouldn't
  block legitimate agent traffic outright unless intentional.
- `sitemap.xml` should be present, current, and list canonical URLs, giving an
  agent a reliable map of the site without needing to crawl link-by-link.

## API discoverability
- Well-known API discovery patterns (`/.well-known/`, linked docs from the
  homepage footer, `Link` HTTP headers pointing to API docs) reduce the effort
  needed for an agent to find programmatic access points.
- A human-readable "Developers" or "API" section that's easy to find from the
  homepage is a positive signal even before checking spec quality.

## Actionability for agents
Beyond read access, agentic readiness includes whether an agent can *act*:
submit a form, complete a purchase, book something — via a documented,
stable interface rather than reverse-engineered POST requests.

## Scoring considerations
- Presence and quality of `llms.txt`, `robots.txt`, `sitemap.xml`: contributes
  to the discoverability score.
- Clear, linked developer/API documentation: contributes to both
  discoverability and interaction scores.
- Absence of all of the above: agent must rely entirely on generic web
  crawling and inference.