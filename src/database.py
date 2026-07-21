# src/database.py - Gestion de la base de données SQLite

import sqlite3
from src.logger import db, ok, err

DB_PATH = "sma.db"

def init_db():
    """Crée la table si elle n'existe pas."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY,
            product TEXT,
            price REAL,
            quantity INTEGER,
            status TEXT,
            path TEXT,
            tracking_number TEXT,
            error TEXT,
            mode TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
    db("Database initialized (sma.db)")

def save_order(id_cmd, product, price, quantity, status, path, tracking=None, error=None, mode="normal"):
    """Sauvegarde ou met à jour une commande."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    path_str = " -> ".join(path) if path else ""
    
    c.execute('''
        INSERT OR REPLACE INTO orders 
        (id, product, price, quantity, status, path, tracking_number, error, mode)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (id_cmd, product, price, quantity, status, path_str, tracking, error, mode))
    
    conn.commit()
    conn.close()
    ok(f"Order {id_cmd} saved (status: {status})")

def get_all_orders():
    """Récupère toutes les commandes triées par date."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT * FROM orders ORDER BY created_at DESC')
    rows = c.fetchall()
    conn.close()
    return rows

def get_order_by_id(id_cmd):
    """Récupère une commande spécifique."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT * FROM orders WHERE id = ?', (id_cmd,))
    row = c.fetchone()
    conn.close()
    return row

def get_stats():
    """Donne des statistiques sur les commandes."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT status, COUNT(*) FROM orders GROUP BY status')
    stats = c.fetchall()
    conn.close()
    return stats
