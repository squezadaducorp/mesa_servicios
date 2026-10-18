import { useQuery } from "@tanstack/react-query";
import { get } from "./client";
import type { Catalogos } from "./types";

export function useCatalogos() {
  return useQuery({ queryKey: ["catalogos"], queryFn: () => get<Catalogos>("/catalogos"), staleTime: 5 * 60_000 });
}

export function useConteoNotificaciones(habilitado: boolean) {
  return useQuery({
    queryKey: ["notificaciones", "conteo"],
    queryFn: () => get<{ no_leidas: number }>("/notificaciones/conteo"),
    refetchInterval: 30_000,
    enabled: habilitado,
  });
}
