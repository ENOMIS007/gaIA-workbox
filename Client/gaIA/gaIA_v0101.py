import Database_dealer
import TTS_offline
import Dispatcher
import Interprete
import BackgroundServices
import threading
import Wifi_manager
import Calendar
import Music
import time
import re
import Chat_output
import os
import requests
import socket
import App


# Tentativo iniziale di discovery del server all'avvio.
# Dopo l'avvio, l'aggiornamento continuo è gestito da BackgroundServices tramite Wifi_manager.listen_for_server() in background.
# get_server_url() restituisce sempre l'URL più aggiornato.
Wifi_manager.discover_server()
if not Wifi_manager.get_server_url():
    Wifi_manager.set_server_url("http://127.0.0.1:5000")


_STOP_KEYWORDS = {"stop", "basta", "fermati"}


# Rimuove "gaia" ad inizio richiesta
def remove_wake_word(text: str) -> str:
    return re.sub(r"^\s*gaia[,.]?\s*", "", text, flags=re.IGNORECASE).strip()


# Controlla che sia un comando di stop
def is_stop_command(transcript: str) -> bool:
    return any(kw in transcript.lower() for kw in _STOP_KEYWORDS)


# Wrapper locale per leggere sempre l'URL aggiornato del server
def get_server_url():
    return Wifi_manager.get_server_url()


def init_full_transcript(chat=False, uuid=None):
    # Istruzioni base del sistema — sempre presenti come primo messaggio
    base_content = (
        "Tu sei gaIA. gaIA è un'intelligenza artificiale avanzata che migliora l'esperienza umana analizzando dati e fornendo risposte pertinenti. "
        "Sempre pronta ad aiutare, evolve continuamente per offrire soluzioni efficaci."
    )
    if not chat:
        base_content += " Non usare trattini, asterischi, grassetto o trattini per intervalli di tempo (esempio: 1987 1988). Risposte al massimo 300 caratteri."

    messages = [{"role": "system", "content": base_content}]

    if uuid is not None:
        conversazioni = Database_dealer.get_conversazioni_by_chat_id(uuid)
        # Costruzione della cronologia con ruoli nativi user/assistant.
        # In questo modo Ollama gestisce correttamente i turni di conversazione senza rischio di continuare la chat da solo.
        for conv in conversazioni:
            if len(conv) > 0 and conv[0]:
                messages.append({"role": "user", "content": conv[0].strip()})
            if len(conv) > 1 and conv[1]:
                messages.append({"role": "assistant", "content": conv[1].strip()})

    return messages


#### Inizializzazione ####
full_transcript = init_full_transcript()

IA_is_thinking = False
stop_thread = None
stop_signal = threading.Event()
stop_main_cycle = threading.Event()
request_in_response = False  # Inizializzazione della variabile globale
chat_mode_active = True
stop_vocal = False
r = 0
transcript = ""  # Variabile globale per la trascrizione
conversation_mode = False   # Variabile booleana per tracciare se l'ultima risposta dell'IA è stata una domanda 
conversation_mode_stop = False
conversation_memory = None
EXIT = False

#Inizializzazione delle variabili di stato
Dispatcher.init_context(
    server_url=get_server_url(),
    connection_status=BackgroundServices.connection_status,
    chat_mode_active=chat_mode_active,
    conversation_memory=conversation_memory,
    conversation_mode=conversation_mode,
)

# Callback per inviare chunk in tempo reale alla UI (modalità chat).
# Viene impostata da generate_response() prima di ogni chiamata e azzerata al termine.
current_chunk_callback = None


def stop_main():
    global stop_vocal
    while True:
        if stop_main_cycle.is_set():
            try:
                requests.post(f"{get_server_url()}/stop_stt")
            except requests.exceptions.ConnectionError:
                # Server irraggiungibile: procedi comunque a fermare il ciclo vocale
                pass
            stop_vocal = True
            # Sblocca server_changed.wait() nel caso il ciclo vocale sia in attesa di riconnessione.
            # Senza questo run() rimarrebbe bloccato anche dopo che stop_vocal è True
            Wifi_manager.server_changed.set()
            break
        time.sleep(0.2)


def stop_main_thread():
    # Thread separato per fermare run()
    vocal_stop = threading.Thread(target=stop_main)
    vocal_stop.daemon = True  # Imposta il thread come daemon
    vocal_stop.start()



