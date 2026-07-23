# src/sma_core.py - SMA parallèle avec délais par agent

import threading
import queue
import random
import time
from src.logger import info, ok, err, warn, recv, send, init, sep
from src.modelisation import get_next_state
from src.superviseur import Superviseur, Foncteur
from src.database import init_db, get_product, update_stock

init_db()

# --- 0. LOG COLLECTOR ---
class LogCollector:
    def __init__(self, order_id, storage):
        self.order_id = order_id
        self.storage = storage
        self.lock = threading.Lock()
    
    def log(self, message, type="info"):
        with self.lock:
            if self.order_id in self.storage:
                self.storage[self.order_id].append({
                    "time": time.strftime("%H:%M:%S"),
                    "message": message,
                    "type": type
                })

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
    def __init__(self, name, bus, log_collector):
        super().__init__()
        self.name = name
        self.bus = bus
        self.bus.register(name)
        self.active = True
        self.daemon = True
        self.log_collector = log_collector
        self.delay = 1.5  # délai par défaut (en secondes)
    
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

# --- 3. AGENTS SPÉCIFIQUES AVEC DÉLAIS ---
class Receptionniste(Agent):
    def process(self, message):
        order = message.get("order", {})
        self.log_collector.log(f"[Receptionniste] Commande brute {order.get('id', '?')} - Contenu: {order}", "recv")
        
        product_id = order.get("product_id")
        quantity = order.get("quantity")
        if product_id is None:
            err(f"Commande {order.get('id', '?')} refusée : product_id manquant")
            self.log_collector.log("[Receptionniste] Erreur : product_id manquant", "err")
            order["status"] = "REFUSED"
            order["error"] = "Format invalide (product_id manquant)"
            return None
        if quantity is None or quantity <= 0:
            err(f"Commande {order.get('id', '?')} refusée : quantité invalide")
            self.log_collector.log("[Receptionniste] Erreur : quantité invalide", "err")
            order["status"] = "REFUSED"
            order["error"] = "Quantité invalide"
            return None
        
        product = get_product(product_id)
        if not product:
            order["status"] = "REFUSED"
            order["error"] = "Produit non trouvé en base"
            self.log_collector.log(f"[Receptionniste] Produit {product_id} inconnu", "err")
            return None
        
        order["product_name"] = product[1]
        order["price"] = product[2]
        order["stock"] = product[3]
        order["state"] = "Created"
        order["status"] = "OK"
        order["history"] = ["Created"]
        self.log_collector.log(f"[Receptionniste] Commande {order['id']} validée ({product[1]})", "ok")
        # Délai de traitement
        time.sleep(self.delay)
        return {"target": "Verificateur", "message": {"order": order}}

class Verificateur(Agent):
    def process(self, message):
        order = message.get("order", {})
        self.log_collector.log(f"[Verificateur] Commande {order.get('id', '?')} (état: {order.get('state', '?')})", "recv")
        product_id = order.get("product_id")
        quantity = order.get("quantity", 1)
        product = get_product(product_id)
        if not product:
            order["status"] = "FAILED"
            order["error"] = "Produit non trouvé"
            self.log_collector.log("[Verificateur] Produit inconnu", "err")
            time.sleep(self.delay)
            return {"target": "Banquier", "message": {"order": order}}
        if product[3] < quantity:
            order["status"] = "FAILED"
            order["error"] = f"Stock insuffisant (demande: {quantity}, disponible: {product[3]})"
            self.log_collector.log("[Verificateur] Stock insuffisant", "err")
            time.sleep(self.delay)
            return {"target": "Banquier", "message": {"order": order}}
        update_stock(product_id, -quantity)
        next_state = get_next_state(order["state"], "Verify")
        if next_state:
            order["state"] = next_state
            order["status"] = "OK"
            order["history"].append(next_state)
            self.log_collector.log(f"[Verificateur] Commande {order['id']} vérifiée (stock OK)", "ok")
        time.sleep(self.delay)
        return {"target": "Banquier", "message": {"order": order}}

class Banquier(Agent):
    def process(self, message):
        order = message.get("order", {})
        self.log_collector.log(f"[Banquier] Commande {order.get('id', '?')} (état: {order.get('state', '?')})", "recv")
        if order.get("status") == "FAILED":
            self.log_collector.log("[Banquier] Commande déjà en échec", "warn")
            time.sleep(self.delay)
            return {"target": "Logistique", "message": {"order": order}}
        payment_ok = random.random() < 0.7
        if not payment_ok:
            order["status"] = "FAILED"
            order["error"] = "Paiement refusé"
            self.log_collector.log("[Banquier] Paiement refusé", "err")
            time.sleep(self.delay)
            return {"target": "Logistique", "message": {"order": order}}
        next_state = get_next_state(order["state"], "Pay")
        if next_state:
            order["state"] = next_state
            order["status"] = "OK"
            order["history"].append(next_state)
            self.log_collector.log(f"[Banquier] Commande {order['id']} payée", "ok")
        time.sleep(self.delay)
        return {"target": "Logistique", "message": {"order": order}}

class Logistique(Agent):
    def process(self, message):
        order = message.get("order", {})
        self.log_collector.log(f"[Logistique] Commande {order.get('id', '?')} (état: {order.get('state', '?')})", "recv")
        if order.get("status") == "FAILED":
            self.log_collector.log("[Logistique] Commande en échec, expédition annulée", "warn")
            time.sleep(self.delay)
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
        self.log_collector.log(f"[Logistique] Commande {order['id']} expédiée ! Suivi : {tracking}", "ok")
        time.sleep(self.delay)
        return {"target": "Superviseur", "message": {"order": order}}

# --- Le Superviseur est défini dans superviseur.py, on n'ajoute pas de délai ici (il est déjà réactif).
# Mais on peut lui ajouter un petit délai pour éviter les doublons. On le fera dans superviseur.py.

# --- 4. FONCTION DE LANCEMENT (pour compatibilité, non utilisée directement) ---
def run_sma(order_test, mode="normal"):
    # Cette fonction n'est pas utilisée via l'API, mais on la garde pour le test en ligne de commande.
    # L'API utilise le LogCollector et les agents avec délais.
    pass
