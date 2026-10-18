"""Limitador de intentos en memoria (ventana deslizante) para endpoints sensibles como el login.

Es por proceso: con varios workers el límite efectivo se multiplica. Nginx aplica además
`limit_req` sobre /api/v1/auth/ (ver frontend/nginx.conf).
"""
import threading
import time
from collections import defaultdict, deque


class Limitador:
    def __init__(self, maximo: int, ventana_seg: int = 60):
        self.maximo, self.ventana = maximo, ventana_seg
        self._eventos: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def permitir(self, clave: str) -> bool:
        ahora = time.monotonic()
        with self._lock:
            q = self._eventos[clave]
            while q and ahora - q[0] > self.ventana:
                q.popleft()
            if len(q) >= self.maximo:
                return False
            q.append(ahora)
            if len(self._eventos) > 10000:   # evita crecimiento ilimitado
                for k in [k for k, v in self._eventos.items() if not v]:
                    del self._eventos[k]
            return True

    def reiniciar(self) -> None:
        with self._lock:
            self._eventos.clear()