#### Funzione per processare la richiesta e dare una risposta o eseguire un comando ####
def process_request(user_message=None):
    global full_transcript, request_in_response, transcript, r, conversation_mode, conversation_mode_stop, conversation_memory, EXIT
    concatenazione_frasi = False
    skills_answer = False
    EXIT = False
    
    ##-- Step 1: Controlli per gestire input utente
    if user_message is not None:
        transcript = user_message
        full_transcript = init_full_transcript(True, App.current_chat_uuid)
    elif conversation_mode and not conversation_mode_stop:
        try:
            response = requests.post(f"{get_server_url()}/start_stt", json={})
            if response.status_code == 200:
                transcript = response.json().get("transcription")
        except requests.exceptions.ConnectionError:
            # Server irraggiungibile: aspetta che listen_for_server segnali un cambio o un ripristino del server, oppure che stop_main_cycle interrompa il ciclo.
            # Il timeout di 0.2s evita freeze all'ingresso in modalità chat testuale.
            print("[STT] Connessione al server persa. In attesa di riconnessione...")
            while not stop_main_cycle.is_set():
                if Wifi_manager.server_changed.wait(timeout=0.2):
                    Wifi_manager.server_changed.clear()
                    break
            print("[STT] Server disponibile, riprovo...")
            return
    elif not request_in_response:
        try:
            response = requests.post(f"{get_server_url()}/start_stt", json={"keyword": True})
            if response.status_code == 200:
                transcript = response.json().get("transcription")
        except requests.exceptions.ConnectionError:
            # Server irraggiungibile: aspetta che listen_for_server segnali un cambio o un ripristino del server, oppure che stop_main_cycle interrompa il ciclo.
            # Il timeout di 0.2s evita freeze all'ingresso in modalità chat testuale.
            print("[STT] Connessione al server persa. In attesa di riconnessione...")
            while not stop_main_cycle.is_set():
                if Wifi_manager.server_changed.wait(timeout=0.2):
                    Wifi_manager.server_changed.clear()
                    break
            print("[STT] Server disponibile, riprovo...")
            return
    else:
        r += 1  
          
    if transcript is None:
        EXIT = True
        
    else:
    
        if user_message is None:
            Chat_output.set_transcript(transcript)
        
        print(f"\nUser: {transcript}")
        
        transcript = remove_wake_word(transcript)
        
        if user_message is None and is_stop_command(transcript):
            if not TTS_offline.is_queue_empty():
                TTS_offline.stop()
                stop_signal.set()
                Database_dealer.insert_conversazione(transcript, "Stop.", App.current_chat_uuid)
            elif Music.player is not None:
                Music.stop_music()
                Database_dealer.insert_conversazione(transcript, "Musica in pausa.", App.current_chat_uuid)
            return
        
        ##-- Step 2: se viene riconosciuto un intent allora si chiama la skill corrispondente tramite Dispatcher.skills, altrimenti fallback AI
        Dispatcher.update_context(
            get_server_url(),
            BackgroundServices.connection_status,
            chat_mode_active,
        )

        result = Interprete.classify(transcript)
        intent = result["intent"]
        confidence = result["confidence"]
        print(f"[Intent: {intent} | Confidence: {confidence:.2f}]")

        if intent is not None:
            risposta = Dispatcher.skills(intent, transcript)
        else:
            risposta = None
            
            
        ##-- Step 3: Se CustomResponse.skill non fornisce una risposta, utilizza IA_response
        if risposta is None:
            if user_message is None:
                global stop_thread
                stop_signal.clear()
                stop_thread = threading.Thread(target=stop_response)
                stop_thread.start()
            else:
                global IA_is_thinking
                IA_is_thinking = True
            
            # Chiama IA_response per ottenere la risposta in chunk e vocalizzala man mano chunk_callback è passata solo in modalità chat (user_message is not None)
            risposta = IA_response(transcript, user_message,
                                   chunk_callback=current_chunk_callback if user_message is not None else None)
                    
            if user_message is None:
                
                while not TTS_offline.is_queue_empty():
                    time.sleep(0.1)
                
                requests.post(f"{get_server_url()}/stop_stt")
                stop_signal.set()  # Assicurati che il thread di monitoraggio si chiuda correttamente
                stop_thread.join()
            else:
                IA_is_thinking = False
            
        else:
            ##-- Step 4: Se CustomResponse.skill ha fornito una risposta, la vocalizzi e la salvi normalmente
            if user_message is None:
                if risposta == "Musica ripresa.":
                    pass  # non vocalizzare, non fermare, non fare nulla
                elif risposta != "Musica in pausa.":
                    TTS_offline.music_status_set()
                    if risposta.startswith("Riproduzione:"):
                        TTS_offline.run(risposta, True)
                    else:
                        TTS_offline.run(risposta, concatenazione_frasi)
                else:
                    TTS_offline.music_status_unset()
                
            skills_answer = True
            
            
        # Salva la conversazione e sincronizza con MySQL (solo se online)
        current_state = BackgroundServices.connection_status.get('state')
        Database_dealer.insert_conversazione(transcript, risposta, App.current_chat_uuid)
        if current_state == 'online':
            threading.Thread(
                target=Database_dealer.sync_all_tables,
                daemon=True
            ).start()


        if request_in_response and r == 1:
            request_in_response = False
                
        
        ##-- Step 5: Tiene traccia della conversazione se necessario.
        # Usa il ruolo "assistant" (non "system") perché è una risposta di gaIA, non un'istruzione al modello.
        if (conversation_mode or conversation_memory) and not skills_answer:
            full_transcript.append({"role": "assistant", "content": risposta})
        
        
        ##-- Step 6: Resetta il full_transcript e transcript dopo ogni risposta, se necessario
        if not request_in_response and not conversation_mode and not conversation_memory:
            r = 0
            transcript = ""
            full_transcript = init_full_transcript(chat=(user_message is not None))




