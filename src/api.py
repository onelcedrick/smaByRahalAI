# src/api.py - API REST avec interface web (Version française)

import time
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List
import uvicorn

from src.sma_core import (
    MessageBus,
    Receptionniste,
    Verificateur,
    Banquier,
    Logistique,
    Superviseur,
    Foncteur
)
from src.database import get_all_orders, get_stats
from src.logger import api, info, ok, err

app = FastAPI(title="SMA + Théorie des Catégories API")

# Servir les fichiers statiques (interface)
app.mount("/static", StaticFiles(directory="frontend"), name="static")

# Modèles de données
class OrderInput(BaseModel):
    product: str
    price: float
    quantity: int = 1
    mode: str = "normal"

class OrderResponse(BaseModel):
    order_id: int
    status: str
    path: List[str]
    tracking_number: Optional[str] = None
    error: Optional[str] = None

# --- Routes API ---

@app.get("/")
async def root():
    """Redirige vers l'interface utilisateur."""
    return FileResponse("frontend/index.html")

@app.post("/run", response_model=OrderResponse)
async def run_order(order: OrderInput):
    """
    Exécute le SMA sur une nouvelle commande.
    """
    order_id = int(time.time() * 1000) % 100000
    
    order_dict = {
        "id": order_id,
        "product": order.product,
        "price": order.price,
        "quantity": order.quantity,
        "status": "INIT",
        "mode_actif": order.mode
    }
    
    api(f"Commande reçue {order_id} (mode: {order.mode})")
    
    # --- Lancement du SMA ---
    bus = MessageBus()
    foncteur = Foncteur(bus, mode=order.mode)
    
    agents = [
        Receptionniste("Receptionniste", bus),
        Verificateur("Verificateur", bus),
        Banquier("Banquier", bus),
        Logistique("Logistique", bus)
    ]
    superviseur = Superviseur(bus)
    agents.append(superviseur)
    
    for agent in agents:
        agent.start()
    
    time.sleep(0.5)
    bus.send("Receptionniste", {"order": order_dict})
    time.sleep(5)
    
    for agent in agents:
        agent.stop()
    for agent in agents:
        agent.join(timeout=1)
    
    report = superviseur.report()
    if order_id not in report:
        raise HTTPException(status_code=500, detail="La commande n'a pas été traitée par le Superviseur")
    
    data = report[order_id]
    return OrderResponse(
        order_id=order_id,
        status=data["status"],
        path=data["path"],
        tracking_number=order_dict.get("tracking_number"),
        error=order_dict.get("error")
    )

@app.get("/history")
async def history():
    """Retourne l'historique complet des commandes."""
    rows = get_all_orders()
    result = []
    for row in rows:
        result.append({
            "id": row[0],
            "product": row[1],
            "price": row[2],
            "quantity": row[3],
            "status": row[4],
            "path": row[5],
            "tracking": row[6],
            "error": row[7],
            "mode": row[8],
            "date": row[9]
        })
    return result

@app.get("/stats")
async def stats():
    """Statistiques sur les commandes."""
    return {"stats": get_stats()}

if __name__ == "__main__":
    uvicorn.run("src.api:app", host="0.0.0.0", port=8000, reload=True)
