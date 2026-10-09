import logging
import os
import re
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from models import Customer, Debt, DebtStatus, Merchant  # noqa: F401  (Merchant registers its table)

load_dotenv()
logger = logging.getLogger("nceda")


# ==========================================
# CONFIGURATION
# ==========================================
def make_engine(url: str):
    """Build the SQLAlchemy engine. SQLite (used by tests) needs special args."""
    echo = os.getenv("SQL_ECHO", "0") == "1"
    if url.startswith("sqlite"):
        return create_engine(
            url,
            echo=echo,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    # pool_pre_ping recovers from connections that Neon closed while idle.
    return create_engine(url, echo=echo, pool_pre_ping=True)


DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Copy .env.example to .env and fill it in."
    )

engine = make_engine(DATABASE_URL)

# Unset -> "*" so the HTML can be opened straight from disk (origin "null") in
# development. In production set ALLOWED_ORIGINS to the real front-end origin.
ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(engine)
    yield


app = FastAPI(title="Nceda Ledger API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,  # no cookies are used; wildcard+credentials is unsafe
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type"],
)


def get_session():
    with Session(engine) as session:
        yield session


# ==========================================
# DATA PAYLOAD SCHEMAS
# ==========================================
_PHONE_RE = re.compile(r"^\+?\d{9,15}$")


class DebtSubmission(BaseModel):
    customer_name: str = Field(min_length=1, max_length=100)
    customer_id: str = Field(pattern=r"^\d{13}$")  # 13-digit South African ID
    customer_phone: str
    amount: float = Field(gt=0, le=1_000_000)
    items: str = Field(min_length=1, max_length=500)

    @field_validator("customer_name", "items")
    @classmethod
    def _strip_and_require_text(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v

    @field_validator("customer_phone")
    @classmethod
    def _normalise_phone(cls, v: str) -> str:
        cleaned = re.sub(r"[\s\-()]", "", v)
        if not _PHONE_RE.match(cleaned):
            raise ValueError("must be a valid phone number (9-15 digits)")
        return cleaned

    @field_validator("amount")
    @classmethod
    def _round_amount(cls, v: float) -> float:
        return round(v, 2)


# ==========================================
# API ENDPOINTS
# ==========================================
@app.get("/")
def read_root():
    return {"message": "Nceda Ledger API is running!"}


@app.get("/health")
def health(session: Session = Depends(get_session)):
    """Liveness + database connectivity check."""
    try:
        session.exec(select(1)).one()
    except SQLAlchemyError:
        logger.exception("Health check failed")
        raise HTTPException(status_code=503, detail="Database unavailable.")
    return {"status": "ok"}


@app.get("/api/ledger")
def get_ledger(
    status: Optional[DebtStatus] = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
):
    """Debts joined with their customer profile, newest first."""
    statement = select(Debt, Customer).join(Customer, Debt.customer_id == Customer.id)
    if status:
        statement = statement.where(Debt.status == status.value)
    statement = (
        statement.order_by(Debt.created_at.desc(), Debt.id.desc())
        .offset(offset)
        .limit(limit)
    )

    return [
        {
            "id": debt.id,
            "customer_name": customer.name,
            "customer_id": customer.national_id,  # the 13-digit ID
            "customer_phone": customer.phone,
            "amount": debt.amount,
            "items": debt.items,
            "status": debt.status,
            "created_at": debt.created_at,
            "discount": debt.discount,
        }
        for debt, customer in session.exec(statement).all()
    ]


@app.post("/api/debts", status_code=201)
def log_new_debt(payload: DebtSubmission, session: Session = Depends(get_session)):
    """Handles the 'Log New Debt' form submission."""
    try:
        customer = session.exec(
            select(Customer).where(Customer.national_id == payload.customer_id)
        ).first()

        if customer:
            # The ID is already registered: the name must match.
            if customer.name.strip().lower() != payload.customer_name.lower():
                # Deliberately do not echo the registered name back (POPIA).
                raise HTTPException(
                    status_code=400,
                    detail="Security Alert: this ID is already registered to a different name.",
                )
        else:
            customer = Customer(
                name=payload.customer_name,
                national_id=payload.customer_id,
                phone=payload.customer_phone,
            )
            session.add(customer)
            session.flush()  # assigns customer.id without committing

        new_debt = Debt(
            customer_id=customer.id,
            amount=payload.amount,
            items=payload.items,
            status=DebtStatus.PENDING.value,
        )
        session.add(new_debt)
        session.commit()  # customer + debt are committed together
        session.refresh(new_debt)

        return {"message": "Debt logged successfully", "debt_id": new_debt.id}

    except HTTPException:
        session.rollback()
        raise
    except SQLAlchemyError:
        session.rollback()
        logger.exception("Failed to log debt")  # never log the payload (contains ID)
        raise HTTPException(status_code=500, detail="Database transaction failed.")


@app.patch("/api/debts/{debt_id}/status")
def update_debt_status(
    debt_id: int, status: DebtStatus, session: Session = Depends(get_session)
):
    """Updates the status when a customer approves consent or pays."""
    debt = session.get(Debt, debt_id)
    if not debt:
        raise HTTPException(status_code=404, detail="Debt not found")

    if debt.status == DebtStatus.SETTLED.value and status != DebtStatus.SETTLED:
        raise HTTPException(status_code=409, detail="A settled debt cannot be reopened.")

    debt.status = status.value
    try:
        session.add(debt)
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        logger.exception("Failed to update debt status")
        raise HTTPException(status_code=500, detail="Database transaction failed.")
    return {"message": f"Status updated to {status.value}"}
