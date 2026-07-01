import os
import subprocess
import difflib
import platform
import re
import win32com.client
import Database_dealer


def aggiungi_app(percorso: str) -> str:
    percorso = percorso.replace('"', '').strip()
    if not os.path.exists(percorso):
        return "Il percorso specificato non esiste."

    nome_app = os.path.splitext(os.path.basename(percorso))[0].strip().lower()
    percorso = os.path.abspath(percorso)

    Database_dealer.insert_app(nome_app, percorso)
    return f"App '{nome_app}' aggiunta con successo!"


def apri_app(nome_app: str) -> str:
    nome_app = nome_app.strip().lower()

    if not nome_app:
        return "Nome dell'app non valido."

    app_path = Database_dealer.get_link_by_name(nome_app)
    if app_path:
        avvia_app(app_path)
        return f"Avvio di '{nome_app}' in corso."

    # Approssimazione nome
    tutte = Database_dealer.get_all_names()
    closest = difflib.get_close_matches(nome_app, tutte, n=1, cutoff=0.6)
    if closest:
        nome_match = closest[0]
        app_path = Database_dealer.get_link_by_name(nome_match)
        avvia_app(app_path)
        return f"Avvio di '{nome_match}' in corso."

    return f"Nessuna app trovata simile a '{nome_app}'."


def avvia_app(app_path: str):
    try:
        if app_path.lower().endswith(".url"):
            url = get_real_url_from_url(app_path)
            if url:
                subprocess.run(["start", url], shell=True, check=True)
            else:
                print("Impossibile trovare l'URL del gioco.")
        elif os.path.exists(app_path):
            if app_path.lower().endswith(".lnk") and platform.system() == "Windows":
                app_path = get_target_from_lnk(app_path)

            if os.access(app_path, os.X_OK):
                subprocess.Popen([app_path])
            elif app_path.endswith(".sh"):
                subprocess.Popen(["bash", app_path])
            elif platform.system() == "Windows":
                os.startfile(app_path)
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", app_path])
            elif platform.system() == "Linux":
                subprocess.Popen(["xdg-open", app_path])
        else:
            print(f"Percorso non valido: {app_path}")
    except Exception as e:
        print(f"Errore nell'avvio dell'app: {e}")


def get_real_url_from_url(url_path: str) -> str | None:
    try:
        with open(url_path, 'r') as f:
            for line in f:
                if line.startswith("URL="):
                    return line.split("=", 1)[1].strip()
    except Exception as e:
        print(f"Errore nella lettura del file .url: {e}")
    return None


def get_target_from_lnk(lnk_path: str) -> str | None:
    try:
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortcut(lnk_path)
        return shortcut.TargetPath
    except Exception as e:
        print(f"Errore nel risolvere il collegamento: {e}")
    return None


def mostra_app() -> str:
    nomi = Database_dealer.get_all_names()
    return "\n".join(nomi) if nomi else "Nessuna app salvata."


if __name__ == '__main__':
    while True:
        cmd = input("'apri <nome>' / 'aggiungi <percorso>' / 'mostra': ").strip()
        if cmd.startswith("mostra"):
            print(mostra_app())
        elif cmd.startswith("aggiungi "):
            print(aggiungi_app(cmd[len("aggiungi "):]))
        elif cmd.startswith("apri "):
            print(apri_app(cmd[len("apri "):]))
