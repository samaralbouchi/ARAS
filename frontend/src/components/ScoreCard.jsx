function ScoreCard({ title, score }) {
  let color = "#22c55e";

  if (score < 50) {
    color = "#ef4444";
  } else if (score < 75) {
    color = "#f59e0b";
  }

  return (
    <div className="score-card">
      <h3>{title}</h3>

      <h1 style={{ color }}>
        {score.toFixed(1)}
      </h1>

      <p>/100</p>
    </div>
  );
}

export default ScoreCard;