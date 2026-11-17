# Manual de usuario

La Mesa de Servicios de ADUCORP es el canal único para pedir y atender consultas de clasificación arancelaria, legal aduanero, FedEx, regímenes especiales y trámites aduaneros. Este manual explica cómo usarla según su rol. Lo que ve en pantalla depende de los permisos de su rol.

| Rol | Qué hace en la mesa |
|---|---|
| **Cliente interno** | Crea tickets, sigue su avance, responde cuando le piden información y reabre si la solución no le sirve |
| **Analista** | Atiende los tickets que tiene asignados dentro del plazo (SLA) |
| **Supervisor** | Vigila los tickets de sus categorías, reasigna, escala y revisa los indicadores de su área |
| **Admin Mesa** | Coordina toda la mesa: asigna, controla los SLA y revisa los indicadores |
| **Gerencia** | Consulta el dashboard, los indicadores y las exportaciones (solo lectura) |
| **Super Admin** | Administra el sistema (ver el [manual del administrador](08-manual-administrador.md)) |

## 1. Ingreso

![Inicio de sesión](capturas/01-login.png)

1. Abra la dirección que le indicó TI, por ejemplo `https://mesa.aducorp.com.ec`.
2. Escriba su correo y su contraseña. Si la empresa usa Active Directory, son los mismos de su computadora.
3. La primera vez, o después de que TI le asigne una contraseña temporal, el sistema le pedirá una nueva. Debe tener al menos 10 caracteres, con mayúscula, minúscula, número y símbolo.

Tras 5 intentos fallidos la cuenta se bloquea 15 minutos. Si olvidó su contraseña, pida a TI una contraseña temporal.

La sesión se renueva sola mientras trabaja. Al terminar, use **Cerrar sesión** en el menú de su nombre, sobre todo en equipos compartidos.

## 2. Crear un ticket

![Nuevo ticket con el asistente IA](capturas/04-nuevo-ia.png)

1. Pulse **Nuevo ticket**.
2. Escriba un **asunto** corto y una **descripción** completa: número de DAI o DAE, cliente, mercancía, plazos y lo que necesita.
3. Mientras escribe, el **Asistente IA** propone la categoría y la subcategoría, con su porcentaje de confianza y las palabras que reconoció, además de la prioridad y el responsable. Si la propuesta es correcta, no tiene que hacer nada; si no, pulse otra sugerencia o elija la categoría a mano.
4. Elija el **cliente** si la consulta es de un cliente de ADUCORP y revise la **prioridad**:

| Prioridad | Cuándo usarla | Plazo de solución |
|---|---|---|
| Urgente | Mercancía detenida, aforo en curso, multa o plazo legal que vence hoy | 4 h laborables |
| Alta | Afecta a un embarque o trámite de esta semana | 8 h |
| Media | Consulta normal | 24 h (3 días laborables) |
| Baja | Informativa, sin fecha | 48 h |

5. Adjunte los documentos que ayuden (PDF, Word, Excel, imágenes, XML, ZIP, correos `.msg` o `.eml`, hasta 20 MB cada uno).
6. Pulse **Crear ticket**. Recibirá el número (por ejemplo `ADU-2026-000651`) y el ticket queda asignado de forma automática al responsable de la categoría.

**Antes de enviar, quizá ya tiene solución.** Mientras escribe, a la derecha aparecen artículos de la **Base de conocimiento** parecidos a su problema. Si uno lo resuelve, pulse **Se resolvió, no crear ticket**. Si no, cree el ticket normal: el responsable verá qué artículos ya revisó. La base de conocimiento también está en el menú para consultarla cuando quiera.

**Equipo afectado.** En las categorías de equipos (computadoras, impresoras, tokens…) aparece el campo *Equipo afectado*: elija su equipo para que quede en su historial.

**En nombre de otra persona.** Si un administrador le dio ese permiso, arriba aparece *¿Para quién es este ticket?*. Elija *En nombre de otra persona*, la persona y el motivo. Esa persona recibe un correo avisándole; usted podrá seguir el ticket en solo lectura desde «Tickets en los que participé».

