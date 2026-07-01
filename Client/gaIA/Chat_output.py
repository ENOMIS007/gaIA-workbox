# Variabile globale per memorizzare il messaggio
custom_message = None
transcript = None


def set_message(new_message):
    global custom_message
    custom_message = new_message

def get_info():
    return custom_message


def set_transcript(new_transcript):
    global transcript
    transcript = new_transcript

def get_transcript():
    return transcript