import threading
import Wifi_manager
import Calendar
import time


# Dizionario condiviso tra tutti i thread per leggere lo stato di connessione.
# Struttura: {'state': "online" | "lan_only" | "offline"}
connection_status = {'state': 'online'}

def loop_controllo_promemoria():
    while True:
        Calendar.controllo_promemoria()
        time.sleep(30)  # Controlla ogni 30s: i promemoria hanno granularità di minuti



def run():
    # Thread separato per monitorare la connessione WiFi
    monitor_wifi_thread = threading.Thread(target=Wifi_manager.monitor_wifi, args=(connection_status,))
    monitor_wifi_thread.daemon = True  # Imposta il thread come daemon
    monitor_wifi_thread.start()

    # Thread separato per il discovery continuo del server
    # Aggiorna SERVER_URL in Wifi_manager ogni volta che arriva un pacchetto dal server
    listen_server_thread = threading.Thread(target=Wifi_manager.listen_for_server, args=(connection_status,))
    listen_server_thread.daemon = True  # Imposta il thread come daemon
    listen_server_thread.start()
    
    # Thread separato per controllare promemoria scaduti
    controllo_promemoria_thread = threading.Thread(target=loop_controllo_promemoria)
    controllo_promemoria_thread.daemon = True  # Imposta il thread come daemon
    controllo_promemoria_thread.start()
    

if __name__ == "__main__":
    run()