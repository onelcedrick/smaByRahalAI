# src/modelisation.py - Modélisation catégorique (graphe)

from src.logger import info, warn, ok

# La catégorie : les objets sont les états, les flèches les transitions
CATEGORY = {
    "Created": {          # Objet (état initial)
        "Verify": "Verified"
    },
    "Verified": {
        "Pay": "Paid"
    },
    "Paid": {
        "Ship": "Shipped"
    },
    "Shipped": {
        "Deliver": "Delivered"
    },
    "Delivered": {}       # Objet terminal
}

def get_next_state(current_state, arrow):
    """Applique une flèche à un objet. Retourne l'état suivant ou None."""
    if current_state in CATEGORY and arrow in CATEGORY[current_state]:
        return CATEGORY[current_state][arrow]
    return None

def compose(start_state, arrows):
    """
    Vérifie la composition (loi de la catégorie).
    Retourne le chemin complet si réussi, sinon None.
    """
    current = start_state
    path = [start_state]
    
    for arrow in arrows:
        next_state = get_next_state(current, arrow)
        if next_state is None:
            warn(f"Composition impossible : arrow '{arrow}' cannot follow '{current}'")
            return None
        path.append(next_state)
        current = next_state
    
    ok(f"Composition valid : {' -> '.join(path)}")
    return path

if __name__ == "__main__":
    info("Testing categorical model...")
    compose("Created", ["Verify", "Pay", "Ship", "Deliver"])
    compose("Created", ["Pay"])  # Invalid
