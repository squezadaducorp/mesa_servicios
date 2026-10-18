# Frontend – Mesa de Servicios ADUCORP

React 19 + TypeScript + Vite + Material UI 9, con la identidad visual de ADUCORP.

## Desarrollo

```bash
npm install
npm run dev          # http://localhost:5173 (proxy /api → http://localhost:8000)
npm run build        # compila a dist/
```

## Estructura

```
src/
  api/          cliente HTTP (JWT + refresh automático), tipos y hooks
  auth/         contexto de sesión y permisos
  components/   layout (menú lateral, notificaciones), chips de estado/SLA, avisos
  pages/        login, tickets, detalle, nuevo ticket con IA, notificaciones, dashboard, indicadores
  pages/admin/  usuarios, roles y permisos, catálogo y clientes, SLA y calendario, auditoría, configuración
```

El menú y las acciones se muestran según los permisos del usuario; la API vuelve a
validarlos en cada solicitud.

## Producción

`docker build -t aducorp-web .` genera una imagen Nginx (puertos 8080 y 8443) que sirve la
aplicación y reenvía `/api` al contenedor `api`.
