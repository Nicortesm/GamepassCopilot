import streamlit as st
import sqlite3
import os
import json
import re
import openai

# --- Configuración de la página ---
st.set_page_config(layout="wide", page_title="Asesor de Game Pass con IA")

# --- Configuración de la App ---
NOMBRE_BD = "gamepass_catalog.db"

# --- Funciones de la App ---
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
        st.error(f"Error en la búsqueda por palabras clave: {e}")
        st.info("Asegúrate de que la base de datos 'gamepass_catalog.db' contiene la columna 'search_keywords'.")
        return []

@st.cache_data(show_spinner="🧠 Consultando al Asesor IA...")
def get_ai_recommendations(_conn, user_input):
    try:
        openai.api_key = st.secrets["openai"]["api_key"]
    except Exception:
        st.error("Clave de API de OpenAI no configurada en los Secrets de Streamlit.")
        return []
    
    all_games_context = _conn.execute(
        "SELECT title, genres, description, features FROM games WHERE genres IS NOT NULL AND genres != 'No disponible'"
    ).fetchall()
    
    if not all_games_context:
        st.warning("No se encontraron juegos con géneros en la base de datos para alimentar a la IA.")
        return []
        
    game_list_for_prompt = [
        {"title": g['title'], "genres": g['genres'], "description_snippet": (g['description'][:150] + "..."), "features": g['features']} 
        for g in all_games_context if g['description'] and g['features']
    ]
    
    json_example_str = json.dumps({"titles": ["Overcooked! 2", "Cooking Simulator"]})
    
    system_prompt = f"""
    Eres un Asesor de Videojuegos experto en Xbox Game Pass. Tu misión es recomendar juegos del catálogo disponible.
    Analiza la petición del usuario y, basándote en el catálogo que te proporciono, recomienda los juegos más adecuados.
    Considera el título, géneros, descripción y características para entender la esencia de cada juego.

    Catálogo disponible: {json.dumps(game_list_for_prompt, indent=2)}

    Reglas de respuesta:
    1. Tu ÚNICA salida debe ser un objeto JSON.
    2. El JSON debe contener una clave: "titles".
    3. El valor de "titles" debe ser una lista de strings con los NOMBRES EXACTOS de los juegos.
    4. No añadas explicaciones. Si no encuentras nada, devuelve una lista vacía: {{"titles": []}}.
    
    Ejemplo de petición: "Juegos de cocina"
    Respuesta EJEMPLO: {json_example_str}
    """
    
    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_input}],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        return json.loads(response.choices[0].message.content).get("titles", [])
    except Exception as e:
        st.error(f"Error al comunicarse con el Asesor de IA: {e}")
        return []

def get_games_by_titles(conn, titles):
    """Obtiene los detalles de los juegos en el orden recomendado por la IA."""
    if not titles: return []
    
    # --- CORRECCIÓN FINAL ---
    # La lista de parámetros debe contener los títulos dos veces:
    # una para la cláusula IN y otra para la cláusula ORDER BY CASE.
    params = tuple(titles) * 2
    
    placeholders = ','.join('?' for _ in titles)
    
    # Construir la parte del ORDER BY dinámicamente
    order_by_clause = "ORDER BY CASE title "
    for i, title in enumerate(titles):
        order_by_clause += f"WHEN ? THEN {i} "
    order_by_clause += "END"
    
    query = f"SELECT * FROM games WHERE title IN ({placeholders}) {order_by_clause}"
    
    return conn.cursor().execute(query, params).fetchall()
    # --- FIN DE LA CORRECCIÓN ---

def display_game_card(game):
    with st.container(border=True):
        col1, col2 = st.columns([1, 3])
        with col1:
            if game['image_url'] and game['image_url'] != "No disponible":
                st.image(game['image_url'])
        with col2:
            st.subheader(game['title'])
            st.link_button("✔️ Ver en la Tienda de Xbox", game['url'], use_container_width=True, type="primary")
            
            genres = game['genres'] if 'genres' in game.keys() and game['genres'] else "No disponible"
            st.caption(f"**Géneros:** {genres}")
            
            description = game['description'] if game['description'] and game['description'] != 'No disponible' else "No hay descripción."
            st.write(description[:250] + "..." if len(description) > 250 else description)
            
            with st.expander("Más detalles"):
                st.write(f"**Desarrollador:** {game['developer']}")
                st.write(f"**Editor:** {game['publisher']}")
                st.write(f"**Fecha de Lanzamiento:** {game['release_date']}")

# --- Interfaz Principal ---
st.title("🎮 Asesor de Game Pass con IA")
conn = get_db_connection()

if conn:
    total_games = conn.execute("SELECT COUNT(id) FROM games").fetchone()[0]
    st.success(f"Catálogo con **{total_games}** juegos. ¡Listo para buscar!")
    
    search_mode = st.radio(
        "Elige tu modo de búsqueda:",
        ("Búsqueda por Palabras Clave", "Asistente con IA (Recomendado)"),
        horizontal=True, index=1,
        help="Palabras Clave: Rápido, busca nombres exactos. Asistente IA: Entiende lo que pides (ej: 'juegos como Overcooked')."
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
        
        if results:
            st.write(f"#### Se encontraron {len(results)} resultados:")
            for game in results:
                display_game_card(game)
        else:
            if user_input:
                st.warning(f"No se encontraron resultados para '{user_input}'. Intenta con otros términos.")
else:
    st.info("Iniciando la aplicación y conectando a la base de datos...")

# --- Pie de página ---
st.sidebar.markdown("---")
st.sidebar.header("Sobre este Proyecto")
st.sidebar.info("Esta herramienta usa un scraper para obtener datos y la API de OpenAI para la búsqueda avanzada.")
st.sidebar.markdown("Creado con ❤️ por [@TuUsuario](https://instagram.com/TuUsuario)")
