from kivy.app import App
from kivy.uix.widget import Widget
from kivy.uix.button import Button
from kivy.graphics import Line, Color, Ellipse
from kivy.clock import Clock
from kivy.animation import Animation
from kivy.properties import NumericProperty
import math
import random

# Widget Ascolto
class CircleWidget(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.drawing_visible = True
        self.center_circle_radius = 20

        self.angle1 = 0
        self.angle2 = 0
        self.angle3 = 0

        self.period1 = 4
        self.period2 = 6
        self.period3 = 8

        self.min_speed = 0.5
        self.max_speed = 5

        self.time1 = 0
        self.time2 = 0
        self.time3 = 0

        with self.canvas:
            Color(1, 1, 1)
            self.arc1 = Line(circle=(self.center[0], self.center[1], 60, 0, 90), width=4)
            self.arc2 = Line(circle=(self.center[0], self.center[1], 80, 0, 120), width=4)
            self.arc3 = Line(circle=(self.center[0], self.center[1], 100, 0, 150), width=4)
            self.center_circle = Ellipse(pos=(self.center[0] - self.center_circle_radius, self.center[1] - self.center_circle_radius), size=(self.center_circle_radius * 2, self.center_circle_radius * 2))

        Clock.schedule_interval(self.update_arcs, 1 / 60.)

    def update_arcs(self, dt):
        if not self.drawing_visible:
            return

        self.time1 += dt
        self.time2 += dt
        self.time3 += dt

        speed1 = self.min_speed + (self.max_speed - self.min_speed) * (0.5 + 0.5 * math.sin(2 * math.pi * self.time1 / self.period1))
        speed2 = self.min_speed + (self.max_speed - self.min_speed) * (0.5 + 0.5 * math.sin(2 * math.pi * self.time2 / self.period2))
        speed3 = self.min_speed + (self.max_speed - self.min_speed) * (0.5 + 0.5 * math.sin(2 * math.pi * self.time3 / self.period3))

        self.angle1 = (self.angle1 + speed1) % 360
        self.angle2 = (self.angle2 + speed2) % 360
        self.angle3 = (self.angle3 + speed3) % 360

        self.arc1.circle = (self.center[0], self.center[1], 60, self.angle1, self.angle1 + 90)
        self.arc2.circle = (self.center[0], self.center[1], 80, self.angle2, self.angle2 + 120)
        self.arc3.circle = (self.center[0], self.center[1], 100, self.angle3, self.angle3 + 150)

    def on_size(self, *args):
        if not self.drawing_visible:
            return

        self.arc1.circle = (self.center[0], self.center[1], 60, self.angle1, self.angle1 + 90)
        self.arc2.circle = (self.center[0], self.center[1], 80, self.angle2, self.angle2 + 120)
        self.arc3.circle = (self.center[0], self.center[1], 100, self.angle3, self.angle3 + 150)
        self.center_circle.pos = (self.center[0] - self.center_circle_radius, self.center[1] - self.center_circle_radius)
        self.center_circle.size = (self.center_circle_radius * 2, self.center_circle_radius * 2)

# Widget Parlato
class AnimatedDot(Widget):
    height_scale = NumericProperty(1)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (None, None)
        self.size = (40, 40)
        with self.canvas:
            Color(1, 1, 1)
            self.ellipse = Ellipse(pos=self.pos, size=self.size)
        self.bind(pos=self.update_graphics, size=self.update_graphics, height_scale=self.update_graphics)

    def update_graphics(self, *args):
        self.ellipse.pos = (self.pos[0], self.pos[1] - (self.height_scale - 1) * self.size[1] / 2)
        self.ellipse.size = (self.size[0], self.size[1] * self.height_scale)

    def random_animate(self, *args):
        new_scale = random.uniform(1.5, 3)
        duration = random.uniform(0.2, 0.5)
        anim = Animation(height_scale=new_scale, duration=duration) + Animation(height_scale=1, duration=duration)
        anim.on_complete = self.random_animate
        anim.start(self)

class DotWidget(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.dots = []
        self.create_dots()

    def create_dots(self):
        positions = [
            (self.width / 2 - 110, self.height / 2 - 20),
            (self.width / 2 - 50, self.height / 2 - 20),
            (self.width / 2 + 10, self.height / 2 - 20),
            (self.width / 2 + 70, self.height / 2 - 20),
        ]
        for pos in positions:
            dot = AnimatedDot(pos=pos)
            self.add_widget(dot)
            dot.random_animate()
            self.dots.append(dot)

    def on_size(self, *args):
        for dot, pos in zip(self.dots, [
            (self.width / 2 - 110, self.height / 2 - 20),
            (self.width / 2 - 50, self.height / 2 - 20),
            (self.width / 2 + 10, self.height / 2 - 20),
            (self.width / 2 + 70, self.height / 2 - 20),
        ]):
            dot.pos = pos

# Funzioni per cambiare il disegno
def switch_to_ascolto(layout, circle_widget, dot_widget):
    """Funzione per cambiare al disegno Ascolto."""
    switch_widget(layout, circle_widget, dot_widget)

def switch_to_parlato(layout, circle_widget, dot_widget):
    """Funzione per cambiare al disegno Parlato."""
    switch_widget(layout, dot_widget, circle_widget)

def switch_widget(layout, new_widget, current_widget):
    """Funzione che gestisce il cambio fluido del disegno."""
    anim_out = Animation(opacity=0, duration=0.3)
    anim_out.start(current_widget)

    anim_out.bind(on_complete=lambda *args: _remove_and_add_widget(layout, new_widget, current_widget))

def _remove_and_add_widget(layout, new_widget, current_widget):
    """Rimuove il widget corrente e aggiunge quello nuovo."""
    layout.remove_widget(current_widget)
    layout.add_widget(new_widget)
    new_widget.opacity = 0
    anim_in = Animation(opacity=1, duration=0.3)
    anim_in.start(new_widget)

