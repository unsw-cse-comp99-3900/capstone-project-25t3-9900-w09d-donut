import { createBrowserRouter } from "react-router-dom";
import AppLayout from "./components/AppLayout";
import HomePage from "./pages/HomePage";
import PlanReviewPage from "./pages/PlanReviewPage";
import ResearchDashboard from "./pages/ResearchDashboard";

export const AppRouter = createBrowserRouter([
  {
    path: "/",
    element: <AppLayout />,
    children: [
      { index: true, element: <HomePage /> },
      { path: "plan-review", element: <PlanReviewPage /> },
      { path: "research-dashboard", element: <ResearchDashboard /> }
    ]
  }
]);
