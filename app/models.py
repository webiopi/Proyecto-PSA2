"""Modelos de la base de datos."""
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

ROL_ADMIN = "Admin"
ROL_FARMACEUTICO = "Farmacéutico"
ROL_MEDICO = "Médico"
ROLES = (ROL_ADMIN, ROL_FARMACEUTICO, ROL_MEDICO)


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100))
    # Identificador de acceso (login). Se añade al esquema pedido para poder iniciar sesión.
    usuario: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    rol: Mapped[str] = mapped_column(String(20))
    password_hash: Mapped[str] = mapped_column(String(255))
    # Las cuentas auto-registradas quedan pendientes hasta que un Admin las apruebe.
    aprobado: Mapped[bool] = mapped_column(default=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Medicamento(Base):
    __tablename__ = "medicamentos"
    __table_args__ = (
        UniqueConstraint("nombre", "lote", name="uq_medicamento_nombre_lote"),
        CheckConstraint("stock_actual >= 0", name="ck_stock_actual"),
        CheckConstraint("stock_minimo >= 0", name="ck_stock_minimo"),
        CheckConstraint("stock_maximo >= stock_minimo", name="ck_stock_rango"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150), index=True)
    principio_activo: Mapped[str] = mapped_column(String(150), index=True)
    lote: Mapped[str] = mapped_column(String(50), index=True)
    fecha_caducidad: Mapped[date] = mapped_column(Date, index=True)
    stock_actual: Mapped[int] = mapped_column(default=0)
    stock_minimo: Mapped[int] = mapped_column(default=0)
    stock_maximo: Mapped[int] = mapped_column(default=0)


ESTADO_PENDIENTE = "Pendiente"
ESTADO_CONFIRMADA = "Confirmada"
ESTADO_RECHAZADA = "Rechazada"


class OrdenCompra(Base):
    """Pedido hecho por un médico; el farmacéutico lo confirma (rebaja stock) o lo rechaza."""
    __tablename__ = "ordenes_compra"

    id: Mapped[int] = mapped_column(primary_key=True)
    medico_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    estado: Mapped[str] = mapped_column(String(20), default=ESTADO_PENDIENTE, index=True)
    notas: Mapped[str] = mapped_column(String(300), default="")
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resuelto_por_id: Mapped[Optional[int]] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    resuelto_en: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    medico: Mapped[Usuario] = relationship(foreign_keys=[medico_id])
    resuelto_por: Mapped[Optional[Usuario]] = relationship(foreign_keys=[resuelto_por_id])
    items: Mapped[List["OrdenItem"]] = relationship(
        back_populates="orden", cascade="all, delete-orphan", order_by="OrdenItem.id"
    )

    @property
    def total_unidades(self) -> int:
        return sum(i.cantidad for i in self.items)


class OrdenItem(Base):
    __tablename__ = "orden_items"
    __table_args__ = (CheckConstraint("cantidad > 0", name="ck_item_cantidad"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    orden_id: Mapped[int] = mapped_column(ForeignKey("ordenes_compra.id"), index=True)
    medicamento_id: Mapped[int] = mapped_column(ForeignKey("medicamentos.id"))
    cantidad: Mapped[int]

    orden: Mapped[OrdenCompra] = relationship(back_populates="items")
    medicamento: Mapped[Medicamento] = relationship()
