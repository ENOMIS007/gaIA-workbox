import threading
import sounddevice as sd
import numpy as np
import queue
import os
import time
from faster_whisper import WhisperModel

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

# Parametri
MODEL_SIZE = "large-v3"
# MODEL_SIZE = "small"
BEAM_SIZE = 2
LANGUAGE = "it"
TRIGGER_WORDS = {"Gaia", "Ehi gaia"}  # Set che contiene le frasi e le parole chiave
SAMPLING_RATE = 16000  # Campionamento a 16kHz
SILENCE_THRESHOLD = 0.01  # Soglia di silenzio per considerare la fine della frase
MIN_SILENCE_DURATION = 0.5  # Durata del silenzio di 0.5 secondi per considerare la fine della frase
MAX_BUFFER_SIZE = SAMPLING_RATE * 10  # Dimensione massima del buffer di 10 secondi
WAIT_FOR_NEXT_PHRASE_TIMEOUT = 4.0  # Massimo 4 secondi di silenzio dopo "Gaia."

# Coda audio per lo streaming continuo
audio_queue = queue.Queue()

# Inizializzazione del modello
model = WhisperModel(MODEL_SIZE)

# Variabili globali per la trascrizione e lo stato
transcription = None
waiting_for_next_phrase = False
waiting_timer_start = None  # Timer per monitorare il silenzio dopo "Gaia."

# Aggiunta del segnale di stop globale
stop_signal = threading.Event()


# Funzione per la registrazione audio continua
def audio_callback(indata, frames, time, status):
    if status:
        print(status)
    audio_queue.put(indata.copy())


# Funzione per formattare il testo secondo le regole richieste
def format_text(text, capitalize_first_letter=True):
    formatted_text = text.lower()
    sentences = formatted_text.split(".")
    formatted_sentences = []

    for sentence in sentences:
        sentence = sentence.strip()
        if sentence:
            if capitalize_first_letter:
                sentence = sentence.capitalize()
            sentence = sentence.replace("!", ".").replace("?", "?").replace(";", ",")
            if not (sentence.endswith('.') or sentence.endswith('?')):
                sentence += '.'
            formatted_sentences.append(sentence)

    return " ".join(formatted_sentences).strip()


# Funzione per processare l'audio e trascrivere se la parola "Gaia" è contenuta
def process_audio(keyword_mode=True):
    global transcription, waiting_for_next_phrase, waiting_timer_start
    buffer = np.zeros((0, 1), dtype=np.float32)
    is_recording = False
    silence_duration = 0
    min_activation_threshold = 0.02  # Livello minimo del segnale per attivare la trascrizione
    activation_detected = False  # Flag per tracciare se il segnale è abbastanza forte per iniziare
    silence_start_time = None  # Variabile per tracciare il tempo di inizio del silenzio

    while not stop_signal.is_set():  # Controlla se il segnale di stop è stato impostato
        try:
            audio_data = audio_queue.get()

            if stop_signal.is_set():  # Controlla se il segnale di stop è stato impostato
                break

            buffer = np.concatenate((buffer, audio_data), axis=0)
            if len(buffer) > MAX_BUFFER_SIZE:
                buffer = buffer[-MAX_BUFFER_SIZE:]

            # Calcolo della media assoluta per il livello del segnale
            current_signal_level = np.mean(np.abs(audio_data))

            if current_signal_level < SILENCE_THRESHOLD:
                silence_duration += len(audio_data) / SAMPLING_RATE
                if silence_start_time is None:
                    silence_start_time = time.time()
            else:
                silence_duration = 0
                silence_start_time = None  # Reset del timer quando il parlato è rilevato

            # Controlla se il segnale supera la soglia per iniziare la registrazione
            if current_signal_level > min_activation_threshold:
                activation_detected = True

            # Avvia la trascrizione solo se il segnale supera la soglia e c'è abbastanza audio registrato
            if activation_detected and silence_duration >= MIN_SILENCE_DURATION and is_recording:
                segments, _ = model.transcribe(
                    buffer.squeeze(),
                    language=LANGUAGE,
                    beam_size=BEAM_SIZE
                )
                phrase_detected = False

                for segment in segments:
                    text = segment.text.strip()

                    # Modalità con parola chiave
                    if keyword_mode:
                        if waiting_for_next_phrase:
                            formatted_text = format_text(text, capitalize_first_letter=False)
                            transcription += " " + formatted_text
                            print("Aggiunta la frase successiva: ", formatted_text)
                            waiting_for_next_phrase = False
                            waiting_timer_start = None
                            phrase_detected = True
                            break

                        formatted_text = format_text(text)

                        # Verifica se una delle parole chiave è contenuta nel testo
                        if any(trigger_word in formatted_text for trigger_word in TRIGGER_WORDS):
                            print(f"Frase rilevata con parola chiave: ", formatted_text)
                            transcription = formatted_text
                            phrase_detected = True

                            if formatted_text in {f"{word}." for word in TRIGGER_WORDS}:
                                waiting_for_next_phrase = True
                                waiting_timer_start = time.time()
                            break

                        if not phrase_detected:
                            print("Parola chiave non rilevata nella frase.")

                    # Modalità senza parola chiave
                    else:
                        formatted_text = format_text(text)
                        print("Frase rilevata: ", formatted_text)
                        transcription = formatted_text
                        phrase_detected = True
                        break

                # Svuota il buffer dopo aver processato l'audio
                buffer = np.zeros((0, 1), dtype=np.float32)
                is_recording = False
                activation_detected = False  # Resetta il flag di attivazione

                if transcription and (not keyword_mode or (keyword_mode and not waiting_for_next_phrase)):
                    break

            elif silence_duration < MIN_SILENCE_DURATION:
                is_recording = True

            # Timeout per la frase successiva
            if waiting_for_next_phrase and waiting_timer_start is not None:
                elapsed_time = time.time() - waiting_timer_start
                if elapsed_time > WAIT_FOR_NEXT_PHRASE_TIMEOUT:
                    print("Timeout raggiunto dopo la parola chiave, reset della flag e trascrizione.")
                    waiting_for_next_phrase = False
                    transcription = None
                    waiting_timer_start = None

        except queue.Empty:
            continue


# Funzione principale per avviare il processo di riconoscimento vocale
def run(keyword=False):
    global transcription
    transcription = None

    # Resetta il segnale di stop ogni volta che si chiama run
    stop_signal.clear()

    processing_thread = threading.Thread(target=process_audio, args=(keyword,))
    processing_thread.daemon = True
    processing_thread.start()

    with sd.InputStream(callback=audio_callback, channels=1, samplerate=SAMPLING_RATE):
        while transcription is None or (keyword and waiting_for_next_phrase):
            if stop_signal.is_set():  # Controlla se il segnale di stop è stato impostato
                break
            time.sleep(0.1)
    
    return transcription


# Funzione per interrompere la trascrizione esternamente
def stop():
    stop_signal.set()


if __name__ == "__main__":
#     run(keyword=True)
    run()
