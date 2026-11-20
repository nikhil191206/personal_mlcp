import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { GlobalWorkerOptions, getDocument } from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { api } from "../api.js";
import { download, safeUrl } from "../lib.js";

GlobalWorkerOptions.workerSrc = workerUrl;

/**
 * One company's one-page report, shown in its own browser tab. Browser PDF viewers open a link in the same
 * tab and ignore any "new tab" setting in the file, so the page is drawn here with pdf.js and every source
 * link is a normal <a target="_blank"> placed over it: clicking a source opens a new tab and the report stays.
 */
export default function ReportView() {
  const { runId, companyId } = useParams();
  const holder = useRef(null);
  const [blob, setBlob] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const pdfBlob = await api.companyReport(runId, companyId, "pdf");
        if (cancelled) return;
        setBlob(pdfBlob);
        const pdf = await getDocument({ data: new Uint8Array(await pdfBlob.arrayBuffer()) }).promise;
        const page = await pdf.getPage(1);
        const width = Math.min(holder.current.clientWidth || 1200, 1400);
        const viewport = page.getViewport({ scale: width / page.getViewport({ scale: 1 }).width });
        const ratio = window.devicePixelRatio || 1;

        const sheet = document.createElement("div");
        sheet.className = "report-sheet";
        sheet.style.width = `${viewport.width}px`;
        sheet.style.height = `${viewport.height}px`;
        const canvas = document.createElement("canvas");
        canvas.width = Math.floor(viewport.width * ratio);
        canvas.height = Math.floor(viewport.height * ratio);
        canvas.style.width = `${viewport.width}px`;
        canvas.style.height = `${viewport.height}px`;
        sheet.appendChild(canvas);
        await page.render({ canvas, canvasContext: canvas.getContext("2d"), viewport,
          transform: ratio === 1 ? null : [ratio, 0, 0, ratio, 0, 0] }).promise;

        for (const a of await page.getAnnotations()) {
          const url = a.subtype === "Link" ? safeUrl(a.url) : null;
          if (!url) continue;
          const [x1, y1, x2, y2] = viewport.convertToViewportRectangle(a.rect);
          const link = Object.assign(document.createElement("a"), { href: url, target: "_blank", rel: "noopener noreferrer", title: url });
          Object.assign(link.style, { left: `${Math.min(x1, x2)}px`, top: `${Math.min(y1, y2)}px`,
            width: `${Math.abs(x2 - x1)}px`, height: `${Math.abs(y2 - y1)}px` });
          sheet.appendChild(link);
        }
        if (!cancelled) holder.current.replaceChildren(sheet);
      } catch (e) {
        if (!cancelled) setError(e);
      }
    })();
    return () => { cancelled = true; };
  }, [runId, companyId]);

  return (
    <div className="report-view">
      <div className="report-view-bar">
        <span>{companyId} · run {runId} · source links open in a new tab</span>
        {blob && <button className="btn btn-sm btn-secondary" onClick={() => download(blob, `${companyId}_${runId}.pdf`)}>Download PDF</button>}
      </div>
      {error && <div className="banner error" role="alert">{error.message}{error.detail && <div className="detail">{error.detail}</div>}</div>}
      <div ref={holder} className="report-view-page">{!error && "Building the report..."}</div>
    </div>
  );
}
