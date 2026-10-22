# Jellyfin Invite Codes

Web mínima (un solo archivo Python, **sin dependencias**) para **generar códigos de
invitación de Jellyfin** desde el móvil en dos toques, usando la API de
[jfa-go](https://github.com/hrfee/jfa-go). Tiene su propio login, así que puedes dársela a
alguien de confianza sin que tenga acceso al panel de jfa-go ni al de Jellyfin.

> **Estado: v1.0, en uso diario** en un servidor casero. Interfaz en castellano.
> Issues y PRs bienvenidos.

*English summary below.*

## Qué hace

- Elige **tipo** (normal o administrador → un perfil de jfa-go), **cuántos códigos**, **usos
  por código**, **validez** (1/3/7/30 días) y una **etiqueta** ("para mi primo").
- Te enseña los enlaces nuevos **una sola vez**, con un botón de "copiar todos". Recargar no
  genera más códigos.
- Lista los códigos activos (usos que quedan, caducidad) y permite borrarlos.
- Da el **enlace local** si entras desde casa y el **público** si entras desde fuera.

## Seguridad

- Contraseña con **scrypt** y sesión en cookie `HttpOnly` + `SameSite=Lax` (30 días, se
  renueva sola).
- **Bloqueo global** de 15 min tras 5 fallos: pensado para ir detrás de un túnel o proxy
  donde todas las peticiones llegan con la misma IP.
- Cabeceras `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store`.
- Aun así: **ponla detrás de HTTPS** si la expones a internet.

## Instalar

### Docker

```bash
cp docker-compose.example.yml docker-compose.yml     # edita las URLs y perfiles
docker compose up -d --build
docker compose exec codigos python3 app.py --password   # crea usuario y contraseña
```

### Sin Docker

```bash
export CODIGOS_CONFIG=./codigos.json JFA_URL=http://localhost:8056 JFA_USUARIO=admin JFA_CLAVE=...
python3 app.py --password
python3 app.py            # http://localhost:8057
```

En jfa-go crea antes los perfiles ("Usuario normal" y "Administrador", o los nombres que pongas
en `JFA_PERFIL_*`).

## Variables

| Variable | Por defecto | Qué es |
|---|---|---|
| `CODIGOS_CONFIG` | `/config/codigos.json` | Usuario y hash de esta web |
| `CODIGOS_PUERTO` | 8057 | Puerto |
| `CODIGOS_BASE` | `/codigos` | Prefijo si va detrás de nginx (también responde en `/`) |
| `JFA_URL` | `http://jfa-go:8056` | jfa-go visto desde esta web (+ `url_base` si tiene) |
| `JFA_USUARIO` / `JFA_CLAVE` | — | Admin de jfa-go. Si faltan, se leen de `JFA_INI` |
| `JFA_INI` | `/jfa/config.ini` | `config.ini` de jfa-go (sección `[jellyfin]`) |
| `JFA_LAN` | = `JFA_URL` | Base del enlace de invitación para la red local |
| `JFA_EXTERNO` | — | Base del enlace para quien entra desde fuera |
| `JFA_PERFIL_NORMAL` / `JFA_PERFIL_ADMIN` | `Usuario normal` / `Administrador` | Perfiles de jfa-go |

Comprobación de salud: `GET /salud` → `ok`.

## Pendiente

- [ ] Tipos de cuenta configurables (no solo normal/admin).
- [ ] Varios usuarios con permisos distintos en esta web.
- [ ] Traducción (i18n).

## English summary

Single-file, dependency-free Python web app to **generate Jellyfin invite codes** through the
**jfa-go** API from your phone: pick account type (maps to jfa-go profiles), number of codes,
uses, validity and a label; copy all links at once; list and delete active invites. Its own
login (scrypt, HttpOnly cookie, global lockout). Docker or plain `python3 app.py`. Spanish UI.

## Licencia

MIT (ver `LICENSE`). No está afiliado a Jellyfin ni a jfa-go.
