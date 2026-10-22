#!/usr/bin/env python3
# Códigos: web mínima para generar invitaciones de un solo uso para registrarse en Jellyfin,
# a través de la API de jfa-go (https://github.com/hrfee/jfa-go), con login propio (no el de Jellyfin).
# - Tipos: "normal" y "admin" -> perfiles de jfa-go (JFA_PERFIL_NORMAL / JFA_PERFIL_ADMIN).
# - Seguridad: contraseña con scrypt, sesión en cookie HttpOnly/SameSite, bloqueo global de 15 min
#   tras 5 fallos (pensado para ir detrás de un proxy/túnel donde todo llega con la misma IP).
# Config: $CODIGOS_CONFIG (usuario, hash, sal). Crear/cambiar la contraseña: python3 app.py --password
import base64, configparser, hashlib, hmac, html, ipaddress, json, os, re, secrets, sys, time, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CONFIG = os.environ.get("CODIGOS_CONFIG", "/config/codigos.json")
JFA_INI = os.environ.get("JFA_INI", "/jfa/config.ini")
JFA = os.environ.get("JFA_URL", "http://jfa-go:8056")   # jfa-go visto desde aquí (+ su url_base, si tiene)
PUERTO = int(os.environ.get("CODIGOS_PUERTO", "8057"))
# Dirección PÚBLICA de jfa-go que verán los invitados: en la red local y desde fuera.
JFA_LAN = os.environ.get("JFA_LAN", JFA)
JFA_EXTERNO = os.environ.get("JFA_EXTERNO", "")       # vacío = usar siempre JFA_LAN
BASE = os.environ.get("CODIGOS_BASE", "/codigos")     # prefijo si va detrás de un proxy (también responde en /)
PERFILES = {"normal": os.environ.get("JFA_PERFIL_NORMAL", "Usuario normal"),
            "admin": os.environ.get("JFA_PERFIL_ADMIN", "Administrador")}
SESIONES = {}            # sha256(token) -> caduca (se guarda en disco: sobrevive a reinicios)
DURACION = 30 * 86400    # 30 días, renovándose en cada visita
SESIONES_F = os.path.join(os.path.dirname(CONFIG), "sesiones.json")
try:
    SESIONES.update({k: v for k, v in json.load(open(SESIONES_F)).items() if v > time.time()})
except Exception:
    pass


def huella(tok):
    return hashlib.sha256(tok.encode()).hexdigest()


def guardar_sesiones():
    try:
        json.dump({k: v for k, v in SESIONES.items() if v > time.time()}, open(SESIONES_F, "w"))
        os.chmod(SESIONES_F, 0o600)
    except OSError:
        pass
RECIENTES = {}           # token -> códigos recién creados (se enseñan una vez: recargar no genera nada)
FALLOS = []              # instantes de intentos fallidos
BLOQUEO = {"hasta": 0}


def hash_pw(pw, sal):
    return hashlib.scrypt(pw.encode(), salt=bytes.fromhex(sal), n=2**14, r=8, p=1).hex()


def cargar():
    return json.load(open(CONFIG))


