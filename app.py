# ==============================================================================
# CELDA ÚNICA: SCRAPER Y GENERADOR DE APP - VERSIÓN FINAL Y ROBUSTA
# ==============================================================================

# --- Instalación de Dependencias para Colab ---
!pip install selenium beautifulsoup4 tqdm streamlit -q --upgrade
print("Dependencias de scraping y Streamlit instaladas/actualizadas.")

# --- Importaciones ---
import os
import sqlite3
import time
import json
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup
from tqdm.notebook import tqdm
import streamlit as st

# --- Configuración General ---
RUN_SCRAPER = True
URL_PRINCIPAL = "https://www.xbox.com/es-CO/games/browse?IncludedInSubscription=CFQ7TTC0KHS0%2CCFQ7TTC0KGQ8%2CCFQ7TTC0K6L8%2CCFQ7TTC0P85B%2CCFQ7TTC0K5DJ"
NOMBRE_BD = "gamepass_catalog.db"

# --- Limpieza de la Base de Datos Antigua ---
if RUN_SCRAPER and os.path.exists(NOMBRE_BD):
    print(f"Eliminando la base de datos antigua '{NOMBRE_BD}' para recrearla con la nueva estructura.")
    os.remove(NOMBRE_BD)

# ==============================================================================
# 1. FUNCIONES DEL SCRAPER (VERSIÓN FINAL Y ROBUSTA)
# ==============================================================================

def setup_selenium_in_colab():
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--log-level=3')
    options.add_argument('--disable-gpu')
    options.page_load_strategy = 'eager'
    prefs = {"profile.managed_default_content_settings.images": 2, "profile.managed_default_content_settings.fonts": 2}
    options.add_experimental_option("prefs", prefs)
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(45)
    return driver