El personal de la mesa ve además los campos **Canal** (portal, correo, teléfono, presencial), para registrar pedidos que llegaron por otra vía, y **Asignar a**, para elegir el responsable. Si deja *Asignar a* vacío, la asignación es automática.

### Avisos generales y aprobaciones

* Si arriba aparece un **aviso general** en rojo (por ejemplo «ECUAPASS no responde»), el equipo ya lo sabe: no hace falta crear un ticket. Pulse **A mí también me afecta** (puede dejar un comentario, como una DAI que vence hoy) y le llegará un correo con cada novedad. Si escribe un ticket con palabras parecidas, el formulario le ofrece vincularlo al aviso o «Solo marcar me afecta».
* Algunas solicitudes (por ejemplo accesos o equipo nuevo) necesitan el visto bueno de su jefe directo: quedan **Por aprobar** y la mesa empieza a atenderlas al aprobarse. Si su jefe la rechaza, verá el motivo en el ticket.
* Si usted es jefe, en el menú aparece **Por aprobar** con las solicitudes de su equipo. También le llega un correo con los botones Aprobar y Rechazar (rechazar pide un comentario).

## 3. Lista de tickets

![Lista de tickets](capturas/02-tickets.png)

* Cada fila muestra el número, el asunto y la categoría, el solicitante y el cliente, la prioridad, el estado, el responsable y la **barra de SLA** con el porcentaje del plazo consumido.
* La barra es verde por debajo del 75 %, amarilla desde el 75 %, naranja desde el 90 % y roja cuando el plazo venció.
* **Filtros:** estado, prioridad, categoría, subcategoría, responsable, cliente, fechas, SLA (cumplido, incumplido, en curso o en riesgo, es decir 75 % o más) y *Solo asignados a mí*. Pulse **Filtros** para mostrarlos.
* **Tickets en los que participé** (analistas y supervisores): botón bajo el buscador que muestra los tickets que usted atendió alguna vez, aunque hoy estén con otro responsable o en otra categoría (por ejemplo, pasaron a LEGAL). Puede abrirlos y ver su historial y comentarios, pero solo el responsable actual puede modificarlos.
* **Pestañas (analistas y supervisores):** *Mis tickets*, *Por vencer hoy* y *Vencidos* (cada una con su número) y *Todos*. *Por vencer hoy* muestra sus tickets que vencen antes de terminar la jornada, el más urgente primero. El correo del resumen diario abre esta pestaña.
* **Vence en:** bajo la barra de SLA, el tiempo laborable que falta para el próximo plazo («Faltan 1 h 35 min», «Vencido hace 20 min»). Si dice *1.ª resp.*, el plazo es el de la primera respuesta. Verde con más de 2 h, ámbar hasta 2 h, naranja en los últimos 30 min y rojo vencido.
* **Orden:** más recientes, más antiguos, mayor consumo de SLA o próximo a vencer.
* Quien tiene permiso de exportar puede descargar la lista filtrada en Excel, PDF o CSV.

En el celular la lista se muestra como tarjetas:

![Tickets en el celular](capturas/07-movil-tickets.png)

## 4. Atender un ticket (Analista, Supervisor y Admin Mesa)

![Detalle del ticket](capturas/03-detalle.png)

El detalle muestra la descripción, los datos del solicitante y del cliente, los plazos de **primera respuesta** y **resolución**, la conversación y el **historial** completo.

**Flujo habitual:**

```mermaid
flowchart LR
    N[Nuevo] --> A[Asignado] --> P[En proceso] --> R[Resuelto] --> C[Cerrado]
    P --> PC[Pendiente cliente] --> P
    P --> E[Escalado] --> P
    R -.reabrir.-> P
```

