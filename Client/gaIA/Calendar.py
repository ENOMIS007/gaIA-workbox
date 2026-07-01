from datetime import datetime, timedelta, date
from plyer import notification
import Database_dealer
import difflib
import re
import os


### Funzione per ottenere il numero del mese da una stringa ###
def month_from_string(month_str):
    months = {
        "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
        "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
        "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12
    }
    return months.get(month_str.lower(), None)


### Funzione per convertire numeri scritti a lettere in numeri interi ###
def text_to_number(text):
    numbers = {
        "uno": 1, "due": 2, "tre": 3, "quattro": 4, "cinque": 5,
        "sei": 6, "sette": 7, "otto": 8, "nove": 9, "dieci": 10,
        "undici": 11, "dodici": 12, "tredici": 13, "quattordici": 14,
        "quindici": 15, "sedici": 16, "diciassette": 17, "diciotto": 18,
        "diciannove": 19, "venti": 20, "ventuno": 21, "ventidue": 22,
        "ventitré": 23, "ventiquattro": 24, "venticinque": 25, 
        "ventisei": 26, "ventisette": 27, "ventotto": 28, "ventinove": 29,
        "trenta": 30, "trentuno": 31
    }
    return numbers.get(text.lower())


### Funzione per ottenere il nome del mese ###
def month_name(month_number):
    switcher = {
        1: "Gennaio",
        2: "Febbraio",
        3: "Marzo",
        4: "Aprile",
        5: "Maggio",
        6: "Giugno",
        7: "Luglio",
        8: "Agosto",
        9: "Settembre",
        10: "Ottobre",
        11: "Novembre",
        12: "Dicembre"
    }
    return switcher.get(month_number, "Mese non valido")


### Funzione per ottenere il nome del giorno della settimana ###
def day_name(day_number):
    switcher = {
        0: "Lunedì",
        1: "Martedì",
        2: "Mercoledì",
        3: "Giovedì",
        4: "Venerdì",
        5: "Sabato",
        6: "Domenica"
    }
    return switcher.get(day_number, "Giorno non valido")



### Funzione per leggere tutti i promemoria ###
def all_promemoria():
    promemoria = Database_dealer.get_all_promemoria()
    
    if not promemoria:
        return "Nessun promemoria impostato."
    
    risultato = ""
    for i, (id_, desc, scadenza) in enumerate(promemoria, start=1):
        try:
            data_formattata = datetime.strptime(scadenza, "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y %H:%M")
        except ValueError:
            data_formattata = scadenza  # fallback nel caso il formato non sia quello atteso
        risultato += f"{i}. {data_formattata} - {desc}\n"
    
    return risultato.strip()


def cancella_promemoria(messaggio):
    messaggio = re.sub(r'[^\w\s]', '', messaggio).strip().lower()
    promemoria = Database_dealer.get_all_promemoria()
    
    # Raccoglie tutte le descrizioni pulite per il confronto
    desc_pulite = [re.sub(r'[^\w\s]', '', desc).strip().lower() for _, desc, _ in promemoria]
    
    # Cerca la corrispondenza più simile (tolleranza errori di battitura)
    closest = difflib.get_close_matches(messaggio, desc_pulite, n=1, cutoff=0.6)
    
    if closest:
        match_desc = closest[0]
        # Trova l'ID corrispondente alla descrizione trovata e cancellalo
        for id_, desc, scadenza in promemoria:
            if re.sub(r'[^\w\s]', '', desc).strip().lower() == match_desc:
                Database_dealer.delete_promemoria(id_)
                return "Promemoria cancellato."
                
    return "Nessun promemoria trovato con il messaggio fornito."


### Funzione per impostare un promemoria ###
def imposta_promemoria(messaggio: str, data: date, ora: str = None):
    adesso = datetime.now()
    if data and ora:
        data_completa = datetime.combine(data, datetime.strptime(ora, "%H:%M").time())
    elif data:
        data_completa = datetime.combine(data, datetime.strptime("12:00", "%H:%M").time())
    else:
        return "Data non specificata."

    # Salva il promemoria nel file
    messaggio = re.sub(r'\.+$', '', messaggio)
    Database_dealer.insert_promemoria(messaggio, data_completa)
    
    return f"Promemoria impostato per: {data_completa.strftime('%d/%m/%Y %H:%M')}"


### Funzione per controllare e gestire i promemoria scaduti ###
def controllo_promemoria():
    adesso = datetime.now()
    
    promemoria = Database_dealer.get_all_scadenze()
        
    # Controlla ogni promemoria
    for id_, scadenza in promemoria:
        data_promemoria = datetime.strptime(scadenza, "%Y-%m-%d %H:%M:%S")
        # Se il promemoria è scaduto, avvisa e cancella
        if data_promemoria <= adesso:
            desc = Database_dealer.get_desc_by_id(id_)
            notification.notify(
                title=desc,
                message="Promemoria",
                timeout=4 # durata della notifica in secondi
            )
            print(f"Promemoria scaduto: {data_promemoria.strftime('%d/%m/%Y %H:%M')} - {desc}")
            Database_dealer.delete_promemoria(id_)


### Funzione per calcolare una data futura ###
def data_futura(data: date) -> str:
    if data is None:
        return "Non ho capito la data richiesta."
    
    giorno_settimana = day_name(data.weekday())
    return f"{giorno_settimana} {data.day} {month_name(data.month)}"


### Funzione per ottenere l'orario attuale ###
def orario_attuale():
    return f"Sono le ore {datetime.now().strftime('%H e %M')}"


### Funzione per ottenere il giorno attuale ###
def giorno_attuale():
    current_time = datetime.now()
    giorno_settimana = day_name(current_time.weekday())  # weekday() restituisce 0 per Lunedì
    data = current_time.day
    mese = month_name(current_time.month)
    return f"Oggi è {giorno_settimana} {data} {mese}"


# Esempio d'uso delle funzioni
if __name__ == "__main__":
    
#     print(orario_attuale())
#     print("\n")
#     
#     print(giorno_attuale())
#     print("\n")
#     
#     # Chiedi quanti giorni nel data
#     giorni = input("Inserisci la tua domanda: ")
#     print("\n", data_futura(giorni))
#     print("\n")
    
    # Controlla i promemoria scaduti
    controllo_promemoria()
    print("\n")
    
    # Visualizza i promemoria
    print(all_promemoria())
    print("\n")

    # Imposta un nuovo promemoria
    from ParamExtractor import _parse_date, _parse_time
    messaggio = input("Inserisci il messaggio del promemoria: ")
    raw = input("Per quando? (es. domani alle 15, 12/03, venerdì): ")
    data = _parse_date(raw)
    ora  = _parse_time(raw)
    print(imposta_promemoria(messaggio, data, ora))

#     print("\n")
#     
#     # Cancella un promemoria
#     messaggio = input("Inserisci il messaggio del promemoria da cancellare: ")
#     print(cancella_promemoria(messaggio))
