from flask import Flask, request, jsonify, Response, stream_with_context
import threading
import socket
import time
from ollama import chat, ChatResponse
import STT_offline
import psutil
import subprocess
import re
import json
import os

app = Flask(__name__)

# IP fisso dell'hotspot Mobile di Windows (virtualmente invariabile)
HOTSPOT_IP = "192.168.137.1"

# Porta su cui il server invia i pacchetti di discovery
BROADCAST_PORT = 5001
# Porta su cui il server ascolta gli ACK dei client
ACK_PORT = 5002
# Intervallo broadcast sulla rete internet (secondi)
INTERNET_BROADCAST_INTERVAL = 1
# Intervallo di ritrasmissione unicast verso nuovi client hotspot (secondi)
HOTSPOT_UNICAST_INTERVAL = 2

# Percorso del file di configurazione (stessa cartella del server)
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server_config.json")


# Funzione per fare una richiesta al modello Ollama con streaming (in chunk).
# Riceve una lista di messaggi strutturati (system/user/assistant) invece di una stringa singola.
# Così Ollama gestisce nativamente i turni di conversazione.
def query_ollama_stream(messages):
    try:
        # Effettua la chiamata al modello 'llama3.2' con stream=True
        response_stream = chat(
            model='llama3.2',
            messages=messages,
            stream=True
        )

        # Genera e invia la risposta in chunk al client
        for chunk in response_stream:
            if 'message' in chunk:
                content = chunk['message']['content']
                yield content

    except Exception as e:
        print("Errore:", e)
        yield f"Errore durante la richiesta a Ollama: {str(e)}"


# Funzione per gestire la richiesta del client e inviare la risposta in chunk
@app.route("/query_ollama", methods=["POST"])
def query():
    data = request.get_json()
    messages = data.get("messages")

    if not messages:
        return jsonify({"error": "Messages non forniti"}), 400

    try:
        # Usa stream_with_context per gestire correttamente il contesto Flask
        return Response(
            stream_with_context(query_ollama_stream(messages)),
            content_type='text/plain; charset=utf-8'
        )
    except Exception as e:
        print("Errore:", e)
        return jsonify({"error": str(e)}), 500


# Endpoint per avviare il riconoscimento vocale
@app.route("/start_stt", methods=["POST"])
def start_stt():
    try:
        data = request.get_json()
        keyword_mode = data.get("keyword", False)
        transcription = STT_offline.run(keyword=keyword_mode)
        return jsonify({"transcription": transcription})
    except Exception as e:
        print("Errore:", e)
        return jsonify({"error": str(e)}), 500


# Endpoint per interrompere il riconoscimento vocale
@app.route("/stop_stt", methods=["POST"])
def stop_stt():
    try:
        STT_offline.stop()
        return jsonify({"message": "Riconoscimento vocale interrotto"})
    except Exception as e:
        print("Errore:", e)
        return jsonify({"error": str(e)}), 500


# Funzione per ottenere l'IP attivo sulla rete internet (WiFi o Ethernet)
# Esclude deliberatamente la subnet 192.168.137.x dell'hotspot
def get_active_ip():
    preferred = ["Wi-Fi", "WiFi", "wlan", "WLAN", "Ethernet"]
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()

    # Priorità interfacce preferite
    for name in preferred:
        if name in addrs and stats.get(name, None) and stats[name].isup:
            for addr in addrs[name]:
                if (addr.family == socket.AF_INET
                        and not addr.address.startswith(("127.", "169.254.", "192.168.137."))):
                    return addr.address

    # Fallback: qualsiasi altra interfaccia attiva con IP valido (non hotspot)
    for iface, iface_addrs in addrs.items():
        if stats.get(iface, None) and stats[iface].isup:
            for addr in iface_addrs:
                if (addr.family == socket.AF_INET
                        and not addr.address.startswith(("127.", "169.254.", "192.168.137."))):
                    return addr.address
    return None


# Funzione per verificare se l'hotspot Mobile Windows è attivo.
# Cerca l'interfaccia virtuale con IP 192.168.137.1.
def get_hotspot_ip():
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()

    for iface, iface_addrs in addrs.items():
        if stats.get(iface, None) and stats[iface].isup:
            for addr in iface_addrs:
                if addr.family == socket.AF_INET and addr.address == HOTSPOT_IP:
                    return HOTSPOT_IP
    return None


# Ritorna gli IP dei dispositivi attualmente connessi all'hotspot come set
def get_hotspot_client_ips():
    try:
        arp_output = subprocess.check_output("arp -a", shell=True, text=True)
    except subprocess.CalledProcessError:
        return set()

    ips = set()
    for line in arp_output.splitlines():
        match = re.search(r"(192\.168\.137\.\d+)\s+([-\w]+)\s+\w+", line)
        if match:
            ip = match.group(1)
            if ip not in ("192.168.137.1", "192.168.137.255"):
                ips.add(ip)
    return ips


