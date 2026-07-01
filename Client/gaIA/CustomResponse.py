from datetime import datetime
import TTS_offline
import Browsering
import Music
import Light
import Calendar
import Chat_output
import Chat_input
import App_manager
import Weather
import requests


commands_list= """
Lista comandi:\n

Ora attuale:
che ore sono? - che ora è? - Che ore sono? - Che ora è?

Giorno attuale:
che giorno è oggi? - che giorno è? - Che giorno è oggi? - Che giorno è?

Data futura:
che giorno è (+ giorno della settimana o data) - Che giorno è (+ giorno della settimana o data)

Previsioni meteo:
che tempo fa oggi - Che tempo fa oggi - che tempo fa oggi? - Che tempo fa oggi?

Imposta promemoria:
imposta promemoria - Imposta promemoria - crea promemoria - Crea promemoria - nuovo promemoria - Nuovo promemoria

Cancella promemoria:
cancella promemoria - Cancella promemoria - elimina promemoria - Elimina promemoria

Motra promemoria:
mostra promemoria - Mostra promemoria - mostrami i promemoria - Mostrami i promemoria

Risposta precedente:
cosa ti ho chiesto prima? - Cosa ti ho chiesto prima?

Attivare memoria di conversazione:
parliamo un po'. - parliamo un po'? - memoria di chat on. - Memoria di chat on.

Disattivare memoria di conversazione
grazie. - Grazie. - basta così. - Basta così. - memoria di chat off. - Memoria di chat off.

Comandi per musica:
riproduci - metti - Riproduci - Metti  (+ nome canzone ed aventuale artista/i)
aggiungi alla coda - aggiungi in coda - Aggiungi alla coda - Aggiungi in coda - metti in coda - Metti in coda (+ nome canzone ed aventuale artista/i)
ferma musica - pausa musica - stop musica - Ferma musica - Pausa musica - Stop musica
riprendi musica - Riprendi musica
termina musica - Termina musica
mostra coda - Mostra coda
volume + N% - Volume + N%
alza il volume - Alza il volume - abbassa il volume - Abbassa il volume

Comandi luci:
accendi la luce. - accendi le luci. - Accendi la luce. - Accendi le luci.
spegni la luce. - spegni le luci. - Spegni la luce. - Spegni le luci.

Apertura app:
apri - avvia - Apri - Avvia (+ nome app)

Aggiungere app:
aggiungi app - Aggiungi app

Mostra lista app:
mostra app - Mostra app
"""


def stt_response(SERVER_URL):
    response = requests.post(f"{SERVER_URL}/start_stt", json={})
    if response.status_code == 200:
        transcription = response.json().get("transcription")
        return transcription



### Skills di gaIA ###
def skills(SERVER_URL, transcript, connection_status, chat_mode_active=False, conversation_memory=False, conversation_mode=False):
    
    risposta = None
    state = connection_status.get('state', 'online')
    
    print(SERVER_URL)
    
    ### Orario attuale ###
    if any(parola in transcript for parola in ["che ore sono?", "che ora è?", "Che ore sono?", "Che ora è?"]):
        risposta = Calendar.orario_attuale()
        
        
    ### Giorno attuale ###
    elif any(parola in transcript for parola in ["che giorno è oggi?", "che giorno è?", "Che giorno è oggi?", "Che giorno è?"]):
        risposta = Calendar.giorno_attuale()
        
        
    ### Data futura ###
    elif any(parola in transcript for parola in ["che giorno è ", "Che giorno è "]):
        risposta = Calendar.data_futura(transcript)


    ### imposta promemoria ###
    elif any(parola in transcript for parola in ["imposta promemoria", "Imposta promemoria", "crea promemoria", "Crea promemoria", "nuovo promemoria", "Nuovo promemoria"]):
        if chat_mode_active:
            Chat_output.set_message("Inserisci il messaggio del promemoria: ")
            messaggio = Chat_input.get_user_input()
            Chat_output.set_message("Inserisci per quando va il promemoria (formato accettato: 'dd/mm HH:MM', 'dd Month HH:MM', 'dd/mm', 'dd Month' o solo 'HH:MM'): ")
            input_data = Chat_input.get_user_input()
        else:
            TTS_offline.music_status_set()
            TTS_offline.run("Un promemoria per cosa", True)
            messaggio = stt_response(SERVER_URL)
                
            TTS_offline.run("Per quando", True)
            input_data = stt_response(SERVER_URL)
                
        risposta = Calendar.imposta_promemoria(messaggio, input_data)


    ### cancella promemoria ###
    elif any(parola in transcript for parola in ["cancella promemoria", "Cancella promemoria", "elimina promemoria", "Elimina promemoria"]):
        if chat_mode_active:
            Chat_output.set_message("Inserisci il messaggio del promemoria da cancellare: ")
            messaggio = Chat_input.get_user_input()
        else:
            TTS_offline.run("Quale promemoria vuoi cancellare?", None)
            messaggio = stt_response(SERVER_URL)
        risposta = Calendar.cancella_promemoria(messaggio)


    ### mostra tutti i promemoria ###
    elif any(parola in transcript for parola in ["mostra promemoria", "Mostra promemoria", "mostrami i promemoria", "Mostrami i promemoria"]):
        risposta = Calendar.all_promemoria()
        
        
        
        
    ### Risposta precedente ###
