function RecommendationList({ recommendations }) {
  if (!recommendations || recommendations.length === 0) {
    return (
      <div>
        <h2>Recommendations</h2>
        <p>No recommendations 🎉</p>
      </div>
    );
  }

  return (
    <div>
      <h2>Recommendations</h2>

      {recommendations.map((rec, index) => {
        console.log(rec.how_to_apply);
        console.log(typeof rec.how_to_apply);
        
        let color = "#3b82f6";

        if (rec.priority === "critical") color = "#ef4444";
        else if (rec.priority === "high") color = "#f59e0b";
        else if (rec.priority === "medium") color = "#22c55e";

        return (
          <div
            key={index}
            style={{
              background: "white",
              padding: "20px",
              marginBottom: "15px",
              borderRadius: "10px",
              boxShadow: "0 2px 10px rgba(0,0,0,0.08)",
              borderLeft: `6px solid ${color}`,
            }}
          >

            {/* CATEGORY */}
            <h3>
              {rec.category}
            </h3>


            {/* PRIORITY */}
            <span
              style={{
                background: color,
                color: "white",
                padding: "5px 10px",
                borderRadius: "5px",
                fontSize: "14px",
              }}
            >
              {rec.priority.toUpperCase()}
            </span>


            {/* ISSUE */}
            <p style={{marginTop:"15px"}}>
              <strong>Issue:</strong> {rec.issue}
            </p>


            {/* RECOMMENDATION */}
            <p>
              <strong>Recommendation:</strong> {rec.recommendation}
            </p>



            {/* HOW TO APPLY */}
            {rec.how_to_apply && (
              <div
                style={{
                  marginTop: "15px",
                  padding: "15px",
                  background: "#f0fdf4",
                  borderRadius: "8px",
                  border: "1px solid #bbf7d0",
                }}
              >

                <h4>
                  How to apply
                </h4>

                <ul>
                  {Array.isArray(rec.how_to_apply)
                    ? rec.how_to_apply.map((step, i) => (
                        <li key={i}>
                          {step}
                        </li>
                      ))
                    : (
                        <li>
                          {rec.how_to_apply}
                        </li>
                      )
                  }
                </ul>

              </div>
            )}



            {/* SOURCES */}
            {rec.rag_sources && rec.rag_sources.length > 0 && (
              <div
                style={{
                  marginTop: "15px",
                  padding: "15px",
                  background: "#eff6ff",
                  borderRadius: "8px",
                  border: "1px solid #bfdbfe",
                }}
              >

                <h4>
                  Sources
                </h4>


                <ul>
                  {rec.rag_sources.map((source, i) => (
                    <li key={i}>
                      <strong>{source.source}</strong>
                      {" - "}
                      {source.source_type}
                    </li>
                  ))}
                </ul>

              </div>
            )}


          </div>
        );
      })}

    </div>
  );
}


export default RecommendationList;