def setup_database():
    conn = sqlite3.connect(NOMBRE_BD)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT UNIQUE, url TEXT, price TEXT,
            description TEXT, developer TEXT, publisher TEXT, release_date TEXT, image_url TEXT,
            rating_age TEXT, rating_descriptors TEXT, platforms TEXT, features TEXT,
            genres TEXT, search_keywords TEXT
        )
    ''')
    conn.commit()
    conn.close()
    print(f"Base de datos '{NOMBRE_BD}' configurada con la estructura correcta.")

def scrape_main_page(driver):
    print("Accediendo al catálogo de Game Pass...")
    driver.get(URL_PRINCIPAL)
    time.sleep(5)
    click_count = 0
    while True:
        try:
            load_more_button = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Cargar más')]"))
            )
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", load_more_button)
            time.sleep(1)
            driver.execute_script("arguments[0].click();", load_more_button)
            click_count += 1
            print(f"Botón 'Cargar más' presionado ({click_count}).")
            time.sleep(3)
        except:
            print("No se encontró más el botón 'Cargar más'. Se asume que se cargó todo.")
            break
    print("Extrayendo enlaces de los juegos...")
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    game_cards = soup.select("div[class*='ProductCard-module__cardWrapper___']")
    game_urls = [card.find('a', href=True)['href'] for card in game_cards if card.find('a', href=True) and card.find('a', href=True)['href'].startswith('http')]
    print(f"Se encontraron {len(set(game_urls))} juegos únicos en el catálogo.")
    return list(set(game_urls))

def safe_extract_text(soup, selector, default="No disponible"):
    try:
        element = soup.select_one(selector)
        return element.text.strip() if element else default
    except: return default

def extract_game_properties(soup):
    """Función robusta y multi-método para extraer todos los detalles."""
    properties = {
        'developer': 'No disponible', 'publisher': 'No disponible',
        'release_date': 'No disponible', 'genres': 'No disponible'
    }
    
    # MÉTODO 1: Buscar por h3 y div siguiente (estructura principal)
    for title_text, key in [("Desarrollador", "developer"), ("Editor", "publisher"), 
                              ("Fecha de lanzamiento", "release_date"), ("Género", "genres")]:
        try:
            title_element = soup.find('h3', string=lambda text: text and title_text.lower() in text.lower())
            if title_element:
                value_element = title_element.find_next_sibling('div')
                if value_element:
                    properties[key] = value_element.text.strip()
        except:
            continue

    # MÉTODO 2 (RESPALDO): Buscar en la tabla de propiedades alternativa
    prop_containers = soup.select("div[class*='GameProperties-module__gamePropertiesContainer___']")
    for container in prop_containers:
        titles = container.select("span[class*='GameProperties-module__propertyTitle___']")
        values = container.select("span[class*='GameProperties-module__propertyValue___']")
        for title, value in zip(titles, values):
            title_text = title.text.strip().lower()
            value_text = value.text.strip()
            if 'desarrollador' in title_text and properties['developer'] == 'No disponible':
                properties['developer'] = value_text
            elif 'editor' in title_text and properties['publisher'] == 'No disponible':
                properties['publisher'] = value_text
            elif 'fecha de lanzamiento' in title_text and properties['release_date'] == 'No disponible':
                properties['release_date'] = value_text
            elif 'género' in title_text and properties['genres'] == 'No disponible':
                properties['genres'] = value_text

    return properties

def scrape_detail_page(driver, url):
    try:
        driver.get(url)
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, "h1[class*='ProductDetailsHeader-module__productTitle']")))
    except: return None

    soup = BeautifulSoup(driver.page_source, 'html.parser')
    data = {'url': url}
    data['title'] = safe_extract_text(soup, "h1[class*='ProductDetailsHeader-module__productTitle']")
    if data['title'] == "No disponible": return None
    
    data['price'] = safe_extract_text(soup, "span[class*='Price-module__boldText']")
    data['description'] = safe_extract_text(soup, "p[class*='Description-module__description']")
    try: data['image_url'] = soup.select_one("img[class*='ProductDetailsHeader-module__productImage']").get('src')
    except: data['image_url'] = "No disponible"
    
    # Usamos la nueva función robusta
    game_props = extract_game_properties(soup)
    data.update(game_props)
    
    data['rating_age'] = safe_extract_text(soup, "a[class*='EsrbRating-module__link']")
    data['rating_descriptors'] = safe_extract_text(soup, "div[class*='EsrbRating-module__description']")
    data['platforms'] = safe_extract_text(soup, "div[class*='AvailableOn-module__container___']")
    data['features'] = safe_extract_text(soup, "ul[class*='Features-module__container___']")
    
    # Generar keywords para búsqueda rápida
    all_text = ' '.join(filter(None, [
        data.get('title'), data.get('genres'), data.get('features'),
        data.get('description', '')[:200]
    ]))
    keywords = set(re.findall(r'\\b\\w{3,}\\b', all_text.lower()))
    data['search_keywords'] = ' '.join(sorted(list(keywords)))
    
    return data

def save_to_db(conn, game_data):
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO games (title, url, price, description, developer, publisher, release_date, image_url,
                           rating_age, rating_descriptors, platforms, features, genres, search_keywords)
        VALUES (:title, :url, :price, :description, :developer, :publisher, :release_date, :image_url,
                :rating_age, :rating_descriptors, :platforms, :features, :genres, :search_keywords)
        ON CONFLICT(title) DO UPDATE SET
            url=excluded.url, price=excluded.price, description=excluded.description,
            developer=excluded.developer, publisher=excluded.publisher, release_date=excluded.release_date,
            image_url=excluded.image_url, rating_age=excluded.rating_age, rating_descriptors=excluded.rating_descriptors,
            platforms=excluded.platforms, features=excluded.features, genres=excluded.genres, 
            search_keywords=excluded.search_keywords
    ''', game_data)

