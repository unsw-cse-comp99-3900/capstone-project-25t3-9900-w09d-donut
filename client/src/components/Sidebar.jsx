import { NavLink } from "react-router-dom";

const Sidebar = () => (
  <aside className="sidebar">
    <h1 className="sidebar__title">Donut Assistant</h1>
    <nav className="sidebar__nav">
      <NavLink to="/">Workspace Setup</NavLink>
      <NavLink to="/plan-review">Plan Review</NavLink>
      <NavLink to="/research-dashboard">Research Dashboard</NavLink>
    </nav>
  </aside>
);

export default Sidebar;
