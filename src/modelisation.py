# src/modelisation.py - Modélisation catégorique (graphe)

CATEGORY = {
    "Created": {"Verify": "Verified"},
    "Verified": {"Pay": "Paid"},
    "Paid": {"Ship": "Shipped"},
    "Shipped": {"Deliver": "Delivered"},
    "Delivered": {}
}

def get_next_state(current_state, arrow):
    if current_state in CATEGORY and arrow in CATEGORY[current_state]:
        return CATEGORY[current_state][arrow]
    return None

def compose(start_state, arrows):
    current = start_state
    path = [start_state]
    for arrow in arrows:
        next_state = get_next_state(current, arrow)
        if next_state is None:
            return None
        path.append(next_state)
        current = next_state
    return path