def run_scraper_process():
    setup_database()
    driver = setup_selenium_in_colab()
    try:
        print("--- Fase 1: Obteniendo URLs de Game Pass ---")
        game_urls = scrape_main_page(driver)
        if not game_urls:
            print("No se encontraron URLs. Proceso terminado.")
            return

        print(f"\n--- Fase 2: Scraping de {len(game_urls)} juegos ---")
        conn = sqlite3.connect(NOMBRE_BD)
        for url in tqdm(game_urls, desc="Procesando y guardando juegos"):
            game_data = scrape_detail_page(driver, url)
            if game_data:
                save_to_db(conn, game_data)
        conn.commit()
        conn.close()
    finally:
        driver.quit()
        print("\nProceso de scraping finalizado.")

# El código que genera app.py y requirements.txt no cambia
app_code = """
import streamlit as st
import sqlite3
import os
import json
import re
import openai

st.set_page_config(layout="wide", page_title="Buscador Inteligente Game Pass")

NOMBRE_BD = "gamepass_catalog.db"

@st.cache_resource
def get_db_connection():
    if not os.path.exists(NOMBRE_BD):
        st.error(f"Error crítico: El archivo '{NOMBRE_BD}' no se encontró.")
        st.info("Asegúrate de haber subido 'gamepass_catalog.db' a tu repositorio de GitHub.")
        return None
    try:
        conn = sqlite3.connect(NOMBRE_BD, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        st.error(f"Error al conectar con la base de datos: {e}")
        return None

def keyword_search(conn, search_term):
    stop_words = set(['juego', 'juegos', 'de', 'un', 'una', 'con', 'para', 'que', 'sea', 'sean', 'y', 'o', 'el', 'la', 'los', 'las', 'algo', 'asi', 'llamado'])
    keywords = [word for word in re.split(r'[\\s,;]+', search_term.lower()) if word and word not in stop_words]
    if not keywords: return []
    query_parts = ["search_keywords LIKE ?"] * len(keywords)
    full_query = "SELECT * FROM games WHERE " + " AND ".join(query_parts) + " ORDER BY title"
    params = [f"%{kw}%" for kw in keywords]
    try:
        return conn.cursor().execute(full_query, tuple(params)).fetchall()
    except sqlite3.Error as e:
        st.error(f"Error en la búsqueda: {e}. Es posible que la base de datos no se haya generado correctamente.")
        return []

@st.cache_data(show_spinner="🧠 Consultando al Asistente IA...")
def get_ai_recommendations(_conn, user_input):
    try:
        openai.api_key = st.secrets["openai"]["api_key"]
    except:
        st.error("Clave de API de OpenAI no configurada en los Secrets de Streamlit.")
        return []
    
    all_games_context = _conn.execute("SELECT title, genres FROM games WHERE genres IS NOT NULL AND genres != 'No disponible'").fetchall()
    if not all_games_context:
        st.warning("No se encontraron juegos con géneros en la base de datos para alimentar a la IA. Es posible que el scraper no haya extraído esta información.")
        return []
        
    game_list_for_prompt = [{"title": g['title'], "genres": g['genres']} for g in all_games_context]
    json_example_str = json.dumps({"titles": ["Overcooked! 2", "Stardew Valley"]})
    
    system_prompt = f\"\"\"
    Eres un asistente experto en Xbox Game Pass. Tu tarea es analizar la petición del usuario y recomendar juegos del catálogo disponible: {json.dumps(game_list_for_prompt)}.
    RESPONDE SOLAMENTE con un objeto JSON con una única clave "titles" que contenga una lista de strings con los NOMBRES EXACTOS de los juegos.
    No añadas explicaciones. No inventes juegos. Si no encuentras nada, devuelve una lista vacía.
    Ejemplo de respuesta si el usuario pide "juegos de cocina cooperativos": {json_example_str}
    \"\"\"
    
    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_input}],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        return json.loads(response.choices[0].message.content).get("titles", [])
    except Exception as e:
        st.error(f"Ocurrió un error al comunicarse con el Asistente de IA: {e}")
        return []

def get_games_by_titles(conn, titles):
    if not titles: return []
    placeholders = ','.join('?' for _ in titles)
    query = f"SELECT * FROM games WHERE title IN ({placeholders})"
    return conn.cursor().execute(query, tuple(titles)).fetchall()

def display_game_card(game):
    with st.container(border=True):
        col1, col2 = st.columns([1, 3])
        with col1:
            if game['image_url'] and game['image_url'] != "No disponible":
                st.image(game['image_url'])
        with col2:
            st.subheader(game['title'])
            st.link_button("✔️ Ver en la Tienda de Xbox (Incluido en Game Pass)", game['url'], use_container_width=True, type="primary")
            st.caption(f"**Géneros:** {game.get('genres', 'No disponible')}")
            description = game['description'] if game['description'] and game['description'] != 'No disponible' else "No hay descripción disponible."
            st.write(description[:250] + "..." if len(description) > 250 else description)
            with st.expander("Más detalles"):
                st.write(f"**Desarrollador:** {game['developer']}")
                st.write(f"**Editor:** {game['publisher']}")
                st.write(f"**Fecha de Lanzamiento:** {game['release_date']}")

st.title("🎮 Buscador Inteligente del Catálogo de Game Pass")
conn = get_db_connection()

if conn:
    total_games = conn.execute("SELECT COUNT(id) FROM games").fetchone()[0]
    st.success(f"Catálogo con **{total_games}** juegos. ¡Listo para buscar!")
    search_mode = st.radio( "Elige tu modo de búsqueda:",("Búsqueda por Palabras Clave", "Asistente con IA (Recomendado)"), horizontal=True, index=1, help="Palabras Clave: Rápido, busca términos exactos. Asistente IA: Entiende lenguaje natural (ej: 'juegos como Overcooked').")
    user_input = st.text_input("¿Qué te apetece jugar?", placeholder="Ej: un juego de terror para jugar con amigos...")
    if user_input:
        results = []
        if "Palabras Clave" in search_mode:
            with st.spinner("Buscando por palabras clave..."):
                results = keyword_search(conn, user_input)
        else:
            recommended_titles = get_ai_recommendations(conn, user_input)
            if recommended_titles:
                results = get_games_by_titles(conn, recommended_titles)
        if results:
            st.write(f"#### Se encontraron {len(results)} resultados:")
            for game in results:
                display_game_card(game)
        else:
            if user_input:
                st.warning(f"No se encontraron resultados para '{user_input}'. Intenta con otros términos.")
else:
    st.info("Iniciando la aplicación y conectando a la base de datos...")

st.sidebar.markdown("---")
st.sidebar.header("Sobre este Proyecto")
st.sidebar.info("Esta herramienta usa un scraper para obtener datos y la API de OpenAI para la búsqueda avanzada.")
st.sidebar.markdown("Creado con ❤️ por [@TuUsuario](https://instagram.com/TuUsuario)")
"""

# --- Generación de archivos ---
with open("app.py", "w", encoding="utf-8") as f: f.write(app_code)
print("\n✅ Archivo 'app.py' generado con la última versión.")
with open("requirements.txt", "w") as f: f.write("streamlit\nopenai\n")
print("✅ Archivo 'requirements.txt' generado.")

# --- Ejecución del Proceso ---
if RUN_SCRAPER:
    run_scraper_process()
    print(f"\n✅ Archivo '{NOMBRE_BD}' generado/actualizado.")

print("\n--- ¡Todo listo! ---")
print("\n**ACCIÓN REQUERIDA - MUY IMPORTANTE:**")
print("1. **Espera a que el scraper termine**.")
print("2. **Descarga el NUEVO `gamepass_catalog.db`** que se acaba de generar en Colab.")
print("3. **Sube y sobreescribe `gamepass_catalog.db` en tu repositorio de GitHub.**")
print("4. **NO necesitas cambiar `app.py` esta vez.**")
print("5. **Reinicia la app en Streamlit** para que cargue la nueva base de datos.")
