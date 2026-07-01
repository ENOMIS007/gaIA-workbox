import requests

API_KEY = "7a8e267fc0ab97f088b9f162dacce074"
DEFAULT_CITY = "Messina"

# Prende in input la città e da in output le previsioni meteo e la temperatura corrente
def run(citta: str = None):
    city_name = citta.capitalize() if citta else DEFAULT_CITY
    link = f"https://api.openweathermap.org/data/2.5/weather?q={city_name}&appid={API_KEY}&units=metric&lang=it"

    response = requests.get(link)

    if response.status_code == 200:
        data = response.json()
        
        # Estrai la condizione climatica e la temperatura
        condizione_climatica = data["weather"][0]["description"]
        temperatura = data["main"]["temp"]
        
        return f"Oggi a {city_name} ci sono {temperatura}°C con {condizione_climatica}"
    else:
        return f"Errore nella richiesta per '{city_name}': {response.status_code}, {response.text}"

if __name__ == "__main__":
    citta = input("Città (invio per default): ").strip() or None
    r = run(citta)
    print(r)
