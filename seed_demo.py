"""Carga datos de demostración: python seed_demo.py (solo si la tabla está vacía)."""
from datetime import date, timedelta

from app.database import Base, SessionLocal, engine
from app.models import Medicamento

hoy = date.today()
DEMO = [
    # nombre, principio activo, lote, días a caducar, stock, mín, máx
    ("Paracetamol 500 mg", "Paracetamol", "PA2401", 420, 320, 100, 500),
    ("Ibuprofeno 400 mg", "Ibuprofeno", "IB2312", 60, 150, 80, 300),
    ("Amoxicilina 500 mg", "Amoxicilina", "AM2405", 300, 25, 60, 250),
    ("Omeprazol 20 mg", "Omeprazol", "OM2402", 500, 900, 100, 600),
    ("Insulina glargina", "Insulina", "IN2403", 45, 12, 20, 60),
    ("Metformina 850 mg", "Metformina", "ME2310", -10, 80, 50, 200),
    ("Ceftriaxona 1 g", "Ceftriaxona", "CE2406", 200, 40, 30, 120),
    ("Salbutamol inhalador", "Salbutamol", "SA2407", 150, 55, 20, 100),
    ("Losartán 50 mg", "Losartán", "LO2408", 700, 210, 100, 400),
    ("Diclofenaco 75 mg/3 ml", "Diclofenaco", "DI2409", 85, 18, 30, 90),
    ("Suero fisiológico 0.9 % 500 ml", "Cloruro de sodio", "SF2410", 365, 600, 200, 800),
    ("Atorvastatina 20 mg", "Atorvastatina", "AT2411", 540, 130, 60, 250),
    ("Morfina 10 mg/ml", "Morfina", "MO2412", 30, 15, 10, 40),
    ("Heparina sódica 5000 UI", "Heparina", "HE2501", 240, 70, 40, 150),
]

if __name__ == "__main__":
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if db.query(Medicamento).count():
            print("Ya hay medicamentos; no se cargó nada.")
        else:
            for n, p, l, d, s, mi, ma in DEMO:
                db.add(Medicamento(nombre=n, principio_activo=p, lote=l, fecha_caducidad=hoy + timedelta(days=d),
                                   stock_actual=s, stock_minimo=mi, stock_maximo=ma))
            db.commit()
            print("Se cargaron %d medicamentos de demostración." % len(DEMO))
