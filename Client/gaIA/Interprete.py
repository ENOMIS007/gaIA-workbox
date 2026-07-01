# Interpreter.py
# Classificatore FastText per il riconoscimento degli intent.
#
# Utilizzo:
#     from Interpreter import classify, Context
#     result = classify("ferma la musica")
#     # → {"intent": "MUSIC_STOP", "confidence": 0.94}
#     # → {"intent": None, "confidence": 0.21}  se sotto soglia -> fallback AI

import fasttext
import os
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Context — oggetto condiviso tra Dispatcher e skill
# Raggruppa tutti i parametri di stato per evitare firme con 5+ argomenti.
# Viene costruito nel Dispatcher e passato a ogni skill.
# ---------------------------------------------------------------------------

@dataclass
class Context:
    server_url:          str    # URL del server Flask (STT, Ollama)
    connection_status:   dict   # {"state": "online"|"lan_only"|"offline"}
    chat_mode_active:    bool   # True = modalità chat testuale
    conversation_memory: bool   # True = memoria conversazione attiva
    conversation_mode:   bool   # True = modalità conversazione vocale attiva


# ---------------------------------------------------------------------------
# Costanti
# ---------------------------------------------------------------------------

# Percorso assoluto al modello.
MODEL_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "Model\Interprete\interpreter_model.bin"
)

# Soglia per fallback all'AI
CONFIDENCE_THRESHOLD = 0.5


# ---------------------------------------------------------------------------
# Classe Interpreter
# ---------------------------------------------------------------------------

# Classificatore FastText per il riconoscimento degli intent.
# Carica il modello pre-addestrato dal .bin una volta sola all'import.
# Ogni chiamata a classify()
class Interpreter:

    def __init__(self):
        # Controlla che il .bin esista prima di caricarlo.
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(
                f"Modello non trovato: '{MODEL_PATH}'. "
                f"Eseguire prima: python train_model.py"
            )

        # Carica il modello dal .bin
        self._model = fasttext.load_model(MODEL_PATH)

    def classify(self, text: str) -> dict:
        # Normalizza text: convertito in minuscolo, spazi e punto finale rimossi.
        # Necessario per uniformare il testo alle frasi di addestramento.
        text_clean = text.lower().strip().rstrip(".")

        # predict() restituisce due liste parallele, esempio:
        #   labels -> ["__label__MUSIC_PLAY"]
        #   probs  -> [0.94]
        # k=1 → chiediamo solo il miglior match
        labels, probs = self._model.predict(text_clean, k=1)

        # Rimuove il prefisso "__label__" aggiunto automaticamente da FastText
        # "__label__MUSIC_PLAY" -> "MUSIC_PLAY"
        intent     = labels[0].replace("__label__", "")
        confidence = float(probs[0])

        # Controllo sulla confidence, se sotto la soglia -> fallback all'AI
        if confidence < CONFIDENCE_THRESHOLD:
            return {"intent": None, "confidence": confidence}

        return {"intent": intent, "confidence": confidence}


# ---------------------------------------------------------------------------
# Singleton — costruito una volta sola all'import
# ---------------------------------------------------------------------------

interpreter = Interpreter()


# Funzione pubblica (un .run per l'interprete)
def classify(text: str) -> dict:
    return interpreter.classify(text)

