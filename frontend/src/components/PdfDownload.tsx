type PdfDownloadProps = {
  runId: string
}

function PdfDownload({ runId }: PdfDownloadProps) {
  return (
    <a
      className="pdf-download"
      href={`/api/reports/${encodeURIComponent(runId)}/report.pdf`}
      download={`research-report-${runId}.pdf`}
    >
      <span aria-hidden="true">↓</span> Save as PDF
    </a>
  )
}

export default PdfDownload
