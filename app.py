import streamlit as st
import sqlite3
import os
import json
import re
import openai

# --- Configuración de la página ---
st.set_page_config(layout="wide", page_title="Buscador Inteligente Game Pass")

# --- Configuración de la App ---
NOMBRE_BD = "gamepass_catalog.db"

# --- Funciones de la App ---
@st.cache_resource
def get_db_connection():
    """Crea una conexión a la base de datos local que está en el repositorio."""
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

# --- LÓGICA DE BÚSQUEDA HÍBRIDA ---

def intelligent_search_games(conn, search_term):
    """Busca juegos usando palabras clave extraídas del término de búsqueda."""
    stop_words = set(['juego', 'juegos', 'de', 'un', 'una', 'con', 'para', 'que', 'sea', 'sean', 'y', 'o'])
    keywords = [word for word in re.split(r'\\s+|,|;', search_term.lower()) if word and word not in stop_words]
    if not keywords: return []
    query_parts = ["search_keywords LIKE ?"] * len(keywords)
    full_query = "SELECT * FROM games WHERE " + " AND ".join(query_parts) + " ORDER BY title"
    params = [f"%{kw}%" for kw in keywords]
    try:
        return conn.cursor().execute(full_query, tuple(params)).fetchall()
    except sqlite3.Error as e:
        st.error(f"Error en la búsqueda: {e}")
        return []

@st.cache_data(show_spinner="Consultando al Asistente IA...")
def get_ai_recommendations(_conn, user_input):
    """Usa la API de OpenAI para obtener recomendaciones basadas en lenguaje natural."""
    try:
        openai.api_key = st.secrets["openai"]["api_key"]
    except Exception:
        st.error("Clave de API de OpenAI no configurada. Añádela a los secretos de tu app en Streamlit.")
        return []

    all_titles = [row['title'] for row in _conn.execute("SELECT title FROM games ORDER BY title").fetchall()]
    if not all_titles: return []

    # --- CORRECCIÓN AQUÍ ---
    # Definimos el ejemplo JSON por separado para evitar conflictos de comillas
    json_example = {
        "titles": ["Halo Infinite", "Forza Horizon 5"]
    }
    # Usamos json.dumps para convertir el ejemplo a un string formateado
    json_example_str = json.dumps(json_example)

    system_prompt = f\"\"\"
    Eres un asistente experto en Xbox Game Pass. Tu única tarea es analizar la petición del usuario y devolver una lista de títulos de juegos disponibles en este catálogo: {json.dumps(all_titles)}.
    RESPONDE SOLAMENTE con un objeto JSON válido con una única clave "titles" que contenga una lista de strings con los nombres exactos de los juegos.
    No añadas explicaciones, saludos ni texto adicional. No inventes juegos. Si no encuentras nada, devuelve una lista vacía.
    Ejemplo de respuesta: {json_example_str}
    \"\"\"
    # --- FIN DE LA CORRECCIÓN ---
    
    try:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_input}],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        recommended_data = json.loads(response.choices[0].message.content)
        return recommended_data.get("titles", [])
    except Exception as e:
        st.error(f"Error al contactar con la API de OpenAI: {e}")
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
            st.caption(f"Desarrollador: {game['developer']} | Géneros: {game['genres']}")
            st.write(game['description'][:250] + "..." if game['description'] and game['description'] != 'No disponible' else "No hay descripción.")
            with st.expander("Más detalles"):
                st.write(f"**Editor:** {game['publisher']}")
                st.write(f"**Fecha de Lanzamiento:** {game['release_date']}")
                st.write(f"**Plataformas:** {game['platforms']}")
                st.write(f"**Funcionalidades:** {game['features']}")
                st.write(f"**Clasificación:** {game['rating_age']} - _{game['rating_descriptors']}_")

st.title("🎮 Buscador Inteligente del Catálogo de Game Pass")
conn = get_db_connection()
if conn:
    try:
        total_games = conn.execute("SELECT COUNT(id) FROM games").fetchone()[0]
        st.success(f"Catálogo con **{total_games}** juegos. ¡Listo para buscar!")
        search_mode = st.radio(
            "Elige tu modo de búsqueda:",
            ("Búsqueda por Palabras Clave (Rápida y Gratuita)", "Asistente con IA (Para recomendaciones complejas)"),
            horizontal=True,
            help="Usa 'Palabras Clave' para buscar por nombre, género, etc. (ej: 'terror cooperativo'). Usa 'IA' para preguntas como 'recomiéndame algo relajante'."
        )
        user_input = st.text_input("¿Qué quieres jugar?", placeholder="Ej: Halo, carreras mundo abierto, un juego como Stardew Valley...")
        if user_input:
            results = []
            if "Palabras Clave" in search_mode:
                with st.spinner("Buscando en el catálogo..."):
                    results = intelligent_search_games(conn, user_input)
            else:
                recommended_titles = get_ai_recommendations(conn, user_input)
                if recommended_titles:
                    results = get_games_by_titles(conn, recommended_titles)
                elif "openai" in st.secrets:
                    st.warning("El Asistente IA no encontró una recomendación.")
            if results:
                st.write(f"#### Se encontraron {len(results)} resultados para '{user_input}':")
                for game in results:
                    display_game_card(game)
            elif user_input:
                st.warning(f"No se encontraron resultados. Intenta con otros términos o cambia el modo de búsqueda.")
        st.sidebar.info("Esta herramienta usa un scraper para obtener datos y la API de OpenAI para la búsqueda avanzada.")
        st.sidebar.markdown("Creado con ❤️ por [@TuUsuario](https://instagram.com/TuUsuario)")
    except Exception as e:
        st.error(f"Ha ocurrido un error inesperado en la aplicación: {e}")
