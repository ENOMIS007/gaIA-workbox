# Dispatcher.py
# Riceve l'intent già classificato da gaIA_v0101.py e chiama la skill giusta.
# Gestisce internamente il Context.
#
# Flusso per ogni richiesta:
#   1. gaIA_v0101.py chiama classify() → ottiene intent
#   2. gaIA_v0101.py chiama Dispatcher.skills(intent, transcript)
#   3. Dispatcher chiama ParamExtractor.extract() → ottiene params strutturati
#   4. Dispatcher chiama skill.execute(ctx, params)
#   5. La skill usa params già pronti — zero parsing interno
#
# Utilizzo da gaIA_v0101.py:
#     import Dispatcher
#     Dispatcher.init_context(server_url, connection_status, chat_mode_active, ...)
#     Dispatcher.update_context(server_url, connection_status, chat_mode_active)
#     risposta = Dispatcher.skills(intent, transcript)

import requests
import TTS_offline
import Chat_output
import Chat_input
import Calendar
import Music
import Light
import Browsering
import Weather
import App_manager
import ParamExtractor
from ParamExtractor import _parse_reminder
from Interprete import Context


# ---------------------------------------------------------------------------
# Context — creato una volta sola, aggiornato ad ogni iterazione
# Gestito interamente dal Dispatcher
# ---------------------------------------------------------------------------

_ctx: Context = None

# Inizializza il Context
def init_context(server_url: str, connection_status: dict, chat_mode_active: bool, conversation_memory: bool, conversation_mode: bool):
    global _ctx
    _ctx = Context(
        server_url=server_url,
        connection_status=connection_status,
        chat_mode_active=chat_mode_active,
        conversation_memory=conversation_memory,
        conversation_mode=conversation_mode,
    )

# Aggiorna i campi dinamici
def update_context(server_url: str, connection_status: dict, chat_mode_active: bool):
    _ctx.server_url = server_url
    _ctx.connection_status = connection_status
    _ctx.chat_mode_active  = chat_mode_active


# ---------------------------------------------------------------------------
# Helper condivisi — privati, usati solo dalle skill
# ---------------------------------------------------------------------------

# Avvia STT sul server e restituisce la trascrizione.
def _stt(server_url: str) -> str:
    response = requests.post(f"{server_url}/start_stt", json={})
    if response.status_code == 200:
        return response.json().get("transcription", "")
    return ""


# Vocalizza una domanda e attende risposta STT.
def _ask_vocal(server_url: str, prompt: str) -> str:
    TTS_offline.music_status_set()
    TTS_offline.run(prompt, True)
    return _stt(server_url)


# Mostra un prompt nella chat e attende input testuale.
def _ask_chat(prompt: str) -> str:
    Chat_output.set_message(prompt)
    return Chat_input.get_user_input()


def _no_internet() -> str:
    return "Connessione a Internet non disponibile, non posso soddisfare la richiesta."


# ---------------------------------------------------------------------------
# Classe base Skill
# ---------------------------------------------------------------------------

class Skill:
    """
    Interfaccia comune per tutte le skill.

    execute() riceve:
    - ctx:    il Context con stato corrente (connessione, modalità ecc.)
    - params: dict con parametri già estratti da ParamExtractor
              es. {"query": "bohemian rhapsody"} per MUSIC_PLAY

    Restituisce la risposta come stringa.
    Le skill NON fanno parsing — ricevono dati già pronti.
    """
    def execute(self, ctx: Context, params: dict) -> str:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Skill — Tempo / Calendario
# ---------------------------------------------------------------------------

class TIME_CURRENT_Skill(Skill):
    def execute(self, ctx, params):
        return Calendar.orario_attuale()


class DAY_CURRENT_Skill(Skill):
    def execute(self, ctx, params):
        return Calendar.giorno_attuale()


class DAY_FUTURE_Skill(Skill):
    def execute(self, ctx, params):
        from ParamExtractor import _parse_date
        data_raw = params.get("data", "")
        data = _parse_date(data_raw)
        return Calendar.data_futura(data)


# ---------------------------------------------------------------------------
# Skill — Promemoria
# ---------------------------------------------------------------------------

