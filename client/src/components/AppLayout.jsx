import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";

const AppLayout = () => {
  return (
    <div className="app-shell">
      <Sidebar />
      <main className="app-content">
        {/* TODO: Inject global notifications, modals, and loading indicators */}
        <Outlet />
      </main>
    </div>
  );
};

export default AppLayout;
