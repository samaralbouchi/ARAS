import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";


export function downloadReportPDF(result) {

  const doc = new jsPDF();

  const pageWidth = doc.internal.pageSize.getWidth();


  // ===============================
  // HEADER
  // ===============================

  doc.setFillColor(37,99,235);
  doc.rect(0,0,pageWidth,35,"F");

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


  doc.setTextColor(0,0,0);


  let y = 50;



  // ===============================
  // WEBSITE
  // ===============================

  doc.setFontSize(16);
  doc.setFont("helvetica","bold");

  doc.text(
    "Website",
    14,
    y
  );


  y += 8;

  doc.setFontSize(12);
  doc.setFont("helvetica","normal");

  doc.text(
    result.report?.url || result.url || "",
    14,
    y
  );


  y += 15;



  // ===============================
  // SCORE
  // ===============================


  doc.setFontSize(16);
  doc.setFont("helvetica","bold");

  doc.text(
    "Overall Readiness Score",
    14,
    y
  );


  doc.setFontSize(22);
  doc.setTextColor(37,99,235);

  doc.text(
    `${result.overall_score}/100`,
    150,
    y
  );


  doc.setTextColor(0,0,0);

  y += 20;



  // ===============================
  // CATEGORY SCORES
  // ===============================


  doc.setFontSize(16);
  doc.setFont("helvetica","bold");

  doc.text(
    "Category Scores",
    14,
    y
  );


  y += 5;


  autoTable(doc, {

    startY:y,

    head:[
      [
        "Category",
        "Score"
      ]
    ],


    body:[

      [
        "Discoverability",
        result.discoverability?.score?.toFixed(1) || "-"
      ],

      [
        "Comprehension",
        result.comprehension?.score?.toFixed(1) || "-"
      ],

      [
        "Interaction",
        result.interaction?.score?.toFixed(1) || "-"
      ],

      [
        "Security",
        result.security?.score?.toFixed(1) || "-"
      ]

    ]

  });



  y = doc.lastAutoTable.finalY + 15;



  // ===============================
  // RECOMMENDATIONS + RAG
  // ===============================


  doc.setFontSize(18);
  doc.setFont("helvetica","bold");

  doc.text(
    "Recommendations",
    14,
    y
  );


  y += 10;



  result.recommendations?.forEach((rec,index)=>{


    if(y > 250){

      doc.addPage();
      y = 20;

    }



    doc.setFontSize(12);
    doc.setFont("helvetica","bold");


    doc.text(
      `${index+1}. ${rec.category}`,
      18,
      y
    );


    y += 7;



    doc.setFontSize(10);
    doc.setFont("helvetica","normal");


    doc.text(
      `Priority: ${rec.priority}`,
      18,
      y
    );


    y += 6;



    // ISSUE

    const issue = doc.splitTextToSize(
      `Issue: ${rec.issue}`,
      170
    );


    doc.text(
      issue,
      18,
      y
    );


    y += issue.length * 5 + 5;



    // RECOMMENDATION

    const recommendation = doc.splitTextToSize(
      `Recommendation: ${rec.recommendation}`,
      170
    );


    doc.text(
      recommendation,
      18,
      y
    );


    y += recommendation.length * 5 + 5;



    // ===============================
// HOW TO APPLY
// ===============================


if(rec.how_to_apply){


  const howText = Array.isArray(rec.how_to_apply)
    ? rec.how_to_apply.join("\n")
    : rec.how_to_apply;


  const howToApply = doc.splitTextToSize(
    `How to apply:\n${howText}`,
     170
  );


  if(y + howToApply.length * 5 > 270){

    doc.addPage();
    y = 20;

  }


  doc.setFont(
    "helvetica",
    "normal"
  );


  doc.text(
    howToApply,
    18,
    y
  );


  y += howToApply.length * 5 + 5;

}


// ===============================
// SOURCES
// ===============================


if(rec.sources && rec.sources.length > 0){


  const sources = doc.splitTextToSize(
    `Sources:\n${rec.sources.join(", ")}`,
    170
  );


  if(y + sources.length * 5 > 270){

    doc.addPage();
    y = 20;

  }


  doc.text(
    sources,
    18,
    y
  );


  y += sources.length * 5 + 10;

}





    // ===============================
    // RAG CONTEXT
    // ===============================


    if(rec.rag_context){


      const rag = doc.splitTextToSize(
        `RAG Context:\n${rec.rag_context}`,
        165
      );


      if(y + rag.length * 4 > 270){

        doc.addPage();
        y = 20;

      }


      doc.setFont(
        "helvetica",
        "italic"
      );

      doc.setFontSize(9);


      doc.text(
        rag,
        18,
        y
      );


      y += rag.length * 4 + 10;


      doc.setFont(
        "helvetica",
        "normal"
      );

    }


  });



  // ===============================
  // FOOTER
  // ===============================


  const pageCount = doc.internal.getNumberOfPages();


  for(let i = 1; i <= pageCount; i++){


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



  doc.save(
    "ARAF_Assessment_Report.pdf"
  );

}