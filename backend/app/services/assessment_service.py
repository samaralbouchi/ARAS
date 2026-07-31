from types import SimpleNamespace
import httpx
from agents.orchestrator_agent import OrchestratorAgent
from agents.recommendation_agent import RecommendationAgent
from agents.report_generator_agent import ReportGeneratorAgent

from rag.retriever import KnowledgeBaseRetriever

from models.discoverability import DiscoverabilityResult
from models.comprehension import ComprehensionResult
from models.interaction import InteractionResult
from models.security import SecurityResult


class AssessmentService:
    """
    Executes the complete ARAF pipeline:

    OrchestratorAgent
            ↓
    RecommendationAgent
            ↓
    ReportGeneratorAgent
    """

    def __init__(self):
        self.orchestrator = OrchestratorAgent()
        retriever = KnowledgeBaseRetriever(
            k=4
        )

        self.recommendation_agent = RecommendationAgent(
            retriever=retriever
        )

        self.report_generator = ReportGeneratorAgent()

    async def check_url(self, url: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    url,
                    follow_redirects=True
                )

                return response.status_code < 400

        except Exception:
            return False


    async def assess(self, url: str) -> dict:

        # 0. Validate URL
        if not await self.check_url(url):
            return {
                "status": "error",
                "message": "Site inexistant ou inaccessible",
                "url": url
            }
        # 1. Run Orchestrator
        assessment_result = self.orchestrator.run({
            "url": url
        })


        # 2. Convert dictionaries to Result objects
        discoverability = DiscoverabilityResult(
            **assessment_result.discoverability
        )

        comprehension = ComprehensionResult(
            **assessment_result.comprehension
        )

        interaction = InteractionResult(
            **assessment_result.interaction
        )

        security = SecurityResult(
            **assessment_result.security
        )


        # 3. Generate recommendations
        recommendation_result = self.recommendation_agent.evaluate(
            discoverability=discoverability,
            comprehension=comprehension,
            interaction=interaction,
            security=security
        )


        # Object expected by ReportGeneratorAgent
        report_recommendations = SimpleNamespace(
            recommendations=recommendation_result.recommendations,
            rag_sources_used=[]
        )


        # 4. Object expected by ReportGeneratorAgent
        report_assessment = SimpleNamespace(
            url=assessment_result.url,

            overall_score=assessment_result.overall_score,

            category_scores={
                "discoverability": assessment_result.discoverability.get(
                    "score", 0
                ),
                "comprehension": assessment_result.comprehension.get(
                    "score", 0
                ),
                "interaction": assessment_result.interaction.get(
                    "score", 0
                ),
                "security": assessment_result.security.get(
                    "score", 0
                ),
            },

            issues=(
                assessment_result.discoverability.get("issues", [])
                + assessment_result.comprehension.get("issues", [])
                + assessment_result.interaction.get("issues", [])
                + assessment_result.security.get("issues", [])
            ),

            artifacts_collected=[]
        )


        # 5. Generate report
        report = self.report_generator.generate(
            assessment=report_assessment,
            recommendations=report_recommendations
        )

        # 6. API response
        return {
            "url": assessment_result.url,

            "overall_score": assessment_result.overall_score,

            "discoverability": assessment_result.discoverability,
            "comprehension": assessment_result.comprehension,
            "interaction": assessment_result.interaction,
            "security": assessment_result.security,

            "recommendations": [
                rec.__dict__
                for rec in recommendation_result.recommendations
            ],

            "report": report,

            "assessed_at": assessment_result.assessed_at
        }