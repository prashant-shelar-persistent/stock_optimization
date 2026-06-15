import { Routes, Route } from "react-router-dom";
import { Toaster } from "@/components/ui/toaster";
import DashboardPage from "@/pages/DashboardPage";
import HistoryPage from "@/pages/HistoryPage";
import RunDetailPage from "@/pages/RunDetailPage";
import NotFoundPage from "@/pages/NotFoundPage";

/**
 * Root application component.
 *
 * Defines top-level routes:
 *   /              → DashboardPage  (constraint form + real-time results)
 *   /history       → HistoryPage    (past optimization runs)
 *   /run/:runId    → RunDetailPage  (full detail for a single run)
 *   *              → NotFoundPage
 */
export default function App() {
  return (
    <>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/run/:runId" element={<RunDetailPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
      <Toaster />
    </>
  );
}
