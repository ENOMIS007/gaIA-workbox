import threading

# Variabili per memorizzare il messaggio dell'input e il conteggio delle chiamate
message = ""
message_ready = threading.Event()  # Evento per segnalare che un messaggio è pronto
call_count = 0  # Contatore per il numero di chiamate a get_user_input()

def set_message(new_message):
    global message
    message = new_message
    message_ready.set()  # Imposta l'evento quando un messaggio è pronto


def get_user_input():
    global message, call_count
    call_count += 1  # Incrementa il contatore
    message_ready.clear()  # Pulisce l'evento
    message = ""  # Resetta il messaggio
    result = wait_for_input()  # Attende l'input dell'utente
    call_count -= 1  # Decrementa il contatore al termine
    return result  # Restituisce il messaggio


def wait_for_input():
    message_ready.wait()  # Attende che l'evento sia impostato
    return message  # Restituisce il messaggio


# Funzione che restituisce True se get_user_input() è attualmente in esecuzione, altrimenti False. 
def is_get_user_input_called():
    return call_count > 0  # Restituisce True se ci sono chiamate attive
