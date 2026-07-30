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
            <h3>{rec.category}</h3>

            <p>
              <strong>Issue:</strong> {rec.issue}
            </p>

            <p>
              <strong>Recommendation:</strong> {rec.recommendation}
            </p>

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
          </div>
        );
      })}
    </div>
  );
}

export default RecommendationList;