#     elif any(parola in transcript for parola in ["cosa ti ho chiesto prima?", "Cosa ti ho chiesto prima?"]):
#         risposta = f"Hai chiesto: {sheet[f'A{c-1}'].value} ed ho risposto: {sheet[f'B{c-1}'].value}"
        
    
    
    
    ### Attivare memoria di conversazione ###
    elif any(parola in transcript for parola in ["parliamo un po'.", "parliamo un po'?", "memoria di chat on.", "Memoria di chat on."]):
        if any(parola in transcript for parola in ["parliamo un po'.", "parliamo un po'?"]):
            risposta = "Certo, di cosa vuoi parlare?"
        else:
            risposta = "Memoria di chat attivata."
        if not chat_mode_active:
            # modalità conversazione vocale
            conversation_mode = True
        
    ### Disattivare memoria di conversazione ###
    elif any(parola in transcript for parola in ["grazie.", "Grazie.", "basta così.", "Basta così.", "memoria di chat off.", "Memoria di chat off."]):
        if any(parola in transcript for parola in ["grazie.", "Grazie."]):
            risposta = "Prego."
        elif any(parola in transcript for parola in ["basta così.", "Basta così."]):
            risposta = "Va bene."
        else:
            risposta = "Memoria di chat disattivata."
        if not chat_mode_active:
            # modalità conversazione vocale
            conversation_mode = False
    
    
    
    
    ### Comandi per musica ###
    elif any(parola in transcript for parola in ["ferma musica", "pausa musica", "stop musica", "Ferma musica", "Pausa musica", "Stop musica"]):
        Music.stop_music()
        risposta = "Musica in pausa."

    elif any(parola in transcript for parola in ["riprendi musica", "Riprendi musica"]):
        Music.resume_music()
        risposta = "Musica ripresa."

    elif any(parola in transcript for parola in ["termina musica", "Termina musica"]):
        Music.end_music()
        risposta = "Riproduzione terminata."
        
    elif any(parola in transcript for parola in ["mostra coda", "Mostra coda"]):
        risposta = Music.show_queue()

    elif any(parola in transcript for parola in ["volume", "Volume", "alza il volume", "Alza il volume", "abbassa il volume", "Abbassa il volume"]):
        risposta = Music.set_volume(transcript)
        
    elif any(parola in transcript for parola in ["skip", "Skip"]):
        Music.skip_music()
        risposta = "Canzone skippata."
    
    
    
    
    ### Comandi App_manager
    elif any(parola in transcript for parola in ["Apri", "Avvia", "apri", "avvia"]):
        risposta = App_manager.apri_app(transcript)
        
    elif any(parola in transcript for parola in ["mostra app", "Mostra app"]):
        risposta = App_manager.mostra_app()
        
    elif any(parola in transcript for parola in ["aggiungi app", "Aggiungi app"]):
        if chat_mode_active:
            Chat_output.set_message("Inserisci il percorso file dell'app (tasto destro, copia come percorso): ")
            path = Chat_input.get_user_input()
            path = path.rstrip('.')
            transcript = f"aggiungi app {path}"
            print(transcript)
            risposta = App_manager.aggiungi_app(transcript)
        else:
            risposta = "Esegui questo comando sulla chat"
        
        
        
        
    ### Lista comandi eseguibili ###
    elif transcript == "\help.":
        risposta = commands_list
    
    
    
        
    ### Cancellare conversazione attuale ###
