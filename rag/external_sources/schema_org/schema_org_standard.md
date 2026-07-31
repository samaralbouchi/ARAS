# Schema.org Structured Data

Source:
Schema.org Official Documentation

Reference:
https://schema.org/docs/documents.html


## Overview

Schema.org provides a shared vocabulary for structured data on the Web.

It allows websites to describe their content in a machine-readable format that can be understood by search engines and intelligent systems.


## Structured Data Formats

Schema.org can be implemented using:

- JSON-LD
- Microdata
- RDFa


## JSON-LD

JSON-LD is the recommended format for embedding structured data in HTML pages.

Example:

<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Organization",
  "name": "Example Company"
}
</script>


## Benefits for AI Agents

Structured data helps AI systems understand:

- Entity identity
- Products and services
- Organizations
- Events
- Relationships between entities


## Agentic Web Relevance

For AI agents, structured data improves:

- Content understanding
- Entity extraction
- Reliable information retrieval
- Automated reasoning


## Assessment Criteria

A website should provide:

- Valid Schema.org markup
- Appropriate schema types
- Complete properties
- Consistent structured information


## Recommendation Example

If structured data is missing:

Recommendation:
Add Schema.org structured data using JSON-LD to improve machine understanding and AI agent comprehension.
