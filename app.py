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

def keyword_search(conn, search_term):
    """Búsqueda rápida y gratuita por palabras clave."""
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
    """Usa un modelo de IA avanzado para recomendaciones semánticas."""
    try:
        openai.api_key = st.secrets["openai"]["api_key"]
    except:
        st.error("Clave de API de OpenAI no configurada en los Secrets de Streamlit.")
        return []
    
    # MEJORA 1: Darle a la IA el título Y los géneros para más contexto.
    all_games_context = _conn.execute("SELECT title, genres FROM games WHERE genres IS NOT NULL AND genres != 'No disponible'").fetchall()
    if not all_games_context:
        st.warning("No hay datos de juegos con géneros para el asistente de IA. Es posible que el scraper no haya extraído esta información.")
        return []
        
    game_list_for_prompt = [{"title": g['title'], "genres": g['genres']} for g in all_games_context]
    json_example_str = json.dumps({"titles": ["Overcooked! 2", "Stardew Valley"]})
    
    system_prompt = f"""
    Eres un asistente experto en Xbox Game Pass. Tu tarea es analizar la petición del usuario y recomendar juegos del catálogo disponible: {json.dumps(game_list_for_prompt)}.
    RESPONDE SOLAMENTE con un objeto JSON con una única clave "titles" que contenga una lista de strings con los NOMBRES EXACTOS de los juegos.
    No añadas explicaciones. No inventes juegos. Si no encuentras nada, devuelve una lista vacía.
    Ejemplo de respuesta si el usuario pide "juegos de cocina cooperativos": {json_example_str}
    """
    
    try:
        # MEJORA 2: Usar un modelo más inteligente y eficiente.
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ],
            response_format={"type": "json_object"},
            temperature=0.1, # Muy bajo para respuestas predecibles y basadas en hechos
        )
        recommended_data = json.loads(response.choices[0].message.content)
        return recommended_data.get("titles", [])
    except Exception as e:
        st.error(f"Ocurrió un error al comunicarse con el Asistente de IA: {e}")
        return []

def get_games_by_titles(conn, titles):
    """Obtiene los detalles completos de una lista de títulos."""
    if not titles: return []
    placeholders = ','.join('?' for _ in titles)
    query = f"SELECT * FROM games WHERE title IN ({placeholders})"
    return conn.cursor().execute(query, tuple(titles)).fetchall()

def display_game_card(game):
    """Muestra la tarjeta de información de un solo juego."""
    with st.container(border=True):
        col1, col2 = st.columns([1, 3])
        with col1:
            if game['image_url'] and game['image_url'] != "No disponible":
                st.image(game['image_url'])
        with col2:
            st.subheader(game['title'])
            st.link_button("✔️ Ver en la Tienda de Xbox (Incluido en Game Pass)", game['url'], use_container_width=True, type="primary")
            st.caption(f"**Géneros:** {game.get('genres', 'No disponible')}")
            st.write(game['description'][:250] + "..." if game['description'] and game['description'] != 'No disponible' else "No hay descripción disponible.")
            with st.expander("Más detalles"):
                st.write(f"**Desarrollador:** {game['developer']}")
                st.write(f"**Editor:** {game['publisher']}")
                st.write(f"**Fecha de Lanzamiento:** {game['release_date']}")
                st.write(f"**Plataformas:** {game['platforms']}")
                st.write(f"**Funcionalidades:** {game['features']}")
                st.write(f"**Clasificación:** {game['rating_age']} - _{game['rating_descriptors']}_")

# --- Interfaz Principal ---
st.title("🎮 Buscador Inteligente del Catálogo de Game Pass")
conn = get_db_connection()

if conn:
    total_games = conn.execute("SELECT COUNT(id) FROM games").fetchone()[0]
    st.success(f"Catálogo con **{total_games}** juegos. ¡Listo para buscar!")
    
    search_mode = st.radio(
        "Elige tu modo de búsqueda:",
        ("Búsqueda por Palabras Clave", "Asistente con IA (Recomendado)"),
        horizontal=True, index=1,
        help="Palabras Clave: Rápido, busca términos exactos. Asistente IA: Entiende lenguaje natural (ej: 'juegos como Overcooked')."
    )
    
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
            elif "openai" in st.secrets:
                st.warning("El Asistente IA no encontró una recomendación.")
        
        if results:
            st.write(f"#### Se encontraron {len(results)} resultados:")
            for game in results:
                display_game_card(game)
        elif user_input:
            st.warning(f"No se encontraron resultados para '{user_input}'. Intenta con otros términos o cambia el modo de búsqueda.")
else:
    st.info("Iniciando la aplicación y conectando a la base de datos...")

# --- Pie de página ---
st.sidebar.markdown("---")
st.sidebar.header("Sobre este Proyecto")
st.sidebar.info("Esta herramienta usa un scraper para obtener datos y la API de OpenAI para la búsqueda avanzada.")
st.sidebar.markdown("Creado con ❤️ por [@TuUsuario](https://instagram.com/TuUsuario)")
