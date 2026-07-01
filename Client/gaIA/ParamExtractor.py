# ParamExtractor.py
# Estrae parametri strutturati da una trascrizione usando il modello CRF.
# È l'unico modulo che conosce la logica di estrazione.
# Dispatcher e skill ricevono dati già pronti senza dover fare parsing.
#
# Flusso:
#     trascrizione → CRF → parametro grezzo → parsing strutturato → dict
#
# Utilizzo:
#     from ParamExtractor import extract
#     params = extract("MUSIC_PLAY", "fammi sentire qualcosa di eminem")
#     # → {"query": "qualcosa di eminem"}
#
# Prima di usare, generare il modello con:
#     python train_params_model.py

import re
import os
import joblib
from datetime import datetime, timedelta, date
from typing import Optional


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------

def word_features(words: list, i: int, intent: str = "") -> dict:
    """
    Trasforma una parola nel suo contesto in un dizionario di feature.
    Il CRF non lavora sulle parole direttamente — lavora su questi numeri/stringhe.

    Ogni feature cattura un aspetto diverso della parola:
    - Identità:    word.lower, word.clean
    - Morfologia:  suffissi, prefissi, isdigit
    - Struttura:   posizione nella frase, is_first, is_last
    - Contesto:    parola precedente, parola successiva, bigrammi
    - Dominio:     intent (stringe il campo di classificazione)

    NON usiamo feature legate a maiuscole/minuscole (isupper, istitle)
    perché lo STT è imprevedibile — "Jane" può diventare "jane" o "JANE".
    Tutto viene normalizzato in minuscolo.
    """
    word       = words[i]
    word_lower = word.lower()
    # Rimuove punteggiatura — "brevi?" → "brevi", "AC/DC" → "ACDC"
    word_clean = re.sub(r"[^\w]", "", word_lower)

    features = {
        # --- Dominio ---
        # L'intent è la feature più importante — permette al CRF di imparare
        # pattern diversi per ogni skill. "coda" in MUSIC_ADD_TO_QUEUE è X,
        # in altro contesto potrebbe essere P.
        "intent": intent,

        # --- Identità ---
        # La parola intera — feature più potente per parole viste nel training.
        # Il CRF memorizza che "metti" in MUSIC_PLAY è quasi sempre X.
        "word.lower": word_lower,
        "word.clean": word_clean,

        # --- Morfologia: suffissi ---
        # Rivelano la forma grammaticale della parola.
        # "-esti", "-bbe" → condizionale → spesso X ("metteresti", "vorrebbe")
        # "-one", "-ale"  → sostantivi   → spesso P
        "word.suffix2": word_clean[-2:] if len(word_clean) >= 2 else word_clean,
        "word.suffix3": word_clean[-3:] if len(word_clean) >= 3 else word_clean,
        "word.suffix4": word_clean[-4:] if len(word_clean) >= 4 else word_clean,

        # --- Morfologia: prefissi ---
        # "ri-" indica verbo ("riproduci", "ricordami") → spesso X
        "word.prefix2": word_clean[:2] if len(word_clean) >= 2 else word_clean,
        "word.prefix3": word_clean[:3] if len(word_clean) >= 3 else word_clean,

        # --- Morfologia: numeri ---
        # Numeri puri ("15", "80") → quasi sempre P (volume, data, ora)
        "word.isdigit":   word_clean.isdigit(),
        # Contiene cifre ("18:30") → probabile P anche se non è numero puro
        "word.has_digit": any(c.isdigit() for c in word_clean),

        # --- Struttura: posizione ---
        # Keyword tendono verso 0.0 (inizio frase)
        # Parametri tendono verso 1.0 (fine frase)
        # max(..., 1) evita divisione per zero su frasi di una sola parola
        "word.position": round(i / max(len(words) - 1, 1), 2),
        "word.is_first": i == 0,
        "word.is_last":  i == len(words) - 1,
    }

    # --- Contesto sinistro: parola precedente ---
    # Il contesto è fondamentale per il CRF — il tag di una parola
    # dipende da quello delle parole vicine.
    if i > 0:
        prev_lower = words[i - 1].lower()
        features.update({
            # La parola precedente — pattern tipo: dopo "coda" → P
            "prev.lower":   prev_lower,
            # Se la precedente è un numero — utile per sequenze numeriche
            "prev.isdigit": words[i - 1].lower().replace(" ", "").isdigit(),
            # Bigramma sinistro — coppia (precedente, corrente)
            # Cattura relazioni che le feature singole non vedono:
            # "in_coda" → X, "alle_15" → 15 è P, "di_annalisa" → P
            "bigram.prev":  f"{prev_lower}_{word_lower}",
        })
    else:
        # Beginning Of Sentence — la prima parola tende ad essere X (keyword)
        features["BOS"] = True

    # --- Contesto destro: parola successiva ---
    if i < len(words) - 1:
        nxt_lower = words[i + 1].lower()
        features.update({
            "next.lower":   nxt_lower,
            "next.isdigit": words[i + 1].lower().replace(" ", "").isdigit(),
            # Bigramma destro — coppia (corrente, successiva)
            # "metti_in" → X, "coda_jane" → segnala che "jane" sarà P
            "bigram.next":  f"{word_lower}_{nxt_lower}",
        })
    else:
        # End Of Sentence — l'ultima parola tende ad essere P (parametro)
        features["EOS"] = True

    return features


