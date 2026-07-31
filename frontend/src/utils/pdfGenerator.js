import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";

export function downloadReportPDF(result) {
const doc = new jsPDF();

const pageWidth = doc.internal.pageSize.getWidth();


// ===== HEADER =====

doc.setFillColor(37, 99, 235);

doc.rect(0, 0, pageWidth, 35, "F");

doc.setTextColor(255,255,255);

doc.setFontSize(24);

doc.setFont("helvetica","bold");

doc.text("ARAF",14,18);

doc.setFontSize(11);

doc.setFont("helvetica","normal");

doc.text(
"Agentic Readiness Assessment Framework",
14,
27
);


// Retour au noir

doc.setTextColor(0,0,0);

let y = 50;


// ===== WEBSITE =====

doc.setFontSize(16);

doc.setFont("helvetica","bold");

doc.text("Website",14,y);

doc.setFont("helvetica","normal");

doc.setFontSize(12);

y+=8;

doc.text(
result.report?.url || result.url,
14,
y
);

y+=12;


// ===== DATE =====

doc.setFont("helvetica","bold");

doc.setFontSize(16);

doc.text(
"Assessment Date",
14,
y
);

doc.setFont("helvetica","normal");

doc.setFontSize(12);

y+=8;

doc.text(
result.report?.generated_at || new Date().toLocaleString(),
14,
y
);

y+=15;


// ===== SCORE =====

doc.setFillColor(240,245,255);

doc.roundedRect(
14,
y,
180,
28,
3,
3,
"F"
);

doc.setFontSize(14);

doc.setFont("helvetica","bold");

doc.text(
"Overall Readiness Score",
20,
y+10
);

doc.setFontSize(24);

doc.setTextColor(37,99,235);

doc.text(
`${result.overall_score}/100`,
150,
y+17
);

doc.setTextColor(0,0,0);

y+=40;

  // Scores des agents
  doc.setFontSize(15);
  doc.text("Category Scores", 14, y);

  y += 5;

  autoTable(doc, {
    startY: y,

    head: [["Category", "Score", "Status"]],

    body: [
        [
        "Discoverability",
        result.discoverability?.score.toFixed(1),
        result.discoverability?.score >= 75
            ? "Excellent"
            : result.discoverability?.score >= 50
            ? "Good"
            : "Needs Improvement",
        ],

        [
        "Comprehension",
        result.comprehension?.score.toFixed(1),
        result.comprehension?.score >= 75
            ? "Excellent"
            : result.comprehension?.score >= 50
            ? "Good"
            : "Needs Improvement",
        ],

        [
        "Interaction",
        result.interaction?.score.toFixed(1),
        result.interaction?.score >= 75
            ? "Excellent"
            : result.interaction?.score >= 50
            ? "Good"
            : "Needs Improvement",
        ],

        [
        "Security",
        result.security?.score.toFixed(1),
        result.security?.score >= 75
            ? "Excellent"
            : result.security?.score >= 50
            ? "Good"
            : "Needs Improvement",
        ],
    ],

    headStyles: {
        fillColor: [37, 99, 235],
        textColor: [255, 255, 255],
        fontStyle: "bold",
        halign: "center",
    },

    bodyStyles: {
        halign: "center",
        fontSize: 11,
    },

    alternateRowStyles: {
        fillColor: [245, 247, 250],
    },

    styles: {
        cellPadding: 4,
        lineColor: [220, 220, 220],
        lineWidth: 0.1,
    },
  });


  y = doc.lastAutoTable.finalY + 15;


// ===============================
// RECOMMENDATIONS
// ===============================

doc.setFont("helvetica", "bold");
doc.setFontSize(18);
doc.text("Recommendations", 14, y);

y += 10;

result.recommendations?.forEach((rec, index) => {

  if (y > 240) {
    doc.addPage();
    y = 20;
  }

  // Fond gris clair
  doc.setFillColor(248, 250, 252);
  doc.roundedRect(14, y, 182, 30, 3, 3, "F");

  // Titre
  doc.setFont("helvetica", "bold");
  doc.setFontSize(12);

  doc.text(
    `${index + 1}. ${rec.category}`,
    18,
    y + 8
  );

  // Issue
  doc.setFont("helvetica", "normal");
  doc.setFontSize(10);

  const issue = doc.splitTextToSize(
    `Issue: ${rec.issue}`,
    165
  );

  doc.text(
    issue,
    18,
    y + 15
  );

  // Recommendation
  const recommendation = doc.splitTextToSize(
    `Recommendation: ${rec.recommendation}`,
    165
  );

  doc.text(
    recommendation,
    18,
    y + 22 + issue.length * 5
  );

  y +=
    35 +
    issue.length * 5 +
    recommendation.length * 5;

});

// ===============================
// CONCLUSION
// ===============================

if (y > 220) {
  doc.addPage();
  y = 20;
}

doc.setFillColor(235, 245, 255);
doc.roundedRect(14, y, 182, 55, 3, 3, "F");

doc.setFont("helvetica", "bold");
doc.setFontSize(18);

doc.text("Conclusion", 20, y + 12);

doc.setFont("helvetica", "normal");
doc.setFontSize(11);

let conclusion = "";

if (result.overall_score >= 85) {

  conclusion =
    "The website demonstrates an excellent level of readiness for AI agents and the Agentic Web. Only minor improvements are recommended to further enhance discoverability, interoperability and security.";

} else if (result.overall_score >= 60) {

  conclusion =
    "The website shows a good level of readiness but several improvements are recommended. Addressing the identified issues will significantly improve compatibility with AI agents.";

} else {

  conclusion =
    "The website currently presents a low level of readiness for AI agents. Several critical improvements are recommended to increase discoverability, comprehension, interaction capabilities and security.";

}

const text = doc.splitTextToSize(
  conclusion,
  170
);

doc.text(
  text,
  20,
  y + 24
);


// ===============================
// FOOTER
// ===============================

const pageCount = doc.internal.getNumberOfPages();

for (let i = 1; i <= pageCount; i++) {

  doc.setPage(i);

  doc.setFontSize(9);

  doc.setTextColor(120);

  doc.text(
    "ARAF - Agentic Readiness Assessment Framework",
    14,
    285
  );

  doc.text(
    `Page ${i}/${pageCount}`,
    170,
    285
  );

}

  // Sauvegarde
  doc.save("ARAF_Assessment_Report.pdf");
}