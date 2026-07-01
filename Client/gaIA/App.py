from kivy.app import App
from kivy.uix.widget import Widget
from kivy.uix.label import Label
from kivy.lang import Builder
from kivy.uix.screenmanager import Screen, ScreenManager, NoTransition, SlideTransition
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.core.text import LabelBase
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.image import Image
from kivy.animation import Animation
from kivy.graphics import Color, RoundedRectangle
from kivy.properties import BooleanProperty, StringProperty, ObjectProperty, NumericProperty, ListProperty
from Animation_main import CircleWidget, DotWidget, switch_widget
import Change_state

from datetime import datetime
import os
import threading
import json

import Database_dealer
import gaIA_v0101
import Chat_input
import Chat_output
import BackgroundServices


CRED_FILE = "..\login_state.json"
current_chat_uuid = ""
last_text_chat_uuid = ""


def _save_login_state(email: str, keep_logged: bool):
    """Salva lo stato di accesso nel file di credenziali."""
    with open(CRED_FILE, 'w') as f:
        json.dump({'keep_logged': keep_logged, 'email': email}, f)


# Registra le varianti del font
LabelBase.register(
    name="Roboto",
    fn_regular="..\\Roboto\\Roboto-Regular.ttf",
    fn_bold="..\\Roboto\\Roboto-Bold.ttf",
    fn_italic="..\\Roboto\\Roboto-Italic.ttf",
    fn_bolditalic="..\\Roboto\\Roboto-BoldItalic.ttf"
)


