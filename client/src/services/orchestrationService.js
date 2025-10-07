// Centralized orchestrator for client-side service calls
import apiClient from "./apiClient";

export const requestPlan = async (_payload) => {
  // TODO: Replace stub with POST /requests integration
  throw new Error("requestPlan not implemented");
};

export const approvePlan = async (_requestId, _adjustments) => {
  // TODO: Replace stub with PATCH /requests/:id/approval integration
  throw new Error("approvePlan not implemented");
};

export const fetchDraft = async (_requestId) => {
  // TODO: Replace stub with GET /requests/:id/draft integration
  throw new Error("fetchDraft not implemented");
};

export const submitRefinement = async (_requestId, _message) => {
  // TODO: Replace stub with POST /requests/:id/refine integration
  throw new Error("submitRefinement not implemented");
};

export default {
  requestPlan,
  approvePlan,
  fetchDraft,
  submitRefinement
};
