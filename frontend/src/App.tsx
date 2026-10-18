import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import Layout from "./components/Layout";
import { Cargando } from "./components/Comunes";
import Login from "./pages/Login";
import { P } from "./utils/permisos";

const Dashboard = lazy(() => import("./pages/Dashboard"));
const Reportes = lazy(() => import("./pages/Reportes"));
const Tickets = lazy(() => import("./pages/Tickets"));
const TicketNuevo = lazy(() => import("./pages/TicketNuevo"));
const TicketDetalle = lazy(() => import("./pages/TicketDetalle"));
const Notificaciones = lazy(() => import("./pages/Notificaciones"));
const CambiarClave = lazy(() => import("./pages/CambiarClave"));
const Usuarios = lazy(() => import("./pages/admin/Usuarios"));
const Roles = lazy(() => import("./pages/admin/Roles"));
const Catalogo = lazy(() => import("./pages/admin/Catalogo"));
const Sla = lazy(() => import("./pages/admin/Sla"));
const Auditoria = lazy(() => import("./pages/admin/Auditoria"));
const Configuracion = lazy(() => import("./pages/admin/Configuracion"));

function Protegida({ children }: { children: ReactNode }) {
  const { usuario, cargando } = useAuth();
  const location = useLocation();
  if (cargando) return <Cargando alto={400} />;
  if (!usuario) return <Navigate to="/login" replace state={{ desde: location.pathname }} />;
  if (usuario.debe_cambiar_clave && location.pathname !== "/cambiar-clave") return <Navigate to="/cambiar-clave" replace />;
  return <>{children}</>;
}

function Requiere({ permisos, children }: { permisos: string[]; children: ReactNode }) {
  const { puede } = useAuth();
  return puede(...permisos) ? <>{children}</> : <Navigate to="/tickets" replace />;
}

function Inicio() {
  const { puede } = useAuth();
  return <Navigate to={puede(P.DASHBOARD) ? "/dashboard" : "/tickets"} replace />;
}

export default function App() {
  return (
    <Suspense fallback={<Cargando alto={400} />}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          element={
            <Protegida>
              <Layout />
            </Protegida>
          }
        >
          <Route index element={<Inicio />} />
          <Route path="dashboard" element={<Requiere permisos={[P.DASHBOARD]}><Dashboard /></Requiere>} />
          <Route path="reportes" element={<Requiere permisos={[P.REPORTE]}><Reportes /></Requiere>} />
          <Route path="tickets" element={<Tickets />} />
          <Route path="tickets/nuevo" element={<Requiere permisos={[P.CREAR]}><TicketNuevo /></Requiere>} />
          <Route path="tickets/:id" element={<TicketDetalle />} />
          <Route path="notificaciones" element={<Notificaciones />} />
          <Route path="cambiar-clave" element={<CambiarClave />} />
          <Route path="admin/usuarios" element={<Requiere permisos={[P.USUARIOS]}><Usuarios /></Requiere>} />
          <Route path="admin/roles" element={<Requiere permisos={[P.ROLES]}><Roles /></Requiere>} />
          <Route path="admin/catalogo" element={<Requiere permisos={[P.CATALOGO]}><Catalogo /></Requiere>} />
          <Route path="admin/sla" element={<Requiere permisos={[P.SLA]}><Sla /></Requiere>} />
          <Route path="admin/auditoria" element={<Requiere permisos={[P.AUDITORIA]}><Auditoria /></Requiere>} />
          <Route path="admin/configuracion" element={<Requiere permisos={[P.SISTEMA]}><Configuracion /></Requiere>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