# ---------------------------------------------------------------------------
# Costanti — aggiorna il path se sposti i file
# ---------------------------------------------------------------------------

MODEL_PATH = "Model\ParamsExtractor\params_model.pkl"


# ---------------------------------------------------------------------------
# Vocabolario temporale
# ---------------------------------------------------------------------------

MONTHS = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
    "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
    "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12
}

WEEKDAYS = {
    "lunedì": 0, "martedì": 1, "mercoledì": 2, "giovedì": 3,
    "venerdì": 4, "sabato": 5, "domenica": 6
}

WRITTEN_NUMBERS = {
    "uno": 1, "due": 2, "tre": 3, "quattro": 4, "cinque": 5,
    "sei": 6, "sette": 7, "otto": 8, "nove": 9, "dieci": 10,
    "undici": 11, "dodici": 12, "tredici": 13, "quattordici": 14,
    "quindici": 15, "sedici": 16, "diciassette": 17, "diciotto": 18,
    "diciannove": 19, "venti": 20, "ventuno": 21, "ventidue": 22,
    "ventitré": 23, "ventiquattro": 24, "venticinque": 25,
    "ventisei": 26, "ventisette": 27, "ventotto": 28, "ventinove": 29,
    "trenta": 30, "trentuno": 31
}

SPECIAL_TIMES = {
    "mezzogiorno":    "12:00",
    "mezzanotte":     "00:00",
    "mattina":        "09:00",
    "mattino":        "09:00",
    "di mattina":     "09:00",
    "pomeriggio":     "15:00",
    "nel pomeriggio": "15:00",
    "di pomeriggio":  "15:00",
    "sera":           "20:00",
    "di sera":        "20:00",
    "stasera":        "20:00",
}

SPECIAL_MINUTES = {
    "mezza": 30,
    "mezzo": 30,
    "un quarto": 15,
    "quarto": 15,
    "tre quarti": 45,
}

SPECIAL_MINUTES_MINUS = {
    "meno un quarto": 15,
    "meno quarto": 15,
}


# Pattern che segnalano la parte temporale in una frase di promemoria.
# Usati da _parse_reminder() per separare il messaggio dalla data/ora.
# ORDINE CRITICO: dal più specifico al più generico.
# I pattern composti vanno prima — "alle 15" deve essere rimosso come unità
# altrimenti "15" rimarrebbe orfano nel messaggio.

