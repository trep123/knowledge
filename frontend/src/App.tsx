import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import MainLayout from "./layouts/MainLayout";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import KnowledgeBases from "./pages/KnowledgeBases";
import Documents from "./pages/Documents";
import Retrieval from "./pages/Retrieval";
import Chat from "./pages/Chat";
import ApiKeys from "./pages/ApiKeys";
import ApiUsage from "./pages/ApiUsage";
import { useAuth } from "./store/auth";

function RequireAuth({ children }: { children: JSX.Element }) {
  const token = useAuth((s) => s.token);
  if (!token) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/"
          element={
            <RequireAuth>
              <MainLayout />
            </RequireAuth>
          }
        >
          <Route index element={<Dashboard />} />
          <Route path="kbs" element={<KnowledgeBases />} />
          <Route path="documents" element={<Documents />} />
          <Route path="retrieval" element={<Retrieval />} />
          <Route path="chat" element={<Chat />} />
          <Route path="api-keys" element={<ApiKeys />} />
          <Route path="api-usage" element={<ApiUsage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
