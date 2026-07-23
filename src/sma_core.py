# src/sma_core.py - SMA parallèle (Vérificateur avec stock réel)

import threading
import queue
import random
import time
from src.logger import info, ok, err, warn, recv, send, init, sep
from src.modelisation import get_next_state
from src.superviseur import Superviseur, Foncteur
from src.database import init_db, get_product, update_stock

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
                init(f"Boîte aux lettres créée pour '{agent_name}'")
    
    def send(self, target, message):
        with self.lock:
            if target in self.mailboxes:
                self.mailboxes[target].put(message)
                order_id = message.get("order", {}).get("id", "?")
                send(f"Message vers '{target}' (Commande {order_id})")
            else:
                err(f"Destinataire '{target}' inconnu !")
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
    def process(self, message):
        order = message.get("order", {})
        recv(f"Commande brute {order.get('id', '?')} - Contenu reçu: {order}")
        
        # Vérification stricte des champs obligatoires
        product_id = order.get("product_id")
        quantity = order.get("quantity")
        
        if product_id is None:
            err(f"Commande {order.get('id', '?')} refusée : 'product_id' manquant ou nul")
            order["status"] = "REFUSED"
            order["error"] = "Format invalide (product_id manquant)"
            return None
        
        if quantity is None or quantity <= 0:
            err(f"Commande {order.get('id', '?')} refusée : quantité invalide ({quantity})")
            order["status"] = "REFUSED"
            order["error"] = "Quantité invalide"
            return None
        
        # Récupération du produit en base
        product = get_product(product_id)
        if not product:
            order["status"] = "REFUSED"
            order["error"] = "Produit non trouvé en base"
            err(f"Commande {order['id']} refusée : produit inconnu (id={product_id})")
            return None
        
        # Ajout des infos produit (snapshot)
        order["product_name"] = product[1]   # nom
        order["price"] = product[2]          # prix
        order["stock"] = product[3]          # stock actuel
        
        order["state"] = "Created"
        order["status"] = "OK"
        order["history"] = ["Created"]
        ok(f"Commande {order['id']} validée ({product[1]}) - Envoi au Vérificateur")
        return {"target": "Verificateur", "message": {"order": order}}


class Verificateur(Agent):
    def process(self, message):
        order = message.get("order", {})
        recv(f"Commande {order.get('id', '?')} (état: {order.get('state', '?')})")
        
        product_id = order.get("product_id")
        quantity = order.get("quantity", 1)
        
        # Re-vérification du stock en base (au cas où)
        product = get_product(product_id)
        if not product:
            order["status"] = "FAILED"
            order["error"] = "Produit non trouvé"
            err(f"Commande {order['id']} : PRODUIT INCONNU")
            return {"target": "Banquier", "message": {"order": order}}
        
        # Vérification de la disponibilité
        if product[3] < quantity:
            order["status"] = "FAILED"
            order["error"] = f"Stock insuffisant (demande: {quantity}, disponible: {product[3]})"
            err(f"Commande {order['id']} : STOCK INSUFFISANT")
            return {"target": "Banquier", "message": {"order": order}}
        
        # Décrémenter le stock
        update_stock(product_id, -quantity)
        
        # Appliquer la flèche "Verify"
        next_state = get_next_state(order["state"], "Verify")
        if next_state:
            order["state"] = next_state
            order["status"] = "OK"
            order["history"].append(next_state)
            ok(f"Commande {order['id']} vérifiée (Stock OK, nouveau stock: {product[3] - quantity})")
        return {"target": "Banquier", "message": {"order": order}}


class Banquier(Agent):
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
    info("Test du SMA avec Catalogue Produits")
    # Exemple de commande avec product_id (1 = UltraBook Pro)
    order1 = {"id": 1001, "product_id": 1, "quantity": 1, "status": "INIT"}
    run_sma(order1, mode="normal")
    
    order2 = {"id": 1002, "product_id": 3, "quantity": 2, "status": "INIT"}  # Casque Audio Pro
    run_sma(order2, mode="debug")
