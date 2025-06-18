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
        st.error(f"Error en la búsqueda por palabras clave: {e}")
        return []

@st.cache_data(show_spinner="🧠 Consultando al Asistente IA...")
def get_ai_recommendations(_conn, user_input):
    """Usa un modelo de IA avanzado para recomendaciones semánticas."""
    try:
        openai.api_key = st.secrets["openai"]["api_key"]
    except Exception:
        st.error("Clave de API de OpenAI no configurada. Añádela a los secretos (secrets) de tu app en Streamlit.")
        return []

    # MEJORA 1: Darle a la IA el título Y los géneros para más contexto.
    all_games_context = _conn.execute("SELECT title, genres FROM games WHERE genres != 'No disponible'").fetchall()
    game_list_for_prompt = [{"title": g['title'], "genres": g['genres']} for g in all_games_context]
    
    if not game_list_for_prompt:
        st.warning("No hay datos de juegos con géneros para el asistente de IA.")
        return []

    json_example_str = json.dumps({"titles": ["Overcooked! 2", "Stardew Valley"]})
    
    system_prompt = f"""
    Eres un asistente experto y amigable del catálogo Xbox Game Pass. Tu misión es analizar la petición del usuario y recomendar juegos del catálogo disponible.
    El catálogo completo es esta lista de objetos JSON: {json.dumps(game_list_for_prompt)}.

    Tu única tarea es devolver un objeto JSON con una única clave "titles". El valor de esta clave debe ser una lista de strings con los NOMBRES EXACTOS de los juegos que mejor coincidan con la petición del usuario.
    
    - Entiende el sentimiento y la intención: si piden "juegos relajantes", busca en los géneros "Simulación", "Aventura", "Puzzle". Si piden "algo como Overcooked", busca juegos de "Cooperativo", "Cocina", "Acción".
    - No añadas explicaciones, saludos, ni texto adicional. Tu respuesta DEBE ser solo el objeto JSON.
    - No inventes juegos. Si no encuentras una buena coincidencia, devuelve una lista vacía.
    
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
            st.caption(f"**Géneros:** {game['genres']}")
            st.write(game['description'][:250] + "..." if game['description'] and game['description'] != 'No disponible' else "No hay descripción disponible.")
            with st.expander("Más detalles"):
                st.write(f"**Desarrollador:** {game['developer']}")
                st.write(f"**Editor:** {game['publisher']}")
                st.write(f"**Fecha de Lanzamiento:** {game['release_date']}")
                st.write(f"**Plataformas:** {game['platforms']}")
                st.write(f"**Funcionalidades:** {game['features']}")
                st.write(f"**Clasificación:** {game['rating_age']} - _{game['rating_descriptors']}_")

# --- Interfaz Principal de la App ---
st.title("🎮 Buscador Inteligente del Catálogo de Game Pass")

conn = get_db_connection()
if conn:
    total_games = conn.execute("SELECT COUNT(id) FROM games").fetchone()[0]
    st.success(f"Catálogo con **{total_games}** juegos. ¡Listo para buscar!")
    
    search_mode = st.radio(
        "Elige tu modo de búsqueda:",
        ("Búsqueda por Palabras Clave", "Asistente con IA (Recomendado)"),
        horizontal=True,
        index=1, # Por defecto, selecciona el modo IA
        help="La 'Búsqueda por Palabras Clave' es rápida para nombres exactos. El 'Asistente con IA' entiende lenguaje natural y es ideal para recomendaciones (ej: 'juegos de cocina como Overcooked')."
    )
    user_input = st.text_input("¿Qué te apetece jugar?", placeholder="Ej: un juego de terror para jugar con amigos...")
    
    if user_input:
        results = []
        if "Palabras Clave" in search_mode:
            with st.spinner("Buscando por palabras clave..."):
                results = keyword_search(conn, user_input)
        else: # Asistente con IA
            recommended_titles = get_ai_recommendations(conn, user_input)
            if recommended_titles:
                results = get_games_by_titles(conn, recommended_titles)
            elif "openai" in st.secrets:
                st.info("El Asistente IA no encontró una recomendación para esa búsqueda. ¡Prueba otra idea!")
        
        if results:
            st.write(f"#### Se encontraron {len(results)} resultados para '{user_input}':")
            for game in results:
                display_game_card(game)
        elif user_input:
            st.warning(f"No se encontraron resultados para '{user_input}'. Intenta con otros términos.")
else:
    st.info("Iniciando la aplicación y conectando a la base de datos...")

# --- Pie de página ---
st.sidebar.markdown("---")
st.sidebar.header("Sobre este Proyecto")
st.sidebar.info("Esta herramienta usa un scraper para obtener el catálogo de Game Pass y un modelo de IA (OpenAI) para la búsqueda avanzada.")
st.sidebar.markdown("Creado con ❤️ por [@TuUsuario](https://instagram.com/TuUsuario)")
