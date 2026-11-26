"""Base de conocimiento: paso a paso con imágenes y formato (negrita, cursiva, subrayado, color)."""
from tests.conftest import API

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def subir(client, h, nombre="paso1.png", contenido=PNG, mime="image/png"):
    return client.post(f"{API}/conocimiento/imagenes", files=[("archivo", (nombre, contenido, mime))], headers=h)


def crear(client, h, solucion, visibilidad="EXTERNO", estado="PUBLICADO", articulo_id=None):
    body = {"titulo": "Fondo de cámara en videollamada", "sintoma": "No aparece el fondo de Aducorp", "solucion": solucion,
            "palabras_clave": "teams, fondo, cámara", "estado": estado, "visibilidad": visibilidad}
    if articulo_id:
        return client.put(f"{API}/conocimiento/{articulo_id}", json=body, headers=h)
    return client.post(f"{API}/conocimiento", json=body, headers=h)


def test_imagenes_en_pasos_respetan_visibilidad(client, como):
    sup = como("supervisor.tecnico")
    r = subir(client, sup)
    assert r.status_code == 201, r.text
    img = r.json()
    assert img["marca"] == f"[imagen:{img['id']}]"
    # Antes de guardar el artículo solo la ve quien la subió
    assert client.get(f"{API}/conocimiento/imagenes/{img['id']}", headers=sup).content == PNG
    assert client.get(f"{API}/conocimiento/imagenes/{img['id']}", headers=como("maria.andrade")).status_code == 404

    solucion = f"Abra [b]Teams[/b] y entre a [color=#C62828]Configuración[/color]\n{img['marca']}\nElija el fondo [u]Aducorp[/u]"
    a = crear(client, sup, solucion)
    assert a.status_code == 201, a.text
    a = a.json()
    assert "[imagen:" not in a["extracto"] and "[b]" not in a["extracto"]
    # Externo publicado: el cliente (solicitante) la ve
    assert client.get(f"{API}/conocimiento/imagenes/{img['id']}", headers=como("maria.andrade")).content == PNG
    # Sugerencia al crear ticket sin marcas en el texto
    sug = client.post(f"{API}/conocimiento/sugerir", json={"texto": "fondo de aducorp en la cámara de teams"}, headers=como("maria.andrade")).json()
    assert sug and "[imagen" not in sug[0]["extracto"]

    # Interno: el cliente ya no la ve; el personal sí
    assert crear(client, sup, solucion, visibilidad="INTERNO", articulo_id=a["id"]).status_code == 200
    assert client.get(f"{API}/conocimiento/imagenes/{img['id']}", headers=como("maria.andrade")).status_code == 404
    assert client.get(f"{API}/conocimiento/imagenes/{img['id']}", headers=como("david.medina")).status_code == 200

    # Si se quita del texto, se da de baja
    assert crear(client, sup, "Abra Teams y elija el fondo de Aducorp", visibilidad="INTERNO", articulo_id=a["id"]).status_code == 200
    assert client.get(f"{API}/conocimiento/imagenes/{img['id']}", headers=sup).status_code == 404


def test_imagenes_validaciones(client, como):
    sup = como("supervisor.tecnico")
    assert subir(client, sup, "virus.exe", b"MZ" + b"\x00" * 40, "application/octet-stream").status_code == 422
    assert subir(client, sup, "falsa.png", b"no soy imagen", "image/png").status_code == 422
    assert subir(client, sup, "documento.pdf", b"%PDF-1.4 ...", "application/pdf").status_code == 422
    assert subir(client, como("maria.andrade")).status_code == 403   # el cliente no escribe artículos
    # La imagen de otra persona, aún sin guardar, no se puede usar
    ajena = subir(client, como("david.medina")).json()
    assert crear(client, sup, f"Paso uno del procedimiento\n{ajena['marca']}").status_code == 422
    assert crear(client, sup, "Paso uno del procedimiento\n[imagen:99999]").status_code == 422


def test_imagen_copiada_de_otro_articulo_se_duplica(client, como):
    sup = como("supervisor.tecnico")
    img = subir(client, sup).json()
    interno = crear(client, sup, f"Paso técnico interno\n{img['marca']}", visibilidad="INTERNO").json()
    externo = crear(client, sup, f"Paso sencillo para todos\n{img['marca']}").json()
    nuevo = int(externo["solucion"].split("[imagen:")[1].split("]")[0])
    assert nuevo != img["id"]
    assert client.get(f"{API}/conocimiento/imagenes/{nuevo}", headers=como("maria.andrade")).content == PNG
    assert client.get(f"{API}/conocimiento/imagenes/{img['id']}", headers=como("maria.andrade")).status_code == 404
    assert client.get(f"{API}/conocimiento/{interno['id']}", headers=sup).json()["solucion"].endswith(img["marca"])


def test_enlace_para_compartir_sin_cuenta(client, como):
    sup = como("supervisor.tecnico")
    img = subir(client, sup).json()
    a = crear(client, sup, f"Abra [b]Teams[/b]\n{img['marca']}").json()
    enlace = a["enlace_publico"]
    assert enlace and enlace.startswith(f"/ayuda/{a['id']}/")
    llave = enlace.rsplit("/", 1)[1]
    assert client.get(f"{API}/conocimiento/{a['id']}", headers=como("maria.andrade")).json()["enlace_publico"] is None   # solo el personal lo genera

    pub = client.get(f"{API}/publico/articulos/{a['id']}/{llave}")   # sin sesión
    assert pub.status_code == 200 and pub.json()["titulo"] == a["titulo"] and "palabras_clave" not in pub.json()
    assert client.get(f"{API}/publico/articulos/{a['id']}/{llave}/imagenes/{img['id']}").content == PNG
    assert client.get(f"{API}/publico/articulos/{a['id']}/llave-falsa").status_code == 404
    assert client.get(f"{API}/conocimiento/imagenes/{img['id']}").status_code == 401   # la ruta normal sigue pidiendo sesión

    # Si pasa a interno, el enlace deja de funcionar
    interno = crear(client, sup, f"Abra [b]Teams[/b]\n{img['marca']}", visibilidad="INTERNO", articulo_id=a["id"]).json()
    assert interno["enlace_publico"] is None
    assert client.get(f"{API}/publico/articulos/{a['id']}/{llave}").status_code == 404
    assert client.get(f"{API}/publico/articulos/{a['id']}/{llave}/imagenes/{img['id']}").status_code == 404
