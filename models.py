from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from sqlmodel import Field, Relationship, SQLModel


def utcnow() -> datetime:
    """Timezone-aware UTC timestamp (datetime.utcnow() is deprecated)."""
    return datetime.now(timezone.utc)


class DebtStatus(str, Enum):
    PENDING = "PENDING"    # logged by the merchant, awaiting customer consent
    ACTIVE = "ACTIVE"      # customer consented
    OVERDUE = "OVERDUE"    # past due
    SETTLED = "SETTLED"    # paid


# ==========================================
# 1. CUSTOMER MODEL
# ==========================================
class Customer(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str

    # POPIA compliance: the national ID is personal information and must be
    # handled strictly (never log it, never expose it beyond what is needed).
    national_id: str = Field(index=True, unique=True, max_length=13)
    phone: str

    debts: List["Debt"] = Relationship(back_populates="customer")


# ==========================================
# 2. MERCHANT MODEL
# ==========================================
class Merchant(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    store_name: str
    owner_initials: str = Field(max_length=2)
    notification_preference: str = Field(default="WhatsApp & SMS")

    debts: List["Debt"] = Relationship(back_populates="merchant")


# ==========================================
# 3. DEBT (LEDGER) MODEL
# ==========================================
class Debt(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    customer_id: Optional[int] = Field(
        default=None, foreign_key="customer.id", index=True
    )
    merchant_id: Optional[int] = Field(default=None, foreign_key="merchant.id")

    amount: float
    items: str
    status: str = Field(default=DebtStatus.PENDING.value, index=True)
    created_at: datetime = Field(default_factory=utcnow)
    discount: Optional[float] = Field(default=None)

    customer: Optional[Customer] = Relationship(back_populates="debts")
    merchant: Optional[Merchant] = Relationship(back_populates="debts")
