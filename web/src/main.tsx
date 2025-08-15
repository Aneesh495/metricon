import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { WorkbenchBoundary } from "./components/WorkbenchBoundary";
import "./styles.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 10000, retry: 1, refetchOnWindowFocus: false },
    mutations: { retry: false },
  },
});
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <WorkbenchBoundary>
        <App />
      </WorkbenchBoundary>
    </QueryClientProvider>
  </React.StrictMode>,
);
