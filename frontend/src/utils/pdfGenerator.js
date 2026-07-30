import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";

export function downloadReportPDF(result) {
  const doc = new jsPDF();

  let y = 20;

  // Titre
  doc.setFontSize(20);
  doc.text(
    "Agentic Readiness Assessment Report",
    14,
    y
  );

  y += 15;

  doc.setFontSize(12);

  // Informations générales
  doc.text(
    `Website: ${result.report?.url || result.url}`,
    14,
    y
  );

  y += 8;

  doc.text(
    `Generated at: ${result.report?.generated_at || ""}`,
    14,
    y
  );

  y += 8;

  doc.text(
    `Overall Score: ${result.overall_score}/100`,
    14,
    y
  );

  y += 15;


  // Scores des agents
  doc.setFontSize(15);
  doc.text("Category Scores", 14, y);

  y += 5;

  autoTable(doc, {
    startY: y,
    head: [
      ["Agent", "Score"]
    ],
    body: [
      [
        "Discoverability",
        result.discoverability?.score || 0
      ],
      [
        "Comprehension",
        result.comprehension?.score || 0
      ],
      [
        "Interaction",
        result.interaction?.score || 0
      ],
      [
        "Security",
        result.security?.score || 0
      ],
    ],
  });


  y = doc.lastAutoTable.finalY + 15;


  // Recommandations
  doc.setFontSize(15);
  doc.text(
    "Recommendations",
    14,
    y
  );

  y += 8;

  result.recommendations?.forEach((rec, index) => {

    if (y > 270) {
      doc.addPage();
      y = 20;
    }

    doc.setFontSize(11);

    doc.text(
      `${index + 1}. ${rec.category}`,
      14,
      y
    );

    y += 6;

    doc.text(
      `Issue: ${rec.issue}`,
      18,
      y
    );

    y += 6;


    const text = doc.splitTextToSize(
      `Recommendation: ${rec.recommendation}`,
      170
    );

    doc.text(
      text,
      18,
      y
    );

    y += text.length * 6 + 8;

  });


  // Sauvegarde
  doc.save("ARAF_Assessment_Report.pdf");
}