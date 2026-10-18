import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Checkbox, Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Tooltip, Typography } from "@mui/material";
import { get, put } from "../../api/client";
import type { PermisoCat, Rol } from "../../api/types";
import { mensajeError, useAviso } from "../../components/Aviso";
import { Cargando, Encabezado, ErrorCarga } from "../../components/Comunes";

export default function Roles() {
  const qc = useQueryClient();
  const avisar = useAviso();
  const roles = useQuery({ queryKey: ["admin", "roles"], queryFn: () => get<Rol[]>("/admin/roles") });
  const permisos = useQuery({ queryKey: ["admin", "permisos"], queryFn: () => get<PermisoCat[]>("/admin/permisos") });
  const [matriz, setMatriz] = useState<Record<number, Set<string>>>({});
  const [cambiados, setCambiados] = useState<Set<number>>(new Set());

  useEffect(() => {
    if (roles.data) setMatriz(Object.fromEntries(roles.data.map((r) => [r.id, new Set(r.permisos)])));
  }, [roles.data]);

  const guardar = useMutation({
    mutationFn: async () => {
      for (const id of cambiados) await put(`/admin/roles/${id}/permisos`, { permisos: [...matriz[id]] });
    },
    onSuccess: () => {
      setCambiados(new Set());
      qc.invalidateQueries({ queryKey: ["admin", "roles"] });
      avisar("Matriz de permisos actualizada. Los usuarios la reciben al renovar su sesión.");
    },
    onError: (e) => avisar(mensajeError(e), "error"),
  });

  if (roles.isLoading || permisos.isLoading) return <Cargando />;
  if (roles.error || permisos.error) return <ErrorCarga error={roles.error ?? permisos.error} />;

  const alternar = (rolId: number, p: string) => {
    setMatriz((m) => {
      const s = new Set(m[rolId]);
      if (s.has(p)) s.delete(p);
      else s.add(p);
      return { ...m, [rolId]: s };
    });
    setCambiados((c) => new Set(c).add(rolId));
  };

  const modulos = [...new Set(permisos.data!.map((p) => p.modulo))];

  return (
    <>
      <Encabezado
        titulo="Roles y permisos"
        subtitulo="Matriz RBAC: marque qué puede hacer cada rol"
        acciones={
          <Button variant="contained" disabled={!cambiados.size || guardar.isPending} onClick={() => guardar.mutate()}>
            Guardar cambios{cambiados.size ? ` (${cambiados.size})` : ""}
          </Button>
        }
      />
      <Alert severity="info" sx={{ mb: 2 }}>
        El rol Super Administrador conserva todos los permisos. Los cambios quedan registrados en la auditoría.
      </Alert>
      <Paper>
        <TableContainer sx={{ maxHeight: "70vh" }}>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                <TableCell>Permiso</TableCell>
                {roles.data!.map((r) => (
                  <TableCell key={r.id} align="center" sx={{ minWidth: 110 }}>
                    {r.nombre}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {modulos.map((mod) => [
                <TableRow key={mod}>
                  <TableCell colSpan={roles.data!.length + 1} sx={{ bgcolor: "#F1F5FA", fontWeight: 700, textTransform: "uppercase", fontSize: 12 }}>
                    {mod}
                  </TableCell>
                </TableRow>,
                ...permisos.data!
                  .filter((p) => p.modulo === mod)
                  .map((p) => (
                    <TableRow key={p.codigo} hover>
                      <TableCell>
                        <Typography variant="body2">{p.descripcion}</Typography>
                        <Typography variant="caption" sx={{ color: "text.secondary", fontFamily: "monospace" }}>
                          {p.codigo}
                        </Typography>
                      </TableCell>
                      {roles.data!.map((r) => (
                        <TableCell key={r.id} align="center">
                          <Tooltip title={r.codigo === "SUPER_ADMIN" ? "No editable" : ""}>
                            <span>
                              <Checkbox
                                size="small"
                                checked={matriz[r.id]?.has(p.codigo) ?? false}
                                disabled={r.codigo === "SUPER_ADMIN"}
                                onChange={() => alternar(r.id, p.codigo)}
                              />
                            </span>
                          </Tooltip>
                        </TableCell>
                      ))}
                    </TableRow>
                  )),
              ])}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>
    </>
  );
}
