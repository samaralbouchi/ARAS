# Semantic HTML and DOM Quality

## Why it matters for agents
Agents that read raw HTML benefit heavily from semantic structure: it reduces
the number of tokens needed to understand a page and lowers the chance of
misinterpreting content.

## Signals of good semantic HTML
- Proper use of landmark elements: `<header>`, `<nav>`, `<main>`, `<article>`,
  `<footer>`, rather than generic `<div>` soup.
- Meaningful heading hierarchy (`<h1>` once per page, logical `<h2>`/`<h3>`
  nesting) that mirrors the actual content structure.
- Descriptive `alt` text on meaningful images, and `aria-label`/`aria-*`
  attributes where visual-only cues would otherwise convey meaning.
- Forms with proper `<label>` associations and clear `name`/`id` attributes,
  so an agent can map form fields to their purpose.
- Tables using `<th>`, `scope`, and `<caption>` for tabular data rather than
  layout tables.

## Signals of poor semantic HTML (agent-hostile)
- Deeply nested generic `<div>`/`<span>` structures with no semantic tags.
- Content rendered client-side via JavaScript with no server-rendered
  fallback, meaning a simple crawl returns an empty shell.
- Critical information conveyed only through images or icons with no text
  alternative.
- Inconsistent or auto-generated class/id names with no semantic meaning.

## Token efficiency
Semantic, well-pruned HTML is also more token-efficient for an LLM-based agent
to consume — less boilerplate per unit of actual information, which matters
for cost and context-window budgets during multi-page crawls.

## Scoring considerations
- Clean semantic structure, server-rendered content, good token density: high
  comprehension score.
- Heavy client-side rendering with no fallback, div-soup: low score, flag as
  a major issue since it blocks lightweight agents entirely.