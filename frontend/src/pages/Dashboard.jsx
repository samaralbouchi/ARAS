import { useState } from "react";
import api from "../api/axios";

import ScoreCard from "../components/ScoreCard";
import RecommendationList from "../components/RecommendationList";
import ReportViewer from "../components/ReportViewer";
import OverallScore from "../components/OverallScore";
import LoadingAgents from "../components/LoadingAgents";

function Dashboard() {
  const [url, setUrl] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  async function analyze() {
    if (!url) {
      alert("Please enter a website URL");
      return;
    }

    try {
      setLoading(true);

      const response = await api.post("/assess", {
        url: url,
      });

      setResult(response.data);
    } catch (error) {
      console.error(error);
      alert("Error while analyzing the website.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="container">

      {/* Hero Section */}

      <section className="hero">

        <h1>ARAF</h1>

        <h2>
          Agentic Readiness Assessment Framework
        </h2>

        <p>
          Evaluate how prepared your website is for AI Agents,
          Large Language Models (LLMs), GEO, AEO and the
          Agentic Web.
        </p>

        <div className="input-box">

          <input
            type="text"
            placeholder="https://example.com"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />

          <button onClick={analyze} disabled={loading}>
            {loading ? "Analyzing..." : "Analyze Website"}
          </button>

        </div>

      </section>

      {loading && <LoadingAgents />}

      {result && (
        <>

          <OverallScore
            score={result.overall_score}
          />

          <h2 className="section-title">

            Assessment Categories

          </h2>

          <div className="scores">

            <ScoreCard
              title="Discoverability"
              score={result.discoverability?.score}
            />

            <ScoreCard
              title="Comprehension"
              score={result.comprehension?.score}
            />

            <ScoreCard
              title="Interaction"
              score={result.interaction?.score}
            />

            <ScoreCard
              title="Security"
              score={result.security?.score}
            />

          </div>

          <div className="card">

            <RecommendationList
              recommendations={result.recommendations}
            />

          </div>

          <div className="card">

            <ReportViewer
              report={result}
            />

          </div>

        </>
      )}

    </div>
  );
}

export default Dashboard;