# Thread che ascolta gli ACK UDP dai client sulla porta ACK_PORT.
# Quando un client risponde, viene aggiunto a confirmed_clients.
# Così il thread unicast smette di inviargli pacchetti.
def ack_listener(confirmed_clients: set, lock: threading.Lock):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", ACK_PORT))
    sock.settimeout(1.0)
    print(f"[ACK] In ascolto sulla porta {ACK_PORT}...")

    while True:
        try:
            data, addr = sock.recvfrom(64)
            client_ip = addr[0]
            if data == b"ACK":
                with lock:
                    if client_ip not in confirmed_clients:
                        confirmed_clients.add(client_ip)
                        print(f"[ACK] Ricevuto da {client_ip} — invio unicast interrotto.")
        except socket.timeout:
            continue
        except Exception as e:
            print(f"[ACK] Errore: {e}")


# Broadcast periodico sulla rete internet (ogni INTERNET_BROADCAST_INTERVAL secondi).
# Serve ai client sulla rete normale per scoprire o aggiornare l'IP del server.
# Il socket viene bindato esplicitamente sull'interfaccia internet per evitare che Windows, quando l'hotspot è attivo,
# instradi il broadcast sull'interfaccia virtuale 192.168.137.x invece che sulla rete WiFi/Ethernet principale.
def broadcast_internet_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(0.2)

    current_ip = None
    start_time = time.time()  # Usato per silenziare errori nei primi secondi di avvio

    while True:
        new_ip = get_active_ip()

        if new_ip != current_ip:
            if new_ip:
                print(f"[Broadcast] Interfaccia internet attiva: {new_ip}:5000")
                # Ricrea il socket e bindalo sulla nuova interfaccia internet.
                # Necessario quando l'IP cambia (es. riconnessione WiFi).
                try:
                    sock.close()
                except:
                    pass
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.settimeout(0.2)
                try:
                    sock.bind((new_ip, 0))
                except Exception as e:
                    print(f"[Broadcast] Errore bind interfaccia: {e}")
            else:
                print("[Broadcast] Nessuna connessione internet attiva")
            current_ip = new_ip

        if current_ip:
            message = f"{current_ip}:5000".encode()
            try:
                sock.sendto(message, ('<broadcast>', BROADCAST_PORT))
            except Exception as e:
                # Ignora errori nei primi 3 secondi: l'interfaccia potrebbe non essere
                # ancora pronta al momento dell'avvio
                if time.time() - start_time > 3:
                    print(f"[Broadcast] Errore invio: {e}")

        time.sleep(INTERNET_BROADCAST_INTERVAL)


# Unicast mirato verso i nuovi client sull'hotspot.
# Logica:
#   - Monitora i dispositivi connessi all'hotspot tramite ARP
#   - Per ogni nuovo client (non ancora confermato) invia l'IP del server ogni
#     HOTSPOT_UNICAST_INTERVAL secondi finché non arriva l'ACK
#   - Se un client già confermato sparisce dalla rete ARP, viene rimosso da
#     confirmed_clients: al riconnettimento verrà trattato come nuovo
def unicast_hotspot_ip(confirmed_clients: set, lock: threading.Lock):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    known_clients = set()   # tutti i client visti almeno una volta in questa sessione

    while True:
        hotspot_ip = get_hotspot_ip()

        if hotspot_ip:
            current_clients = get_hotspot_client_ips()

            with lock:
                # Rimuovi i client che si sono disconnessi da confirmed e known
                # così al riconnettimento vengono trattati come nuovi
                disconnected = known_clients - current_clients
                for ip in disconnected:
                    confirmed_clients.discard(ip)
                    known_clients.discard(ip)
                    print(f"[Hotspot] Client disconnesso: {ip} — rimosso dalla lista.")

                # Invia l'IP ai client non ancora confermati
                message = f"{hotspot_ip}:5000".encode()
                for ip in current_clients:
                    known_clients.add(ip)
                    if ip not in confirmed_clients:
                        try:
                            sock.sendto(message, (ip, BROADCAST_PORT))
                            print(f"[Hotspot] Inviato IP a {ip} (in attesa di ACK)")
                        except Exception as e:
                            print(f"[Hotspot] Errore invio a {ip}: {e}")

        time.sleep(HOTSPOT_UNICAST_INTERVAL)


# Avvia i tre thread separati: broadcast internet, unicast hotspot, listener ACK
def broadcast_server_ip():
    lock = threading.Lock()
    confirmed_clients = set()   # IP dei client hotspot che hanno già risposto con ACK

    # Thread broadcast rete internet
    t_internet = threading.Thread(
        target=broadcast_internet_ip,
        daemon=True
    )

    # Thread unicast hotspot
    t_hotspot = threading.Thread(
        target=unicast_hotspot_ip,
        args=(confirmed_clients, lock),
        daemon=True
    )

    # Thread listener ACK
    t_ack = threading.Thread(
        target=ack_listener,
        args=(confirmed_clients, lock),
        daemon=True
    )

    t_internet.start()
    t_hotspot.start()
    t_ack.start()


