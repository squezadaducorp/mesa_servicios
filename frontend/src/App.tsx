import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import Layout from "./components/Layout";
import CierreInactividad from "./components/CierreInactividad";
import { Cargando } from "./components/Comunes";
import Login from "./pages/Login";
import EntraRetorno from "./pages/EntraRetorno";
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
const Conocimiento = lazy(() => import("./pages/Conocimiento"));
const RespuestasRapidas = lazy(() => import("./pages/admin/RespuestasRapidas"));
const Recurrentes = lazy(() => import("./pages/admin/Recurrentes"));
const ReportesProgramados = lazy(() => import("./pages/admin/ReportesProgramados"));
const Inventario = lazy(() => import("./pages/admin/Inventario"));
const Aprobaciones = lazy(() => import("./pages/tercera/Aprobaciones"));
const ReglasAprobacion = lazy(() => import("./pages/tercera/ReglasAprobacion"));
const AvisosGenerales = lazy(() => import("./pages/tercera/AvisosGenerales"));
const SeguimientoPublico = lazy(() => import("./pages/tercera/SeguimientoPublico"));
const CatalogoServicios = lazy(() => import("./pages/cuarta/Catalogo"));
const ServicioFormulario = lazy(() => import("./pages/cuarta/ServicioFormulario"));
const AdminServicios = lazy(() => import("./pages/cuarta/AdminServicios"));
const Cambios = lazy(() => import("./pages/cuarta/Cambios"));
const CambioNuevo = lazy(() => import("./pages/cuarta/CambioNuevo"));
const CambioDetalle = lazy(() => import("./pages/cuarta/CambioDetalle"));
const Seguridad = lazy(() => import("./pages/cuarta/Seguridad"));
const Cumplimiento = lazy(() => import("./pages/cumplimiento/Cumplimiento"));
const Problemas = lazy(() => import("./pages/ronda4b/Problemas"));
const ProblemaDetalle = lazy(() => import("./pages/ronda4b/ProblemaDetalle"));
const PanelGerencial = lazy(() => import("./pages/ronda4b/PanelGerencial"));
const ControlTiempo = lazy(() => import("./pages/ronda4c/ControlTiempo"));
const Proveedores = lazy(() => import("./pages/ronda4c/Proveedores"));
const SolicitudPublica = lazy(() => import("./pages/SolicitudPublica"));
const EncuestaPublica = lazy(() => import("./pages/EncuestaPublica"));
const ArticuloPublico = lazy(() => import("./pages/ArticuloPublico"));

function Protegida({ children }: { children: ReactNode }) {
  const { usuario, cargando } = useAuth();
  const location = useLocation();
  if (cargando) return <Cargando alto={400} />;
  if (!usuario) return <Navigate to="/login" replace state={{ desde: location.pathname }} />;
  if (usuario.debe_cambiar_clave && location.pathname !== "/cambiar-clave") return <Navigate to="/cambiar-clave" replace state={{ desde: location.pathname }} />;
  return (
    <>
      {children}
      <CierreInactividad />
    </>
  );
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
        <Route path="/auth/entra" element={<EntraRetorno />} />
        <Route path="/solicitud" element={<SolicitudPublica />} />
        <Route path="/encuesta" element={<EncuestaPublica />} />
        <Route path="/ayuda/:id/:llave" element={<ArticuloPublico />} />
        <Route path="/seguimiento" element={<SeguimientoPublico />} />
        <Route path="/seguimiento/:id/:llave" element={<SeguimientoPublico />} />
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
          <Route path="conocimiento" element={<Conocimiento />} />
          <Route path="respuestas" element={<Requiere permisos={[P.VER_TODOS, P.VER_AREA, P.VER_ASIGNADOS]}><RespuestasRapidas /></Requiere>} />
          <Route path="recurrentes" element={<Requiere permisos={[P.RECURRENTES]}><Recurrentes /></Requiere>} />
          <Route path="reportes-correo" element={<Requiere permisos={[P.REPORTES_PROGRAMAR]}><ReportesProgramados /></Requiere>} />
          <Route path="inventario" element={<Requiere permisos={[P.INVENTARIO_VER, P.INVENTARIO]}><Inventario /></Requiere>} />
          <Route path="aprobaciones" element={<Aprobaciones />} />
          <Route path="avisos" element={<Requiere permisos={[P.AVISOS]}><AvisosGenerales /></Requiere>} />
          <Route path="admin/aprobaciones" element={<Requiere permisos={[P.APROBACIONES]}><ReglasAprobacion /></Requiere>} />
          <Route path="catalogo" element={<CatalogoServicios />} />
          <Route path="catalogo/:id" element={<ServicioFormulario />} />
          <Route path="cambios" element={<Cambios />} />
          <Route path="cambios/nuevo" element={<CambioNuevo />} />
          <Route path="cambios/:id" element={<CambioDetalle />} />
          <Route path="cambios/:id/editar" element={<CambioNuevo />} />
          <Route path="seguridad" element={<Seguridad />} />
          <Route path="cumplimiento" element={<Cumplimiento />} />
          <Route path="problemas" element={<Requiere permisos={[P.PROBLEMAS, P.KB, P.PANEL]}><Problemas /></Requiere>} />
          <Route path="problemas/:id" element={<Requiere permisos={[P.PROBLEMAS, P.KB, P.PANEL]}><ProblemaDetalle /></Requiere>} />
          <Route path="panel" element={<Requiere permisos={[P.PANEL]}><PanelGerencial /></Requiere>} />
          <Route path="tiempo" element={<Requiere permisos={[P.TIEMPO]}><ControlTiempo /></Requiere>} />
          <Route path="proveedores" element={<Requiere permisos={[P.PROVEEDORES]}><Proveedores /></Requiere>} />
          <Route path="admin/servicios" element={<Requiere permisos={[P.SERVICIOS]}><AdminServicios /></Requiere>} />
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
