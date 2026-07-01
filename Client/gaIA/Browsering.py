from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import re


## Funzione che rimuove il testo da impurità come [1] ##
def clean_text(text):
    text = re.sub(r'\[\d+\]', '', text)
    text = text.strip()
    return text


## Rimuove eventuali punti finali ed articoli dalle parole chiavi ##
def remove_article_and_punctuation(text):
    articles = ["il", "lo", "la", "i", "gli", "le", "un", "uno", "una"]
    words = text.split()
    if words and words[0].lower() in articles:
        words.pop(0)
    cleaned_text = ' '.join(words)
    if cleaned_text.endswith('.'):
        cleaned_text = cleaned_text[:-1].strip()
    return cleaned_text


## Estrapola dalla richiesta in input le parole chiave che vanno ricercate ##
def extract_keywords(text):
    keywords_indicators = ["ricerca", "cerca su internet"]
    for indicator in keywords_indicators:
        index = text.lower().find(indicator)
        if index != -1:
            keywords = text[index + len(indicator):].strip()
            cleaned_keywords = remove_article_and_punctuation(keywords)
            return cleaned_keywords
    return "Nessuna query trovata"


## Apre e cerca dentro Wikipedia.org ##
def get_wikipedia_intro(driver, query):
    driver.get("https://www.wikipedia.org/")
    search_box = driver.find_element(By.NAME, "search")
    search_box.send_keys(query)
    search_box.send_keys(Keys.RETURN)

    try:
        # Attendere fino a quando il primo paragrafo è visibile
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.mw-parser-output > p"))
        )
    except Exception as e:
        print(f"Errore durante l'attesa della pagina: {e}")
        return "Errore durante la ricerca"

    page_content = driver.page_source
    soup = BeautifulSoup(page_content, 'html.parser')
    # Trova il primo paragrafo nella sezione di contenuto principale
    paragraph = soup.select_one('div.mw-parser-output > p').get_text()
    cleaned_paragraph = clean_text(paragraph)
    return cleaned_paragraph


## Funzione principale ##
def run(transcript):
    query = extract_keywords(transcript)
    with webdriver.Chrome(service=Service(ChromeDriverManager().install())) as driver:
        result = get_wikipedia_intro(driver, query)
    return result


if __name__ == "__main__":
    request = input("Come posso aiutarti oggi? : ")
    print(run(request))
