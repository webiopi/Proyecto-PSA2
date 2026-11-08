"""Pruebas de integración (BD temporal). Ejecutar: python -m pytest -q  o  python tests/test_app.py"""
import os
import re
import tempfile
from datetime import date, timedelta
from unittest import mock

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = "sqlite:///%s/test.db" % _tmp
os.environ["SECRET_KEY"] = "test-secret"
os.environ["TELEGRAM_BOT_TOKEN"] = "123:abc"
os.environ["TELEGRAM_MODE"] = "webhook"
os.environ["TELEGRAM_WEBHOOK_SECRET"] = "s3cret"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import ollama, telegram_bot  # noqa: E402


def _login(c, u, p):
    return c.post("/login", data={"usuario": u, "password": p}, follow_redirects=False)


def test_flujo_completo():
    with TestClient(app) as c:
        # Sin sesión -> redirige a login; API -> 401
        assert c.get("/dashboard", follow_redirects=False).status_code == 303
        assert c.post("/api/ai/analisis").status_code == 401
        # Con BD vacía /login lleva al registro del Admin
        assert c.get("/login", follow_redirects=False).headers["location"].startswith("/registro")

        r = c.post("/registro", data={"nombre": "Ana Admin", "usuario": "ana", "password": "password1",
                                      "password2": "password1", "rol": "Admin"}, follow_redirects=False)
        assert r.status_code == 303
        # Segundo registro: pendiente, y no puede elegir Admin
        r = c.post("/registro", data={"nombre": "Dr House", "usuario": "house", "password": "password1",
                                      "password2": "password1", "rol": "Admin"})
        assert r.status_code == 400
        r = c.post("/registro", data={"nombre": "Dr House", "usuario": "house", "password": "password1",
                                      "password2": "password1", "rol": "Médico"}, follow_redirects=False)
        assert r.status_code == 303
        assert _login(c, "house", "password1").status_code == 403  # pendiente
        assert _login(c, "ana", "mala").status_code == 401

        r = _login(c, "ana", "password1")
        assert r.status_code == 303 and "HttpOnly" in r.headers["set-cookie"]
        assert c.get("/dashboard").status_code == 200

        # CRUD
        hoy = date.today()
        def med(nombre, lote, dias, act, mn, mx):
            return {"nombre": nombre, "principio_activo": "X", "lote": lote,
                    "fecha_caducidad": (hoy + timedelta(days=dias)).isoformat(),
                    "stock_actual": act, "stock_minimo": mn, "stock_maximo": mx}
        assert c.post("/inventario/nuevo", data=med("Bajo", "L1", 300, 5, 10, 50), follow_redirects=False).status_code == 303
        assert c.post("/inventario/nuevo", data=med("Alto", "L2", 300, 90, 10, 50), follow_redirects=False).status_code == 303
        assert c.post("/inventario/nuevo", data=med("Cad", "L3", 30, 20, 10, 50), follow_redirects=False).status_code == 303
        assert c.post("/inventario/nuevo", data=med("=cmd()", "L4", 300, 20, 10, 50), follow_redirects=False).status_code == 303
        assert c.post("/inventario/nuevo", data=med("Ok", "L5", 300, 20, 10, 50), follow_redirects=False).status_code == 303
        assert c.post("/inventario/nuevo", data=med("Ok", "l5", 300, 20, 10, 50)).status_code == 400  # duplicado
        assert c.post("/inventario/nuevo", data=med("Mal", "L6", 300, 20, 60, 50)).status_code == 400  # min>max
        assert c.post("/inventario/nuevo", data={**med("Mal", "L7", 300, 20, 1, 5), "fecha_caducidad": "xx"}).status_code == 400

        html = c.get("/inventario").text
        assert html.count("row-alert") == 3
        assert "Bajo mínimo" in html and "Sobre máximo" in html and "Caduca en" in html

        # Edición y 404
        mid = int(re.search(r"/inventario/(\d+)/editar", html).group(1))
        assert c.get("/inventario/%d/editar" % mid).status_code == 200
        assert c.get("/inventario/9999/editar").status_code == 404

        # Consulta con filtros
        assert "Bajo" in c.get("/consulta?nombre=baj").text
        assert "Alto" not in c.get("/consulta?nombre=baj").text
        assert c.get("/consulta?lote=L3").text.count("<code>") == 1
        assert c.get("/consulta?estado=bajo_minimo").text.count("<code>") == 1
        assert c.get("/consulta?nombre=%25").text.count("<code>") == 0  # comodín escapado
        assert c.get("/consulta?page=999").status_code == 200

        # Dashboard y CSV
        d = c.get("/dashboard").text
        assert 'data-count="5"' in d
        csv = c.get("/reportes/exportar.csv").text
        assert "'=cmd()" in csv and csv.startswith("\ufeff")
        assert csv.count("\n") == 6
        assert "Cad" in c.get("/reportes/exportar.csv?tipo=caducar").text

        # Usuarios: aprobar y rol Médico sin permisos
        assert "house" in c.get("/usuarios").text
        hid = int(re.search(r"/usuarios/(\d+)/aprobar", c.get("/usuarios").text).group(1))
        assert c.post("/usuarios/%d/aprobar" % hid, follow_redirects=False).status_code == 303
        assert c.post("/usuarios/crear", data={"nombre": "Farma", "usuario": "farma", "password": "password1",
                                               "rol": "Farmacéutico"}, follow_redirects=False).status_code == 303
        assert c.post("/usuarios/1/eliminar", follow_redirects=False).headers["location"].find("error") > 0  # a sí mismo

        with TestClient(app) as m:
            assert _login(m, "house", "password1").status_code == 303
            assert m.get("/usuarios").status_code == 403
            assert m.get("/inventario/nuevo").status_code == 403
            assert m.post("/inventario/%d/eliminar" % mid).status_code == 403
            assert m.get("/reportes/exportar.csv").status_code == 403
            assert m.post("/api/ai/analisis").status_code == 403
            assert m.get("/inventario").status_code == 200 and "Nuevo medicamento" not in m.get("/inventario").text

        # Eliminar usuario suspende sesión inmediatamente
        assert c.post("/usuarios/%d/eliminar" % hid, follow_redirects=False).status_code == 303
        assert m.get("/dashboard", follow_redirects=False).status_code == 303

        # Eliminar medicamento
        assert c.post("/inventario/%d/eliminar" % mid, follow_redirects=False).status_code == 303

        # Ollama (mock)
        async def fake(prompt):
            assert "Cad" in prompt
            return "Comprar X"
        with mock.patch.object(ollama, "generar", fake):
            j = c.post("/api/ai/analisis").json()
            assert j["analisis"] == "Comprar X" and j["caducan"] >= 1
        with mock.patch.object(ollama.settings, "OLLAMA_URL", "http://127.0.0.1:9/api/generate"):
            r = c.post("/api/ai/analisis")  # Ollama no disponible
        assert r.status_code in (503, 504, 502) and "detail" in r.json()

        # Telegram
        assert c.post("/api/telegram/webhook", json={}).status_code == 403
        enviados = []
        async def fake_api(client, metodo, **p):
            enviados.append(p)
        with mock.patch.object(telegram_bot, "_api", fake_api):
            upd = {"message": {"chat": {"id": 7}, "text": "cad"}}
            r = c.post("/api/telegram/webhook", json=upd, headers={"X-Telegram-Bot-Api-Secret-Token": "s3cret"})
            assert r.status_code == 200
            assert "Stock: 20" in enviados[-1]["text"] and "Cad" in enviados[-1]["text"]
            c.post("/api/telegram/webhook", json={"message": {"chat": {"id": 7}, "text": "/criticos"}},
                   headers={"X-Telegram-Bot-Api-Secret-Token": "s3cret"})
            assert "Bajo" in enviados[-1]["text"]

        # Logout
        c.post("/logout")
        assert c.get("/dashboard", follow_redirects=False).status_code == 303