# Per eseguire un comando PowerShell e ritornarne l'output 
def run_ps(cmd):
    result = subprocess.run(["powershell", "-Command", cmd],
                            capture_output=True, text=True)
    return result.stdout.strip()


# Legge SSID e password dal file di configurazione esterno.
# Restituisce (ssid, password) o (None, None) se il file manca o è malformato.
def load_hotspot_config():
    if not os.path.exists(CONFIG_PATH):
        print(f"❌ File di configurazione non trovato: {CONFIG_PATH}")
        return None, None
    try:
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)
        ssid = config["hotspot"]["ssid"]
        password = config["hotspot"]["password"]
        return ssid, password
    except (KeyError, json.JSONDecodeError) as e:
        print(f"❌ Errore nella lettura della configurazione: {e}")
        return None, None


# Avvio dell'hotspot
def start_hotspot(ssid, password):
    if len(password) < 8:
        print("❌ Password troppo corta (minimo 8 caratteri)")
        return
    
    print("⚙️ Avvio Hotspot Mobile automaticamente...")
    ps_cmd = """
        Add-Type -AssemblyName Windows.Networking
        Add-Type -AssemblyName Windows.Networking.Connectivity
        Add-Type -AssemblyName Windows.Networking.NetworkOperators
        $tetheringManager = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager, Windows, ContentType=WindowsRuntime]::CreateFromConnectionProfile(
            [Windows.Networking.Connectivity.NetworkInformation, Windows, ContentType=WindowsRuntime]::GetInternetConnectionProfile()
        )
        $accessPointConfig = $tetheringManager.GetCurrentAccessPointConfiguration()
        $accessPointConfig.Ssid = '{ssid}'
        $accessPointConfig.Passphrase = '{password}'
        $tetheringManager.ConfigureAccessPointAsync($accessPointConfig) | Out-Null
        $tetheringManager.StartTetheringAsync() | Out-Null
    """.format(ssid=ssid, password=password)
    
    run_ps(ps_cmd)
    print(f"✅ Hotspot '{ssid}' avviato con successo!")
        
        
# Stop hotspot
def stop_hotspot():
    print("🛑 Arresto Hotspot Mobile...")
    ps_cmd = """
        Add-Type -AssemblyName Windows.Networking.NetworkOperators
        $tetheringManager = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager, Windows, ContentType=WindowsRuntime]::CreateFromConnectionProfile(
            [Windows.Networking.Connectivity.NetworkInformation, Windows, ContentType=WindowsRuntime]::GetInternetConnectionProfile()
        )
        $tetheringManager.StopTetheringAsync() | Out-Null
    """
    run_ps(ps_cmd)
    print("✅ Hotspot fermato.")
    
    
# Ritorna gli IP e MAC dei dispositivi connessi all'hotspot Mobile
def get_connected_devices():
    try:
        arp_output = subprocess.check_output("arp -a", shell=True, text=True)
    except subprocess.CalledProcessError:
        print("❌ Errore: impossibile eseguire arp -a")
        return

    devices = []
    for line in arp_output.splitlines():
        match = re.search(r"(192\.168\.137\.\d+)\s+([-\w]+)\s+\w+", line)
        if match:
            ip, mac = match.groups()
            if ip not in ("192.168.137.1", "192.168.137.255"):
                devices.append({"IP": ip, "MAC": mac})

    if not devices:
        print("⚠️ Nessun dispositivo connesso all'hotspot rilevato.")
    else:
        print("\n👥 Dispositivi connessi all'hotspot:")
        for d in devices:
            print(f"IP: {d['IP']} | MAC: {d['MAC']}")
            
            
# Mostra le info in merito alla scheda Wi-Fi
def show_status():
    print("\n📶 Stato scheda Wi-Fi:")
    output = run_ps("Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | Format-Table Name, InterfaceDescription, Status, MacAddress, LinkSpeed")
    print(output)


if __name__ == "__main__":
    # ⚠️ PROMEMORIA: disattivare manualmente la modalità risparmio energetico dell'hotspot
    # su Windows: Impostazioni → Rete e Internet → Hotspot mobile → disattiva
    # "Quando non ci sono dispositivi connessi, disattiva l'hotspot mobile automaticamente"
    # In alternativa via registro: HKLM\SYSTEM\CurrentControlSet\Services\icssvc\Settings
    # impostare PeerlessTimeoutEnabled = 0 (richiede riavvio del servizio icssvc)

    # Carica la configurazione e avvia l'hotspot prima di tutto il resto
    ssid, password = load_hotspot_config()
    if ssid and password:
        start_hotspot(ssid, password)
    else:
        print("⚠️ Hotspot non avviato: configurazione mancante o non valida.")

    broadcast_server_ip()
    app.run(host="0.0.0.0", port=5000)