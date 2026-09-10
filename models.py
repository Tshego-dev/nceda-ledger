from typing import List, Optional
from datetime import datetime
from sqlmodel import Field, SQLModel, Relationship

# ==========================================
# 1. CUSTOMER MODEL
# ==========================================
class Customer(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    
    # POPIA Compliance: National ID must be strictly controlled
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
    
    customer_id: Optional[int] = Field(default=None, foreign_key="customer.id")
    merchant_id: Optional[int] = Field(default=None, foreign_key="merchant.id")
    
    amount: float
    items: str 
    status: str = Field(default="PENDING") 
    created_at: datetime = Field(default_factory=datetime.utcnow)
    discount: Optional[float] = Field(default=None) 
    
    customer: Optional[Customer] = Relationship(back_populates="debts")
    merchant: Optional[Merchant] = Relationship(back_populates="debts")