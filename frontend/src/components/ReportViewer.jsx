import { downloadReportPDF } from "../utils/pdfGenerator";

function ReportViewer({ report }) {

  if (!report) return null;

  return (
    <div className="report-viewer">

      <h2>
        Assessment Report
      </h2>


      <button
        className="pdf-button"
        onClick={() => downloadReportPDF(report)}
      >
        📄 Download PDF Report
      </button>


    </div>
  );
}

export default ReportViewer;