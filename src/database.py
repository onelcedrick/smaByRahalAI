# src/database.py - Connexion à la base existante (table produit)

import sqlite3
from src.logger import db, ok, err

DB_PATH = "sma.db"   # Changez ici si votre base est ailleurs

def init_db():
    """Initialise les tables SMA et s'adapte à la table produit existante."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # --- Vérifier / créer la table produit ---
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='produit'")
    if c.fetchone():
        db("Table 'produit' existante trouvée.")
        # Vérifier la présence de la colonne 'stock'
        c.execute("PRAGMA table_info(produit)")
        cols = [col[1] for col in c.fetchall()]
        if 'stock' not in cols:
            c.execute("ALTER TABLE produit ADD COLUMN stock INTEGER DEFAULT 10")
            conn.commit()
            db("Colonne 'stock' ajoutée à 'produit'.")
    else:
        db("Table 'produit' non trouvée. Création...")
        c.execute('''
            CREATE TABLE produit (
                idP INTEGER PRIMARY KEY AUTOINCREMENT,
                nom TEXT NOT NULL,
                prix REAL NOT NULL,
                stock INTEGER DEFAULT 10,
                description TEXT
            )
        ''')
        # Peuplement initial
        produits = [
            ("UltraBook Pro", 1299.99, 5, "Ordinateur portable"),
            ("SmartPhone X", 899.00, 8, "Smartphone"),
            ("Casque Audio Pro", 149.99, 15, "Casque sans fil"),
            ("Tablette Lite", 399.00, 3, "Tablette"),
            ("Souris Ergonomique", 59.99, 20, "Souris sans fil")
        ]
        c.executemany("INSERT INTO produit (nom, prix, stock, description) VALUES (?,?,?,?)", produits)
        conn.commit()
        db("Catalogue initial créé (5 produits).")
    
    # --- Table historique SMA (indépendante) ---
    c.execute('''
        CREATE TABLE IF NOT EXISTS sma_orders (
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
    db("Base de données prête.")


# --- Accès aux produits ---
def get_all_products():
    """Retourne (idP, nom, prix, stock, description)."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT idP, nom, prix, stock, description FROM produit ORDER BY nom')
    rows = c.fetchall()
    conn.close()
    return rows

def get_product(product_id):
    """Retourne un produit par son idP."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT idP, nom, prix, stock, description FROM produit WHERE idP = ?', (product_id,))
    row = c.fetchone()
    conn.close()
    return row

def update_stock(product_id, delta):
    """Met à jour le stock (delta négatif pour vente)."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE produit SET stock = stock + ? WHERE idP = ?', (delta, product_id))
    conn.commit()
    conn.close()
    db(f"Stock produit {product_id} mis à jour ({delta})")


# --- Historique SMA ---
def save_order(id_cmd, product, price, quantity, status, path, tracking=None, error=None, mode="normal"):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    path_str = " -> ".join(path) if path else ""
    c.execute('''
        INSERT OR REPLACE INTO sma_orders 
        (id, product, price, quantity, status, path, tracking_number, error, mode)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (id_cmd, product, price, quantity, status, path_str, tracking, error, mode))
    conn.commit()
    conn.close()
    ok(f"Commande SMA {id_cmd} sauvegardée")

def get_all_orders():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT * FROM sma_orders ORDER BY created_at DESC')
    rows = c.fetchall()
    conn.close()
    return rows

def get_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT status, COUNT(*) FROM sma_orders GROUP BY status')
    stats = c.fetchall()
    conn.close()
    return stats
