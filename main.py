import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select, create_engine, SQLModel
from pydantic import BaseModel
from dotenv import load_dotenv

# Import the database schemas
from models import Customer, Merchant, Debt

# Load the Neon connection string
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL, echo=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(engine)
    yield

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_session():
    with Session(engine) as session:
        yield session

# ==========================================
# DATA PAYLOAD SCHEMAS
# ==========================================
class DebtSubmission(BaseModel):
    customer_name: str
    customer_id: str
    customer_phone: str
    amount: float
    items: str

# ==========================================
# API ENDPOINTS
# ==========================================

@app.get("/")
def read_root():
    return {"message": "Nceda Ledger API is running!"}

@app.get("/api/ledger")
def get_ledger(session: Session = Depends(get_session)):
    """Fetches all debts AND joins the customer data to populate the frontend."""
    # Perform a SQL JOIN to get the Customer profile linked to each Debt
    statement = select(Debt, Customer).join(Customer)
    results = session.exec(statement).all()
    
    formatted_debts = []
    for debt, customer in results:
        formatted_debts.append({
            "id": debt.id,
            "customer_name": customer.name,
            "customer_id": customer.national_id,  # The 13-digit ID
            "customer_phone": customer.phone,
            "amount": debt.amount,
            "items": debt.items,
            "status": debt.status,
            "created_at": debt.created_at,
            "discount": debt.discount
        })
        
    return formatted_debts

@app.post("/api/debts")
def log_new_debt(payload: DebtSubmission, session: Session = Depends(get_session)):
    """Handles the 'Log New Debt' form submission."""
    try:
        # 1. Check if the ID already exists in the database
        customer = session.exec(select(Customer).where(Customer.national_id == payload.customer_id)).first()
        
        # 2. If the ID exists, verify the name matches!
        if customer:
            if customer.name.strip().lower() != payload.customer_name.strip().lower():
                raise HTTPException(
                    status_code=400, 
                    detail=f"Security Alert: ID {payload.customer_id} is already registered to {customer.name}."
                )
        
        # 3. If ID does not exist, safely create a new profile
        else:
            customer = Customer(
                name=payload.customer_name,
                national_id=payload.customer_id,
                phone=payload.customer_phone
            )
            session.add(customer)
            session.commit()
            session.refresh(customer)

        # 4. Create the new debt record
        new_debt = Debt(
            customer_id=customer.id, 
            amount=payload.amount,
            items=payload.items,
            status="PENDING"
        )
        
        session.add(new_debt)
        session.commit()
        session.refresh(new_debt)
        
        return {"message": "Debt logged successfully", "debt_id": new_debt.id}
    
    except HTTPException:
        # Pass our custom 400 security alert straight to the frontend
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail="Database transaction failed.")

@app.patch("/api/debts/{debt_id}/status")
def update_debt_status(debt_id: int, status: str, session: Session = Depends(get_session)):
    """Updates the status when a customer approves consent or pays."""
    debt = session.get(Debt, debt_id)
    if not debt:
        raise HTTPException(status_code=404, detail="Debt not found")
        
    debt.status = status
    session.add(debt)
    session.commit()
    return {"message": f"Status updated to {status}"}