if __name__ == "__main__":
    test_flujo_completo()
    print("OK")


def test_orden_de_compra():
    """Médico pide -> farmacéutico confirma -> stock rebajado y orden en reportes."""
    from app.database import SessionLocal
    from app.models import Medicamento, Usuario
    from app.security import hash_password

    with SessionLocal() as db:
        for n, u, r in (("Dr. Medico", "doc_oc", "Médico"), ("Farma", "farma_oc", "Farmacéutico")):
            db.add(Usuario(nombre=n, usuario=u, rol=r, password_hash=hash_password("password1"), aprobado=True))
        m = Medicamento(nombre="Paracetamol OC", principio_activo="Paracetamol", lote="OC1",
                        fecha_caducidad=date.today() + timedelta(days=400), stock_actual=10, stock_minimo=1, stock_maximo=50)
        db.add(m)
        db.commit()
        mid = m.id

    with TestClient(app) as med, TestClient(app) as farma:
        _login(med, "doc_oc", "password1")
        _login(farma, "farma_oc", "password1")
        assert "btn-pedido" in med.get("/inventario").text
        assert "btn-pedido" not in farma.get("/inventario").text
        assert farma.post("/api/ordenes", json={"items": [{"medicamento_id": mid, "cantidad": 1}]}).status_code == 403
        assert med.get("/api/ordenes/buscar?q=paracet").json()["items"][0]["id"] == mid
        # Más que el stock -> rechazado
        assert med.post("/api/ordenes", json={"items": [{"medicamento_id": mid, "cantidad": 99}]}).status_code == 400
        # IA (mock)
        async def fake(prompt):
            return 'Texto {"ids": [%d, 9999], "explicacion": "Analgésico"}' % mid
        with mock.patch.object(ollama, "generar", fake):
            r = med.post("/api/ordenes/sugerir", json={"dolencia": "dolor de cabeza"}).json()
        assert [s["id"] for s in r["sugeridos"]] == [mid]
        # Pedido válido
        r = med.post("/api/ordenes", json={"items": [{"medicamento_id": mid, "cantidad": 4}], "notas": "urgente"})
        assert r.status_code == 200
        oid = r.json()["id"]
        assert "btn-confirmar-%d" % oid in farma.get("/inventario").text
        assert med.post("/ordenes/%d/confirmar" % oid, follow_redirects=False).status_code == 403
        assert farma.post("/ordenes/%d/confirmar" % oid, follow_redirects=False).status_code == 303
        with SessionLocal() as db:
            assert db.get(Medicamento, mid).stock_actual == 6
        # No se puede confirmar dos veces
        farma.post("/ordenes/%d/confirmar" % oid, follow_redirects=False)
        with SessionLocal() as db:
            assert db.get(Medicamento, mid).stock_actual == 6
        assert "#%d" % oid in farma.get("/dashboard").text
        assert "Confirmada" in med.get("/dashboard").text
        assert farma.get("/reportes/exportar.csv?tipo=ordenes").status_code == 200
