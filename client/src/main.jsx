import React from "react";
import ReactDOM from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import { AppRouter } from "./routes";
import { AppStoreProvider } from "./store";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <AppStoreProvider>
      <RouterProvider router={AppRouter} />
    </AppStoreProvider>
  </React.StrictMode>
);
