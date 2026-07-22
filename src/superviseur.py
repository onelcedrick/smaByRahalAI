# src/superviseur.py - Superviseur et Foncteur (Version française)

import threading
import time
from src.logger import info, ok, warn, err, recv, init
from src.modelisation import CATEGORY
from src.database import save_order

class Superviseur(threading.Thread):
    """
    Agent observateur qui valide les compositions catégoriques.
    """
    def __init__(self, bus):
        super().__init__()
        self.nom = "Superviseur"
        self.bus = bus
        self.bus.register(self.nom)
        self.active = True
        self.daemon = True
        self.tracked_orders = {}  # {id: {"path": [], "status": "..."}}
        self.violations = []
    
    def stop(self):
        self.active = False
    
    def run(self):
        init("Superviseur démarré, validation des compositions...")
        while self.active:
            msg = self.bus.receive(self.nom, timeout=0.3)
            if msg is not None:
                self._analyze(msg)
            time.sleep(0.05)
        info("Superviseur arrêté")
    
    def _analyze(self, message):
        order = message.get("order")
        if not order:
            return
        
        order_id = order.get("id")
        history = order.get("history", [])
        status = order.get("status")
        mode = order.get("mode_actif", "normal")
        
        if order_id not in self.tracked_orders:
            self.tracked_orders[order_id] = {"path": [], "status": "EN_COURS"}
        
        if history and len(history) > len(self.tracked_orders[order_id]["path"]):
            self.tracked_orders[order_id]["path"] = history.copy()
        
        # Si la commande est terminée ou en échec
        if status == "TERMINATED" or status == "FAILED":
            path = self.tracked_orders[order_id]["path"]
            
            if len(path) >= 2:
                valid = True
                for i in range(len(path)-1):
                    dep = path[i]
                    arr = path[i+1]
                    found = False
                    for arrow, dest in CATEGORY.get(dep, {}).items():
                        if dest == arr:
                            found = True
                            break
                    if not found:
                        valid = False
                        violation = f"Transition invalide {dep} -> {arr}"
                        self.violations.append((order_id, violation))
                        warn(f"VIOLATION : {violation}")
                        break
                
                if valid:
                    self.tracked_orders[order_id]["status"] = "VALIDE"
                    ok(f"Commande {order_id} : chemin valide ! {' -> '.join(path)}")
                    save_order(
                        id_cmd=order_id,
                        product=order.get("product", "Inconnu"),
                        price=order.get("price", 0.0),
                        quantity=order.get("quantity", 1),
                        status="VALIDE",
                        path=path,
                        tracking=order.get("tracking_number"),
                        error=None,
                        mode=mode
                    )
                else:
                    self.tracked_orders[order_id]["status"] = "INVALIDE"
                    save_order(
                        id_cmd=order_id,
                        product=order.get("product", "Inconnu"),
                        price=order.get("price", 0.0),
                        quantity=order.get("quantity", 1),
                        status="INVALIDE",
                        path=path,
                        tracking=order.get("tracking_number"),
                        error="Violation de composition",
                        mode=mode
                    )
            else:
                self.tracked_orders[order_id]["status"] = "ECHEC"
                warn(f"Commande {order_id} : chemin incomplet {path}")
                save_order(
                    id_cmd=order_id,
                    product=order.get("product", "Inconnu"),
                    price=order.get("price", 0.0),
                    quantity=order.get("quantity", 1),
                    status="ECHEC",
                    path=path,
                    tracking=order.get("tracking_number"),
                    error=order.get("error", "Échec métier"),
                    mode=mode
                )
    
    def report(self):
        """Génère un rapport des compositions vérifiées."""
        print("\n" + "="*60)
        print("RAPPORT DU SUPERVISEUR")
        print("="*60)
        for oid, data in self.tracked_orders.items():
            path_str = " -> ".join(data["path"]) if data["path"] else "(vide)"
            print(f"  Commande {oid}: {data['status']} | Chemin: {path_str}")
        if self.violations:
            print("\n  Violations détectées :")
            for oid, violation in self.violations:
                print(f"    - Commande {oid}: {violation}")
        print("="*60)
        return self.tracked_orders


class Foncteur:
    """
    Le Foncteur transforme globalement le comportement du SMA
    (ex: mode normal vs debug) sans modifier les agents.
    """
    def __init__(self, bus, mode="normal"):
        self.bus = bus
        self.mode = mode
        self.rules = self._define_rules()
    
    def _define_rules(self):
        if self.mode == "normal":
            return {
                "Verify": {"target": "Verificateur", "action": "Verify"},
                "Pay": {"target": "Banquier", "action": "Pay"},
                "Ship": {"target": "Logistique", "action": "Ship"},
                "Deliver": {"target": "Logistique", "action": "Deliver"}
            }
        elif self.mode == "debug":
            return {
                "Verify": {"target": "Verificateur", "action": "Verify_DEBUG", "delay": 0.3},
                "Pay": {"target": "Banquier", "action": "Pay_DEBUG", "delay": 0.3},
                "Ship": {"target": "Logistique", "action": "Ship_DEBUG", "delay": 0.2},
                "Deliver": {"target": "Logistique", "action": "Deliver_DEBUG", "delay": 0.2}
            }
        return {}
    
    def apply(self, arrow, order):
        """Applique la transformation du foncteur à une flèche."""
        if arrow in self.rules:
            rule = self.rules[arrow]
            order["mode_actif"] = self.mode
            if "delay" in rule:
                time.sleep(rule["delay"])
            return {
                "target": rule["target"],
                "message": {"order": order, "action": rule["action"]}
            }
        return None