class REMINDER_SET_Skill(Skill):
    def execute(self, ctx, params):
        messaggio = params.get("messaggio")
        data      = params.get("data")
        ora       = params.get("ora")

        # Chiede solo i parametri mancanti
        if not messaggio:
            if ctx.chat_mode_active:
                messaggio = _ask_chat("Inserisci il messaggio del promemoria: ")
            else:
                messaggio = _ask_vocal(ctx.server_url, "Un promemoria per cosa")

        if not data and not ora:
            if ctx.chat_mode_active:
                raw = _ask_chat("Per quando? (es. domani alle 15, venerdì, 12/03): ")
            else:
                raw = _ask_vocal(ctx.server_url, "Per quando")

            p_extra = _parse_reminder(raw)
            data = p_extra["data"]
            ora  = p_extra["ora"]

            # Se il parse non ha trovato data/ora valide, chiedi di nuovo una sola volta
            if not data and not ora:
                errore = "Non ho capito la data. Riprova (es. domani alle 15, 27/07, venerdì alle 9): "
                if ctx.chat_mode_active:
                    raw = _ask_chat(errore)
                else:
                    raw = _ask_vocal(ctx.server_url, "Non ho capito. Ripeti la data e l'ora")
                p_extra = _parse_reminder(raw)
                data = p_extra["data"]
                ora  = p_extra["ora"]

        return Calendar.imposta_promemoria(messaggio, data, ora)


class REMINDER_DELETE_Skill(Skill):
    def execute(self, ctx, params):
        messaggio = params.get("messaggio")
        if not messaggio:
            if ctx.chat_mode_active:
                messaggio = _ask_chat("Inserisci il messaggio del promemoria da cancellare: ")
            else:
                messaggio = _ask_vocal(ctx.server_url, "Quale promemoria vuoi cancellare?")
        return Calendar.cancella_promemoria(messaggio)


class REMINDER_SHOW_Skill(Skill):
    def execute(self, ctx, params):
        return Calendar.all_promemoria()


# ---------------------------------------------------------------------------
# Skill — Meteo
# ---------------------------------------------------------------------------

class WEATHER_Skill(Skill):
    def execute(self, ctx, params):
        if ctx.connection_status.get("state") != "online":
            return _no_internet()
        # citta è già estratta da ParamExtractor — None se non specificata
        citta = params.get("citta")
        return Weather.run(citta)


# ---------------------------------------------------------------------------
# Skill — Musica
# ---------------------------------------------------------------------------

class MUSIC_PLAY_Skill(Skill):
    def execute(self, ctx, params):
        if ctx.connection_status.get("state") != "online":
            return _no_internet()
        query = params.get("query")
        if not query:
            if ctx.chat_mode_active:
                query = _ask_chat("Cosa vuoi ascoltare? ")
            else:
                query = _ask_vocal(ctx.server_url, "Cosa vuoi ascoltare?")
        return Music.youtube_player(query)


class MUSIC_ADD_TO_QUEUE_Skill(Skill):
    def execute(self, ctx, params):
        if ctx.connection_status.get("state") != "online":
            return _no_internet()
        query = params.get("query")
        if not query:
            if ctx.chat_mode_active:
                query = _ask_chat("Cosa vuoi aggiungere alla coda? ")
            else:
                query = _ask_vocal(ctx.server_url, "Cosa vuoi aggiungere alla coda?")
        return Music.add_to_queue(query)


class MUSIC_STOP_Skill(Skill):
    def execute(self, ctx, params):
        Music.stop_music()
        return "Musica in pausa."


class MUSIC_RESUME_Skill(Skill):
    def execute(self, ctx, params):
        Music.resume_music()
        return "Musica ripresa."


class MUSIC_END_Skill(Skill):
    def execute(self, ctx, params):
        Music.end_music()
        return "Riproduzione terminata."


class MUSIC_QUEUE_SHOW_Skill(Skill):
    def execute(self, ctx, params):
        return Music.show_queue()


class MUSIC_VOLUME_Skill(Skill):
    def execute(self, ctx, params):
        # valore, direzione e delta già strutturati da ParamExtractor
        valore    = params.get("valore")
        direzione = params.get("direzione")
        delta     = params.get("delta")
        return Music.set_volume(valore, direzione, delta)


class MUSIC_SKIP_Skill(Skill):
    def execute(self, ctx, params):
        Music.skip_music()
        return "Canzone skippata."


# ---------------------------------------------------------------------------
# Skill — Luci
# ---------------------------------------------------------------------------

class LIGHT_ON_Skill(Skill):
    def execute(self, ctx, params):
        if ctx.connection_status.get("state") != "online":
            return _no_internet()
        Light.on()
        return "Luce accesa."


class LIGHT_OFF_Skill(Skill):
    def execute(self, ctx, params):
        if ctx.connection_status.get("state") != "online":
            return _no_internet()
        Light.off()
        return "Luce spenta."


# ---------------------------------------------------------------------------
# Skill — App
# ---------------------------------------------------------------------------

class APP_OPEN_Skill(Skill):
    def execute(self, ctx, params):
        nome_app = params.get("nome_app")
        if not nome_app:
            if ctx.chat_mode_active:
                nome_app = _ask_chat("Quale app vuoi aprire? ")
            else:
                nome_app = _ask_vocal(ctx.server_url, "Quale app vuoi aprire?")
        return App_manager.apri_app(nome_app)


