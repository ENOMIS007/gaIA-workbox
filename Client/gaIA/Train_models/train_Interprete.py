# train_model.py
# Addestra il modello FastText dal dataset e lo salva su disco.
# Eseguire ogni volta che si modifica skills_dataset.txt.
# Se il dataset non è cambiato, non raddestra.

import fasttext
import hashlib
import os


# ---------------------------------------------------------------------------
# Costanti
# ---------------------------------------------------------------------------

DATASET_PATH = "..\Datasets\skills_dataset.txt"
MODEL_PATH   = "..\Model\Interprete\interpreter_model.bin"
HASH_PATH    = "..\Model\Interprete\interpreter_model.hash"

# Iperparametri FastText
EPOCHS      = 50   # quante volte legge il dataset — più alto = impara meglio
LEARN_RATE  = 0.5  # velocità di apprendimento — 0.5 è buon compromesso per dataset piccoli
WORD_NGRAMS = 2    # considera coppie di parole vicine — fondamentale per distinguere "metti in coda" da "metti bohemian rhapsody"


# ---------------------------------------------------------------------------
# Funzioni
# ---------------------------------------------------------------------------

def compute_hash() -> str:
    # Legge il dataset in binario e calcola l'hash MD5.
    with open(DATASET_PATH, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def train():
    current_hash = compute_hash()

    # Controlla se esiste già un modello con lo stesso hash del dataset.
    # Se sì, il dataset non è cambiato e quindi nessun training necessario.
    if os.path.exists(MODEL_PATH) and os.path.exists(HASH_PATH):
        with open(HASH_PATH, "r") as f:
            saved_hash = f.read().strip()
        if saved_hash == current_hash:
            print("✓ Modello già aggiornato, nessuna rigenerazione necessaria.")
            return

    print("⚙  Addestramento in corso...")

    # Addestra FastText sul dataset.
    model = fasttext.train_supervised(
        input=DATASET_PATH,
        epoch=EPOCHS,
        lr=LEARN_RATE,
        wordNgrams=WORD_NGRAMS,
        minn=3,
        maxn=6,
        verbose=0        # silenzia l'output di FastText
    )

    # Salva il modello su disco come .bin
    model.save_model(MODEL_PATH)

    # Salva l'hash del dataset appena usato.
    with open(HASH_PATH, "w") as f:
        f.write(current_hash)

    print(f"✓ Modello salvato in '{MODEL_PATH}'")
    print(f"✓ Hash salvato in '{HASH_PATH}'")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    train()
