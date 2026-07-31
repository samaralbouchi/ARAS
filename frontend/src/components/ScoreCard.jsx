function ScoreCard({ title, score }) {
  let color = "#22c55e";
  let status = "Excellent";
  let icon = "✅";

  if (score < 50) {
    color = "#ef4444";
    status = "Needs Improvement";
    icon = "❌";
  } else if (score < 75) {
    color = "#f59e0b";
    status = "Good";
    icon = "⚠️";
  }

  switch (title) {
    case "Discoverability":
      icon = "🛰️";
      break;

    case "Comprehension":
      icon = "🧠";
      break;

    case "Interaction":
      icon = "🔗";
      break;

    case "Security":
      icon = "🛡️";
      break;

    default:
      break;
  }

  return (
    <div
      className="score-card"
      style={{
        borderTop: `6px solid ${color}`,
      }}
    >
      <div className="score-icon">
        {icon}
      </div>

      <h3>{title}</h3>

      <div
        className="score-number"
        style={{ color }}
      >
        {score.toFixed(1)}
      </div>

      <p className="score-status">
        {status}
      </p>
    </div>
  );
}

export default ScoreCard;