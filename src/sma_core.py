# src/sma_core.py - SMA parallèle avec bus de messages (Version française)

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
    """Centralise les échanges entre agents."""
    def __init__(self):
        self.mailboxes = {}
        self.lock = threading.Lock()
    
    def register(self, agent_name):
        with self.lock:
            if agent_name not in self.mailboxes:
                self.mailboxes[agent_name] = queue.Queue()
                init(f"Boîte aux lettres créée pour '{agent_name}'")
    
    def send(self, target, message):
        with self.lock:
            if target in self.mailboxes:
                self.mailboxes[target].put(message)
                order_id = message.get("order", {}).get("id", "?")
                send(f"Message vers '{target}' (Commande {order_id})")
            else:
                err(f"Destinataire '{target}' inconnu !")
            
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
    """Classe abstraite pour tous les agents."""
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
        raise NotImplementedError("Les sous-classes doivent implémenter process()")
    
    def run(self):
        info(f"{self.name} démarré")
        while self.active:
            msg = self.bus.receive(self.name, timeout=0.3)
            if msg is not None:
                response = self.process(msg)
                if response:
                    self.bus.send(response["target"], response["message"])
            time.sleep(0.05)
        info(f"{self.name} arrêté")


# --- 3. AGENTS SPÉCIFIQUES ---

class Receptionniste(Agent):
    """Agent 1 : Valide le format et initie la commande."""
    def process(self, message):
        order = message.get("order", {})
        recv(f"Commande brute {order.get('id', '?')}")
        if "product" not in order or "price" not in order:
            order["status"] = "REFUSED"
            order["error"] = "Format invalide"
            err(f"Commande {order['id']} refusée")
            return None
        order["state"] = "Created"
        order["status"] = "OK"
        order["history"] = ["Created"]
        ok(f"Commande {order['id']} validée, envoi au Vérificateur")
        return {"target": "Verificateur", "message": {"order": order}}


class Verificateur(Agent):
    """Agent 2 : Vérifie la disponibilité du stock."""
    def process(self, message):
        order = message.get("order", {})
        recv(f"Commande {order.get('id', '?')} (état: {order.get('state', '?')})")
        stock_ok = random.random() < 0.8
        if not stock_ok:
            order["status"] = "FAILED"
            order["error"] = "Stock insuffisant"
            err(f"Commande {order['id']} : RUPTURE DE STOCK")
            return {"target": "Banquier", "message": {"order": order}}
        
        next_state = get_next_state(order["state"], "Verify")
        if next_state:
            order["state"] = next_state
            order["status"] = "OK"
            order["history"].append(next_state)
            ok(f"Commande {order['id']} vérifiée")
        return {"target": "Banquier", "message": {"order": order}}


class Banquier(Agent):
    """Agent 3 : Traite le paiement."""
    def process(self, message):
        order = message.get("order", {})
        recv(f"Commande {order.get('id', '?')} (état: {order.get('state', '?')})")
        if order.get("status") == "FAILED":
            warn(f"Commande {order['id']} déjà en échec")
            return {"target": "Logistique", "message": {"order": order}}
        
        payment_ok = random.random() < 0.7
        if not payment_ok:
            order["status"] = "FAILED"
            order["error"] = "Paiement refusé"
            err(f"Commande {order['id']} : PAIEMENT REFUSÉ")
            return {"target": "Logistique", "message": {"order": order}}
        
        next_state = get_next_state(order["state"], "Pay")
        if next_state:
            order["state"] = next_state
            order["status"] = "OK"
            order["history"].append(next_state)
            ok(f"Commande {order['id']} payée ({order.get('price', '?')} EUR)")
        return {"target": "Logistique", "message": {"order": order}}


class Logistique(Agent):
    """Agent 4 : Prépare et expédie la commande."""
    def process(self, message):
        order = message.get("order", {})
        recv(f"Commande {order.get('id', '?')} (état: {order.get('state', '?')})")
        if order.get("status") == "FAILED":
            warn(f"Commande {order['id']} en échec, expédition annulée")
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
        ok(f"Commande {order['id']} expédiée ! Suivi : {tracking}")
        return {"target": "Superviseur", "message": {"order": order}}


# --- 4. FONCTION DE LANCEMENT ---
def run_sma(order_test, mode="normal"):
    sep("=")
    info(f"LANCEMENT DU SMA AVEC CATÉGORIES (mode: {mode})")
    sep("=")
    
    bus = MessageBus()
    foncteur = Foncteur(bus, mode=mode)
    info(f"Foncteur créé en mode '{mode}'")
    
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
    info(f"Injection de la commande {order_test['id']}")
    bus.send("Receptionniste", {"order": order_test})
    
    time.sleep(6)
    
    for agent in agents:
        agent.stop()
    for agent in agents:
        agent.join(timeout=1)
    
    superviseur.report()
    sep("=")
    info("SMA TERMINÉ")
    sep("=")


# --- 5. MAIN ---
if __name__ == "__main__":
    info("Test du SMA + Base de données")
    order1 = {"id": 1001, "product": "Tablette", "price": 599, "quantity": 1, "status": "INIT"}
    run_sma(order1, mode="normal")
    
    order2 = {"id": 1002, "product": "Casque Audio", "price": 149, "quantity": 2, "status": "INIT"}
    run_sma(order2, mode="debug")
