import {
  CircularProgressbar,
  buildStyles,
} from "react-circular-progressbar";

import "react-circular-progressbar/dist/styles.css";

function OverallScore({ score }) {
  let color = "#22c55e";
  let status = "Excellent";

  if (score < 50) {
    color = "#ef4444";
    status = "Needs Improvement";
  } else if (score < 75) {
    color = "#f59e0b";
    status = "Good";
  }

  return (
    <div
      style={{
        width: 230,
        margin: "40px auto",
        textAlign: "center",
      }}
    >
      <CircularProgressbar
        value={score}
        text={`${score.toFixed(0)}%`}
        styles={buildStyles({
          textColor: color,
          pathColor: color,
          trailColor: "#e5e7eb",
        })}
      />

      <h2
        style={{
          marginTop: 25,
        }}
      >
        Overall Readiness
      </h2>

      <p
        style={{
          color,
          fontWeight: "bold",
          fontSize: 20,
        }}
      >
        {status}
      </p>
    </div>
  );
}

export default OverallScore;