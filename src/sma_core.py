# src/sma_core.py - SMA parallèle avec threads et bus de messages

import threading
import queue
import random
import time
from src.logger import info, ok, err, warn, recv, send, init, sep
from src.modelisation import get_next_state
from src.superviseur import Superviseur, Foncteur
from src.database import init_db

init_db()

# --- 1. BUS DE MESSAGES ---
class MessageBus:
    def __init__(self):
        self.mailboxes = {}
        self.lock = threading.Lock()
    
    def register(self, agent_name):
        with self.lock:
            if agent_name not in self.mailboxes:
                self.mailboxes[agent_name] = queue.Queue()
                init(f"Mailbox created for '{agent_name}'")
    
    def send(self, target, message):
        with self.lock:
            if target in self.mailboxes:
                self.mailboxes[target].put(message)
                order_id = message.get("order", {}).get("id", "?")
                send(f"Message to '{target}' (Order {order_id})")
            else:
                err(f"Target '{target}' unknown !")
            
            # Copie vers le Superviseur (interception)
            if "Superviseur" in self.mailboxes and target != "Superviseur":
                self.mailboxes["Superviseur"].put(message)
    
    def receive(self, agent_name, timeout=0.5):
        if agent_name in self.mailboxes:
            try:
                return self.mailboxes[agent_name].get(timeout=timeout)
            except queue.Empty:
                return None
        return None


# --- 2. AGENT DE BASE ---
class Agent(threading.Thread):
    def __init__(self, name, bus):
        super().__init__()
        self.name = name
        self.bus = bus
        self.bus.register(name)
        self.active = True
        self.daemon = True
    
    def stop(self):
        self.active = False
    
    def process(self, message):
        raise NotImplementedError("Subclasses must implement process()")
    
    def run(self):
        info(f"{self.name} started")
        while self.active:
            msg = self.bus.receive(self.name, timeout=0.3)
            if msg is not None:
                response = self.process(msg)
                if response:
                    self.bus.send(response["target"], response["message"])
            time.sleep(0.05)
        info(f"{self.name} stopped")


# --- 3. AGENTS SPÉCIFIQUES ---

class Receptionniste(Agent):
    def process(self, message):
        order = message.get("order", {})
        recv(f"Raw order {order.get('id', '?')}")
        if "product" not in order or "price" not in order:
            order["status"] = "REFUSED"
            order["error"] = "Invalid format"
            err(f"Order {order['id']} refused")
            return None
        order["state"] = "Created"
        order["status"] = "OK"
        order["history"] = ["Created"]
        ok(f"Order {order['id']} validated, sending to Verificateur")
        return {"target": "Verificateur", "message": {"order": order}}


class Verificateur(Agent):
    def process(self, message):
        order = message.get("order", {})
        recv(f"Order {order.get('id', '?')} (state: {order.get('state', '?')})")
        stock_ok = random.random() < 0.8
        if not stock_ok:
            order["status"] = "FAILED"
            order["error"] = "Out of stock"
            err(f"Order {order['id']} : OUT OF STOCK")
            return {"target": "Banquier", "message": {"order": order}}
        
        next_state = get_next_state(order["state"], "Verify")
        if next_state:
            order["state"] = next_state
            order["status"] = "OK"
            order["history"].append(next_state)
            ok(f"Order {order['id']} verified")
        return {"target": "Banquier", "message": {"order": order}}


class Banquier(Agent):
    def process(self, message):
        order = message.get("order", {})
        recv(f"Order {order.get('id', '?')} (state: {order.get('state', '?')})")
        if order.get("status") == "FAILED":
            warn(f"Order {order['id']} already failed")
            return {"target": "Logistique", "message": {"order": order}}
        
        payment_ok = random.random() < 0.7
        if not payment_ok:
            order["status"] = "FAILED"
            order["error"] = "Payment refused"
            err(f"Order {order['id']} : PAYMENT REFUSED")
            return {"target": "Logistique", "message": {"order": order}}
        
        next_state = get_next_state(order["state"], "Pay")
        if next_state:
            order["state"] = next_state
            order["status"] = "OK"
            order["history"].append(next_state)
            ok(f"Order {order['id']} paid ({order.get('price', '?')} EUR)")
        return {"target": "Logistique", "message": {"order": order}}


class Logistique(Agent):
    def process(self, message):
        order = message.get("order", {})
        recv(f"Order {order.get('id', '?')} (state: {order.get('state', '?')})")
        if order.get("status") == "FAILED":
            warn(f"Order {order['id']} failed, shipping cancelled")
            return {"target": "Superviseur", "message": {"order": order}}
        
        tracking = f"AZ-{random.randint(1000, 9999)}-FR"
        order["tracking_number"] = tracking
        
        next_state = get_next_state(order["state"], "Ship")
        if next_state:
            order["state"] = next_state
            order["history"].append(next_state)
        
        next_state = get_next_state(order["state"], "Deliver")
        if next_state:
            order["state"] = next_state
            order["history"].append(next_state)
        
        order["status"] = "TERMINATED"
        ok(f"Order {order['id']} shipped ! Tracking : {tracking}")
        return {"target": "Superviseur", "message": {"order": order}}


# --- 4. FONCTION DE LANCEMENT ---
def run_sma(order_test, mode="normal"):
    sep("=")
    info(f"STARTING SMA WITH CATEGORIES (mode: {mode})")
    sep("=")
    
    bus = MessageBus()
    foncteur = Foncteur(bus, mode=mode)
    info(f"Foncteur created in mode '{mode}'")
    
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
    order_test["mode_actif"] = mode
    info(f"Injecting order {order_test['id']}")
    bus.send("Receptionniste", {"order": order_test})
    
    time.sleep(6)
    
    for agent in agents:
        agent.stop()
    for agent in agents:
        agent.join(timeout=1)
    
    superviseur.report()
    sep("=")
    info("SMA TERMINATED")
    sep("=")


# --- 5. MAIN ---
if __name__ == "__main__":
    info("Testing SMA + DB")
    order1 = {"id": 1001, "product": "Tablet", "price": 599, "quantity": 1, "status": "INIT"}
    run_sma(order1, mode="normal")
    
    order2 = {"id": 1002, "product": "Headphones", "price": 149, "quantity": 2, "status": "INIT"}
    run_sma(order2, mode="debug")
