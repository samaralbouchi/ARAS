import { useState } from "react";
import api from "../api/axios";

import ScoreCard from "../components/ScoreCard";
import RecommendationList from "../components/RecommendationList";
import ReportViewer from "../components/ReportViewer";


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


      <h1>
        ARAS Assessment Dashboard
      </h1>


      <p className="subtitle">
        Evaluate how ready a website is for AI agents
      </p>



      <div className="card">

        <div className="input-box">


          <input
            type="text"
            placeholder="Enter website URL"
            value={url}
            onChange={(e)=>setUrl(e.target.value)}
          />


          <button onClick={analyze}>

            {loading ? "Analyzing..." : "Analyze"}

          </button>


        </div>

      </div>



      {result && (

        <>


          <div className="card">

            <h2>
              Overall Score
            </h2>


            <div className="score-value">

              {result.overall_score}/100

            </div>


          </div>





          <h2>
            Agent Scores
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