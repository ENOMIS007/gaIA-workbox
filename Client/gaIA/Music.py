import yt_dlp
import vlc
import time
import re
import threading
from queue import Queue
from youtubesearchpython import VideosSearch


# Logger custom per yt-dlp: le versioni recenti richiedono un oggetto con
# metodi debug/warning/error invece di scrivere direttamente su sys.stdout.
# Necessario in ambienti embedded (es. Kivy) dove sys.stdout può non essere
# un file-like object valido.
class _YtdlpLogger:
    def debug(self, msg):
        if msg.startswith('[debug] '):
            pass  # sopprime i messaggi di debug verbose
        else:
            print(msg)

    def info(self, msg):
        print(msg)

    def warning(self, msg):
        print(f"[yt-dlp WARNING] {msg}")

    def error(self, msg):
        print(f"[yt-dlp ERROR] {msg}")


_YTDLP_OPTS_BASE = {
    'quiet': True,
    'no_warnings': True,
    'logger': _YtdlpLogger(),
}

# Pre-inizializza l'istanza VLC all'import del modulo.
# Il costo della prima inizializzazione (rigenerazione cache plugin)
# avviene così all'avvio dell'app, non durante la prima richiesta dell'utente.
_vlc_instance = vlc.Instance()

# Variabili globali
player = None
music_thread = None
music_lock = threading.Lock()
music_queue = Queue()
skip_flag = threading.Event()
_volume_before_duck = None
_current_volume = 60


# Funzione per cercare il link YouTube
def search_youtube(query):
    videos_search = VideosSearch(query, limit=1)
    result = videos_search.result()
    if result['result']:
        return result['result'][0]['link']
    else:
        print("Nessun risultato trovato")
        return None


def estrai_artista_titolo(video_title):
    clean_title = re.sub(r'\(.*?\)|\[.*?\]', '', video_title).strip()
    match = re.match(r'^\s*(.+?)\s*[-–:|]\s*(.+?)$', clean_title)
    if match:
        artista = match.group(1).strip()
        titolo = match.group(2).strip()
    else:
        artista = "Artista sconosciuto"
        titolo = clean_title

    return artista, titolo


# Funzione per preparare i dati della canzone
def prepare_song(song_query):
    cleaned_query = re.sub(r'.*(riproduci|aggiungi alla coda|aggiungi in coda|metti in coda|metti)\s*', '', song_query).strip().rstrip('.') + " lyrics"
    print(cleaned_query)
    video_url = search_youtube(cleaned_query)

    if not video_url:
        return None

    ydl_opts = {**_YTDLP_OPTS_BASE, 'format': 'bestaudio[ext=m4a]/bestaudio'}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(video_url, download=False)
        audio_url = None
        for fmt in info_dict.get("formats", []):
            if fmt.get("acodec") != "none" and fmt.get("vcodec") == "none" and fmt.get('ext') in ['m4a', 'webm', 'mp3']:
                audio_url = fmt.get("url")
                break


        if not audio_url:
            return None

        video_title = info_dict.get('title', '')
        duration = info_dict.get('duration', 0)

    artist, track = estrai_artista_titolo(video_title)

    return {
        "title": track,
        "artist": artist,
        "url": video_url,
        "audio_url": audio_url,
        "duration": duration
    }


# Funzione per riprodurre la musica
def play_music(audio_url, duration):
    global player, _current_volume
    with music_lock:
        if player:
            player.stop()
        player = _vlc_instance.media_player_new(audio_url)
        _current_volume = 60
        player.audio_set_volume(_current_volume)
        player.play()

    start_time = time.time()
    while True:
        if skip_flag.is_set():
            skip_flag.clear()
            break

        with music_lock:
            if player is None or player.get_state() == vlc.State.Ended:
                break

        if time.time() - start_time >= duration:
            break
        time.sleep(1)

    with music_lock:
        if player:
            player.stop()


# Comandi controllo musica
def stop_music():
    with music_lock:
        if player:
            state = player.get_state()
            if state == vlc.State.Playing:
                player.pause()
                print("Musica in pausa.")
            elif state == vlc.State.Paused:
                print("Musica già in pausa.")
            else:
                print("Nessuna musica da mettere in pausa.")

def resume_music():
    with music_lock:
        if player:
            state = player.get_state()
            if state == vlc.State.Paused:
                player.play()
                print("Musica ripresa.")
            elif state == vlc.State.Playing:
                print("Musica già in riproduzione.")
            else:
                print("Nessuna musica da riprendere.")


# Abbassa il volume durante il TTS, salva il volume corrente per poterlo ripristinare
def duck_volume(level: int = 35):
    global _volume_before_duck
    with music_lock:
        if player and _volume_before_duck is None:
            _volume_before_duck = _current_volume
            player.audio_set_volume(level)


