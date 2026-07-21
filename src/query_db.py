# src/query_db.py - Affiche l'historique des commandes

from src.database import get_all_orders, get_stats
from src.logger import info, sep

def show_history():
    sep("=")
    info("ORDERS HISTORY (Database)")
    sep("=")
    
    orders = get_all_orders()
    if not orders:
        info("No orders found.")
        return
    
    for row in orders:
        oid, product, price, qty, status, path, tracking, error, mode, date = row
        print(f"\n  Order #{oid} ({date})")
        print(f"    Product : {product} (x{qty}) - {price} EUR")
        print(f"    Status  : {status}")
        print(f"    Path    : {path}")
        if tracking:
            print(f"    Tracking: {tracking}")
        if error:
            print(f"    Error   : {error}")
        print(f"    Mode    : {mode}")
    
    stats = get_stats()
    print("\n" + "-"*60)
    info("STATISTICS:")
    for status, count in stats:
        print(f"    {status}: {count} order(s)")
    sep("=")

if __name__ == "__main__":
    show_history()
