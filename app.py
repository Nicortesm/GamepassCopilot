import streamlit as st
import sqlite3
import os
import json
import re
import openai

# --- Configuración de la página ---
st.set_page_config(layout="wide", page_title="Buscador Inteligente Game Pass")

# --- Configuración de la App ---
# El nombre de la base de datos que está en el mismo repositorio
NOMBRE_BD = "gamepass_catalog.db"

# --- Funciones de la App ---
@st.cache_resource
def get_db_connection():
    """
    Crea una conexión a la base de datos local que está en el repositorio.
    No necesita descargar nada.
    """
    # Verifica que el archivo de la base de datos exista en el repositorio.
    if not os.path.exists(NOMBRE_BD):
        st.error(f"Error Crítico: El archivo '{NOMBRE_BD}' no se encontró en el repositorio.")
        st.info("Asegúrate de que 'gamepass_catalog.db' fue subido a GitHub junto con app.py.")
        return None
        
    try:
        conn = sqlite3.connect(NOMBRE_BD, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        st.error(f"Error al conectar con la base de datos: {e}")
        return None

# --- LÓGICA DE BÚSQUEDA HÍBRIDA ---

def intelligent_search_games(conn, search_term):
    """
    Busca juegos usando palabras clave extraídas del término de búsqueda.
    Es rápido, gratuito y eficiente para búsquedas directas.
    """
    # Palabras a ignorar para no generar ruido
    stop_words = set(['juego', 'juegos', 'de', 'un', 'una', 'con', 'para', 'que', 'sea', 'sean', 'el', 'la', 'los', 'las'])
    
    # Limpia y extrae palabras clave de la búsqueda del usuario
    keywords = [word for word in re.split(r'\\s+|,|;', search_term.lower()) if word and word not in stop_words]
    
    if not keywords:
        return []

    # Construye una consulta SQL dinámica
    # Busca cada palabra clave en el título, descripción, géneros y características.
    query_parts = []
    params = []
    for keyword in keywords:
        part = "(title LIKE ? OR description LIKE ? OR genres LIKE ? OR features LIKE ?)"
        query_parts.append(part)
        # Añade el parámetro 4 veces por cada campo
        param = f"%{keyword}%"
        params.extend([param, param, param, param])

    full_query = "SELECT * FROM games WHERE " + " AND ".join(query_parts) + " ORDER BY title"
    
    try:
        cursor = conn.cursor()
        cursor.execute(full_query, tuple(params))
        return cursor.fetchall()
    except sqlite3.Error as e:
        st.error(f"Error al realizar la búsqueda: {e}")
        return []

@st.cache_data(show_spinner="Consultando al Asistente IA...")
def get_ai_recommendations(_conn, user_input):
    """
    Usa la API de OpenAI para obtener recomendaciones basadas en lenguaje natural.
    Es ideal para búsquedas complejas o semánticas.
    """
    try:
        # Lee la clave desde los secretos de Streamlit (que configurarás en el dashboard)
        openai.api_key = st.secrets["openai"]["api_key"]
    except (KeyError, FileNotFoundError):
        st.error("Clave de API de OpenAI no configurada. Por favor, añádela a los secretos (secrets) de tu app en Streamlit Community Cloud.")
        return []

    # Obtiene la lista completa de títulos de la base de datos
    all_titles = [row['title'] for row in _conn.execute("SELECT title FROM games ORDER BY title").fetchall()]
    
    if not all_titles:
        st.warning("La base de datos de juegos está vacía.")
        return []

    # Instrucciones precisas para que la IA devuelva solo lo que necesitamos
    system_prompt = f\"\"\"
    Eres un asistente experto en el catálogo de Xbox Game Pass.
    Tu única tarea es analizar la petición del usuario y devolver una lista de títulos de juegos que coincidan con la petición.
    La lista de juegos disponibles es la siguiente: {json.dumps(all_titles)}.
    SOLAMENTE puedes responder con un objeto JSON válido con una única clave "titles" que contenga una lista de strings con los nombres exactos de los juegos.
    No añadas explicaciones, saludos ni texto adicional. No inventes juegos. Si no encuentras nada, devuelve una lista vacía.
    Ejemplo de respuesta: {{"titles": ["Halo Infinite", "Forza Horizon 5"]}}
    \"\"\"
    
    try:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        
        content = response.choices[0].message.content
        recommended_data = json.loads(content)
        return recommended_data.get("titles", [])

    except Exception as e:
        st.error(f"Error al contactar con la API de OpenAI: {e}")
        return []

def get_games_by_titles(conn, titles):
    """Obtiene los detalles completos de una lista de títulos."""
    if not titles:
        return []
    placeholders = ','.join('?' for _ in titles)
    query = f"SELECT * FROM games WHERE title IN ({placeholders})"
    try:
        cursor = conn.cursor()
        cursor.execute(query, tuple(titles))
        return cursor.fetchall()
    except sqlite3.Error as e:
        st.error(f"Error al recuperar detalles de juegos: {e}")
        return []

# --- Funciones de la Interfaz ---
def display_game_card(game):
    """Muestra la tarjeta de información de un solo juego."""
    col1, col2 = st.columns([1, 3])
    
    with col1:
        if game['image_url'] and "http" in game['image_url']:
            st.image(game['image_url'], width=250)
        st.write(f"**Precio (si no tienes Game Pass):** {game['price']}")
        if game['rating_age'] != "No disponible":
            st.write(f"**Clasificación:** {game['rating_age']}")
            if game['rating_descriptors'] != "No disponible":
                st.caption(f"_{game['rating_descriptors']}_")
    
    with col2:
        st.subheader(game['title'])
        st.link_button("✔️ Incluido en Game Pass - Ver en la Tienda", game['url'], use_container_width=True, type="primary")
        
        with st.expander("Descripción, Géneros y Detalles"):
            st.write(game['description'])
            st.write("---")
            st.write(f"**Géneros:** {game['genres']}")
            st.write(f"**Desarrollador:** {game['developer']}")
            st.write(f"**Editor:** {game['publisher']}")
            st.write(f"**Fecha de Lanzamiento:** {game['release_date']}")

        with st.expander("Plataformas y Funcionalidades"):
            st.write("**Plataformas Compatibles:**")
            st.write(game['platforms'])
            st.write("**Funcionalidades del Juego:**")
            st.write(game['features'])
            if game['accessibility_summary'] != "No disponible":
                st.write("**Resumen de Accesibilidad:**")
                st.write(game['accessibility_summary'])

    st.divider()

# --- Interfaz Principal de la App ---
st.title("🎮 Buscador Inteligente del Catálogo de Game Pass")
st.write("Encuentra juegos en el catálogo de Game Pass usando una búsqueda normal o preguntándole a nuestro asistente con IA.")

conn = get_db_connection()
if not conn:
    st.stop()

total_games = conn.execute("SELECT COUNT(id) FROM games").fetchone()[0]
st.info(f"Catálogo actualizado con **{total_games}** juegos de Game Pass.")

# --- Selector de Modo de Búsqueda ---
search_mode = st.radio(
    "Elige tu modo de búsqueda:",
    ("Búsqueda Normal (Rápida y Gratuita)", "Asistente IA (Para recomendaciones complejas)"),
    horizontal=True,
    help="La Búsqueda Normal es ideal para buscar por nombre, género o características (ej: 'carreras mundo abierto'). El Asistente IA es para preguntas como 'recomiéndame un juego relajante' o 'algo parecido a Fallout'."
)

user_input = st.text_input("¿Qué quieres jugar?", placeholder="Ej: Halo, multijugador cooperativo, un RPG como los de antes...")
results_container = st.container()

if user_input:
    results = []
    if search_mode == "Búsqueda Normal (Rápida y Gratuita)":
        with st.spinner("Buscando en el catálogo..."):
            results = intelligent_search_games(conn, user_input)
    
    elif search_mode == "Asistente IA (Para recomendaciones complejas)":
        recommended_titles = get_ai_recommendations(conn, user_input)
        if recommended_titles:
            results = get_games_by_titles(conn, recommended_titles)
        else:
            if "openai" in st.secrets: # Solo muestra este mensaje si la clave API está configurada
                st.warning("El Asistente IA no pudo encontrar una recomendación para tu búsqueda.")

    with results_container:
        if results:
            st.success(f"¡Se encontraron {len(results)} coincidencias para '{user_input}'!")
            for game in results:
                display_game_card(game)
        else:
            if search_mode == "Búsqueda Normal (Rápida y Gratuita)":
                st.warning(f"No se encontraron resultados para '{user_input}'. Intenta con otros términos o cambia al modo Asistente IA.")
else:
    with results_container:
        st.write("Empieza a escribir para ver los resultados.")

# --- Pie de página ---
st.sidebar.markdown("---")
st.sidebar.header("Sobre este Proyecto")
st.sidebar.info("Esta herramienta usa un scraper para obtener el catálogo de Game Pass y un modelo de IA (OpenAI) para la búsqueda avanzada.")
st.sidebar.markdown("Creado con ❤️ por [@TuUsuarioDeInstagram](https://instagram.com/TuUsuarioDeInstagram)")