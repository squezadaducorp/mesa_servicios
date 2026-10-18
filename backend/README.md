# Backend – Mesa de Servicios ADUCORP

API REST en **FastAPI + SQLAlchemy 2** sobre **SQL Server 2022**, con Clean Architecture.

```
app/
  domain/          Reglas puras: estados y transiciones, motor SLA en horas laborables
  application/     Casos de uso (servicios), DTOs y errores de negocio
  infrastructure/  ORM, repositorios, correo SMTP, almacenamiento, LDAP/AD, IA
  api/             Routers FastAPI v1, dependencias de seguridad (JWT + RBAC)
  worker.py        Motor SLA, escalamiento 75/90/100 %, cierre automático, cola de correos
scripts/           Generador de datos demo
tests/             Pruebas (pytest)
```

## Ejecutar en desarrollo (SQLite, sin SQL Server)

```bash
pip install -r requirements-dev.txt
python -m app.infrastructure.db.semilla        # crea aducorp_dev.db con datos base
uvicorn app.main:app --reload                   # http://localhost:8000/api/v1/docs
python -m app.worker                            # en otra terminal
pytest                                          # 31 pruebas
```

## Ejecutar contra SQL Server

1. Cree la base con los scripts de `../database` (ver `docs/02-modelo-datos.md`).
2. Copie `.env.example` a `.env` y ajuste `DATABASE_URL`, `JWT_SECRET` y SMTP.
3. `uvicorn app.main:app` y `python -m app.worker`.

Imagen Docker: `docker build -t aducorp-api .` (la misma imagen sirve para la API y, con
`python -m app.worker`, para el worker).

## Swagger

`/api/v1/docs` (Swagger UI) y `/api/v1/redoc`. Inicie sesión con `POST /auth/login`
y pegue el `access_token` en **Authorize**.

Usuarios de prueba (contraseña `Aducorp2026!`, se exige cambio en el primer ingreso en SQL Server):
`admin@`, `mesa.servicios@`, `gerencia@`, `supervisor.tecnico@`, `supervisor.operativo@`,
`david.medina@`, `juan.villamar@`, `denisse.quinga@`, `claudia.vasquez@`, `jorge.caicedo@`,
`debbie.diaz@`, `carlos.torres@`, `maria.andrade@` … todos `@aducorp.com.ec`.

## IA

`AI_PROVIDER=local` (por defecto) clasifica, prioriza, sugiere responsable y respuesta,
resume y calcula riesgo sin salir de la red. `AI_PROVIDER=llm` usa Claude mediante el SDK
oficial de Anthropic (`ANTHROPIC_API_KEY`); el asunto y la descripción del ticket se envían
a la API de Anthropic. Ante cualquier error vuelve automáticamente al motor local.