class JfaGo:
    token, caduca = None, 0

    def _login(self):
        # credenciales del admin de jfa-go: JFA_USUARIO/JFA_CLAVE, o leídas de su config.ini
        usuario, clave = os.environ.get("JFA_USUARIO"), os.environ.get("JFA_CLAVE")
        if not (usuario and clave):
            ini = configparser.ConfigParser(); ini.read(JFA_INI)
            if not ini.has_section("jellyfin"):
                raise RuntimeError(f"faltan JFA_USUARIO/JFA_CLAVE y no puedo leer {JFA_INI}")
            usuario, clave = ini["jellyfin"]["username"], ini["jellyfin"]["password"]
        cred = base64.b64encode(f"{usuario}:{clave}".encode()).decode()
        r = urllib.request.Request(JFA + "/token/login", headers={"Authorization": "Basic " + cred})
        self.token = json.load(urllib.request.urlopen(r, timeout=20))["token"]
        self.caduca = time.time() + 600

    def api(self, metodo, ruta, datos=None):
        if time.time() > self.caduca:
            self._login()
        r = urllib.request.Request(JFA + ruta, method=metodo,
                                   data=json.dumps(datos).encode() if datos is not None else None,
                                   headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"})
        cuerpo = urllib.request.urlopen(r, timeout=20).read()
        return json.loads(cuerpo) if cuerpo else None


jfa = JfaGo()

CSS = """
:root{--fondo:#141414;--caja:#1f1f1f;--borde:#333;--texto:#eee;--suave:#9a9a9a;--acento:#C5E02B;--morado:#D66AF7;--rojo:#ff6b6b}
*{box-sizing:border-box}body{margin:0;background:var(--fondo);color:var(--texto);font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:46rem;margin:0 auto;padding:1.5rem 1rem 3rem}h1{font-size:1.5rem;margin:.2rem 0 1.2rem}h1 span{color:var(--acento)}
.caja{background:var(--caja);border:1px solid var(--borde);border-radius:.8rem;padding:1.2rem;margin-bottom:1.2rem}
label{display:block;font-size:.85rem;color:var(--suave);margin:.6rem 0 .25rem}
input,select{width:100%;padding:.65rem .7rem;border-radius:.5rem;border:1px solid var(--borde);background:#111;color:var(--texto);font-size:1rem}
button{margin-top:1rem;padding:.7rem 1.1rem;border:0;border-radius:.5rem;background:var(--acento);color:#111;font-weight:700;font-size:1rem;cursor:pointer}
button.sec{background:transparent;color:var(--suave);border:1px solid var(--borde);margin:0;padding:.35rem .7rem;font-size:.85rem;font-weight:500}
.fila{display:grid;grid-template-columns:1fr 1fr;gap:.8rem}@media(max-width:520px){.fila{grid-template-columns:1fr}}
.nuevo{border-color:var(--acento)}.codigo{font-family:ui-monospace,monospace;font-size:1.35rem;letter-spacing:.04em;color:var(--acento);word-break:break-all}
.enlace{font-family:ui-monospace,monospace;font-size:.85rem;word-break:break-all;color:var(--suave)}
table{width:100%;border-collapse:collapse;font-size:.9rem}td,th{padding:.55rem .3rem;border-bottom:1px solid var(--borde);text-align:left;vertical-align:middle}
th{color:var(--suave);font-weight:500}.tag{padding:.1rem .5rem;border-radius:1rem;font-size:.75rem;font-weight:700}
.tag.admin{background:var(--morado);color:#111}.tag.normal{background:#333;color:var(--texto)}
.err{color:var(--rojo)}.top{display:flex;justify-content:space-between;align-items:center}.mono{font-family:ui-monospace,monospace}
"""


def pagina(cuerpo, titulo="Códigos"):
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{titulo}</title><style>{CSS}</style></head><body><main>{cuerpo}</main></body></html>"""


class App(BaseHTTPRequestHandler):
    server_version = "codigos"

    def log_message(self, fmt, *a):
        sys.stderr.write("%s %s\n" % (time.strftime("%F %T"), fmt % a))

    # --- utilidades
    def sesion(self):
        c = self.headers.get("Cookie", "")
        for parte in c.split(";"):
            k, _, v = parte.strip().partition("=")
            if k == "cod_sesion" and SESIONES.get(huella(v), 0) > time.time():
                if SESIONES[huella(v)] - time.time() < DURACION - 86400:   # renovar como mucho una vez al día
                    SESIONES[huella(v)] = time.time() + DURACION
                    guardar_sesiones()
                return v
        return None

    def enviar(self, codigo, cuerpo, extra=None):
        datos = cuerpo.encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(datos)

    def ir(self, ruta, extra=None):
        self.send_response(303)
        self.send_header("Location", (self.base + ruta) if ruta != "/" or self.base else "/")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()

    def form(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        return {k: v[0] for k, v in urllib.parse.parse_qs(self.rfile.read(min(n, 10000)).decode()).items()}

    def enlace(self, codigo):
        # si se entra a esta web desde la red local, enlace local; si no, el público (JFA_EXTERNO)
        host = self.headers.get("Host", "").rsplit(":", 1)[0].strip("[]")
        try:
            local = host == "localhost" or ipaddress.ip_address(host).is_private
        except ValueError:
            local = False
        return f"{JFA_LAN if local or not JFA_EXTERNO else JFA_EXTERNO}/invite/{codigo}"

    # --- páginas
    def login_html(self, error=""):
        e = f'<p class="err">{html.escape(error)}</p>' if error else ""
        return pagina(f"""<h1>🎟️ <span>Códigos</span> de invitación</h1><div class="caja"><form method="post" action="{self.base}/entrar">
<label>Usuario</label><input name="u" autocomplete="username" autofocus>
<label>Contraseña</label><input name="p" type="password" autocomplete="current-password">{e}
<button>Entrar</button></form></div>""")

    def panel_html(self, error=""):
        nuevos = RECIENTES.pop(self.sesion(), None)
        try:
            inv = jfa.api("GET", "/invites").get("invites") or []
        except Exception as ex:
            inv, error = [], f"No se puede hablar con jfa-go: {ex}"
        filas = ""
        for i in sorted(inv, key=lambda x: x.get("created", 0), reverse=True):
            tipo = next((t for t, p in PERFILES.items() if p == i.get("profile")), "normal")
            cad = time.strftime("%d/%m %H:%M", time.localtime(i["valid_till"])) if i.get("valid_till") else f"{i.get('days', '?')} d"
            usos = "∞" if i.get("no-limit") else str(i.get("remaining-uses", 1))
            etiqueta = re.sub(r"\s*#[0-9a-f]{8}$", "", i.get("label") or "")
            filas += f"""<tr><td class="mono">{html.escape(i['code'])}</td><td><span class="tag {tipo}">{tipo}</span></td>
<td>{html.escape(etiqueta)}</td><td>{usos}</td><td>{cad}</td>
<td><form method="post" action="{self.base}/borrar" onsubmit="return confirm('¿Borrar este código?')">
<input type="hidden" name="c" value="{html.escape(i['code'])}"><button class="sec">Borrar</button></form></td></tr>"""
        tabla = f"<table><tr><th>Código</th><th>Tipo</th><th>Etiqueta</th><th>Usos que quedan</th><th>Caduca</th><th></th></tr>{filas}</table>" if filas else '<p style="color:var(--suave)">No hay códigos activos.</p>'
        n = ""
        if nuevos:
            lista = "".join(f"""<div style="padding:.6rem 0;border-top:1px solid var(--borde)"><div class="codigo">{html.escape(x['codigo'])}</div>
<div class="enlace">{html.escape(x['enlace'])}</div></div>""" for x in nuevos)
            todos = html.escape("\n".join(x['enlace'] for x in nuevos))
            usos = nuevos[0]['usos']
            n = f"""<div class="caja nuevo"><div style="color:var(--suave);font-size:.85rem">{len(nuevos)} código(s) nuevo(s) · {nuevos[0]['tipo']} ·
{'1 uso' if usos == 1 else f'{usos} usos'} cada uno</div>{lista}
<button class="sec" style="margin-top:.8rem" onclick="navigator.clipboard.writeText(this.dataset.t);this.textContent='¡Copiados!'" data-t="{todos}">Copiar todos los enlaces</button></div>"""
        e = f'<p class="err">{html.escape(error)}</p>' if error else ""
        return pagina(f"""<div class="top"><h1>🎟️ <span>Códigos</span> de invitación</h1>
<div style="display:flex;gap:.6rem;align-items:center">
<form method="post" action="{self.base}/salir"><button class="sec">Salir</button></form></div></div>{e}{n}
<div class="caja"><form method="post" action="{self.base}/crear"><div class="fila">
<div><label>Tipo de cuenta</label><select name="tipo"><option value="normal">Normal (familia)</option><option value="admin">Administrador</option></select></div>
<div><label>Cuántos códigos</label><input name="cantidad" type="number" min="1" max="20" value="1"></div>
<div><label>Usos por código</label><input name="usos" type="number" min="1" max="100" value="1"></div>
<div><label>Válido durante</label><select name="dias"><option value="1">1 día</option><option value="3">3 días</option><option value="7" selected>7 días</option><option value="30">30 días</option></select></div>
</div><label>Etiqueta (para quién es, opcional)</label><input name="etiqueta" maxlength="40" placeholder="p. ej. mi primo">
<button>Generar</button></form></div>
<div class="caja"><h3 style="margin-top:0">Códigos activos</h3>{tabla}</div>""")

    # --- rutas
    def ruta(self):
        """Funciona en la raíz (http://host:8057/) y bajo BASE (p.ej. /codigos detrás de nginx)."""
        r = urllib.parse.urlparse(self.path).path
        if r == BASE or r.startswith(BASE + "/"):
            self.base = BASE
            return r[len(BASE):] or "/"
        self.base = ""
        return r or "/"

    def do_GET(self):
        ruta = self.ruta()
        if ruta == "/":
            return self.enviar(200, self.panel_html() if self.sesion() else self.login_html())
        if ruta == "/salud":
            return self.enviar(200, "ok")
        self.enviar(404, pagina("<p>No existe.</p>"))

    def do_POST(self):
        ruta = self.ruta()
        f = self.form()
        if ruta == "/entrar":
            ahora = time.time()
            if ahora < BLOQUEO["hasta"]:
                return self.enviar(429, self.login_html(f"Demasiados intentos. Prueba en {int((BLOQUEO['hasta'] - ahora) / 60) + 1} min."))
            cfg = cargar()
            ok = hmac.compare_digest(f.get("u", ""), cfg["usuario"]) & hmac.compare_digest(hash_pw(f.get("p", ""), cfg["sal"]), cfg["hash"])
            if not ok:
                FALLOS[:] = [t for t in FALLOS if ahora - t < 900] + [ahora]
                if len(FALLOS) >= 5:
                    BLOQUEO["hasta"] = ahora + 900; FALLOS.clear()
                time.sleep(1)
                return self.enviar(401, self.login_html("Usuario o contraseña incorrectos."))
            tok = secrets.token_urlsafe(32)
            SESIONES[huella(tok)] = ahora + DURACION
            guardar_sesiones()
            return self.ir("/", {"Set-Cookie": f"cod_sesion={tok}; Path=/; HttpOnly; SameSite=Lax; Max-Age={DURACION}"})
        if not self.sesion():
            return self.ir("/")
        if ruta == "/salir":
            SESIONES.pop(huella(self.sesion()), None)
            guardar_sesiones()
            return self.ir("/", {"Set-Cookie": f"cod_sesion=; Path=/; Max-Age=0"})
        if ruta == "/crear":
            tipo = f.get("tipo") if f.get("tipo") in PERFILES else "normal"
            dias = int(f.get("dias", "7")) if f.get("dias", "7") in ("1", "3", "7", "30") else 7
            try:
                cantidad = min(max(int(f.get("cantidad", "1")), 1), 20)
                usos = min(max(int(f.get("usos", "1")), 1), 100)
            except ValueError:
                cantidad, usos = 1, 1
            etiqueta = (("[ADMIN] " if tipo == "admin" else "") + f.get("etiqueta", "")[:40]).strip()
            creados = []
            try:
                marcas = []
                for _ in range(cantidad):
                    marca = secrets.token_hex(4); marcas.append(marca)
                    jfa.api("POST", "/invites", {"months": 0, "days": dias, "hours": 0, "minutes": 0, "multiple-uses": usos > 1,
                                                 "no-limit": False, "remaining-uses": usos, "profile": PERFILES[tipo],
                                                 "label": f"{etiqueta} #{marca}".strip()})
                todas = jfa.api("GET", "/invites").get("invites") or []
                for marca in marcas:
                    for i in todas:
                        if (i.get("label") or "").endswith("#" + marca):
                            creados.append({"tipo": "administrador" if tipo == "admin" else "normal", "usos": usos,
                                            "codigo": i["code"], "enlace": self.enlace(i["code"])})
                RECIENTES[self.sesion()] = creados
            except Exception as ex:
                return self.enviar(500, self.panel_html(error=f"No se pudo crear: {ex}"))
            # redirigir (POST→GET): así recargar la página no vuelve a generar códigos
            return self.ir("/")
        if ruta == "/borrar":
            try:
                jfa.api("DELETE", "/invites", {"code": f.get("c", "")})
            except Exception:
                pass
            return self.ir("/")
        self.enviar(404, pagina("<p>No existe.</p>"))


if __name__ == "__main__":
    if "--password" in sys.argv:
        import getpass
        u = input("Usuario [admin]: ").strip() or "admin"
        p = getpass.getpass("Contraseña nueva: ")
        sal = secrets.token_hex(16)
        json.dump({"usuario": u, "sal": sal, "hash": hash_pw(p, sal)}, open(CONFIG, "w"))
        os.chmod(CONFIG, 0o600)
        print("Guardado.")
        sys.exit()
    print(f"Códigos en http://0.0.0.0:{PUERTO}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PUERTO), App).serve_forever()
