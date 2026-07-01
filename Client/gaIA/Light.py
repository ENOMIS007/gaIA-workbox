from PyP100 import PyL530
import time

l530 = PyL530.L530("192.168.173.251", "simone.project.gaia@gmail.com", "simone2006")
#l530.setColor(30, 80)  # Sets the color of the connected bulb to Hue: 30°, Saturation: 80% (Orange)

changed_colors = False

def on():
    global changed_colors
    
    l530.turnOn() #Turns the connected plug on
    if not changed_colors:
        l530.setBrightness(100)  # Sets the brightness of the connected bulb to 50% brightness
        l530.setColorTemp(3370)  # Sets the color temperature of the connected bulb to 2700 Kelvin (Warm White)
    
    
def off():
    l530.turnOff() #Turns the connected plug off
    
    
def change_colors(color):
    global changed_colors
    
#     if color == "arancione":
    l530.setColor(30, 80) #Arancione
    changed_colors = True


# Funzioni extra:
#[
# l530.toggleState() #Toggles the state of the connected plug
# 
# l530.turnOnWithDelay(4) #Turns the connected plug on after 10 seconds
# l530.turnOffWithDelay(10) #Turns the connected plug off after 10 seconds
# 
# l530.getDeviceInfo() #Returns dict with all the device info of the connected plug
# l530.getDeviceName() #Returns the name of the connected plug set in the app
# 
# All the bulbs have the same basic functions as the plugs and additionally allow for the following functions.
# l530.setBrightness(50)  # Sets the brightness of the connected bulb to 50% brightness
# l530.setColorTemp(2700)  # Sets the color temperature of the connected bulb to 2700 Kelvin (Warm White)
# l530.setColor(30, 80)  # Sets the color of the connected bulb to Hue: 30°, Saturation: 80% (Orange)
#]


if __name__ == "__main__":
    off()
    time.sleep(1)
    on()
#     print(l530.getDeviceInfo())
