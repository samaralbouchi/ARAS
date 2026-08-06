"""
Comprehension Agent.

Evaluates how easily an AI agent can understand
and interpret a website homepage.
"""

from __future__ import annotations

from models.evidence import WebsiteEvidence
from models.comprehension import ComprehensionResult


class ComprehensionAgent:
    """
    Analyze website comprehension readiness.

    This agent only evaluates collected evidence.
    It does not crawl websites and does not use LLM reasoning.
    """

    def analyze(
        self,
        evidence: WebsiteEvidence
    ) -> ComprehensionResult:

        



        checks = {}
        details = {}
        issues = []
        recommendations = []


        # =====================================================
        # 1. Structured data availability
        # =====================================================

        json_ld_found = len(evidence.json_ld_items) > 0
        microdata_found = len(evidence.microdata_items) > 0
        rdfa_found = len(evidence.rdfa_items) > 0

        structured_found = (
            json_ld_found
            or microdata_found
            or rdfa_found
        )

        checks["structured_data_availability"] = structured_found


        details["structured_data"] = {

            "json_ld_found": json_ld_found,

            "microdata_found": microdata_found,

            "rdfa_found": rdfa_found
        }


        if not structured_found:

            issues.append(
                "No structured data found."
            )

            recommendations.append(
                "Add JSON-LD structured data using Schema.org vocabulary."
            )



        # =====================================================
        # 2. JSON-LD semantic understanding
        # =====================================================

        json_ld_ok = json_ld_found

        checks["json_ld_semantic_understanding"] = json_ld_ok


        details["json_ld"] = {

            "items": evidence.json_ld_items

        }


        if not json_ld_ok:

            issues.append(
                "No JSON-LD semantic information found."
            )

            recommendations.append(
                "Add JSON-LD markup to describe website entities."
            )



        # =====================================================
        # 3. Schema.org entity description
        # =====================================================

        schema_types = self._extract_schema_types(evidence)

        schema_ok = len(schema_types) > 0


        checks["schema_org_entity_description"] = schema_ok


        details["schema_entities"] = {

            "schema_types": schema_types

        }


        if not schema_ok:

            issues.append(
                "No Schema.org entities detected."
            )

            recommendations.append(
                "Define semantic entities such as Organization, Product, Article or FAQ."
            )



        # =====================================================
        # 4. Metadata completeness
        # =====================================================

        has_title = bool(evidence.title)

        has_description = bool(
            evidence.meta_tags.get("description")
        )

        has_language = bool(
            evidence.language
        )


        metadata_ok = (
            has_title
            and has_description
            and has_language
        )


        checks["metadata_completeness"] = metadata_ok


        details["metadata"] = {

            "title": has_title,

            "description": has_description,

            "language": has_language

        }


        if not metadata_ok:

            missing = []

            if not has_title:
                missing.append("title")

            if not has_description:
                missing.append("meta description")

            if not has_language:
                missing.append("language")


            issues.append(
                f"Missing metadata information: {', '.join(missing)}"
            )


            recommendations.append(
                "Add title, meta description and language attributes."
            )



        # =====================================================
        # 5. Content representation formats
        # =====================================================

        formats = []


        if json_ld_found:
            formats.append("JSON-LD")

        if microdata_found:
            formats.append("Microdata")

        if rdfa_found:
            formats.append("RDFa")


        semantic_formats_ok = len(formats) > 0


        checks["content_representation_formats"] = semantic_formats_ok


        details["semantic_formats"] = formats


        if not semantic_formats_ok:

            issues.append(
                "Poor semantic representation."
            )

            recommendations.append(
                "Provide machine-readable content representations for AI agents."
            )



        # =====================================================
        # 6. Open Graph
        # =====================================================

        open_graph_ok = bool(
            evidence.open_graph
        )


        checks["open_graph_semantic_information"] = open_graph_ok


        details["open_graph"] = evidence.open_graph


        if not open_graph_ok:

            issues.append(
                "Missing Open Graph metadata."
            )

            recommendations.append(
                "Add Open Graph metadata."
            )



        # =====================================================
        # 7. Internal content structure
        # =====================================================

        internal_structure_ok = bool(
            evidence.internal_links
        )


        checks["internal_content_structure"] = (
            internal_structure_ok
        )


        details["internal_links"] = {

            "count": len(
                evidence.internal_links
            )

        }


        if not internal_structure_ok:

            issues.append(
                "No internal content structure found."
            )

            recommendations.append(
                "Add internal links so agents can navigate content organization."
            )



        # =====================================================
        # 8. Accessibility semantics
        # =====================================================

        accessibility_ok = (

            bool(evidence.aria_attributes)

            or evidence.labels_count > 0

        )


        checks["accessibility_semantics"] = accessibility_ok


        details["accessibility"] = {

            "aria": evidence.aria_attributes,

            "labels": evidence.labels_count,

            "forms": evidence.forms_count

        }


        if not accessibility_ok:

            issues.append(
                "Accessibility semantic information is limited."
            )

            recommendations.append(
                "Add ARIA attributes and semantic labels."
            )



        # =====================================================
        # 9. Language declaration
        # =====================================================

        language_ok = bool(
            evidence.language
        )


        checks["language_declared"] = language_ok


        if not language_ok:

            issues.append(
                "Document language is not declared."
            )

            recommendations.append(
                "Add lang attribute to HTML element."
            )



        # =====================================================
        # 10. Content efficiency
        # =====================================================

        ratio = 0


        if evidence.html_length:

            ratio = (
                evidence.text_length
                /
                evidence.html_length
            )


        efficiency_ok = ratio >= 0.10


        checks["content_efficiency"] = efficiency_ok


        details["content_efficiency"] = {

            "text_html_ratio":
                round(ratio,3)

        }


        if not efficiency_ok:

            issues.append(
                "The HTML contains little meaningful text."
            )

            recommendations.append(
                "Improve content structure and reduce unnecessary markup."
            )



        # =====================================================
        # Score
        # =====================================================

        total = len(checks)

        passed = sum(
            1
            for value in checks.values()
            if value
        )


        score = (
            passed / total * 100
            if total
            else 0
        )


        return ComprehensionResult(

            score=round(score,2),

            checks=checks,

            details=details,

            recommendations=list(
                dict.fromkeys(recommendations)
            ),

            issues=list(
                dict.fromkeys(issues)
            )

        )



    # Compatibility with OrchestratorAgent

    def evaluate(
        self,
        evidence: WebsiteEvidence
    ) -> ComprehensionResult:

        return self.analyze(evidence)



    # Extract Schema.org types from JSON-LD

    def _extract_schema_types(
        self,
        evidence: WebsiteEvidence
    ):

        types = []


        for item in evidence.json_ld_items:

            if "@type" in item:

                value = item["@type"]

                if isinstance(value,list):

                    types.extend(value)

                else:

                    types.append(value)


        return list(set(types))