| Acción | Botón | Efecto |
|---|---|---|
| Empezar a trabajar | **Iniciar atención** | Pasa a *En proceso* y cumple la primera respuesta |
| Pedir información al solicitante | **Cambiar estado** › *Pendiente cliente* | **Pausa el SLA** hasta que el solicitante responda |
| Responder o registrar avance | Caja de comentario | Un comentario público también cumple la primera respuesta |
| Dejar una nota solo para el equipo | Marque **Nota interna** | El solicitante no la ve |
| Adjuntar un documento | **Adjuntar archivo** | Queda en el ticket y en el historial |
| Dar la solución | **Resolver** | Detiene el SLA de resolución |
| Pedir ayuda a su supervisor | **Más acciones › Escalar** | Pasa a *Escalado* con el motivo y avisa al supervisor |
| Cambiar asunto, categoría o prioridad | **Más acciones › Editar** | Si cambia la prioridad, el plazo se recalcula |
| Reasignar (Supervisor, Admin Mesa y el analista responsable del ticket) | **Reasignar** | Avisa al nuevo responsable. El analista que lo traspasa lo sigue viendo en «Tickets en los que participé» |

El ticket resuelto se **cierra solo** después de 72 horas laborables. También puede cerrarse antes desde *Más acciones › Cerrar directamente*.

**Personas en copia.** En el panel **Personas en copia** del ticket, pulse **Editar** para agregar o quitar correos (hasta 10). Esas personas reciben por correo cada respuesta que se envía al solicitante y el aviso de cierre; nunca reciben las notas internas. Pueden venir ya cargadas por la copia automática de la categoría o del cliente, o desde el CC del correo con el que llegó el ticket.

Al escribir una respuesta, el campo **Enviar copia a (opcional)** viene con esas personas. Puede quitar o agregar correos **solo para ese envío**, sin cambiar la lista del ticket. Cada comentario muestra a quién se copió («Copia a: …»). Si alguien en copia contesta el correo, su respuesta entra al ticket como **nota interna** para que el equipo decida.

**Asistente IA en el ticket:**

* **Sugerir respuesta:** propone un borrador a partir de la plantilla de la subcategoría. Revíselo y edítelo antes de enviarlo.
* **Resumir ticket:** resume la conversación, útil en tickets largos o al recibir uno reasignado.
* **Riesgo de incumplimiento:** porcentaje de probabilidad de que el ticket no se cumpla a tiempo (verde por debajo de 40 %, ámbar desde 40 % y rojo desde 70 %), según el plazo consumido, el estado y la carga del responsable.

**Avisos de SLA.** Al 75 % del plazo recibe una notificación y un correo. Al 90 % se avisa a su supervisor y al coordinador. Al 100 % el ticket queda *Incumplido* y se escala solo.

### Avisos antes de vencer

La Mesa avisa al responsable **antes** de que venza el plazo, por la campana y por correo:

* **1.ª respuesta:** si nadie ha respondido y falta 1 hora para el plazo de la primera respuesta.
* **1.er aviso:** cuando faltan 2 horas laborables para resolver.
* **2.º aviso (urgente):** cuando faltan 30 minutos; también avisa al supervisor y al coordinador.
* **Barra roja arriba de la pantalla:** mientras la Mesa está abierta, si uno de sus tickets está en los últimos 30 minutos. Se puede cerrar con la ✕.
* **Resumen diario (08:30):** un correo con sus tickets que vencen hoy. Si no tiene ninguno, no llega.

Los tiempos los define el administrador en *SLA y calendario › Alertas antes de vencer*.

### Mi disponibilidad (vacaciones y permisos)

En el menú de su nombre (arriba a la derecha) › **Mi disponibilidad**:

1. Elija el motivo, desde cuándo y cuándo regresa.
2. Elija el **reemplazo**: la Mesa sugiere a quien atiende sus mismas categorías y tiene menos tickets abiertos.
3. Decida si pasan sus tickets abiertos al reemplazo o solo los nuevos. Con *Ver qué tickets pasan* revisa la lista.
4. Deje marcado *Devolverme los tickets cuando regrese* y *Avisar a los solicitantes*.
5. **Programar ausencia.** Si la fecha de inicio ya llegó, los tickets pasan de inmediato; si es futura, pasan solos ese día.

Mientras está ausente, los tickets nuevos de sus categorías van al reemplazo, y quien lo cubre ve el aviso «Usted cubre a … hasta …». Al regresar, la Mesa le devuelve los tickets que sigan abiertos. Si vuelve antes, use **Volví antes** en el mismo diálogo. Su supervisor y el administrador también pueden registrarle la ausencia desde *Usuarios*.

