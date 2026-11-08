# SIFARH · Inventario farmacéutico hospitalario

FastAPI + SQLAlchemy + SQLite + Jinja2. Autenticación con JWT en cookie `HttpOnly`/`SameSite=Lax`.

## Puesta en marcha

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # opcional, ajusta Telegram/Ollama
python seed_demo.py           # opcional: datos de demostración
python run.py                 # http://127.0.0.1:8000
```

La primera visita redirige a `/registro`: **la primera cuenta creada es Admin**. Los registros posteriores
quedan *pendientes* (rol Médico/Farmacéutico, nunca Admin) hasta que un Admin los apruebe en `/usuarios`.

## Estructura

```
app/
  main.py  config.py  database.py  models.py  security.py  deps.py  templating.py
  routes/    auth, reports (dashboard + CSV), inventory (CRUD), search (consulta), users, api (Telegram/Ollama)
  services/  inventory (alertas, búsqueda, CSV), telegram_bot, ollama
  templates/ layout, login, registro, dashboard, inventario, medicamento_form, consulta, usuarios
  static/    css/style.css, js/app.js
tests/test_app.py   seed_demo.py   run.py
```

## Permisos

| Acción                          | Admin | Farmacéutico | Médico |
|---------------------------------|:-----:|:------------:|:------:|
| Ver dashboard / consulta / inventario | ✔ | ✔ | ✔ |
| Crear/editar/eliminar medicamentos    | ✔ | ✔ | ✖ |
| Exportar CSV, análisis con IA         | ✔ | ✔ | ✖ |
| Administrar usuarios                  | ✔ | ✖ | ✖ |

## Alertas (resaltadas en rojo/naranja)

Stock < mínimo · Stock > máximo · Caducidad ≤ 90 días (`DIAS_ALERTA_CADUCIDAD`) o ya caducado.

## Telegram

1. Crea un bot con @BotFather y pon `TELEGRAM_BOT_TOKEN` en `.env`.
2. **Modo `polling`** (por defecto, ideal en local): el servidor arranca un worker; no necesita URL pública.
3. **Modo `webhook`**: `TELEGRAM_MODE=webhook`, define `TELEGRAM_WEBHOOK_SECRET` y registra
   `https://TU_HOST/api/telegram/webhook` con `setWebhook` (parámetro `secret_token`).
4. Restringe quién puede consultar con `TELEGRAM_ALLOWED_CHAT_IDS` (envía `/start` al bot para ver tu `chat_id`).

Comandos: texto libre o `/stock <texto>`, `/criticos`, `/caducan`, `/ayuda`.

## Ollama

`POST /api/ai/analisis` (sesión Admin/Farmacéutico; botón en el dashboard) envía a `OLLAMA_URL`
los medicamentos caducados/por caducar y con stock crítico (máx. 50 de cada tipo) y devuelve el análisis.
Configura el modelo con `OLLAMA_MODEL` (debe estar descargado: `ollama pull <modelo>`).

## Pruebas

```bash
PYTHONPATH=. python tests/test_app.py
```

## Notas de seguridad

- Contraseñas con PBKDF2-SHA256; bloqueo temporal tras 5 intentos fallidos de login.
- Se revalida el usuario en BD en cada petición (suspender/eliminar surte efecto inmediato).
- Pon `COOKIE_SECURE=1` si sirves por HTTPS. Para producción, migra a PostgreSQL y un limitador de intentos compartido.
- El CSV neutraliza inyección de fórmulas (`=`, `+`, `-`, `@`).
