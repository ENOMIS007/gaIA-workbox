# train_params_model.py
# Addestra il modello CRF per l'estrazione dei parametri dalle trascrizioni.
# Eseguire ogni volta che si modifica skills_params_dataset.txt:
#     python train_params_model.py
#
# Tag usati nel dataset:
#     X = tutto quello che non è parametro (keyword + rumore)
#     P = parametro — quello che ci serve estrarre

import re
import joblib
import hashlib
import os
import sklearn_crfsuite


# ---------------------------------------------------------------------------
# Costanti
# ---------------------------------------------------------------------------

DATASET_PATH = "..\Datasets\skills_params_dataset.txt"
MODEL_PATH   = "..\Model\ParamsExtractor\params_model.pkl"
HASH_PATH    = "..\Model\ParamsExtractor\params_model.hash"


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
# Lettura dataset
# ---------------------------------------------------------------------------

def load_dataset(path: str) -> tuple:
    """
    Legge skills_params_dataset.txt e prepara i dati per il training.

    Restituisce tre liste parallele — stesso indice = stessa frase:
    - X:       lista di liste di feature dict (una lista per frase)
    - y:       lista di liste di tag X/P (una lista per frase)
    - intents: lista di intent corrispondenti a ogni frase

    Formato del file:
        # MUSIC_PLAY                    ← sezione intent
        metti/X storie/P brevi/P        ← frase taggata
        riproduci/X qualcosa/P          ← frase taggata
    """
    X, y, intents = [], [], []
    current_intent = None

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            # Riga di sezione — aggiorna l'intent corrente
            if line.startswith("#"):
                current_intent = line.replace("#", "").strip()
                continue

            # Riga taggata — divide ogni token in (parola, tag)
            tokens = line.split()
            words, tags = [], []
            for token in tokens:
                if "/" not in token:
                    continue
                # rsplit per gestire parole con slash come "AC/DC"
                # "AC/DC/P" → rsplit("/", 1) → ["AC/DC", "P"]
                parts = token.rsplit("/", 1)
                if len(parts) == 2:
                    words.append(parts[0])
                    tags.append(parts[1])

            if words and current_intent:
                # Costruisce le feature per ogni parola della frase
                features = [word_features(words, i, current_intent)
                            for i in range(len(words))]
                X.append(features)
                y.append(tags)
                intents.append(current_intent)

    return X, y, intents


# ---------------------------------------------------------------------------
# Hash — evita riaddestramenti inutili
# ---------------------------------------------------------------------------

def compute_hash() -> str:
    """Hash MD5 del dataset — cambia se anche un solo carattere viene modificato."""
    with open(DATASET_PATH, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train():
    """
    Addestra il CRF e salva il modello su disco.
    Se il dataset non è cambiato dall'ultimo training, non raddestra.
    """
    current_hash = compute_hash()

    # Controlla se il modello è già aggiornato
    if os.path.exists(MODEL_PATH) and os.path.exists(HASH_PATH):
        with open(HASH_PATH, "r") as f:
            saved_hash = f.read().strip()
        if saved_hash == current_hash:
            print("✓ Modello già aggiornato, nessuna rigenerazione necessaria.")
            return

    print("⚙  Lettura dataset...")
    X, y, intents = load_dataset(DATASET_PATH)
    print(f"   Frasi caricate:  {len(X)}")
    print(f"   Intent distinti: {len(set(intents))}")

    print("⚙  Addestramento CRF...")
    crf = sklearn_crfsuite.CRF(
        algorithm="lbfgs",           # ottimizzatore L-BFGS — veloce e stabile
        c1=0.1,                      # regolarizzazione L1 — pesi inutili → 0
        c2=0.1,                      # regolarizzazione L2 — evita overfitting
        max_iterations=100,          # converge prima con dataset piccoli
        all_possible_transitions=True # generalizza su transizioni non viste
    )
    crf.fit(X, y)

    # Salva modello e hash
    joblib.dump(crf, MODEL_PATH)
    with open(HASH_PATH, "w") as f:
        f.write(current_hash)

    print(f"✓ Modello salvato in '{MODEL_PATH}'")
    print(f"✓ Hash salvato in '{HASH_PATH}'")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    train()
