# change_state.py

state = "ascolto"  # Stato iniziale

def get_state():
    """Ritorna lo stato corrente."""
    global state
    return state

def set_state(new_state):
    """Aggiorna lo stato."""
    global state
    state = new_state
