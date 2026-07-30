import { downloadReportPDF } from "../utils/pdfGenerator";

function ReportViewer({ report }) {

  if (!report) return null;

  return (
    <div>

      <h2>Assessment Report</h2>

      <button onClick={() => downloadReportPDF(report)}>
        📄 Download PDF
      </button>

    </div>
  );
}

export default ReportViewer;