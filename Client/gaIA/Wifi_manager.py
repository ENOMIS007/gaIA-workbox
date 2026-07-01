import socket
import time
import threading

# ── Costanti ──────────────────────────────────────────────────────────────────

FAILURE_THRESHOLD = 2
CHECK_INTERVAL = 2

# Porta su cui arrivano i pacchetti di discovery dal server
BROADCAST_PORT = 5001
# Porta su cui inviare l'ACK al server (hotspot unicast)
ACK_PORT = 5002
# Prefisso subnet hotspot Windows
HOTSPOT_SUBNET = "192.168.137."

# Possibili stati:
#   "online"   → connessione internet presente, tutto funziona
#   "lan_only" → rete locale presente ma niente internet (es. hotspot del server)
#   "offline"  → nessuna rete rilevata


# ── Funzioni di rilevamento ───────────────────────────────────────────────────

def is_connected() -> bool:
    """Controlla se c'è connessione a Internet raggiungendo il DNS di Google."""
    try:
        socket.create_connection(('8.8.8.8', 53), timeout=2)
        return True
    except OSError:
        return False


def has_local_network() -> bool:
    """
    Restituisce True se esiste almeno un'interfaccia di rete attiva con un IP
    valido (esclude loopback e link-local 169.254.x.x).
    Serve a distinguere 'lan_only' da 'offline'.
    """
    try:
        hostname = socket.gethostname()
        addrs = socket.getaddrinfo(hostname, None)
        for item in addrs:
            ip = item[4][0]
            if (not ip.startswith("127.")
                    and not ip.startswith("169.254.")
                    and ":" not in ip):
                return True
    except OSError:
        pass
    return False


def detect_connection_state() -> str:
    """
    Determina lo stato di connessione corrente.

    Logica a cascata:
      1. Internet raggiungibile → "online"
      2. Rete locale presente   → "lan_only"
      3. Nessuna rete           → "offline"
    """
    if is_connected():
        return "online"
    if has_local_network():
        return "lan_only"
    return "offline"


# ── Monitor connessione ───────────────────────────────────────────────────────

def monitor_wifi(connection_status: dict,
                 failure_threshold: int = FAILURE_THRESHOLD):
    """
    Loop continuo che aggiorna `connection_status['state']` con lo stato corrente.

    La transizione verso uno stato peggiore richiede `failure_threshold` check
    consecutivi (evita falsi positivi). Il miglioramento è invece immediato.

    Args:
        connection_status: dizionario condiviso tra i thread, modificato in-place
                           → connection_status['state']: "online"|"lan_only"|"offline"
        failure_threshold: soglia prima di abbassare lo stato
    """
    previous_state = None
    failed_attempts = 0

    connection_status.setdefault('state', 'online')

    while True:
        current_state = detect_connection_state()

        if current_state == previous_state or _is_improvement(current_state, previous_state):
            failed_attempts = 0
            _apply_state(connection_status, current_state, previous_state)
            previous_state = current_state
        else:
            failed_attempts += 1
            if failed_attempts >= failure_threshold:
                _apply_state(connection_status, current_state, previous_state)
                previous_state = current_state
                failed_attempts = 0

        time.sleep(CHECK_INTERVAL)


# ── Helpers interni ───────────────────────────────────────────────────────────

_STATE_RANK = {"offline": 0, "lan_only": 1, "online": 2}

def _is_improvement(new: str, old) -> bool:
    return _STATE_RANK.get(new, 0) > _STATE_RANK.get(old, 0)


def _apply_state(connection_status: dict, new_state: str, old_state):
    connection_status['state'] = new_state

    if new_state == old_state:
        return

    messages = {
        "online":   "✅ Connessione Internet presente. Modalità online.",
        "lan_only": "🔶 Rete locale attiva ma niente Internet. Modalità LAN-only.",
        "offline":  "❌ Nessuna rete rilevata. Modalità offline.",
    }
    print(messages.get(new_state, f"Stato sconosciuto: {new_state}"))


# ── SERVER URL condiviso ──────────────────────────────────────────────────────

# Oggetto condiviso per l'URL del server, aggiornabile da più thread in sicurezza.
# gaIA_v097.py lo importa e usa get/set invece della variabile globale diretta.
_server_url_lock = threading.Lock()
_server_url = None

# Evento che si attiva quando il server cambia URL oppure torna raggiungibile
# dopo un'interruzione (anche con lo stesso IP).
# gaIA_v097.py lo ascolta per riprendere il ciclo vocale senza uscire dal loop.
server_changed = threading.Event()

def get_server_url() -> str | None:
    with _server_url_lock:
        return _server_url

def set_server_url(url: str):
    with _server_url_lock:
        global _server_url
        _server_url = url


# ── Discovery e aggiornamento dinamico SERVER_URL ────────────────────────────

def _send_ack(server_ip: str):
    """Invia un pacchetto ACK UDP al server per confermare la ricezione dell'IP."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(b"ACK", (server_ip, ACK_PORT))
        sock.close()
        print(f"[Discovery] ACK inviato a {server_ip}")
    except Exception as e:
        print(f"[Discovery] Errore invio ACK: {e}")


def _is_hotspot_packet(sender_ip: str) -> bool:
    """Restituisce True se il pacchetto proviene dalla subnet dell'hotspot."""
    return sender_ip.startswith(HOTSPOT_SUBNET)