#     elif any(parola in transcript for parola in ["cancella conversazione.", "Cancella conversazione."]):
#         risposta = "Certamente"
#         new_sheet = record_conversation.create_sheet(title="New Conversation ghost")
#         if "New Conversation" in record_conversation.sheetnames:
#             record_conversation.remove(record_conversation["New Conversation"])
#         new_sheet.title = "New Conversation"
#         sheet = new_sheet
#         c = 2  # Reset c quando viene creato un nuovo foglio
#         return risposta, sheet, c, False, conversation_memory, conversation_mode
    
    
    
    
######### --------- Da qui non si possono mettere funzioni elif esterni alle funzionalità con WiFi ed Offline --------- #########
    
    
    
    
##### Funzionalità con Internet. Internet presente #####
    elif state == "online":
        
        ### Controllo luci ###
        if any(parola in transcript for parola in ["accendi la luce.", "accendi le luci.", "Accendi la luce.", "Accendi le luci."]):
            Light.on()
            risposta = "Luce accesa."
            
        elif any(parola in transcript for parola in ["spegni la luce.", "spegni le luci.", "Spegni la luce.", "Spegni le luci."]):
            Light.off()
            risposta = "Luce spenta."
            
            
        ### Previsioni meteo attuali ###
        elif any(parola in transcript for parola in ["che tempo fa oggi ", "Che tempo fa oggi ", "che tempo fa oggi?", "Che tempo fa oggi?"]):
            risposta = Weather.run(transcript)
            
            
        ### Ricerca sul Web ###
        elif any(parola in transcript for parola in ["ricerca", "cerca su internet", "Ricerca", "Cerca su internet"]):
            risposta = Browsering.run(transcript)
            
            
        ### Riproduzione brani ###
        elif any(parola in transcript for parola in ["aggiungi alla coda", "aggiungi in coda", "Aggiungi alla coda", "Aggiungi in coda", "metti in coda", "Metti in coda"]):
            risposta = Music.add_to_queue(transcript)
            
        elif any(parola in transcript for parola in ["riproduci", "metti", "Riproduci", "Metti"]):
            risposta = Music.youtube_player(transcript)
            

        
        
##### Funzionalità con Internet. Internet assente (lan_only o offline) #####
# lan_only si comporta come offline: né client né server hanno accesso a Internet
    elif state in ("lan_only", "offline"):
        
        ### Comandi che richiedono Internet ###
        if any(parola in transcript for parola in [
                "accendi la luce.", "accendi le luci.", "Accendi la luce.", "Accendi le luci.",
                "spegni la luce.", "spegni le luci.", "Spegni la luce.", "Spegni le luci.",
                "che tempo fa oggi ", "Che tempo fa oggi ", "che tempo fa oggi?", "Che tempo fa oggi?",
                "ricerca", "cerca su internet", "Ricerca", "Cerca su internet",
                "riproduci", "metti", "Riproduci", "Metti",
                "aggiungi alla coda", "aggiungi in coda", "Aggiungi alla coda", "Aggiungi in coda",
                "metti in coda", "Metti in coda"
            ]):
            risposta = "Connessione a Internet non disponibile, non posso soddisfare la richiesta."
    
    
    
    
    ### Se nessuna delle soluzione corrisponde alla richiesta, allora sarà Ollama a rispondere ###
    else:
        return None, conversation_memory, conversation_mode

    return risposta, conversation_memory, conversation_mode