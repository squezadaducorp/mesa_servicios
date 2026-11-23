"""Servicios iniciales del catálogo (maqueta 26). La migración 14 los carga una sola vez; luego se editan en
Administración › Catálogo de servicios. Las tareas sin responsable quedan con el responsable del ticket."""

CATEGORIA = {"codigo": "SERVICIOS_TI", "nombre": "Servicios de TI",
             "descripcion": "Solicitudes del catálogo de servicios: accesos, equipos, altas y bajas de personal",
             "subcategorias": ["Accesos", "Equipos", "Personal", "Aduanas"],
             "palabras": "acceso,usuario nuevo,alta,baja,equipo,portátil,laptop,impresora,vpn,carpeta,buzón,token,firma electrónica"}

SUCURSALES = ["Guayaquil · Matriz", "Guayaquil · Puerto Marítimo", "Quito · Aeropuerto", "Manta"]

SERVICIOS = [
    {
        "nombre": "Alta de usuario nuevo", "icono": "alta", "grupo": "Personal", "sub": "Personal", "plazo_horas": 16,
        "requiere_aprobacion": True, "lo_pide": "Talento Humano",
        "descripcion": "Correo, equipo, carpetas y accesos para quien ingresa a la empresa.",
        "titulo_campos": "Datos de la persona que ingresa", "titulo_opciones": "¿Qué necesita para trabajar?",
        "campos": [
            {"clave": "nombres", "etiqueta": "Nombres y apellidos", "tipo": "texto", "ancho": 2},
            {"clave": "cedula", "etiqueta": "Cédula", "tipo": "cedula", "ancho": 1},
            {"clave": "fecha_ingreso", "etiqueta": "Fecha de ingreso", "tipo": "fecha", "ancho": 1},
            {"clave": "area", "etiqueta": "Área", "tipo": "area", "ancho": 2},
            {"clave": "cargo", "etiqueta": "Cargo", "tipo": "texto", "ancho": 2},
            {"clave": "jefe", "etiqueta": "Jefe directo", "tipo": "usuario", "ancho": 2, "aprobador": True},
            {"clave": "sucursal", "etiqueta": "Sucursal", "tipo": "lista", "ancho": 2, "opciones": SUCURSALES},
        ],
        "opciones": [
            {"clave": "correo", "etiqueta": "Correo @aducorp.com.ec", "tarea": "Crear correo y licencia M365", "marcado": True},
            {"clave": "portatil", "etiqueta": "Portátil", "tarea": "Preparar portátil e imagen", "marcado": True},
            {"clave": "ecuapass", "etiqueta": "Usuario en ECUAPASS (perfil liquidador)", "tarea": "Alta en ECUAPASS · perfil liquidador",
             "aviso": "ECUAPASS requiere que la persona esté registrada como auxiliar del agente en SENAE. TI le enviará el formulario a firmar."},
            {"clave": "carpeta", "etiqueta": "Carpeta Importaciones 2026", "tarea": "Permiso carpeta Importaciones 2026", "marcado": True},
            {"clave": "contable", "etiqueta": "Sistema contable (consulta)", "tarea": "Usuario de consulta en el sistema contable"},
            {"clave": "vpn", "etiqueta": "VPN para teletrabajo", "tarea": "Configurar VPN"},
            {"clave": "token", "etiqueta": "Token de firma electrónica", "tarea": "Tramitar token de firma electrónica"},
            {"clave": "extension", "etiqueta": "Extensión telefónica", "tarea": "Extensión telefónica", "marcado": True},
            {"clave": "buzon_operaciones", "etiqueta": "Buzón operaciones@", "tarea": "Acceso a buzón operaciones@"},
        ],
    },
    {
        "nombre": "Acceso a ECUAPASS", "icono": "llave", "grupo": "Aduanas", "sub": "Aduanas", "plazo_horas": 8,
        "requiere_aprobacion": True, "lo_pide": "Operaciones",
        "descripcion": "Alta, cambio de perfil o renovación del usuario del agente en el portal de SENAE.",
        "titulo_campos": "Datos del usuario", "titulo_opciones": "¿Qué necesita?",
        "aviso": "ECUAPASS requiere que la persona esté registrada como auxiliar del agente en SENAE.",
        "campos": [
            {"clave": "persona", "etiqueta": "Persona", "tipo": "usuario", "ancho": 2},
            {"clave": "cedula", "etiqueta": "Cédula", "tipo": "cedula", "ancho": 1},
            {"clave": "perfil", "etiqueta": "Perfil", "tipo": "lista", "ancho": 1, "opciones": ["Liquidador", "Tramitador", "Consulta"]},
        ],
        "opciones": [
            {"clave": "alta", "etiqueta": "Alta de usuario", "tarea": "Alta en ECUAPASS", "marcado": True},
            {"clave": "perfil", "etiqueta": "Cambio de perfil", "tarea": "Cambio de perfil en ECUAPASS"},
            {"clave": "renovacion", "etiqueta": "Renovación", "tarea": "Renovación del usuario ECUAPASS"},
        ],
    },
    {
        "nombre": "Token de firma electrónica", "icono": "token", "grupo": "Aduanas", "sub": "Aduanas", "plazo_horas": 24,
        "requiere_aprobacion": True, "lo_pide": "Operaciones",
        "descripcion": "Emisión o renovación del certificado (Security Data / BCE) para firmar DAI.",
        "titulo_campos": "Datos del titular",
        "campos": [
            {"clave": "titular", "etiqueta": "Titular", "tipo": "usuario", "ancho": 2},
            {"clave": "cedula", "etiqueta": "Cédula", "tipo": "cedula", "ancho": 1},
            {"clave": "tramite", "etiqueta": "Trámite", "tipo": "lista", "ancho": 1, "opciones": ["Emisión", "Renovación"]},
            {"clave": "entidad", "etiqueta": "Entidad", "tipo": "lista", "ancho": 2, "opciones": ["Security Data", "Banco Central (BCE)"]},
        ],
        "opciones": [{"clave": "tramitar", "etiqueta": "Tramitar el certificado", "tarea": "Tramitar token de firma electrónica", "siempre": True}],
    },
    {
        "nombre": "Equipo nuevo o reemplazo", "icono": "equipo", "grupo": "Equipos", "sub": "Equipos", "plazo_horas": 40,
        "requiere_aprobacion": True, "lo_pide": None,
        "descripcion": "Portátil, monitor, impresora o periférico, con entrega y acta.",
        "titulo_campos": "¿Para quién y por qué?", "titulo_opciones": "¿Qué equipo necesita?",
        "campos": [
            {"clave": "para", "etiqueta": "Para", "tipo": "usuario", "ancho": 2},
            {"clave": "motivo", "etiqueta": "Motivo", "tipo": "lista", "ancho": 2, "opciones": ["Equipo nuevo", "Reemplazo por daño", "Reemplazo por antigüedad"]},
        ],
        "opciones": [
            {"clave": "portatil", "etiqueta": "Portátil", "tarea": "Preparar portátil e imagen"},
            {"clave": "monitor", "etiqueta": "Monitor", "tarea": "Entregar monitor"},
            {"clave": "impresora", "etiqueta": "Impresora", "tarea": "Instalar impresora"},
            {"clave": "periferico", "etiqueta": "Teclado, mouse u otro periférico", "tarea": "Entregar periférico"},
            {"clave": "acta", "etiqueta": "Acta de entrega", "tarea": "Firmar acta de entrega", "siempre": True},
        ],
    },
    {
        "nombre": "Acceso a carpeta compartida", "icono": "carpeta", "grupo": "Accesos", "sub": "Accesos", "plazo_horas": 4,
        "requiere_aprobacion": True, "lo_pide": None,
        "descripcion": "Lectura o escritura en carpetas del servidor de archivos (p. ej. Importaciones 2026).",
        "campos": [
            {"clave": "carpeta", "etiqueta": "Carpeta", "tipo": "texto", "ancho": 2},
            {"clave": "permiso", "etiqueta": "Permiso", "tipo": "lista", "ancho": 2, "opciones": ["Solo lectura", "Lectura y escritura"]},
        ],
        "opciones": [{"clave": "permiso", "etiqueta": "Dar el permiso", "tarea": "Dar permiso en la carpeta", "siempre": True}],
    },
    {
        "nombre": "Buzón compartido o lista", "icono": "buzon", "grupo": "Accesos", "sub": "Accesos", "plazo_horas": 4,
        "requiere_aprobacion": False, "lo_pide": None,
        "descripcion": "Acceso a buzones como facturacion@ u operaciones@, o crear una lista de correo.",
        "campos": [
            {"clave": "buzon", "etiqueta": "Buzón o lista", "tipo": "texto", "ancho": 2},
            {"clave": "accion", "etiqueta": "¿Qué necesita?", "tipo": "lista", "ancho": 2, "opciones": ["Acceso a un buzón existente", "Crear una lista de correo"]},
        ],
        "opciones": [{"clave": "configurar", "etiqueta": "Configurar", "tarea": "Configurar el buzón o la lista", "siempre": True}],
    },
    {
        "nombre": "VPN para teletrabajo", "icono": "vpn", "grupo": "Accesos", "sub": "Accesos", "plazo_horas": 8,
        "requiere_aprobacion": True, "lo_pide": None,
        "descripcion": "Conexión segura desde casa al sistema contable y al servidor de archivos.",
        "campos": [
            {"clave": "desde", "etiqueta": "Desde", "tipo": "fecha", "ancho": 1},
            {"clave": "hasta", "etiqueta": "Hasta (opcional)", "tipo": "fecha", "ancho": 1, "requerido": False},
            {"clave": "equipo", "etiqueta": "Equipo desde el que se conecta", "tipo": "lista", "ancho": 2, "opciones": ["Portátil de la empresa", "Computadora personal"]},
        ],
        "opciones": [{"clave": "vpn", "etiqueta": "Configurar VPN", "tarea": "Configurar VPN", "siempre": True}],
    },
    {
        "nombre": "Baja de usuario", "icono": "baja", "grupo": "Personal", "sub": "Personal", "plazo_horas": 8, "plazo_texto": "El mismo día",
        "requiere_aprobacion": False, "lo_pide": "Talento Humano",
        "descripcion": "Quitar accesos, respaldar correo y recuperar equipos de quien sale de la empresa.",
        "titulo_campos": "Datos de quien sale", "titulo_opciones": "¿Qué hay que hacer?",
        "campos": [
            {"clave": "persona", "etiqueta": "Persona que sale", "tipo": "usuario", "ancho": 2},
            {"clave": "fecha_salida", "etiqueta": "Último día", "tipo": "fecha", "ancho": 1},
            {"clave": "reenviar", "etiqueta": "Reenviar su correo a", "tipo": "usuario", "ancho": 1, "requerido": False},
        ],
        "opciones": [
            {"clave": "accesos", "etiqueta": "Quitar todos los accesos", "tarea": "Desactivar usuario y accesos", "marcado": True},
            {"clave": "correo", "etiqueta": "Respaldar el correo", "tarea": "Respaldar buzón y reenviar", "marcado": True},
            {"clave": "equipos", "etiqueta": "Recuperar equipos", "tarea": "Recuperar equipos y actualizar inventario", "marcado": True},
            {"clave": "ecuapass", "etiqueta": "Dar de baja en ECUAPASS", "tarea": "Baja en ECUAPASS"},
        ],
    },
]


def normalizado(servicio: dict) -> tuple[list[dict], list[dict]]:
    """Campos y opciones con todos sus valores por defecto (requerido, ancho…), listos para guardar en JSON."""
    from app.application.schemas.cuarta import CampoServicio, OpcionServicio

    return ([CampoServicio(**c).model_dump() for c in servicio.get("campos", [])],
            [OpcionServicio(**o).model_dump() for o in servicio.get("opciones", [])])