### Capturas de pantalla en los comentarios

Debajo del cuadro de comentario puede agregar capturas de pantalla o archivos que viajan con ese comentario:

- **Pegar:** copie la captura (por ejemplo con `Win + Shift + S`) y péguela en el cuadro con **Ctrl+V**.
- **Arrastrar** la imagen o el archivo sobre el cuadro, o usar el botón **Captura o archivo**.

Antes de enviar ve las miniaturas y puede quitarlas con la ✕. Puede enviar hasta 10 por comentario, y también puede enviar solo la captura sin texto.
Las capturas se ven dentro del comentario (clic para ampliar y descargar) y además aparecen en la pestaña **Adjuntos**.
Las que van en una **nota interna** solo las ve el equipo de la mesa.

## 5. Seguimiento del solicitante (Cliente interno)

* En **Tickets** ve todos los que creó, con su estado y su avance.
* Cuando un ticket está en **Pendiente cliente**, la mesa espera su respuesta: escríbala en el comentario y adjunte lo que le pidieron. El plazo se reanuda.
* Si la solución no resolvió el problema, use **Reabrir** en un ticket *Resuelto* o *Cerrado* e indique el motivo.
* No ve las notas internas del equipo.
* **Califique la atención:** cuando su ticket queda *Resuelto*, en el detalle aparece «¿Cómo fue la atención?» con 1 a 5 estrellas y un comentario opcional. También le llega un correo con las 5 estrellas: un clic basta, sin iniciar sesión. Al calificar, el ticket se cierra; si el problema sigue, use **Reabrir** en lugar de calificar. Cada ticket se califica una sola vez.

## 6. Dashboard y reportes

![Dashboard ejecutivo](capturas/10-dashboard.png)

El **Dashboard** (Gerencia, Admin Mesa y Supervisores, estos últimos solo con su área) muestra:

* tickets totales, abiertos, cerrados, escalados y vencidos;
* % de cumplimiento del SLA y tiempos promedio de respuesta y resolución, en horas laborables;
* la tendencia por día, semana o mes, y el cumplimiento del SLA por período;
* las categorías y los responsables con más tickets;
* los **tickets en riesgo**: abiertos que pasaron el 75 % del plazo.

Pulse un indicador o una fila para abrir la lista de tickets correspondiente.

En **Indicadores** encontrará los reportes por categoría, por responsable (con ranking), por cliente y el histórico mensual:

![Indicadores por responsable](capturas/12-ind-responsable.png)

**Filtros de período:** últimos 7, 30 o 90 días, 6 meses, el último año o un rango de fechas, más categoría, responsable, cliente, estado y SLA. Los botones **Excel**, **PDF** y **CSV** descargan el reporte con los filtros aplicados.

## 7. Notificaciones

![Notificaciones](capturas/05-notificaciones.png)

La campana de la barra superior muestra cuántas notificaciones tiene sin leer: tickets asignados, comentarios, pedidos de información, escalamientos, resoluciones, cierres, reaperturas y avisos de SLA. En **Notificaciones** puede ver solo las no leídas y abrir el ticket con un clic. Las más importantes también le llegan por correo.

## 8. Preguntas frecuentes

**¿Por qué el plazo no avanza de noche ni el fin de semana?** El SLA cuenta solo horas laborables: de lunes a viernes, de 08:30 a 13:00 y de 14:00 a 17:30, sin feriados.

**El ECUAPASS no funciona y no puedo cumplir el plazo. ¿Qué hago?** Registre lo ocurrido en una nota y pida al coordinador de la mesa una **excepción de SLA**, que puede extender el plazo o excluir el ticket del indicador.

**¿Puedo borrar un comentario o un adjunto?** No. Todo lo que se registra en un ticket queda en el historial para auditoría. Si se equivocó, agregue un comentario aclarándolo.

**No me deja subir un archivo.** Revise que la extensión esté permitida y que no supere 20 MB. El sistema también rechaza los archivos cuyo contenido no coincide con su extensión, como un ejecutable renombrado a `.pdf`.