class CustomButton(Button):
    hovering = BooleanProperty(False)
    active = BooleanProperty(False)
    hover_enabled = BooleanProperty(True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Window.bind(mouse_pos=self.on_mouse_pos)

    def on_mouse_pos(self, window, pos):
        if not self.get_root_window() or not self.hover_enabled:
            return
        # Controlla se il mouse è sopra questo bottone
        inside = self.collide_point(*self.to_widget(*pos))
        self.hovering = inside
        
    def on_click(self, *args):
        self.activate()

    def activate(self):
        # Cerca il genitore che ha id 'chat_buttons_container'
        container = self.parent
        while container:
            if hasattr(container, 'ids') and 'chat_buttons_container' in container.ids:
                container = container.ids.chat_buttons_container
                break
            container = container.parent
        else:
            # fallback: se non trovato, usa il parent diretto
            container = self.parent

        # Disattiva tutti i pulsanti nei figli di box_container
        for hoverbox in container.children:
            if hasattr(hoverbox, 'ids') and 'main_hoverbox_button' in hoverbox.ids:
                hoverbox.ids.main_hoverbox_button.active = False

        # Attiva questo bottone
        self.active = True




class IconButton(Button):
    source = StringProperty('')
    background_rgba = ListProperty([60/255, 63/255, 65/255, 1])
    
    


class SidebarMixin:
    # Gestione della sidebar #
    def toggle_sidebar(self):
        sidebar = self.ids.sidebar
        menu_button = self.ids.menu_button

        if sidebar.opacity == 0:  # Menu nascosto
            self.show_sidebar()
        else:  # Menu visibile
            self.hide_sidebar()

    # Mostrare sidebar #
    def show_sidebar(self):
        sidebar = self.ids.sidebar
        menu_button = self.ids.menu_button

        # Mostra il menu e sposta il pulsante
        sidebar.opacity = 1
        anim_sidebar = Animation(pos=(self.width - sidebar.width, 0), duration=0.3)
        anim_sidebar.start(sidebar)

        anim_button = Animation(pos=(self.width - sidebar.width - menu_button.width - 10, menu_button.y), duration=0.3)
        anim_button.start(menu_button)

    # Nascondere sidebar #
    def hide_sidebar(self):
        sidebar = self.ids.sidebar
        menu_button = self.ids.menu_button

        # Nasconde il menu e riporta il pulsante nella posizione iniziale
        anim_sidebar = Animation(pos=(self.width, 0), duration=0.3)
        anim_sidebar.bind(on_complete=lambda *args: setattr(sidebar, 'opacity', 0))
        anim_sidebar.start(sidebar)

        anim_button = Animation(pos=(self.width - menu_button.width - 10, menu_button.y), duration=0.3)
        anim_button.start(menu_button)

    # Nascondere sidebar quando si clicca fuori #
    def on_touch_down(self, touch):
        sidebar = self.ids.sidebar
        menu_button = self.ids.menu_button

        if sidebar.opacity == 1:  # Se il menu è visibile
            if sidebar.collide_point(*touch.pos) or menu_button.collide_point(*touch.pos):
                # Il tocco è dentro il menu o sul pulsante "Menu", non chiudere
                return super().on_touch_down(touch)
            else:
                # Tocco fuori dal menu, nascondilo
                self.hide_sidebar()
                return True  # Blocca l'evento dal propagarsi

        return super().on_touch_down(touch)
    



class SettingsWindow(Screen):
    def on_enter(self):
        if os.path.exists(CRED_FILE):
            with open(CRED_FILE, 'r') as f:
                data = json.load(f)
                email = data.get('email', 'Utente sconosciuto')
                self.ids.logged_user_label.text = f"{email}"

    def logout(self):
        if os.path.exists(CRED_FILE):
            os.remove(CRED_FILE)
        self.manager.current = 'login'




class LoginScreen(Screen):
    def do_login(self):
        email = self.ids.email.text
        password = self.ids.password.text
        keep_logged = self.ids.keep_logged_cb.active

        result = Database_dealer.check_credenziali(email, password)

        self.ids.email.text = ""
        self.ids.password.text = ""

        if result:
            _save_login_state(email, keep_logged)
            self.manager.current = 'main'
            self.manager.transition.direction = 'left'
            Animation(opacity=0).start(self.ids.error_container)
        else:
            Animation(opacity=1, d=0.3).start(self.ids.error_container)
            
    def go_to_sign_in(self):
        self.manager.current = 'sign-in'  




class SignInScreen(Screen):
    def do_sign_in(self):
        email = self.ids.email.text
        password = self.ids.password.text
        keep_logged = self.ids.keep_logged_cb.active
        
        if not email or not password:
            self.ids.error_label.text = "Email e password sono obbligatori!"
            Animation(opacity=1, d=0.3).start(self.ids.error_container)
            return

        result = Database_dealer.insert_utente(email, password)
        print(result)

        self.ids.email.text = ""
        self.ids.password.text = ""

        if result:
            _save_login_state(email, keep_logged)
            self.manager.current = 'main'
            self.manager.transition.direction = 'left'
            Animation(opacity=0).start(self.ids.error_container)
        else:
            Animation(opacity=1, d=0.3).start(self.ids.error_container)




class MainWindow(SidebarMixin, Screen):
    cycle_thread = None
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.last_info = None
        
        self.circle_widget = CircleWidget()
        self.dot_widget = DotWidget()
        self.current_widget = self.circle_widget  # Mantieni traccia del widget attuale

        self.layout = FloatLayout(size=self.size)
        self.add_widget(self.layout)

        # Aggiungi CircleWidget al layout inizialmente
        self.layout.add_widget(self.circle_widget)
        
        Clock.schedule_interval(self.update_user_request, 0.1)
        # Controlla costantemente lo stato
        Clock.schedule_interval(self.update_widget, 0.1)

    def on_enter(self):
        global current_chat_uuid, last_text_chat_uuid
        last_text_chat_uuid = current_chat_uuid
        
        # Avvia il ciclo quando si entra nello screen "main"
        if not self.cycle_thread or not self.cycle_thread.is_alive():
            gaIA_v0101.stop_signal.clear()  # Resetta stop_signal
            gaIA_v0101.stop_main_cycle.clear()  # Resetta il flag di stop
            self.cycle_thread = threading.Thread(target=gaIA_v0101.run, daemon=True)
            self.cycle_thread.start()
        last_vocal_date = datetime.fromisoformat(Database_dealer.get_latest_vocal_date())
        if datetime.now().date() != last_vocal_date.date():
            Database_dealer.insert_chat()
        current_chat_uuid = Database_dealer.get_latest_vocal_uuid()

    def on_leave(self):
        # Interrompe il ciclo quando si esce dallo screen "main".
        # Non usare join() qui: bloccherebbe il thread UI di Kivy se run() è in attesa di server_changed (es. server irraggiungibile), causando un freeze visibile.
        # stop_main_cycle + server_changed.set() in stop_main sono sufficienti a sbloccare run() in modo asincrono.
        gaIA_v0101.stop_main_cycle.set()
        self.cycle_thread = None
        self.hide_sidebar()
            
    # Mostra trascrizione #
    def display_user_request(self, text):
        self.ids.user_request_label.text = text
            
    # Aggiorna il testo captato #
    def update_user_request(self, dt):
        info = Chat_output.get_transcript()
        if info and info != self.last_info:
            self.display_user_request(info)
            self.last_info = info
            
    # Aggiorna il disegno in base allo stato #
    def update_widget(self, dt):
        current_state = Change_state.get_state()  # Ottieni lo stato corrente
        if current_state == "ascolto" and self.current_widget != self.circle_widget:
            self.switch_to_circle()
        elif current_state == "parlato" and self.current_widget != self.dot_widget:
            self.switch_to_dot()

    # Passa agli archi (CircleWidget) #
    def switch_to_circle(self):
        switch_widget(self.layout, self.circle_widget, self.current_widget)
        self.current_widget = self.circle_widget

    # Passa ai pallini (DotWidget) #
    def switch_to_dot(self):
        switch_widget(self.layout, self.dot_widget, self.current_widget)
        self.current_widget = self.dot_widget
        
        
        
        
class ChatWindow(SidebarMixin, Screen):
    current_button = None
    thinking_label_displayed = False
    thinking_box = None
    thinking_dots = 0
    thinking_update_counter = 0
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.last_info = None
        self.welcome_shown = False
        Clock.schedule_interval(self.update_chat, 0.1)  # Registra update_chat per essere chiamato ogni 0.1 secondi
        
    def on_enter(self):
        global current_chat_uuid
        gaIA_v0101.stop_signal.clear()  # Resetta il segnale di stop
        if not self.welcome_shown:
            self.show_welcome_message()
            self.welcome_shown = True
        current_chat_uuid = last_text_chat_uuid
        # Mette automaticamente a fuoco il campo input
        Clock.schedule_once(lambda dt: setattr(self.ids.user_input, 'focus', True), 0)
        print("Reset stop_signal su ChatWindow on_enter")
        
    def on_leave(self):
        self.hide_sidebar()
        self.hide_chat_sidebar()

        
    def scroll_to_bottom(self, *args):
        scroll_view = self.ids.chat_window.parent
        scroll_view.scroll_y = 0 
            
    def show_welcome_message(self):
        chat_window = self.ids.chat_window
        chat_window.clear_widgets()

        layout = FloatLayout(size_hint_y=None, height=self.height)

        # Titolo
        title_label = Label(
            text="[b]Benvenuto/a![/b]",
            halign='center',
            valign='middle',
            font_name="Roboto",
            font_size='30sp',
            markup=True,
            color=(1, 1, 1, 1),
            size_hint=(None, None),
            size=(self.width * 0.8, 60),
            pos_hint={"center_x": 0.5, "center_y": 0.60},
            text_size=(self.width * 0.8, None)
        )

        # Spazio vuoto (compensazione visiva)
        spacer = Widget(
            size_hint=(None, None),
            size=(self.width * 0.15, 1)
        )

        icon = Image(
            source=r'..\Immagini\left_arrow_icon.png',
            size_hint=(None, None),
            size=(30, 30),
            allow_stretch=True,
            keep_ratio=True
        )

        first_description_label = Label(
            text=" Seleziona una [b]chat[/b] per iniziare.",
            halign='left',
            valign='middle',
            font_name="Roboto",
            font_size='20sp',
            markup=True,
            color=(1, 1, 1, 1),
            size_hint=(None, None),
            size=(self.width * 0.6, 30),
            text_size=(self.width * 0.6, None)
        )

        description_layout = BoxLayout(
            orientation='horizontal',
            spacing=10,
            size_hint=(None, None),
            size=(self.width * 0.1 + 30 + 10 + self.width * 0.6, 30),
            pos_hint={"center_x": 0.5}
        )
        description_layout.add_widget(spacer)
        description_layout.add_widget(icon)
        description_layout.add_widget(first_description_label)

        second_description_label = Label(
            text="Le chat appariranno cliccando [b]sull'immagine del profilo.[/b]",
            halign='center',
            valign='middle',
            font_name="Roboto",
            font_size='20sp',
            markup=True,
            color=(1, 1, 1, 1),
            size_hint=(None, None),
            size=(self.width * 0.8, 30),
            pos_hint={"center_x": 0.5},
            text_size=(self.width * 0.8, None)
        )

        third_description_label = Label(
            text="Oppure inizia subito a [b]scrivere[/b] per avviare una [b]nuova chat![/b]",
            halign='center',
            valign='middle',
            font_name="Roboto",
            font_size='20sp',
            markup=True,
            color=(1, 1, 1, 1),
            size_hint=(None, None),
            size=(self.width * 0.8, 30),
            pos_hint={"center_x": 0.5},
            text_size=(self.width * 0.8, None)
        )

        # Container descrizioni (UNICO)
        description_container = BoxLayout(
            orientation='vertical',
            spacing=5,
            size_hint=(None, None),
            size=(self.width * 0.8, 90),  # leggermente più compatto ma sufficiente
            pos_hint={"center_x": 0.5, "center_y": 0.42}  # più in basso = più spazio sopra
        )
        description_container.add_widget(description_layout)
        description_container.add_widget(second_description_label)
        description_container.add_widget(third_description_label)

        layout.add_widget(title_label)
        layout.add_widget(description_container)
        chat_window.add_widget(layout)
        Clock.schedule_once(self.scroll_to_bottom)
        
        
    def show_new_chat_message(self):
        chat_window = self.ids.chat_window
        chat_window.clear_widgets()

        layout = FloatLayout(size_hint_y=None, height=self.height)

        message_label = Label(
            text="Come posso esserti utile oggi?",
            halign='center',
            valign='middle',
            font_name="Roboto",
            font_size='24sp',
            color=(1, 1, 1, 1),
            size_hint=(None, None),
            size=(self.width * 0.9, 50),
            pos_hint={"center_x": 0.5, "center_y": 0.5},
            text_size=(self.width * 0.9, None)
        )

        layout.add_widget(message_label)
        chat_window.add_widget(layout)
        Clock.schedule_once(self.scroll_to_bottom)

        
    def send_message(self):
        global current_chat_uuid
        user_input = self.ids.user_input
        user_message = user_input.text.strip()

        if not user_message:
            return

        # Controlla se current_chat_uuid è tra le chat testuali
        chat_list = Database_dealer.get_all_text_chat()
        chat_ids = set(chat[0] for chat in chat_list)

        if current_chat_uuid not in chat_ids:
            # Crea nuova chat
            name = "Nuova Chat"
            Database_dealer.insert_chat(name)

            updated_chats = Database_dealer.get_all_text_chat()
            updated_ids = set(chat[0] for chat in updated_chats)
            new_chat_set = updated_ids - chat_ids
            if new_chat_set:
                current_chat_uuid = new_chat_set.pop()
            else:
                latest_chat = max(updated_chats, key=lambda chat: chat[5])
                current_chat_uuid = latest_chat[0]

            self.populate_chat_buttons()
            self.ids.chat_window.clear_widgets()
            self.ids.chat_name.text = name

            # Attiva il nuovo pulsante
            container = self.ids.chat_sidebar.ids.chat_buttons_container
            for hb in container.children:
                if hasattr(hb, 'ids') and 'main_hoverbox_button' in hb.ids:
                    button = hb.ids.main_hoverbox_button
                    if button.uuid_chat == current_chat_uuid:
                        button.active = True
                        self.current_button = button
                        break

        # Assicura la punteggiatura
        if user_message[-1] not in ('.', '?'):
            user_message += '.'

        self.print_message(user_message, sender='You')
        user_input.text = ""

        if Chat_input.is_get_user_input_called():
            Chat_input.set_message(user_message)
        else:
            self.response_message(user_message)


    def print_message(self, message, sender='gaIA'):
        chat_window = self.ids.chat_window

        message_box = BoxLayout(
            orientation='vertical',
            size_hint_y=None,
            padding=[5, 5],
            spacing=10
        )

        sender_label = Label(
            text=f"[color=808080][b]{sender}:[/b][/color]",
            size_hint_y=None,
            markup=True,
            halign='left' if sender == 'gaIA' else 'right',
            text_size=(Window.width * 0.8, None),
            font_name="Roboto"
        )
        sender_label.bind(texture_size=sender_label.setter('size'))

        if sender == 'gaIA':
            message_label = Label(
                text=f"[color=FFFFFF]{message}[/color]",
                size_hint_y=None,
                markup=True,
                halign='left',
                text_size=(Window.width * 0.8, None),
                valign='top',
                font_name="Roboto"
            )
            message_label.bind(texture_size=message_label.setter('size'))

            message_box.add_widget(sender_label)
            message_box.add_widget(message_label)

            def update_height(*args):
                message_box.height = sender_label.height + message_label.height + 5

            message_label.bind(height=update_height)

        else:
            horizontal_box = BoxLayout(
                orientation='horizontal',
                size_hint_y=None,
                spacing=0,
                padding=[0, 0, 65, 0]
            )

            # Spacer dinamico a sinistra
            spacer = Widget(size_hint_x=1)

            # Label che si adatta al contenuto
            message_label = Label(
                text=f"[color=FFFFFF]{message}[/color]",
                size_hint_y=None,
                size_hint_x=None,  # larghezza gestita manualmente
                markup=True,
                halign='left',  # non più importante, ma lasciato per coerenza
                valign='top',
                text_size=(None, None),
                font_name="Roboto"
            )

            # Canvas background (RoundedRectangle) nel container orizzontale
            with horizontal_box.canvas.before:
                Color(0.22, 0.22, 0.22, 1)
                user_message_bg = RoundedRectangle(radius=[12], pos=(0,0), size=(0,0))

            def update_message_visual(*args):
                padding_x = 10
                padding_y = 6
                max_width = Window.width * 0.6 - 2 * padding_x

                # Gestione larghezza per wrapping
                if message_label.texture_size[0] > max_width:
                    message_label.width = max_width
                else:
                    message_label.width = message_label.texture_size[0]

                message_label.text_size = (message_label.width, None)
                message_label.height = message_label.texture_size[1]

                horizontal_box.height = message_label.height
                message_box.height = sender_label.height + message_label.height + 10

                # Aggiorna posizione e dimensione background
                user_message_bg.pos = (message_label.x - padding_x, message_label.y - padding_y)
                user_message_bg.size = (message_label.width + 2 * padding_x, message_label.height + 2 * padding_y)

            message_label.bind(texture_size=update_message_visual, pos=update_message_visual, size=update_message_visual)

            horizontal_box.add_widget(spacer)
            horizontal_box.add_widget(message_label)

            message_box.add_widget(sender_label)
            message_box.add_widget(horizontal_box)

            # Aggiorna altezza dinamicamente dopo che le label sono renderizzate
            def update_height_user(*args):
                horizontal_box.height = message_label.height
                message_box.height = sender_label.height + message_label.height + 10

            message_label.bind(height=update_height_user)

        message_box.bind(minimum_height=message_box.setter('height'))

        chat_window.add_widget(message_box)
        Clock.schedule_once(self.scroll_to_bottom, 0.1)
        # Return opzionale ritorna il riferimento per poterlo in caso rimuovere 
        return message_box
    

    def response_message(self, user_message):
        # Stato interno per questa sessione di risposta
        self.streaming_text = ""          # accumula i chunk Ollama man mano che arrivano
        self.response_box = None          # box UI creato al primo chunk
        self.response_label = None        # label dentro response_box
        self.first_chunk_received = False # flag che indica se il primo chunk è già arrivato

        def on_chunk(chunk):
            # Chiamata dal thread di generazione per ogni carattere/token Ollama.
            # Non tocca la UI direttamente: usa Clock.schedule_once per farlo sul thread principale di Kivy.
            self.streaming_text += chunk
            current = self.streaming_text  # copia locale per la closure della lambda

            # Setta il flag SUBITO (sul thread di generazione), prima dello schedule.
            # Così update_chat, che gira ogni 0.1s sul thread UI, vede già first_chunk_received=True.
            # Non tenta di rimuovere il thinking box per conto suo ed evita la race condition.
            is_first = not self.first_chunk_received
            if is_first:
                self.first_chunk_received = True

            def update_streaming_label(dt):
                if is_first:
                    # Primo chunk: rimuovi il thinking box e crea il box di risposta definitivo
                    if self.thinking_box is not None:
                        self.ids.chat_window.remove_widget(self.thinking_box)
                        self.thinking_box = None
                        self.thinking_label_displayed = False
                    self.response_box = self.print_message("", sender='gaIA')
                    try:
                        # In Kivy children è in ordine inverso: il primo figlio aggiunto
                        # (sender_label) è in fondo, l'ultimo (message_label) è in cima → children[0]
                        self.response_label = self.response_box.children[0]
                    except IndexError:
                        self.response_label = None

                # Aggiorna la label con tutto il testo accumulato finora
                if self.response_label:
                    self.response_label.text = f"[color=FFFFFF]{current}[/color]"
                    Clock.schedule_once(self.scroll_to_bottom, 0)

            Clock.schedule_once(update_streaming_label, 0)


        def on_done():
            # Chiamata alla fine della generazione (sia Ollama che skill).
            # Se streaming_text è vuoto, significa che nessun chunk è arrivato quindi la risposta viene da una skill, non da Ollama.
            if not self.streaming_text:
                # Leggi la risposta salvata nel DB da process_request
                import Database_dealer as db
                id_ = db.get_last_id()
                skill_response = db.get_risposta_by_id(id_) or 'Nessuna risposta generata'

                def show_skill_response(dt):
                    # Rimuovi il thinking box se ancora presente
                    # (per le skill IA_is_thinking non viene mai impostato a True, ma per sicurezza)
                    if self.thinking_box is not None:
                        self.ids.chat_window.remove_widget(self.thinking_box)
                        self.thinking_box = None
                        self.thinking_label_displayed = False
                    # Crea il box e avvia il typewriter
                    box = self.print_message("", sender='gaIA')
                    try:
                        label = box.children[0]
                    except IndexError:
                        label = None
                    self.start_typewriter(label, skill_response)

                Clock.schedule_once(show_skill_response, 0)
                
            # Se streaming_text non è vuoto (Ollama): i chunk hanno già aggiornato la label in tempo reale, non c'è nulla da fare qui.


        # Avvia la generazione in un thread separato, come faceva il vecchio response_message.
        # on_chunk riceve i chunk Ollama in tempo reale, on_done gestisce le risposte da skill.
        def run_generation():
            gaIA_v0101.generate_response(user_message, chunk_callback=on_chunk)
            on_done()

        threading.Thread(target=run_generation, daemon=True).start()



    def start_typewriter(self, label, full_text, char_index=0, interval=0.016):
        # Mostra full_text carattere per carattere sulla label fornita.
        # interval = caratteri al secondo.
        # Usa Clock.schedule_once ricorsivo invece di un loop per non bloccare il thread UI.
        if label is None or not full_text:
            return

        def type_next(dt):
            nonlocal char_index
            if char_index <= len(full_text):
                label.text = f"[color=FFFFFF]{full_text[:char_index]}[/color]"
                Clock.schedule_once(self.scroll_to_bottom, 0)
                char_index += 1
                Clock.schedule_once(type_next, interval)  # pianifica il prossimo carattere

        Clock.schedule_once(type_next, 0)


    def update_chat(self, dt):
        # Chiamata ogni 0.1s da Clock. Gestisce due cose:
        # 1) Il box "sto pensando" durante l'elaborazione Ollama
        # 2) Le risposte in arrivo da Chat_output

        info = Chat_output.get_info()

        if gaIA_v0101.IA_is_thinking:
            # Non creare né aggiornare il thinking box se i chunk sono già arrivati: significa che la risposta è visibile e "sto pensando" è già stato rimosso da on_chunk.
            if not getattr(self, 'first_chunk_received', False):
                if not self.thinking_label_displayed:
                    # Prima volta che IA_is_thinking è True: crea il box "sto pensando"
                    self.thinking_label_displayed = True
                    if self.thinking_box is None:
                        self.thinking_box = self.print_message("sto pensando", sender='gaIA')
                    self.thinking_update_counter = 0
                else:
                    # Aggiorna i puntini animati ogni 4 tick (= 0.4 secondi)
                    self.thinking_update_counter += 1
                    if self.thinking_update_counter >= 4:
                        self.thinking_update_counter = 0
                        self.thinking_dots = (self.thinking_dots + 1) % 4  # cicla 0 → 1 → 2 → 3 → 0
                        if self.thinking_box:
                            # children[0] è la message_label (Kivy inverte l'ordine dei figli)
                            self.thinking_box.children[0].text = f"sto pensando{'.' * self.thinking_dots}"

        elif not gaIA_v0101.IA_is_thinking and self.thinking_label_displayed:
            # IA_is_thinking è tornato False: rimuovi il box se ancora presente.
            # Questo copre il caso skill (nessun chunk arrivato, on_chunk non è mai stato chiamato).
            self.thinking_label_displayed = False
            if self.thinking_box:
                self.ids.chat_window.remove_widget(self.thinking_box)
                self.thinking_box = None

        # Risposte arrivate tramite Chat_output: crea un box vuoto e lo riempie con l'animazione typewriter
        if info != self.last_info and info is not None:
            box = self.print_message("", sender='gaIA')
            try:
                label = box.children[0]  # message_label è il primo figlio (ordine inverso Kivy)
                self.start_typewriter(label, info)
            except IndexError:
                box_children = list(box.children)
                if box_children:
                    self.start_typewriter(box_children[0], info)
            self.last_info = None
            Chat_output.set_message(None)
            
   
   
    # Gestione della chat_sidebar #
    def toggle_chat_sidebar(self):
        chat_sidebar = self.ids.chat_sidebar
        user_button = self.ids.user_button

        if chat_sidebar.opacity == 0:  # Menu nascosto
            self.show_chat_sidebar()
        else:  # Menu visibile
            self.hide_chat_sidebar()


    # Mostrare chat_sidebar #
    def show_chat_sidebar(self):
        chat_sidebar = self.ids.chat_sidebar
        user_button = self.ids.user_button
        user_button.pos = (10, user_button.y)

        # Mostra il menu e sposta il pulsante
        chat_sidebar.opacity = 1
        chat_sidebar.pos = (-chat_sidebar.width, 0)  # Assicurati che parta fuori schermo a sinistra
        
        self.populate_chat_buttons()
        
        anim_sidebar = Animation(pos=(0, 0), duration=0.3)  # Sidebar entra da sinistra
        anim_sidebar.start(chat_sidebar)

        anim_button = Animation(pos=(chat_sidebar.width + 10, user_button.y), duration=0.3)  # Pulsante si sposta a destra della sidebar
        anim_button.start(user_button)


    # Nascondere chat_sidebar #
    def hide_chat_sidebar(self, on_complete_callback=None):
        chat_sidebar = self.ids.chat_sidebar
        user_button = self.ids.user_button

        anim_sidebar = Animation(pos=(-chat_sidebar.width, 0), duration=0.3)
        # Quando l'animazione finisce, imposta opacity=0 e chiama il callback se c'è
        def on_anim_complete(*args):
            chat_sidebar.opacity = 0
            self.ids.user_input.focus = True
            if on_complete_callback:
                on_complete_callback()

        anim_sidebar.bind(on_complete=on_anim_complete)
        anim_sidebar.start(chat_sidebar)

        anim_button = Animation(pos=(10, user_button.y), duration=0.3)
        anim_button.start(user_button)

        
    # Nascondere chat_sidebar quando si clicca fuori #
    def on_touch_down(self, touch):
        chat_sidebar = self.ids.chat_sidebar
        user_button = self.ids.user_button
        action_box = self.ids.action_box
        user_input = self.ids.user_input
        
        if self.ids.overlay.opacity > 0:
            # lascia che on_overlay_touch_down gestisca
            if self.on_overlay_touch_down(touch):
                return True
            
        if action_box.opacity > 0 and not action_box.collide_point(*touch.pos):
            self.hide_action_box()
            return True

        if chat_sidebar.opacity == 1:  # Se il menu sidebar è visibile
            if (chat_sidebar.collide_point(*touch.pos) or
                user_button.collide_point(*touch.pos) or
                (action_box.opacity > 0 and action_box.collide_point(*touch.pos))):  # Solo se action menu visibile
                return super().on_touch_down(touch)
            else:
                self.hide_chat_sidebar()
                return True
            
        if user_input.collide_point(*touch.pos):
            return user_input.on_touch_down(touch)

        return super().on_touch_down(touch)

    
    # Funzioni per creare tanti HoverBox (pulsanti con pulsante a destra "...") quante sono le chat e poi popolarle
    def populate_chat_buttons(self):
        chat = Database_dealer.get_all_text_chat()
        container = self.ids.chat_sidebar.ids.chat_buttons_container
        container.clear_widgets()

        for chat_row in chat:
            uuid, nome = chat_row[0], chat_row[1]

            hb = HoverBox()
            hb.primary_click = self.create_chat_callback(uuid, nome)

            # Se HoverBox ha un pulsante interno a cui vuoi settare testo:
            if hasattr(hb, 'ids') and 'main_hoverbox_button' in hb.ids:
                button = hb.ids.main_hoverbox_button
                button.text = nome
                button.uuid_chat = uuid
                
                # Usa current_chat_uuid per impostare il pulsante attivo
                if 'current_chat_uuid' in globals() and current_chat_uuid == uuid:
                    button.active = True
            
            container.add_widget(hb)


    def create_chat_callback(self, uuid_chat, nome_chat):
        def callback(instance=None):
            global current_chat_uuid
            current_chat_uuid = uuid_chat
            print(f"Chat selezionata: {nome_chat} con UUID: {current_chat_uuid}")
            
            self.hide_chat_sidebar()
            self.ids.user_input.focus = True
            self.ids.chat_window.clear_widgets()
            
            if instance is not None:
                self.ids.chat_name.text = instance.text
            else:
                self.ids.chat_name.text = Database_dealer.get_chat_name_by_id(uuid_chat)
            
            def load_and_show_conversation():
                # Caricamento dati in thread separato
                def get_conversation_query():
                    conversazioni = Database_dealer.get_conversazioni_by_chat_id(uuid_chat)

                    def load_conversation(dt):
                        def on_chat_height_change(instance, value):
                            # Scroll solo se il contenuto è più alto dello ScrollView
                            scroll_view = self.ids.chat_window.parent
                            scroll_view.scroll_y = 0  # Scrolla in fondo
                            instance.unbind(height=on_chat_height_change)

                        self.ids.chat_window.bind(height=on_chat_height_change)
                        
                        if not conversazioni:
                            # Nessuna conversazione presente
                            self.show_new_chat_message()
                        else:
                            for richiesta, risposta in conversazioni:
                                if richiesta:
                                    self.print_message(richiesta, sender='You')
                                if risposta:
                                    self.print_message(risposta, sender='gaIA')
                                    
                        # Mette a fuoco input dopo caricamento
                        self.ids.user_input.focus = True

                    Clock.schedule_once(load_conversation)
                threading.Thread(target=get_conversation_query).start()
            self.hide_chat_sidebar(on_complete_callback=load_and_show_conversation)
        return callback
    
    
    def reload_chat_button(self, hb_widget, new_name):
        if hasattr(hb_widget, 'ids') and 'main_hoverbox_button' in hb_widget.ids:
            button = hb_widget.ids.main_hoverbox_button
            button.text = new_name
            hb_widget.primary_click = self.create_chat_callback(button.uuid_chat, new_name)


    # Funzioni per gestire l'action menù
    def show_action_menu(self, pulsante):
        self.current_button = pulsante.parent.ids.main_hoverbox_button
        float_layout = self.ids.float_layout
        # Posizione top-right del pulsante in coordinate finestra
        pos_window = pulsante.to_window(pulsante.right, pulsante.top)
        # Converti in coordinate locali di float_layout
        pos_local = float_layout.to_widget(*pos_window)
        action_box = self.ids.action_box
        action_box.opacity = 1
        action_box.disabled = False
        # Posiziona action_box a destra del pulsante, allineato in alto
        x = pos_local[0] + 5  # un piccolo margine a destra
        y = pos_local[1] - action_box.height  # allineato in alto con il pulsante
        # Limita per non uscire fuori dai bordi di float_layout
        x = max(0, min(x, float_layout.width - action_box.width))
        y = max(0, min(y, float_layout.height - action_box.height))
        action_box.pos = (x, y)

    def hide_action_box(self):
        self.ids.action_box.opacity = 0
        self.ids.action_box.disabled = True

    def hide_overlay(self):
        self.ids.overlay.opacity = 0
        
    def show_overlay(self):
        self.ids.overlay.opacity = 1

    def reset_input_state(self):   
        self.ids.chat_name_input.opacity = 0
        self.ids.chat_name_input.disabled = True
        self.ids.input_label.opacity = 0
        self.ids.input_label.disabled = True
        # Riattiva effetto hover
        for hb in self.ids.chat_sidebar.ids.chat_buttons_container.children:
            if hasattr(hb, 'ids') and 'main_hoverbox_button' in hb.ids:
                hb.ids.main_hoverbox_button.hover_enabled = True

    def show_chat_rename_input(self):
        self.show_overlay()
        if not self.current_button:
            return               
        btn = self.current_button
        float_layout = self.ids.float_layout  # FloatLayout che contiene chat_name_input
        # Ottieni la posizione assoluta (window) del pulsante
        pos_window = btn.to_window(btn.x, btn.top)
        # Converti in coordinate relative a float_layout
        pos_local = float_layout.to_widget(*pos_window)
        # Posiziona chat_name_input sopra il bottone (con un piccolo offset)
        chat_name_input = self.ids.chat_name_input
        chat_name_input.size = btn.size
        chat_name_input.pos = (pos_local[0], pos_local[1] - chat_name_input.height)
        chat_name_input.text = btn.text
        chat_name_input.opacity = 1
        chat_name_input.disabled = False
        chat_name_input.focus = True
        self.ids.input_label.opacity = 1
        self.ids.input_label.disabled = False
        self.hide_action_box()
        # Disattiva effetto hover per tutti i bottoni durante la modifica
        for hb in self.ids.chat_sidebar.ids.chat_buttons_container.children:
            if hasattr(hb, 'ids') and 'main_hoverbox_button' in hb.ids:
                hb.ids.main_hoverbox_button.hover_enabled = False

    def on_overlay_touch_down(self, touch):
        chat_input = self.ids.chat_name_input
        if chat_input.opacity == 1:
            if chat_input.collide_point(*touch.pos):
                # Tocca dentro il campo input: non fare nulla
                return False
            else:
                # Tocca fuori dal campo input: chiudi modifica
                self.change_chat_name(chat_input)
                self.reset_input_state()
                self.hide_overlay()
                return True
        return False
    

    def on_action_button(self, action):
        if action == 'modifica':
            self.show_chat_rename_input()
        elif action == 'elimina':
            self.delete_chat()
            self.hide_overlay()
        else:
            print(f"Azione selezionata: {action}")
            self.hide_overlay()
        self.hide_action_box()
        
        
    # Funzioni in merito a creazione, modifica e cancellazione delle chat       
    def new_chat(self):
        name = "Nuova Chat"
        Database_dealer.insert_chat(name)
        self.populate_chat_buttons()

        # Prendi il primo pulsante appena creato (viene aggiunto per ultimo)
        container = self.ids.chat_sidebar.ids.chat_buttons_container
        if container.children:
            hb = container.children[0]  # il più recente è in cima
            if hasattr(hb, 'ids') and 'main_hoverbox_button' in hb.ids:
                button = hb.ids.main_hoverbox_button
                button.active = True
                self.current_button = button
                hb.primary_click()


    def change_chat_name(self, instance):
        if self.current_button:
            new_name = instance.text
            self.current_button.text = new_name
            Database_dealer.update_chat_name(new_name, self.current_button.uuid_chat)
            self.reload_chat_button(self.current_button, new_name)
            # Se il pulsante attuale è attivo, aggiorna anche il nome visualizzato in alto
            if self.current_button.active:
                self.ids.chat_name.text = new_name
        instance.text = ""
        self.reset_input_state()
        self.hide_overlay()
        self.current_button = None
        
    def delete_chat(self):
        Database_dealer.delete_conversazioni_by_chat_id(self.current_button.uuid_chat)
        Database_dealer.delete_chat(self.current_button.uuid_chat)
        self.populate_chat_buttons()
        if self.current_button.active:
            self.ids.chat_name.text = ""
            self.show_welcome_message()
        self.current_button = None
        self.hide_chat_sidebar()
        self.ids.user_input.focus = True



class HoverBox(FloatLayout):
    primary_click = ObjectProperty(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Window.bind(mouse_pos=self.on_mouse_pos)

    def on_mouse_pos(self, window, pos):
        btn = self.ids.main_hoverbox_button
        action_menu_button = self.ids.action_menu_button

        inside_btn = btn.collide_point(*btn.to_widget(*pos))
        inside_action_menu_button = action_menu_button.collide_point(*action_menu_button.to_widget(*pos))

        btn.hovering = inside_btn or inside_action_menu_button

    def function(self):
        if self.primary_click:
            self.primary_click()



class WindowManager(ScreenManager):
    pass



Window.clearcolor = (30 / 255, 30 / 255, 30 / 255, 1)  # Colore della finestra
STYLE_PATH = "..\style.kv"


class CustomTextInput(TextInput):
    max_lines = NumericProperty(7)

    def __init__(self, **kwargs):
        self.app = kwargs.get('app')
        super().__init__(**kwargs)
        self.bind(width=self.on_size_change)
        self.bind(font_size=self.on_size_change)
        self.bind(text=self.on_text_change)
        self._last_line_count = 0  # per controllare variazioni righe
        
        with self.canvas.before:
            self.bg_color = Color(0.2, 0.2, 0.2, 1)  # esempio colore grigio scuro
            self.bg_rect = RoundedRectangle(radius=[15], pos=self.pos, size=(self.size[0] + 58, self.size[1]))

        self.bind(pos=self.update_bg, size=self.update_bg)

    def update_bg(self, *args):
        self.bg_rect.pos = self.pos
        self.bg_rect.size = (self.size[0] + 58, self.size[1])

    def set_height_by_lines(self, line_count):
        visible_lines = min(line_count, self.max_lines)
        self.height = (visible_lines + 1) * self.line_height + self.padding[1] + 20
        if line_count > self.max_lines:
            self.scroll_y = 0
        else:
            self.scroll_y = 1

    def count_lines(self):
        try:
            self._update_graphics()
            lines = len(self._lines)
        except Exception:
            lines = 1
        if self.text.strip() == "":
            self._update_graphics()
            lines = len(self._lines)
        return lines

    def on_size_change(self, *args):
        Clock.schedule_once(lambda dt: self.update_height(), 0)

    def on_text_change(self, instance, value):
        # Aggiorna altezza solo se cambia il numero righe, così evita troppi update
        line_count = self.count_lines()
        if line_count != self._last_line_count:
            self._last_line_count = line_count
            Clock.schedule_once(lambda dt: self.set_height_by_lines(line_count), 0)

    def update_height(self):
        line_count = self.count_lines()
        if line_count != self._last_line_count:
            self._last_line_count = line_count
            self.set_height_by_lines(line_count)

    def keyboard_on_key_down(self, window, keycode, text, modifiers):
        if keycode[1] == 'enter':
            if 'shift' in modifiers:
                Clock.schedule_once(lambda dt: self.set_height_by_lines(self.count_lines()), 0)
                self.insert_text('\n')
            else:
                self.app.root.get_screen('chat').send_message()
            return True
        else:
            return super().keyboard_on_key_down(window, keycode, text, modifiers)





class gaIA_v0101App(App):
    def build(self):
        # Designete Our .kv design file
        kv = Builder.load_file(STYLE_PATH)
        gaIA_v0101.conversation_memory = True
        if os.path.exists(CRED_FILE):
            with open(CRED_FILE, 'r') as f:
                data = json.load(f)
                if data.get('keep_logged'):
                    # Passa direttamente alla schermata home
                    sm = kv
                    sm.transition = NoTransition()
                    sm.current = 'main'
                    sm.transition = SlideTransition()
                    return sm
        return kv
    
    # Funzione per navigare verso lo schermo principale
    def go_to_settings(self):
        self.root.current = 'settings'
        self.root.transition.direction = 'right'
    
    # Funzione per navigare verso lo schermo principale
    def go_to_main(self):
        if self.root.current == 'settings':
            self.root.transition.direction = 'left'
        else:
            self.root.transition.direction = 'right'
        self.root.current = 'main'

    # Funzione per navigare verso lo schermo della chat
    def go_to_chat(self):
        self.root.current = 'chat'
        self.root.transition.direction = 'left'
        


def run():
    BackgroundServices.run()
    gaIA_v0101App().run()


if __name__ == '__main__':
    run()