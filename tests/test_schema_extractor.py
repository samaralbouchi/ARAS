"""Manual smoke test for :class:`SchemaExtractor`.

Covers four cases: a real page with no structured data (example.com),
artificial JSON-LD, artificial Microdata, and artificial RDFa. This
verifies that extraction works end-to-end; it performs no scoring or
assertions about Agentic Readiness.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running this file directly (e.g. from an IDE "Run" button) by
# ensuring the project root is importable, not just the `tests/` folder.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.http_client import HttpClient
from tools.schema_extractor import SchemaExtractor

TEST_URL = "https://example.com"

JSON_LD_HTML = """
<html><head>
<script type="application/ld+json">
{
 "@context": "https://schema.org",
 "@type": "Organization",
 "name": "Example Company"
}
</script>
</head><body></body></html>
"""

MICRODATA_HTML = """
<html><body>
<div itemscope itemtype="https://schema.org/Product">
  <span itemprop="name">Laptop</span>
  <div itemprop="offers" itemscope itemtype="https://schema.org/Offer">
    <span itemprop="price">999</span>
    <span itemprop="priceCurrency">USD</span>
  </div>
</div>
</body></html>
"""

RDFA_HTML = """
<html><body>
<div vocab="https://schema.org/" typeof="Product">
  <span property="name">Laptop</span>
  <span property="price">999</span>
</div>
</body></html>
"""


def _print_result(label: str, result) -> None:
    print(f"--- {label} ---")
    print(f"json_ld:    {result.json_ld}")
    print(f"microdata:  {result.microdata}")
    print(f"rdfa:       {result.rdfa}")
    print()


def test_no_structured_data() -> None:
    """example.com should yield no structured data of any format."""
    with HttpClient() as client:
        response = client.get(TEST_URL)
    result = SchemaExtractor(response.content).extract()
    _print_result("example.com (no structured data)", result)
    assert result.json_ld == []
    assert result.microdata == []
    assert result.rdfa == []


def test_json_ld_extraction() -> None:
    """Artificial JSON-LD should be parsed into a dict."""
    result = SchemaExtractor(JSON_LD_HTML).extract()
    _print_result("artificial JSON-LD", result)
    assert result.json_ld == [
        {
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": "Example Company",
        }
    ]


def test_microdata_extraction() -> None:
    """Artificial Microdata should be parsed with nested item support."""
    result = SchemaExtractor(MICRODATA_HTML).extract()
    _print_result("artificial Microdata", result)
    assert result.microdata == [
        {
            "type": "https://schema.org/Product",
            "properties": {
                "name": "Laptop",
                "offers": {
                    "type": "https://schema.org/Offer",
                    "properties": {
                        "price": "999",
                        "priceCurrency": "USD",
                    },
                },
            },
        }
    ]


def test_rdfa_extraction() -> None:
    """Artificial RDFa should be parsed into type and properties."""
    result = SchemaExtractor(RDFA_HTML).extract()
    _print_result("artificial RDFa", result)
    assert result.rdfa == [
        {
            "type": "Product",
            "properties": {
                "name": "Laptop",
                "price": "999",
            },
        }
    ]


def main() -> None:
    """Run all SchemaExtractor smoke tests and print each result."""
    test_no_structured_data()
    test_json_ld_extraction()
    test_microdata_extraction()
    test_rdfa_extraction()
    print("All SchemaExtractor smoke tests passed.")


if __name__ == "__main__":
    main()
