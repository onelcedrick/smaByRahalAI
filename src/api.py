# src/api.py - API REST avec timeout augmenté

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
from src.database import get_all_orders, get_stats, get_all_products, get_product
from src.logger import api, info, ok, err

app = FastAPI(title="SMA + Théorie des Catégories API")

app.mount("/static", StaticFiles(directory="frontend"), name="static")

class OrderInput(BaseModel):
    product_id: int
    quantity: int = 1
    mode: str = "normal"

class OrderResponse(BaseModel):
    order_id: int
    status: str
    path: List[str]
    tracking_number: Optional[str] = None
    error: Optional[str] = None

@app.get("/")
async def root():
    return FileResponse("frontend/index.html")

@app.get("/catalog")
async def catalog_page():
    return FileResponse("frontend/catalog.html")

@app.get("/products")
async def products():
    rows = get_all_products()
    result = []
    for row in rows:
        result.append({
            "id": row[0],
            "name": row[1],
            "price": row[2],
            "stock": row[3],
            "description": row[4]
        })
    return result

@app.post("/run", response_model=OrderResponse)
async def run_order(order: OrderInput):
    order_id = int(time.time() * 1000) % 100000
    
    product = get_product(order.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Produit non trouvé")
    
    order_dict = {
        "id": order_id,
        "product_id": order.product_id,
        "quantity": order.quantity,
        "status": "INIT",
        "mode_actif": order.mode
    }
    
    api(f"Commande reçue {order_id} (Produit: {product[1]}, Qté: {order.quantity}, Mode: {order.mode})")
    
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
    
    # Attendre que le traitement soit terminé (max 10 secondes)
    max_wait = 10
    waited = 0
    while waited < max_wait:
        time.sleep(0.5)
        waited += 0.5
        # Vérifier si le superviseur a terminé la commande
        if order_id in superviseur.tracked_orders:
            status = superviseur.tracked_orders[order_id]["status"]
            if status in ["VALIDE", "ECHEC", "INVALIDE"]:
                break
    
    # Arrêter les agents
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
    return {"stats": get_stats()}

if __name__ == "__main__":
    uvicorn.run("src.api:app", host="0.0.0.0", port=8000, reload=True)