_TEMPORAL_MARKERS = [
    # ── Orari composti con base speciale ──────────────────────────────────────
    # Vanno prima di tutto perché contengono parole come "mezza" e "quarto"
    # che altrimenti verrebbero rimosse dai pattern semplici prima del tempo.
    r"\bmezzogiorno\s+e\s+(?:mezza|mezzo)\b",      # "mezzogiorno e mezza"
    r"\bmezzogiorno\s+e\s+\d{1,2}\b",              # "mezzogiorno e 10"
    r"\bmezzogiorno\s+meno\s+un\s+quarto\b",       # "mezzogiorno meno un quarto"
    r"\bmezzogiorno\s+meno\s+\d{1,2}\b",           # "mezzogiorno meno 10"
    r"\bmezzanotte\s+e\s+(?:mezza|mezzo)\b",
    r"\bmezzanotte\s+e\s+\d{1,2}\b",
    r"\bmezzanotte\s+meno\s+un\s+quarto\b",
    r"\bmezzanotte\s+meno\s+\d{1,2}\b",

    # ── Orari composti numerici ───────────────────────────────────────────────
    r"\balle\s+\d{1,2}\s+meno\s+un\s+quarto\b",
    r"\balle\s+\d{1,2}\s+meno\s+quarto\b",
    r"\balle\s+\d{1,2}\s+meno\s+\d{1,2}\b",
    r"\b\d{1,2}\s+meno\s+\d{1,2}\b",
    r"\balle\s+\d{1,2}\s+e\s+tre\s+quarti\b",
    r"\balle\s+\d{1,2}\s+e\s+un\s+quarto\b",
    r"\balle\s+\d{1,2}\s+e\s+(?:mezza|mezzo)\b",
    r"\balle\s+\d{1,2}:\d{2}\b",
    r"\balle\s+\d{1,2}\s+e\s+\d{2}\b",
    r"\balle\s+\d{1,2}[.,]\d{2}\b",
    r"\balle\s+\d{1,2}\b",
    r"\ble\s+\d{1,2}:\d{2}\b",
    r"\ble\s+\d{1,2}\s+e\s+\d{2}\b",
    r"\ble\s+\d{1,2}\b",
    r"\b\d{1,2}:\d{2}\b",

    # ── Date numeriche ────────────────────────────────────────────────────────
    r"\bgiorno\s+\d{1,2}\s+(?:" + "|".join(MONTHS.keys()) + r")\b",    # "giorno 18 luglio"
    r"\bgiorno\s+\d{1,2}/\d{1,2}\b",                                   # "giorno 18/07"
    r"\bgiorno\s+\d{1,2}\b",                                           # "giorno 23"
    r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b",
    r"\bil\s+\d{1,2}\b",
    r"\b\d{1,2}\s+(?:" + "|".join(MONTHS.keys()) + r")\b",

    # ── Date relative ─────────────────────────────────────────────────────────
    r"\bdomani\b", r"\bdopodomani\b", r"\boggi\b",
    r"\bfra\b", r"\btra\b",
    r"\blunedì\b", r"\bmartedì\b", r"\bmercoledì\b",
    r"\bgiovedì\b", r"\bvenerdì\b", r"\bsabato\b", r"\bdomenica\b",
    r"\bfine (del )?mese\b", r"\binizio (del )?mese\b",
    r"\bsettimana prossima\b", r"\bmese prossimo\b",

    # ── Orari speciali nominali ───────────────────────────────────────────────
    r"\ba mezzogiorno\b", r"\ba mezzanotte\b",
    r"\bdi mattina\b", r"\bdi mattino\b",
    r"\bnel pomeriggio\b", r"\bdi pomeriggio\b",
    r"\bdi sera\b", r"\bstasera\b",
    r"\bmezzogiorno\b", r"\bmezzanotte\b",
    r"\bmattina\b", r"\bmattino\b",
    r"\bpomeriggio\b", r"\bsera\b",

    # ── Residui frazioni d'ora ────────────────────────────────────────────────
    # Vanno dopo tutti i pattern composti — rimuovono parole orfane rimaste.
    r"\btre\s+quarti\b",        # "tre quarti" prima di "quarti" da solo
    r"\bun\s+quarto\b",         # "un quarto" prima di "quarto" da solo
    r"\be\s+mezza\b",           # "e mezza" prima di "mezza" da solo
    r"\be\s+mezzo\b",
    r"\be\s+\d{1,2}\b",         # "e 10" residuo dopo "mezzogiorno e 10"
    r"\bmeno\s+un\s+quarto\b",  # "meno un quarto" prima di "meno" da solo
    r"\bmeno\s+\d{1,2}\b",      # "meno 10" residuo
    r"\bmezza\b", r"\bmezzo\b",
    r"\bquarto\b",
    r"\bmeno\b",
]

# ---------------------------------------------------------------------------
# Caricamento modello — singleton
# Viene caricato una volta sola all'import, come FastText in Interpreter.py
# ---------------------------------------------------------------------------

if not os.path.exists(MODEL_PATH):
    raise FileNotFoundError(
        f"Modello non trovato: '{MODEL_PATH}'. "
        f"Eseguire prima: python train_params_model.py"
    )

_crf = joblib.load(MODEL_PATH)


