from datetime import datetime
import sqlite3
import mysql.connector
import hashlib
import os
import json
import uuid

CRED_FILE = "..\login_state.json"
DB_PATH = '..\Local_DB.db'

server_ip = "localhost"


# ---------------------------------------------------------------------------
# Utility — hashing password
# ---------------------------------------------------------------------------

def _hash_password(password: str) -> str:
    """Restituisce l'hash SHA-256 della password in formato esadecimale."""
    return hashlib.sha256(password.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Creazione tabelle
# ---------------------------------------------------------------------------

def create_sqlite_tables():
    with connect_local() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS app (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                link TEXT UNIQUE NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS promemoria (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                desc TEXT NOT NULL,
                scadenza DATE NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversazione (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid TEXT UNIQUE NOT NULL,
                richiesta TEXT NOT NULL,
                risposta TEXT NOT NULL,
                id_chat TEXT NOT NULL,
                data DATETIME NOT NULL,
                FOREIGN KEY (id_chat) REFERENCES chat(uuid)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS utente (
                email VARCHAR(255) PRIMARY KEY
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tipo_chat (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat (
                uuid TEXT PRIMARY KEY,
                nome TEXT NOT NULL,
                id_utente VARCHAR(255) NOT NULL,
                id_tipo INTEGER NOT NULL,
                data DATETIME NOT NULL,
                FOREIGN KEY (id_utente) REFERENCES utente(email)
                FOREIGN KEY (id_tipo) REFERENCES tipo_chat(id)
            )
        ''')
        conn.commit()


def create_mysql_tables():
    conn = connect()
    if conn is None:
        return
    cursor = conn.cursor()
    try:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS utenti (
                email VARCHAR(255) PRIMARY KEY UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tipo_chat (
                id INT PRIMARY KEY AUTO_INCREMENT,
                nome TEXT NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat (
                uuid VARCHAR(36) PRIMARY KEY,
                nome TEXT NOT NULL,
                id_utente VARCHAR(255) NOT NULL,
                id_tipo INTEGER NOT NULL,
                data DATETIME NOT NULL,
                FOREIGN KEY (id_utente) REFERENCES utente(email)
                FOREIGN KEY (id_tipo) REFERENCES tipo_chat(id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversazione (
                uuid VARCHAR(36) PRIMARY KEY,
                richiesta LONGTEXT NOT NULL,
                risposta LONGTEXT NOT NULL,
                id_chat VARCHAR(36) NOT NULL,
                data DATETIME NOT NULL,
                FOREIGN KEY (id_chat) REFERENCES chat(uuid)
            )
        ''')
        conn.commit()
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# Server MySQL DB
# ---------------------------------------------------------------------------

def connect():
    try:
        return mysql.connector.connect(
            host=server_ip,
            user="root",
            password="",
            database="login"
        )
    except mysql.connector.Error as err:
        print(f"[ERRORE CONNESSIONE MYSQL] {err}")
        return None


def insert_utente(email, password):
    conn = connect()
    if conn is None:
        print("Impossibile connettersi al database MySQL.")
        return False
    cursor = conn.cursor()
    try:
        hashed = _hash_password(password)
        cursor.execute("INSERT INTO utenti (email, password) VALUES (%s, %s)", (email, hashed))
        conn.commit()
        return True
    except Exception as e:
        print("Errore durante l'inserimento:", e)
        return False
    finally:
        cursor.close()
        conn.close()


def check_credenziali(email, password):
    conn = connect()
    if conn is None:
        print("Impossibile connettersi al database MySQL.")
        return False
    cursor = conn.cursor()
    try:
        hashed = _hash_password(password)
        cursor.execute("SELECT * FROM utenti WHERE email = %s AND password = %s", (email, hashed))
        result = cursor.fetchone()
        return result is not None
    finally:
        cursor.close()
        conn.close()


def delete_utente(email, password):
    conn = connect()
    if conn is None:
        print("Impossibile connettersi al database MySQL.")
        return False
    cursor = conn.cursor()
    try:
        hashed = _hash_password(password)
        cursor.execute("DELETE FROM utenti WHERE email = %s AND password = %s", (email, hashed))
        conn.commit()
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# Local SQLite DB
# ---------------------------------------------------------------------------

def connect_local():
    return sqlite3.connect(DB_PATH)


# ── Funzioni APP ─────────────────────────────────────────────────────────────

def insert_app(nome, link):
    try:
        with connect_local() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO app (nome, link) VALUES (?, ?)", (nome, link))
            conn.commit()
            print("App inserita con successo.")
    except sqlite3.IntegrityError:
        print("Errore: app già esistente.")


def change_name(id, nome):
    with connect_local() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE app SET nome = ? WHERE id = ?", (nome, id))
        conn.commit()


def change_link(id, link):
    with connect_local() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE app SET link = ? WHERE id = ?", (link, id))
        conn.commit()


def delete_app(id):
    with connect_local() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM app WHERE id = ?", (id,))
        conn.commit()


def get_link_by_name(nome):
    with connect_local() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT link FROM app WHERE LOWER(nome) = ?", (nome.lower(),))
        result = cursor.fetchone()
        return result[0] if result else None


def get_all_names():
    with connect_local() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT LOWER(nome) FROM app")
        return [row[0] for row in cursor.fetchall()]


def show_apps():
    with connect_local() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM app")
        for row in cursor.fetchall():
            print(row)


# ── Funzioni promemoria ───────────────────────────────────────────────────────

def insert_promemoria(desc, scadenza):
    with connect_local() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO promemoria (desc, scadenza) VALUES (?, ?)", (desc, scadenza))
        conn.commit()
        print("Promemoria inserito con successo.")


def delete_promemoria(id):
    with connect_local() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM promemoria WHERE id = ?", (id,))
        conn.commit()


def get_all_scadenze():
    with connect_local() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, scadenza FROM promemoria ORDER BY scadenza ASC")
        return cursor.fetchall()


def get_desc_by_id(id):
    with connect_local() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT desc FROM promemoria WHERE id = ?", (id,))
        result = cursor.fetchone()
        return result[0] if result else None


def get_all_promemoria():
    with connect_local() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM promemoria ORDER BY scadenza ASC")
        return cursor.fetchall()


# ── Funzioni conversazione ────────────────────────────────────────────────────

def insert_conversazione(richiesta, risposta, id_chat):
    with connect_local() as conn:
        cursor = conn.cursor()
        uuid_val = str(uuid.uuid4())
        now = datetime.now().isoformat(" ")
        cursor.execute(
            "INSERT INTO conversazione (uuid, richiesta, risposta, id_chat, data) VALUES (?, ?, ?, ?, ?)",
            (uuid_val, richiesta, risposta, id_chat, now)
        )
        conn.commit()
        print("Conversazione inserita con successo.")


def get_last_id():
    with connect_local() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(id) FROM conversazione")
        result = cursor.fetchone()
        return result[0] if result else None


def get_risposta_by_id(id):
    with connect_local() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT risposta FROM conversazione WHERE id = ?", (id,))
        result = cursor.fetchone()
        return result[0] if result else None


def get_all_conversazioni():
    with connect_local() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM conversazione")
        return cursor.fetchall()


def get_conversazioni_by_chat_id(id_chat):
    with connect_local() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT richiesta, risposta FROM conversazione WHERE id_chat = ? ORDER BY id ASC",
            (id_chat,)
        )
        return cursor.fetchall()


def delete_conversazioni_by_chat_id(id_chat):
    """Elimina tutte le conversazioni associate alla chat indicata."""
    with connect_local() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM conversazione WHERE id_chat = ?", (id_chat,))
        conn.commit()


# ── Funzioni chat ─────────────────────────────────────────────────────────────

def _get_current_user() -> str:
    """
    Legge l'email dell'utente corrente dal file di credenziali.
    Ritorna 'Utente sconosciuto' se il file non esiste o è malformato.
    """
    try:
        if os.path.exists(CRED_FILE):
            with open(CRED_FILE, 'r') as f:
                data = json.load(f)
                return data.get('email', 'Utente sconosciuto')
    except (json.JSONDecodeError, OSError):
        pass
    return 'Utente sconosciuto'


def insert_chat(nome=None):
    with connect_local() as conn:
        cursor = conn.cursor()
        uuid_val = str(uuid.uuid4())

        if nome is None:
            nome = "Vocale"
            id_tipo = "2"
        else:
            id_tipo = "1"

        id_utente = _get_current_user()
        now = datetime.now().isoformat(" ")
        cursor.execute(
            "INSERT INTO chat (uuid, nome, id_utente, id_tipo, data) VALUES (?, ?, ?, ?, ?)",
            (uuid_val, nome, id_utente, id_tipo, now)
        )
        conn.commit()
        print("Chat inserita con successo.")


def update_chat_name(nome, uuid):
    with connect_local() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE chat SET nome = ? WHERE uuid = ?", (nome, uuid))
        conn.commit()
        print("Nome della chat modificato con successo.")


def delete_chat(uuid):
    with connect_local() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM chat WHERE uuid = ?", (uuid,))
        conn.commit()
        print("Chat eliminata con successo.")


def get_chat_name_by_id(uuid):
    with connect_local() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT nome FROM chat WHERE uuid = ?", (uuid,))
        result = cursor.fetchone()
        return result[0] if result else None


def get_latest_vocal_uuid():
    with connect_local() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT uuid
            FROM chat AS C
            JOIN tipo_chat AS T ON T.id = C.id_tipo
            WHERE T.nome = "vocale"
            ORDER BY data DESC
            LIMIT 1
        """)
        result = cursor.fetchone()
        return result[0] if result else None


def get_latest_vocal_date():
    with connect_local() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT data
            FROM chat AS C
            JOIN tipo_chat AS T ON T.id = C.id_tipo
            WHERE T.nome = "vocale"
            ORDER BY data DESC
            LIMIT 1
        """)
        result = cursor.fetchone()
        return result[0] if result else None


def get_all_text_chat():
    with connect_local() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM chat AS C
            JOIN tipo_chat AS T ON T.id = C.id_tipo
            WHERE T.nome = "testuale"
        """)
        return cursor.fetchall()


def get_all_chat():
    with connect_local() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM chat")
        return cursor.fetchall()


# ---------------------------------------------------------------------------
# Comunicazione SQLite → MySQL (sincronizzazione)
# ---------------------------------------------------------------------------

def sync_conversazione_tables(mysql_conn, mysql_cursor):
    """
    Sincronizza le conversazioni locali verso MySQL.
    Riceve connessione e cursor già aperti (condivisi con sync_chat_tables).
    """
    mysql_cursor.execute("SELECT uuid FROM conversazione")
    mysql_uuids = {row[0] for row in mysql_cursor.fetchall()}

    with connect_local() as sqlite_conn:
        sqlite_cursor = sqlite_conn.cursor()
        sqlite_cursor.execute("SELECT uuid, richiesta, risposta, id_chat, data FROM conversazione")
        sqlite_data = sqlite_cursor.fetchall()

    nuovi_record = [row for row in sqlite_data if row[0] not in mysql_uuids]

    print(f"Inserimento di {len(nuovi_record)} nuove conversazioni in MySQL...")
    for uuid_val, richiesta, risposta, id_chat, data in nuovi_record:
        mysql_cursor.execute(
            "INSERT INTO conversazione (uuid, richiesta, risposta, id_chat, data) VALUES (%s, %s, %s, %s, %s)",
            (uuid_val, richiesta, risposta, id_chat, data)
        )


def sync_chat_tables(mysql_conn, mysql_cursor):
    """
    Sincronizza le chat locali verso MySQL.
    Riceve connessione e cursor già aperti (condivisi con sync_conversazione_tables).
    """
    mysql_cursor.execute("SELECT uuid FROM chat")
    mysql_uuids = {row[0] for row in mysql_cursor.fetchall()}

    with connect_local() as sqlite_conn:
        sqlite_cursor = sqlite_conn.cursor()
        sqlite_cursor.execute("SELECT uuid, nome, id_utente, id_tipo, data FROM chat")
        sqlite_data = sqlite_cursor.fetchall()

    nuovi_record = [row for row in sqlite_data if row[0] not in mysql_uuids]

    print(f"Inserimento di {len(nuovi_record)} nuove chat in MySQL...")
    for uuid_val, nome, id_utente, id_tipo, data in nuovi_record:
        mysql_cursor.execute(
            "INSERT INTO chat (uuid, nome, id_utente, id_tipo, data) VALUES (%s, %s, %s, %s, %s)",
            (uuid_val, nome, id_utente, id_tipo, data)
        )


def sync_all_tables():
    """
    Sincronizza chat e conversazioni in un'unica connessione MySQL
    per ridurre l'overhead di connessione.
    """
    mysql_conn = connect()
    if mysql_conn is None:
        print("Impossibile connettersi al database MySQL.")
        return

    mysql_cursor = mysql_conn.cursor()
    try:
        sync_chat_tables(mysql_conn, mysql_cursor)
        sync_conversazione_tables(mysql_conn, mysql_cursor)
        mysql_conn.commit()
        print("Sincronizzazione completata con successo.")
    except Exception as e:
        print("Errore durante la sincronizzazione:", e)
        mysql_conn.rollback()
    finally:
        mysql_cursor.close()
        mysql_conn.close()


if __name__ == "__main__":
    sync_all_tables()