def _is_server_reachable(url: str) -> bool:
    """Verifica se il server è raggiungibile con una connessione TCP veloce."""
    try:
        # Estrae host e porta dall'URL (es. "http://10.41.89.197:5000")
        parts = url.replace("http://", "").split(":")
        host = parts[0]
        port = int(parts[1]) if len(parts) > 1 else 5000
        s = socket.create_connection((host, port), timeout=1)
        s.close()
        return True
    except OSError:
        return False


def _monitor_server_reachability():
    """
    Thread separato che monitora periodicamente se il server attuale è raggiungibile.
    Attiva server_changed quando il server torna up dopo essere stato down.
    Separato da listen_for_server per non dipendere dall'arrivo di pacchetti broadcast.
    Copre il caso: server riavviato con stesso IP — URL non cambia ma il client
    deve riprendere il ciclo vocale.
    """
    was_reachable = True  # Assumiamo che all'avvio il server sia raggiungibile

    while True:
        url = get_server_url()
        if url:
            reachable = _is_server_reachable(url)
            if not was_reachable and reachable:
                # Server tornato su: segnala al ciclo vocale di riprendere
                print(f"[Discovery] Server tornato raggiungibile: {url}")
                server_changed.set()
            elif was_reachable and not reachable:
                print(f"[Discovery] Server non raggiungibile: {url}")
            was_reachable = reachable
        time.sleep(2)


def listen_for_server(connection_status: dict):
    """
    Loop continuo che ascolta i pacchetti di discovery sulla porta BROADCAST_PORT.

    Comportamento:
    - Aggiorna SERVER_URL ogni volta che arriva un IP diverso da quello attuale
      e attiva server_changed per sbloccare il ciclo vocale
    - Se il pacchetto proviene dalla subnet hotspot (unicast dal server),
      risponde con ACK una sola volta per IP — non risponde più finché
      non torna internet e SERVER_URL cambia verso un IP non-hotspot
    - Funziona sia per i broadcast della rete internet che per gli unicast hotspot
    - Il rilevamento "server riavviato con stesso IP" è gestito da
      _monitor_server_reachability() in un thread separato
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", BROADCAST_PORT))
    sock.settimeout(1.0)

    # Set degli IP hotspot a cui abbiamo già mandato ACK in questa sessione di rete.
    # Viene svuotato quando SERVER_URL torna su un IP non-hotspot (internet ripristinato).
    ack_sent = set()

    # Avvia il thread di monitoraggio raggiungibilità
    t = threading.Thread(target=_monitor_server_reachability, daemon=True)
    t.start()

    print("[Discovery] In ascolto per pacchetti server...")

    while True:
        try:
            data, addr = sock.recvfrom(64)
            sender_ip = addr[0]
            message = data.decode().strip()

            # Il messaggio ha formato "ip:porta" es. "192.168.1.10:5000"
            if ":" not in message:
                continue

            new_url = f"http://{message}"
            current_url = get_server_url()

            if new_url != current_url:
                # URL cambiato: aggiorna e segnala il cambio al ciclo vocale
                set_server_url(new_url)
                print(f"[Discovery] SERVER_URL aggiornato: {new_url}")
                server_changed.set()

                # Se il nuovo URL non è hotspot significa che è tornato internet:
                # svuota ack_sent così al prossimo ciclo sull'hotspot ripartirà da zero
                if not _is_hotspot_packet(message.split(":")[0]):
                    ack_sent.clear()

            # Se arriva dalla subnet hotspot, rispondi con ACK solo se non lo hai già fatto.
            # Usiamo sender_ip (IP del mittente reale) e non l'IP estratto dal messaggio.
            if _is_hotspot_packet(sender_ip):
                if sender_ip not in ack_sent:
                    _send_ack(sender_ip)
                    ack_sent.add(sender_ip)

        except socket.timeout:
            continue
        except Exception as e:
            print(f"[Discovery] Errore: {e}")


def discover_server(timeout: int = 5) -> str | None:
    """
    Tentativo iniziale di discovery: ascolta per `timeout` secondi un pacchetto
    broadcast/unicast dal server e restituisce l'URL se trovato.
    Dopo l'avvio, il discovery continuo è gestito da listen_for_server() in background.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(timeout)
    try:
        sock.bind(("", BROADCAST_PORT))
        print("In attesa del messaggio broadcast dal server...")
        data, addr = sock.recvfrom(64)
        sender_ip = addr[0]
        message = data.decode().strip()
        url = f"http://{message}"
        set_server_url(url)
        print(f"Server trovato: {url}")

        # Se è un pacchetto hotspot, rispondi subito con ACK al mittente reale
        if _is_hotspot_packet(sender_ip):
            _send_ack(sender_ip)

        return url
    except socket.timeout:
        print("Timeout: Nessun server rilevato.")
        return None
    finally:
        sock.close()