# ---------------------------------------------------------------------------
# Estrazione parametro grezzo con CRF
# ---------------------------------------------------------------------------

# Esempio:
#     intent="MUSIC_PLAY", transcript="fammi sentire qualcosa di eminem"
#     tags: [X, X, P, X, P]
#     → "qualcosa eminem"

def _extract_param(intent: str, transcript: str) -> str:
    # Normalizza in minuscolo
    text  = transcript.lower().strip().rstrip(".?!")
    words = text.split()

    if not words:
        return ""

    # Estrazione delle feature per ogni parola
    features = [word_features(words, i, intent) for i in range(len(words))]
    
    # CRF precide X (non è importante) o P (parametro) per ogni parola
    tags = _crf.predict([features])[0]

    # Tieni solo le parole con tag P
    param_words = [w for w, t in zip(words, tags) if t == "P"]
    return " ".join(param_words).strip()


# ---------------------------------------------------------------------------
# Parsing data
# Lavora sul parametro grezzo (senza keyword)
# ---------------------------------------------------------------------------

# Converte stringa in intero, sia se in cifre ("3") che in parole ("tre")
def _resolve_number(text: str) -> Optional[int]:
    if text.isdigit():
        return int(text)
    return WRITTEN_NUMBERS.get(text.lower())


# Estrae date relative, giorni della settimana e date assolute dal parametro grezzo.
def _parse_date(text: str) -> Optional[date]:
    oggi = date.today()
    text_lower = text.lower().strip().rstrip(".?!")

    # Date relative semplici
    if re.search(r"\boggi\b", text_lower):
        return oggi
    if re.search(r"\bdomani\b", text_lower):
        return oggi + timedelta(days=1)
    if re.search(r"\bdopodomani\b", text_lower):
        return oggi + timedelta(days=2)

    # "fra/tra N giorni/settimane/mesi"
    m = re.search(
        r"\b(?:fra|tra)\s+(\d+|[a-zà-ú]+)\s+(giorn[oi]|settiman[ae]|mes[ei])\b",
        text_lower
    )
    if m:
        n    = _resolve_number(m.group(1))
        unit = m.group(2)
        if n is not None:
            if "giorn"    in unit: return oggi + timedelta(days=n)
            elif "settiman" in unit: return oggi + timedelta(weeks=n)
            elif "mes"      in unit: return oggi + timedelta(days=n * 30)

    # Giorno della settimana
    for day_name, day_idx in WEEKDAYS.items():
        if re.search(rf"\b{day_name}\b", text_lower):
            days_ahead = (day_idx - oggi.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            return oggi + timedelta(days=days_ahead)

    # "fine mese"
    if re.search(r"\bfine (del )?mese\b", text_lower):
        if oggi.month == 12:
            return datetime(oggi.year + 1, 1, 1).date() - timedelta(days=1)
        return datetime(oggi.year, oggi.month + 1, 1).date() - timedelta(days=1)

    # "inizio/primo del mese"
    if re.search(r"\b(inizio|primo) (del )?mese\b", text_lower):
        if oggi.month == 12:
            return datetime(oggi.year + 1, 1, 1).date()
        return datetime(oggi.year, oggi.month + 1, 1).date()

    # "settimana prossima"
    if re.search(r"\bsettimana prossima\b", text_lower):
        return oggi + timedelta(weeks=1)

    # "mese prossimo"
    if re.search(r"\bmese prossimo\b", text_lower):
        return oggi + timedelta(days=30)
    
    # "giorno N" — es. "giorno 23", "giorno 18 luglio", "giorno 18/07"
    m = re.search(r"\bgiorno\s+(\d{1,2})\b", text_lower)
    if m:
        giorno = int(m.group(1))
        # Controlla se c'è anche il mese dopo
        m2 = re.search(r"\bgiorno\s+\d{1,2}\s+(" + "|".join(MONTHS.keys()) + r")\b", text_lower)
        m3 = re.search(r"\bgiorno\s+(\d{1,2})/(\d{1,2})\b", text_lower)
        if m2:
            mese = MONTHS.get(m2.group(1))
            try:
                d = datetime(oggi.year, mese, giorno).date()
                if d < oggi:
                    d = d.replace(year=oggi.year + 1)
                return d
            except ValueError:
                pass
        elif m3:
            giorno = int(m3.group(1))
            mese   = int(m3.group(2))
            try:
                d = datetime(oggi.year, mese, giorno).date()
                if d < oggi:
                    d = d.replace(year=oggi.year + 1)
                return d
            except ValueError:
                pass
        else:
            # Solo "giorno N" — stesso mese se non passato, altrimenti prossimo
            mese = oggi.month if giorno >= oggi.day else oggi.month + 1
            if mese > 12:
                mese = 1
            try:
                d = datetime(oggi.year, mese, giorno).date()
                if d < oggi:
                    d = d.replace(year=oggi.year + 1)
                return d
            except ValueError:
                pass

    # Data numerica "dd/mm" o "dd/mm/yyyy"
    m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", text_lower)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        year = int(m.group(3)) if m.group(3) else oggi.year
        if len(str(year)) == 2:
            year += 2000
        try:
            d = datetime(year, month, day).date()
            if d < oggi:
                d = d.replace(year=oggi.year + 1)
            return d
        except ValueError:
            pass

    # Data testuale "12 marzo" o "il 12 marzo"
    m = re.search(
        r"\b(?:il\s+)?(\d{1,2}|[a-zà-ú]+)\s+(" + "|".join(MONTHS.keys()) + r")\b",
        text_lower
    )
    if m:
        day   = _resolve_number(m.group(1)) if not m.group(1).isdigit() else int(m.group(1))
        month = MONTHS.get(m.group(2))
        if day and month:
            try:
                d = datetime(oggi.year, month, day).date()
                if d < oggi:
                    d = d.replace(year=oggi.year + 1)
                return d
            except ValueError:
                pass

    return None


# ---------------------------------------------------------------------------
# Parsing ora
# ---------------------------------------------------------------------------

# Estrae un orario dal parametro grezzo, restituiendo una stringa "HH:MM" o None.
def _parse_time(text: str) -> Optional[str]:
    text_lower = text.lower().strip().rstrip(".?!")

    # ---------------------------------------------------------------------------
    # 1. Orari speciali con modificatore — PRIMA di SPECIAL_TIMES
    # Gestiamo "mezzogiorno/mezzanotte + e/meno + minuti" qui perché
    # SPECIAL_TIMES restituirebbe subito "12:00" senza guardare i minuti.
    # ---------------------------------------------------------------------------
    _SPECIAL_BASE = {"mezzogiorno": 720, "mezzanotte": 0}  # minuti da mezzanotte

    for base_word, base_minutes in _SPECIAL_BASE.items():
        if re.search(rf"\b{base_word}\b", text_lower):

            # "mezzogiorno e mezza/mezzo" → 12:30
            if re.search(rf"\b{base_word}\s+e\s+(?:mezza|mezzo)\b", text_lower):
                total = (base_minutes + 30) % (24 * 60)
                return f"{total // 60:02d}:{total % 60:02d}"

            # "mezzogiorno e MM" → 12:MM
            m = re.search(rf"\b{base_word}\s+e\s+(\d{{1,2}})\b", text_lower)
            if m:
                total = (base_minutes + int(m.group(1))) % (24 * 60)
                return f"{total // 60:02d}:{total % 60:02d}"

            # "mezzogiorno meno un quarto" → 11:45
            if re.search(rf"\b{base_word}\s+meno\s+un\s+quarto\b", text_lower):
                total = (base_minutes - 15) % (24 * 60)
                return f"{total // 60:02d}:{total % 60:02d}"

            # "mezzogiorno meno MM" → es. 11:50
            m = re.search(rf"\b{base_word}\s+meno\s+(\d{{1,2}})\b", text_lower)
            if m:
                total = (base_minutes - int(m.group(1))) % (24 * 60)
                return f"{total // 60:02d}:{total % 60:02d}"

            # "mezzogiorno" da solo → 12:00
            return f"{base_minutes // 60:02d}:{base_minutes % 60:02d}"

    # ---------------------------------------------------------------------------
    # 2. Orari speciali nominali senza modificatore
    # (mattina, sera, pomeriggio ecc.) — mezzogiorno/mezzanotte già gestiti sopra
    # ---------------------------------------------------------------------------
    for keyword, time_str in SPECIAL_TIMES.items():
        if re.search(rf"\b{re.escape(keyword)}\b", text_lower):
            return time_str

    # ---------------------------------------------------------------------------
    # 3. "alle/le HH meno un quarto / meno quarto"
    # Es. "alle 15 meno un quarto" → 14:45
    # Deve stare prima di "alle HH" per non catturare solo l'ora.
    # ---------------------------------------------------------------------------
    for phrase, minutes in SPECIAL_MINUTES_MINUS.items():
        m = re.search(rf"\b(?:alle|le|ore)\s+(\d{{1,2}})\s+{re.escape(phrase)}\b", text_lower)
        if not m:
            m = re.search(rf"\b(\d{{1,2}})\s+{re.escape(phrase)}\b", text_lower)
        if m:
            hour = int(m.group(1))
            if 0 <= hour <= 23:
                total = (hour * 60 - minutes) % (24 * 60)
                return f"{total // 60:02d}:{total % 60:02d}"

    # ---------------------------------------------------------------------------
    # 4. "alle/le HH e [mezza|quarto|tre quarti]"
    # Es. "alle 9 e un quarto" → 09:15
    # Deve stare prima di "alle HH e MM" per non confondere "mezza" con numero.
    # ---------------------------------------------------------------------------
    for phrase, minutes in SPECIAL_MINUTES.items():
        pattern_phrase = re.escape(phrase)
        m = re.search(rf"\b(?:alle|le|ore)\s+(\d{{1,2}})\s+(?:e\s+)?(?:un\s+)?{pattern_phrase}\b", text_lower)
        if not m:
            m = re.search(rf"\b(\d{{1,2}})\s+(?:e\s+)?(?:un\s+)?{pattern_phrase}\b", text_lower)
        if m:
            hour = int(m.group(1))
            if 0 <= hour <= 23:
                return f"{hour:02d}:{minutes:02d}"

    # ---------------------------------------------------------------------------
    # 5. "alle/le HH meno MM" con minuti numerici
    # Es. "alle 15 meno 20" → 14:40
    # ---------------------------------------------------------------------------
    m = re.search(r"\b(?:alle|le|ore)\s+(\d{1,2})\s+meno\s+(\d{1,2})\b", text_lower)
    if not m:
        m = re.search(r"\b(\d{1,2})\s+meno\s+(\d{1,2})\b", text_lower)
    if m:
        hour, minus = int(m.group(1)), int(m.group(2))
        if 0 <= hour <= 23 and 1 <= minus <= 59:
            total = (hour * 60 - minus) % (24 * 60)
            return f"{total // 60:02d}:{total % 60:02d}"

    # ---------------------------------------------------------------------------
    # 6. "alle/le HH:MM" o "alle HH e MM" o "alle HH."
    # Es. "alle 15:30", "alle 15 e 30"
    # ---------------------------------------------------------------------------
    m = re.search(
        r"\b(?:alle|le)\s+(\d{1,2})(?::(\d{2})|[.,](\d{2})|[\s]+e[\s]+(\d{2})|[.])?\b",
        text_lower
    )
    if m:
        hour   = int(m.group(1))
        minute = int(m.group(2) or m.group(3) or m.group(4) or 0)
        if hour == 24:
            hour = 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"

    # ---------------------------------------------------------------------------
    # 7. Orario senza "alle" — "15:30", "15.30"
    # ---------------------------------------------------------------------------
    m = re.search(r"\b(\d{1,2})[.:](\d{2})\b", text_lower)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"

    # ---------------------------------------------------------------------------
    # 8. Solo ora senza minuti — "alle 15" o "le 15"
    # ---------------------------------------------------------------------------
    m = re.search(r"\b(?:alle|le)\s+(\d{1,2})\b", text_lower)
    if m:
        hour = int(m.group(1))
        if hour == 24:
            return "00:00"
        if 0 <= hour <= 23:
            return f"{hour:02d}:00"

    return None


# ---------------------------------------------------------------------------
# Parsing specifici per intent
# ---------------------------------------------------------------------------


# Dal parametro grezzo separa messaggio, data e ora.
# Restituisce un dizionario con i tre campi, altrimenti None
#
# Esempio:
#     param_grezzo = "chiamare mario domani alle 15"
#     → messaggio: "chiamare mario"
#     → data:      date(2026, 3, 27)
#     → ora:       "15:00"

def _parse_reminder(param_grezzo: str) -> dict:
    if not param_grezzo:
        return {"messaggio": None, "data": None, "ora": None}

    # Estrazione data e ora con regex (lavorano su testo già pulito)
    data = _parse_date(param_grezzo)
    ora  = _parse_time(param_grezzo)

    # Rimuove data e ora per isolare il messaggio
    messaggio = param_grezzo
    for pattern in _TEMPORAL_MARKERS:
        messaggio = re.sub(pattern, "", messaggio, flags=re.IGNORECASE)
        
    # Rimuove articoli elisi orfani — "l'", "dell'", "nell'" rimasti dopo la pulizia
    messaggio = re.sub(r"\b(l'|dell'|nell'|all'|dall'|sull')\s*", "", messaggio, flags=re.IGNORECASE)
    
    messaggio = messaggio.strip().rstrip(",").strip() or None

    # Se c'è un orario ma nessuna data → usa oggi come default
    if ora is not None:
        if data is None:
            data = date.today()
        
        # Controllo se l'orario è già passato
        now = datetime.now()
        ora_dt = datetime.strptime(ora, "%H:%M").time()
        if data == date.today() and ora_dt <= now.time():
            data = data + timedelta(days=1)

    return {
        "messaggio": messaggio,
        "data":      data,
        "ora":       ora,
    }



# Dal parametro grezzo estrae valore numerico o direzione.
# 
# Esempio:
#     "80"    → {"valore": 80,   "direzione": None}
#     "forte" → {"valore": None, "direzione": "su"}
#     "piano" → {"valore": None, "direzione": "giù"}

def _parse_volume(param_grezzo: str) -> dict:
    text = param_grezzo.lower()
    m_num = re.search(r"\b(\d+)\b", text)

    # Parole che indicano direzione "su"
    has_su   = re.search(r"\b(alza|alzami|alzare|forte|alto|su)\b", text)
    # Parole che indicano direzione "giù"
    has_giu  = re.search(r"\b(abbassa|abbassami|abbassare|piano|basso|giù)\b", text)

    if m_num:
        numero = int(m_num.group(1))
        if has_su:
            # "alza di 15" / "metti più forte di 15" → delta relativo
            return {"valore": None, "direzione": "su", "delta": numero}
        elif has_giu:
            # "abbassa di 20" / "metti più piano di 20" → delta relativo
            return {"valore": None, "direzione": "giù", "delta": numero}
        else:
            # "volume a 80" → valore assoluto, nessuna parola di direzione
            return {"valore": numero, "direzione": None}
    if has_su:
        return {"valore": None, "direzione": "su", "delta": None}
    if has_giu:
        return {"valore": None, "direzione": "giù", "delta": None}

    return {"valore": None, "direzione": None, "delta": None}


# ---------------------------------------------------------------------------
# Funzione pubblica — unico punto di ingresso per il Dispatcher
# ---------------------------------------------------------------------------

# Riceve l'intent e la trascrizione pulita dalla wake word e restituisce parametri strutturati pronti per la skill.
# Per intent senza parametri restituisce {} che la skill ignora.
def extract(intent: str, transcript: str) -> dict:
    # Step 1 — CRF estrae il parametro grezzo
    param_grezzo = _extract_param(intent, transcript)

    # Step 2 — parsing specifico per ogni intent
    if intent == "REMINDER_SET":
        # Separa messaggio, data e ora
        return _parse_reminder(param_grezzo)

    elif intent == "REMINDER_DELETE":
        # Solo il messaggio del promemoria da cancellare
        return {"messaggio": param_grezzo or None}

    elif intent in ("MUSIC_PLAY", "MUSIC_ADD_TO_QUEUE"):
        # Query musicale — titolo e/o artista
        return {"query": param_grezzo or None}

    elif intent == "APP_OPEN":
        # Nome dell'app — può essere composto ("visual studio code")
        return {"nome_app": param_grezzo or None}

    elif intent == "WEB_SEARCH":
        # Query di ricerca web
        return {"query": param_grezzo or None}

    elif intent == "MUSIC_VOLUME":
        # Valore numerico o direzione (su/giù)
        return _parse_volume(param_grezzo)

    elif intent == "DAY_FUTURE":
        # Data futura — stringa vuota se non specificata/corretta
        return {"data": param_grezzo or ""}

    elif intent == "WEATHER":
        # Città — None se non specificata → Weather usa il default
        return {"citta": param_grezzo or None}

    else:
        # Intent senza parametri — MUSIC_STOP, TIME_CURRENT ecc.
        return {}