# Ripristina il volume precedente a duck_volume()
def restore_volume():
    global _volume_before_duck
    with music_lock:
        if player and _volume_before_duck is not None:
            player.audio_set_volume(_volume_before_duck)
            _volume_before_duck = None


# Restituisce True se la musica è attualmente in riproduzione
def is_playing() -> bool:
    with music_lock:
        return player is not None and player.get_state() == vlc.State.Playing
    

def end_music():
    global player
    with music_lock:
        if player:
            player.stop()
            player = None
            print("Riproduzione terminata.")


# Imposta il volume — riceve valore assoluto o direzione ("su"/"giù")
def set_volume(valore: int = None, direzione: str = None, delta: int = None):
    global player, _current_volume
    step = 20  # incremento/decremento di default quando non è specificato un delta

    with music_lock:
        if not player:
            return "Nessun lettore attivo."

        # Solo valore
        if valore is not None:
            if 0 <= valore <= 100:
                _current_volume = valore
                player.audio_set_volume(_current_volume)
                return f"Volume impostato a {_current_volume}%."
            else:
                return "Volume fuori dal range (0%-100%)."

        # Delta esplicito: "alza di 15", "abbassa di 20"
        if delta is not None and direzione is not None:
            if direzione == "su":
                _current_volume = min(100, _current_volume + delta)
            elif direzione == "giù":
                _current_volume = max(0, _current_volume - delta)
            player.audio_set_volume(_current_volume)
            return f"Volume {'aumentato' if direzione == 'su' else 'abbassato'} a {_current_volume}%."

        # Direzione senza delta
        if direzione == "su":
            _current_volume = min(100, _current_volume + step)
            player.audio_set_volume(_current_volume)
            return f"Volume aumentato a {_current_volume}%."
        elif direzione == "giù":
            _current_volume = max(0, _current_volume - step)
            player.audio_set_volume(_current_volume)
            return f"Volume abbassato a {_current_volume}%."

        return "Parametri volume non specificati."


# Funzione principale aggiornata per comando "metti"
def youtube_player(song_query):
    global music_thread
    risposta = None
    song_data = prepare_song(song_query)
    if not song_data:
        return "Impossibile trovare la canzone."

    # Ferma la canzone corrente
    skip_music()
    risposta = f"Riproduzione: {song_data['title']} di {song_data['artist']}"

    # Inserisce la nuova canzone in testa alla coda mantenendo le altre
    with music_queue.mutex:
        current_items = list(music_queue.queue)
        music_queue.queue.clear()
        music_queue.queue.appendleft(song_data)
        for item in current_items:
            music_queue.queue.append(item)

    def music_thread_func():
        while not music_queue.empty():
            current_song = music_queue.get()
            skip_flag.clear()  # reset flag skip
            play_music(current_song['audio_url'], current_song['duration'])

    # Aspetta che il thread precedente finisca prima di controllarne lo stato
    if music_thread is not None and music_thread.is_alive():
        music_thread.join(timeout=2)

    if music_thread is None or not music_thread.is_alive():
        music_thread = threading.Thread(target=music_thread_func)
        music_thread.daemon = True
        music_thread.start()

    return risposta


# Aggiunta alla coda senza avvio
def add_to_queue(song_query):
    song_data = prepare_song(song_query)
    if song_data:
        music_queue.put(song_data)
        return f"Canzone aggiunta alla coda: {song_data['title']} di {song_data['artist']}"
    else:
        return "Impossibile aggiungere la canzone."


# Salta brano
def skip_music():
    global player
    with music_lock:
        if player:
            print("Skippando la canzone corrente...")
            skip_flag.set()
        else:
            print("Nessuna canzone da skippare.")
       
# Mostra coda
def show_queue():
    if music_queue.empty():
        return "La coda è vuota."
    else:
        return "\n".join([f"{i+1}. {song['title']} di {song['artist']}" for i, song in enumerate(music_queue.queue)])


# Esecuzione CLI
if __name__ == "__main__":
    while True:
        cmd = input("Comando: ").strip().lower()
        if cmd.startswith("riproduci") or cmd.startswith("metti"):
            risp = youtube_player(cmd)
            print(risp)
        elif cmd.startswith("aggiungi alla coda") or cmd.startswith("aggiungi in coda") or cmd.startswith("metti in coda"):
            risp = add_to_queue(cmd)
            print(risp)
        elif cmd == "skip":
            skip_music()
        elif cmd == "mostra coda":
            risp = show_queue()
            print(risp)
        elif cmd == "ferma musica":
            risp = stop_music()
            print(risp)
        elif cmd.startswith("volume") or "alza il volume" in cmd or "abbassa il volume" in cmd:
            if "alza" in cmd:
                risp = set_volume(direzione="su")
            elif "abbassa" in cmd:
                risp = set_volume(direzione="giù")
            else:
                m = re.search(r'\d+', cmd)
                risp = set_volume(valore=int(m.group())) if m else set_volume()
            print(risp)
        elif cmd == "esci":
            break
        
        