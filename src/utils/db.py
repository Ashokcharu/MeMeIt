import sqlite3
from src.config import DB_PATH

def get_connection():
    """
    Returns a connection to the SQLite database.
    """
    return sqlite3.connect(DB_PATH)
