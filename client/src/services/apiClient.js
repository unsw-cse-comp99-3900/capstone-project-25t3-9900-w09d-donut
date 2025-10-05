import axios from "axios";

const apiClient = axios.create({
  baseURL: "/api",
  timeout: 15000
});

// TODO: Inject auth tokens and request correlation identifiers
// TODO: Centralize response normalization and error handling here

export default apiClient;