#### Definire IA_response ####
def IA_response(transcript, user_message=None, chunk_callback=None):
    global full_transcript, conversation_mode, conversation_memory
    concatenazione_frasi = True
    
    # Aggiungi la richiesta dell'utente al full_transcript
    full_transcript.append({"role": "user", "content": transcript})
    
    risposta = ""  # Variabile per accumulare la risposta
    chunks = ""
    
    # Passa il full_transcript direttamente come lista di messaggi strutturati.
    # Ollama gestisce nativamente i ruoli system/user/assistant, quindi non serve serializzare in stringa né aggiungere workaround per fermare il completamento.

    # Inizia la conversazione con il modello Ollama in streaming
    response = requests.post(
        f"{get_server_url()}/query_ollama",
        json={'messages': full_transcript},
        stream=True
    )

    # Se la risposta è corretta, ricevi e stampa i chunk progressivamente
    if response.status_code == 200:
        
        for chunk in response.iter_content(chunk_size=1, decode_unicode=True):
            if stop_signal.is_set():
                TTS_offline.stop()
                # Ferma la risposta se il segnale di stop è stato impostato
                break
            
            if user_message is None:
                chunks += chunk
                
                if re.search(r'(?<!\d)\.|[!?]', chunks):
                    TTS_offline.music_status_set()
                    TTS_offline.run(chunks, concatenazione_frasi)
                    chunks = ""
            else:
                print(chunk, end='', flush=True)
                # Invia il chunk alla UI in tempo reale se è presente una callback
                if chunk_callback is not None:
                    chunk_callback(chunk)
            risposta += chunk
    


#     if user_message is None:
#         if re.search(r'\?', risposta):
#             conversation_mode = True
#         else:
#             conversation_mode = False


    if not conversation_mode:
        # Ripristina il full_transcript per la prossima interazione
        full_transcript = init_full_transcript(chat=(user_message is not None))

    return risposta



#### Monitoraggio di "Gaia stop" ####
def stop_response():
    global request_in_response, transcript, conversation_mode_stop
    while not stop_signal.is_set():
        response = requests.post(f"{get_server_url()}/start_stt", json={"keyword": True})
        if response.status_code == 200:
            transcript = response.json().get("transcription")
            if transcript is not None and ("Gaia stop." in transcript or "Gaia. stop." in transcript):
                TTS_offline.stop()
                stop_signal.set()
                conversation_mode_stop = True
                print("\nstop eseguito\n")
            elif transcript is not None:
                TTS_offline.stop()
                stop_signal.set()
                conversation_mode_stop = True
                request_in_response = True
                print()
                print("\nnuova richiesta raccolta da stop_response\n")



### Funzione per generare la risposta e restituirla alla Chat-mode ###
# chunk_callback(chunk: str) → opzionale, chiamata per ogni chunk Ollama in tempo reale.
# Se non fornita, il comportamento è identico a prima (nessuno streaming verso la UI)
def generate_response(user_message, chunk_callback=None):
    global current_chunk_callback, chat_mode_active
    current_chunk_callback = chunk_callback
    # In modalità chat chat_mode_active deve essere True
    # così Dispatcher usa _ask_chat invece di _ask_vocal
    chat_mode_active = True
    Dispatcher.update_context(
        get_server_url(),
        BackgroundServices.connection_status,
        chat_mode_active,
    )
    process_request(user_message=user_message)
    current_chunk_callback = None
    id_ = Database_dealer.get_last_id()
    return Database_dealer.get_risposta_by_id(id_)



### Main cycle ###
def run():
    global stop_vocal, EXIT, chat_mode_active
    stop_main_thread()
    stop_vocal = False
    # In modalità vocale chat_mode_active deve essere False
    # così Dispatcher usa _ask_vocal invece di _ask_chat
    chat_mode_active = False
    Dispatcher.update_context(
        get_server_url(),
        BackgroundServices.connection_status,
        chat_mode_active,
    )
    while not stop_vocal:
        process_request()
        if EXIT:
            break

        
        

if __name__ == "__main__":
    run()