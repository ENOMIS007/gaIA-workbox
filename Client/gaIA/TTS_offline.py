import asyncio
import os
import wave
from kivy.core.audio import SoundLoader
from collections import deque
import Music
import time
import Change_state
from piper import PiperVoice

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VOICE = os.path.join(BASE_DIR, "Voice", "Paola", "it_IT-paola-medium.onnx")
voice = PiperVoice.load(VOICE)

OUTPUT_DIR = "audio_files"
sound = None
queue = deque()  # Coda per i file da riprodurre
_audio_counter = 0  # Contatore globale per nomi file univoci
music_on = False


def is_queue_empty():
    global queue
    return len(queue) == 0 and (not sound or sound.state != 'play')


# Genera un file WAV usando Piper
async def synthesize_to_wav(text, file_path):
    dir_path = os.path.dirname(file_path)
    if dir_path and not os.path.exists(dir_path):
        os.makedirs(dir_path, exist_ok=True)
    with wave.open(file_path, "wb") as wav_file:
        voice.synthesize_wav(text, wav_file)


async def amain(text, concatenazione_frasi) -> None:
    global sound, queue, _audio_counter, music_on

    if not concatenazione_frasi:
        file_path = os.path.join(OUTPUT_DIR, "output.wav")
        await synthesize_to_wav(text, file_path)
        sound = SoundLoader.load(file_path)
        if sound:
            if music_on:
                Music.duck_volume()
                sound.bind(on_stop=lambda _: (
                    Music.restore_volume(),
                    Change_state.set_state("ascolto")
                ))
                sound.play()
            else:
                sound.bind(on_stop=lambda _: Change_state.set_state("ascolto"))
                sound.play()
        if music_on:
            music_on = False
    else:
        if not os.path.exists(OUTPUT_DIR):
            os.makedirs(OUTPUT_DIR)

        # Usa il contatore globale per generare nomi file univoci
        # anche quando lo stesso testo viene sintetizzato più volte
        _audio_counter += 1
        file_path = os.path.join(OUTPUT_DIR, f"audio_{_audio_counter}.wav")

        await synthesize_to_wav(text, file_path)
        queue.append(file_path)

        if not sound or sound.state != 'play':
            play_next()


def play_next():
    global sound, _audio_counter, music_on
    if not queue:
        _audio_counter = 0  # reset contatore quando la coda è esaurita
        Change_state.set_state("ascolto")
        time.sleep(0.2)
        Music.restore_volume()
        return

    file_path = queue.popleft()
    sound = SoundLoader.load(file_path)
    if sound:
        sound.bind(on_stop=lambda _: play_next())
        sound.play()




def run(text, concatenazione_frasi):
    print(f"gaIA: {text} \n")
    asyncio.run(amain(text, concatenazione_frasi))
    Change_state.set_state("parlato")
    if music_on:
        Music.duck_volume()


def stop():
    global sound, queue, _audio_counter
    queue.clear()
    _audio_counter = 0
    if sound:
        sound.stop()
        sound = None
    if os.path.exists(OUTPUT_DIR):
        for filename in os.listdir(OUTPUT_DIR):
            file_path = os.path.join(OUTPUT_DIR, filename)
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
            except Exception as e:
                print(f"Errore nel rimuovere il file {file_path}: {e}")


def music_status_set():
    global music_on
    music_on = True

def music_status_unset():
    global music_on
    music_on = False


if __name__ == "__main__":
    print("Premi 'q' per fermare la riproduzione.")
    
    concatenazione_frasi = input("Vuoi settare concatenazione_frasi a True? (s/n): ").strip().lower() == 's'
    
    while True:
        text = input("Testo da vocalizzare: ")
        if text.lower() == 'q':
            stop()
            break
        run(text, concatenazione_frasi)