class APP_ADD_Skill(Skill):
    def execute(self, ctx, params):
        if ctx.chat_mode_active:
            path = _ask_chat(
                "Inserisci il percorso file dell'app "
                "(tasto destro, copia come percorso): "
            ).rstrip(".")
            return App_manager.aggiungi_app(path)
        return "Esegui questo comando dalla chat."


class APP_SHOW_Skill(Skill):
    def execute(self, ctx, params):
        return App_manager.mostra_app()


# ---------------------------------------------------------------------------
# Skill — Web
# ---------------------------------------------------------------------------

class WEB_SEARCH_Skill(Skill):
    def execute(self, ctx, params):
        if ctx.connection_status.get("state") != "online":
            return _no_internet()
        query = params.get("query")
        if not query:
            if ctx.chat_mode_active:
                query = _ask_chat("Cosa vuoi cercare? ")
            else:
                query = _ask_vocal(ctx.server_url, "Cosa vuoi cercare?")
        return Browsering.run(query)


# ---------------------------------------------------------------------------
# Skill — Utilità
# ---------------------------------------------------------------------------

class SHOW_SKILLS_Skill(Skill):
    SKILLS = """Lista skills:

Ora attuale:      che ore sono? | che ora è?
Giorno attuale:   che giorno è oggi?
Data futura:      che giorno è (+ data o giorno)
Meteo:            che tempo fa oggi
Promemoria:       imposta / cancella / mostra promemoria
Musica:           riproduci / aggiungi alla coda / ferma /
                  riprendi / termina / skip / mostra coda / volume
Luci:             accendi la luce | spegni la luce
App:              apri <nome> | aggiungi app | mostra app
Web:              cerca su internet <query>
"""
    def execute(self, ctx, params):
        return self.SKILLS


# ---------------------------------------------------------------------------
# Registro intent → skill
# Aggiungere una skill nuova = creare la classe + aggiungere una riga qui
# ---------------------------------------------------------------------------

SKILL_REGISTRY: dict[str, Skill] = {
    "TIME_CURRENT":       TIME_CURRENT_Skill(),
    "DAY_CURRENT":        DAY_CURRENT_Skill(),
    "DAY_FUTURE":         DAY_FUTURE_Skill(),
    "REMINDER_SET":       REMINDER_SET_Skill(),
    "REMINDER_DELETE":    REMINDER_DELETE_Skill(),
    "REMINDER_SHOW":      REMINDER_SHOW_Skill(),
    "WEATHER":            WEATHER_Skill(),
    "MUSIC_PLAY":         MUSIC_PLAY_Skill(),
    "MUSIC_ADD_TO_QUEUE": MUSIC_ADD_TO_QUEUE_Skill(),
    "MUSIC_STOP":         MUSIC_STOP_Skill(),
    "MUSIC_RESUME":       MUSIC_RESUME_Skill(),
    "MUSIC_END":          MUSIC_END_Skill(),
    "MUSIC_QUEUE_SHOW":   MUSIC_QUEUE_SHOW_Skill(),
    "MUSIC_VOLUME":       MUSIC_VOLUME_Skill(),
    "MUSIC_SKIP":         MUSIC_SKIP_Skill(),
    "LIGHT_ON":           LIGHT_ON_Skill(),
    "LIGHT_OFF":          LIGHT_OFF_Skill(),
    "APP_OPEN":           APP_OPEN_Skill(),
    "APP_ADD":            APP_ADD_Skill(),
    "APP_SHOW":           APP_SHOW_Skill(),
    "WEB_SEARCH":         WEB_SEARCH_Skill(),
    "SHOW_SKILLS":        SHOW_SKILLS_Skill(),
}


# ---------------------------------------------------------------------------
# Punto di ingresso — chiamato da gaIA_v0101.py
# ---------------------------------------------------------------------------

# Riceve l'intent già classificato e la trascrizione originale per chiamare le skill necessarie.
# Le skills ricevono solo ctx e params
# La trascrizione viene passata solo a ParamExtractor
def skills(intent: str, transcript: str) -> str | None:
    # Step 1 — ParamExtractor estrae i parametri strutturati dalla trascrizione
    params = ParamExtractor.extract(intent, transcript)

    # Step 2 — Cerca e chiama la skill
    skill = SKILL_REGISTRY.get(intent)
    
    # Step 3 — Restituisce la risposta o None per il fallback all'AI
    try:
        return skill.execute(_ctx, params)
    except Exception as e:
        print(f"[Dispatcher] Errore nella skill '{intent}': {e}")
        return None
