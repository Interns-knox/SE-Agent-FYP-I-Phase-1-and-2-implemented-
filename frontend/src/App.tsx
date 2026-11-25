import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import { DashboardPage } from "./pages/DashboardPage";
import { CreateProjectPage } from "./pages/CreateProjectPage";
import { WorkspacePage } from "./pages/WorkspacePage";
import { RequirementsPage } from "./pages/RequirementsPage";
import { SrsPage } from "./pages/SrsPage";
import { ArchitecturePage } from "./pages/ArchitecturePage";
import { UmlPage } from "./pages/UmlPage";
import "./App.css";

function NotFoundPage() {
  return (
    <div className="page notfound">
      <h1 className="page__title">Page not found</h1>
      <p className="page__subtitle">
        The page you are looking for does not exist.
      </p>
      <p>
        <Link to="/" className="page__back">
          ← Back to dashboard
        </Link>
      </p>
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/projects/new" element={<CreateProjectPage />} />
        <Route path="/projects/:id" element={<WorkspacePage />} />
        <Route path="/projects/:id/requirements" element={<RequirementsPage />} />
        <Route path="/projects/:id/srs" element={<SrsPage />} />
        <Route path="/projects/:id/architecture" element={<ArchitecturePage />} />
        <Route path="/projects/:id/uml" element={<UmlPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
