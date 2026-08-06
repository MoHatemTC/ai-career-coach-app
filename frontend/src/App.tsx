import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Navigate, Route, BrowserRouter as Router, Routes } from "react-router-dom";

import { AppLayout } from "@/components/layout/AppLayout";
import { IngestionPage } from "@/pages/IngestionPage";
import { LandingPage } from "@/pages/LandingPage";
import { MatchesPage } from "@/pages/MatchesPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { UploadPage } from "@/pages/UploadPage";
import { SessionProvider } from "@/state/SessionContext";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // The pipeline is expensive and the data is not live; refetching because
      // the user tabbed away and back would fire four model calls for nothing.
      refetchOnWindowFocus: false,
      staleTime: 30_000,
      retry: 1,
    },
  },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <SessionProvider>
        <Router>
          <Routes>
            {/* Public register */}
            <Route path="/" element={<LandingPage />} />

            {/* Product register */}
            <Route path="/app" element={<AppLayout />}>
              <Route index element={<Navigate to="/app/upload" replace />} />
              <Route path="upload" element={<UploadPage />} />
              {/* The conversation moved onto the upload screen. Kept as a
                  redirect so old links and the assistant's own "Chat tab"
                  phrasing still land somewhere real. */}
              <Route path="chat" element={<Navigate to="/app/upload" replace />} />
              <Route path="matches" element={<MatchesPage />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="ingestion" element={<IngestionPage />} />
            </Route>

            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Router>
      </SessionProvider>
    </QueryClientProvider>
  );
}
