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
    """Búsqueda por palabras clave en las columnas existentes."""
    stop_words = set(['juego', 'juegos', 'de', 'un', 'una', 'con', 'para', 'que', 'sea', 'sean', 'y', 'o', 'el', 'la', 'los', 'las', 'algo', 'asi', 'llamado'])
    keywords = [word for word in re.split(r'[\\s,;]+', search_term.lower()) if word and word not in stop_words]
    if not keywords: return []
    
    # --- CORRECCIÓN #1: Buscar en las columnas que sí existen ---
    query_parts = []
    params = []
    for kw in keywords:
        query_parts.append("(title LIKE ? OR description LIKE ? OR genres LIKE ?)")
        params.extend([f"%{kw}%", f"%{kw}%", f"%{kw}%"])
        
    full_query = "SELECT * FROM games WHERE " + " AND ".join(query_parts) + " ORDER BY title"
    
    try:
        return conn.cursor().execute(full_query, tuple(params)).fetchall()
    except sqlite3.Error as e:
        st.error(f"Error en la búsqueda: {e}")
        return []

@st.cache_data(show_spinner="🧠 Consultando al Asesor IA...")
def get_ai_recommendations(_conn, user_input):
    """Usa un modelo de IA avanzado con el contexto que sí tenemos."""
    try:
        openai.api_key = st.secrets["openai"]["api_key"]
    except Exception:
        st.error("Clave de API de OpenAI no configurada en los Secrets de Streamlit.")
        return []

    # --- CORRECCIÓN #2: Usar descripción y características como contexto para la IA ---
    all_games_context = _conn.execute(
        "SELECT title, description, genres, features FROM games"
    ).fetchall()
    
    game_list_for_prompt = [
        {
            "title": g['title'],
            "genres": g['genres'] if g['genres'] and g['genres'] != 'No disponible' else 'Varios',
            "description_snippet": (g['description'][:150] + "...") if g['description'] and g['description'] != 'No disponible' else "",
            "features": g['features'] if g['features'] and g['features'] != 'No disponible' else ""
        } 
        for g in all_games_context
    ]
    
    if not game_list_for_prompt:
        st.warning("La base de datos parece estar vacía.")
        return []

    json_example_str = json.dumps({"titles": ["Overcooked! 2", "Cooking Simulator"]})
    
    system_prompt = f"""
    Eres un Asesor de Videojuegos experto en el catálogo de Xbox Game Pass. Tu misión es actuar como un recomendador inteligente y amigable.
    Analiza la petición del usuario y, basándote en el catálogo completo que te proporciono, recomienda los juegos más adecuados.
    Considera el título, los géneros, la descripción y las características para entender la esencia de cada juego.

    Catálogo disponible:
    {json.dumps(game_list_for_prompt, indent=2)}

    Reglas de respuesta:
    1.  Tu ÚNICA salida debe ser un objeto JSON.
    2.  El objeto JSON debe contener una única clave: "titles".
    3.  El valor de "titles" debe ser una lista de strings, con los NOMBRES EXACTOS de los juegos del catálogo.
    4.  No incluyas explicaciones ni texto adicional. Solo el JSON.
    5.  Si no encuentras ninguna coincidencia buena, devuelve una lista vacía: {{"titles": []}}.

    Ejemplo de petición de usuario: "Juegos de cocina"
    Tu respuesta EJEMPLO debería ser: {json_example_str}
    """
    
    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_input}],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        recommended_data = json.loads(response.choices[0].message.content)
        return recommended_data.get("titles", [])
    except Exception as e:
        st.error(f"Ocurrió un error al comunicarse con el Asesor de IA: {e}")
        return []

def get_games_by_titles(conn, titles):
    if not titles: return []
    placeholders = ','.join('?' for _ in titles)
    query = f"SELECT * FROM games WHERE title IN ({placeholders}) ORDER BY CASE title "
    for i, title in enumerate(titles):
        query += f"WHEN ? THEN {i} "
    query += "END"
    params = tuple(titles)
    return conn.cursor().execute(query, params).fetchall()

def display_game_card(game):
    with st.container(border=True):
        col1, col2 = st.columns([1, 3])
        with col1:
            if game['image_url'] and game['image_url'] != "No disponible":
                st.image(game['image_url'])
        with col2:
            st.subheader(game['title'])
            st.link_button("✔️ Ver en la Tienda de Xbox", game['url'], use_container_width=True, type="primary")
            
            # Acceso seguro a la columna 'genres'
            genres = game['genres'] if 'genres' in game.keys() and game['genres'] else "No disponible"
            st.caption(f"**Géneros:** {genres}")
            
            description = game['description'] if game['description'] and game['description'] != 'No disponible' else "No hay descripción disponible."
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
        help="Palabras Clave: Rápido, busca nombres exactos (ej: 'Halo'). Asistente IA: Entiende lo que pides (ej: 'juegos de cocina como Overcooked')."
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
            st.warning(f"No se encontraron resultados para '{user_input}'. Intenta con otros términos.")
else:
    st.info("Iniciando la aplicación y conectando a la base de datos...")

# --- Pie de página ---
st.sidebar.markdown("---")
st.sidebar.header("Sobre este Proyecto")
st.sidebar.info("Esta herramienta usa un scraper para obtener datos y la API de OpenAI para la búsqueda avanzada.")
st.sidebar.markdown("Creado con ❤️ por [@TuUsuario](https://instagram.com/TuUsuario)")
