import { StrictMode, Suspense, lazy } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import App from "./App.jsx";
import "./index.css";

const ReportView = lazy(() => import("./pages/ReportView.jsx"));

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/view/:runId/:companyId" element={<Suspense fallback={null}><ReportView /></Suspense>} />
        <Route path="*" element={<App />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
);
