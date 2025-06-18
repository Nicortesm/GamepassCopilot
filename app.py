import streamlit as st
import sqlite3
import os
import json
import re
import openai

# --- Configuración ---
st.set_page_config(layout="wide", page_title="Asesor de Game Pass con IA")
NOMBRE_BD = "gamepass_catalog.db"

# --- Conexión a la Base de Datos ---
@st.cache_resource
def get_db_connection():
    if not os.path.exists(NOMBRE_BD):
        st.error(f"Error: '{NOMBRE_BD}' no encontrado. Asegúrate de que está en el repositorio.")
        return None
    try:
        conn = sqlite3.connect(NOMBRE_BD, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        st.error(f"Error al conectar con la base de datos: {e}")
        return None

# --- Funciones de Lógica y Búsqueda ---

def keyword_search(conn, keywords):
    """Realiza una búsqueda SQL con una lista de palabras clave."""
    if not keywords: return []
    query_parts = ["search_keywords LIKE ?"] * len(keywords)
    query = "SELECT * FROM games WHERE " + " AND ".join(query_parts) + " ORDER BY title"
    params = [f"%{kw}%" for kw in keywords]
    try:
        return conn.cursor().execute(query, tuple(params)).fetchall()
    except sqlite3.Error:
        return []

@st.cache_data(show_spinner="🧠 Analizando tu petición...")
def classify_and_extract_keywords(user_input):
    """ETAPA 1: Usa IA para clasificar la consulta y extraer palabras clave."""
    try:
        openai.api_key = st.secrets["openai"]["api_key"]
    except:
        return {"type": "error", "content": "API Key no configurada."}

    system_prompt = f"""
    Tu tarea es analizar la petición de un usuario y clasificarla. Responde en JSON.
    1. Clasifica la petición en una de estas categorías: 'specific_title', 'keyword_based', o 'semantic_recommendation'.
    2. Extrae las palabras clave ("keywords") de la petición.
    Ejemplos:
    - Petición: "Halo" -> {{"type": "specific_title", "keywords": ["halo"]}}
    - Petición: "juegos de terror cooperativos" -> {{"type": "keyword_based", "keywords": ["terror", "cooperativo"]}}
    - Petición: "un juego para relajarme después del trabajo" -> {{"type": "semantic_recommendation", "keywords": ["relajante", "tranquilo"]}}
    """
    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_input}],
            response_format={"type": "json_object"}, temperature=0.0
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        return {"type": "error", "content": f"Error en la API: {e}"}

@st.cache_data(show_spinner="🧠 Pidiendo una recomendación personalizada al Asesor IA...")
def get_semantic_recommendation(_conn, user_input, filtered_list=None):
    """ETAPA 2: Se usa solo para recomendaciones semánticas o como respaldo."""
    if filtered_list:
        game_list_for_prompt = [{"title": g['title'], "genres": g['genres'], "description": g['description'][:150]} for g in filtered_list]
        prompt_context = f"Un asistente ya ha pre-filtrado esta lista para ti. Elige de esta lista CORTA:"
    else:
        all_games = _conn.execute("SELECT title, genres, description FROM games").fetchall()
        game_list_for_prompt = [{"title": g['title'], "genres": g['genres'], "description": g['description'][:150]} for g in all_games]
        prompt_context = "Usa el catálogo completo que te proporciono:"

    system_prompt = f"""
    Eres un Asesor de Videojuegos experto en Xbox Game Pass. Tu misión es recomendar juegos.
    {prompt_context}
    Catálogo: {json.dumps(game_list_for_prompt, indent=2)}
    Analiza la petición del usuario y responde con un JSON que contenga la clave "titles" y una lista de los nombres exactos de los juegos recomendados.
    Petición Original del Usuario: "{user_input}"
    """
    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": system_prompt}],
            response_format={"type": "json_object"}, temperature=0.2
        )
        return json.loads(response.choices[0].message.content).get("titles", [])
    except Exception as e:
        st.error(f"Error al refinar la búsqueda con IA: {e}")
        return []

def get_games_by_titles(conn, titles):
    if not titles: return []
    params = tuple(titles) * 2
    placeholders = ','.join('?' for _ in titles)
    order_by_clause = "ORDER BY CASE title " + " ".join(f"WHEN ? THEN {i} " for i, _ in enumerate(titles)) + "END"
    query = f"SELECT * FROM games WHERE title IN ({placeholders}) {order_by_clause}"
    return conn.cursor().execute(query, params).fetchall()

def handle_search_request(conn, user_input):
    """Orquesta el flujo de búsqueda híbrido y avanzado."""
    analysis = classify_and_extract_keywords(user_input)
    
    if analysis.get("type") == "error":
        st.error(analysis.get("content"))
        return []

    search_type = analysis.get("type")
    keywords = analysis.get("keywords", [])
    
    st.info(f"Análisis IA: Tipo de búsqueda detectada: **{search_type}**. Palabras clave: **{', '.join(keywords)}**")

    if search_type in ["specific_title", "keyword_based"]:
        results = keyword_search(conn, keywords)
        if results:
            st.success("¡Búsqueda local exitosa! Mostrando resultados directos.")
            return results
        else:
            st.warning("La búsqueda local no encontró nada. Pasando al Asesor IA para una búsqueda más amplia...")
    
    # Si la búsqueda local falla o es semántica, usar el Asesor IA
    recommended_titles = get_semantic_recommendation(conn, user_input)
    if recommended_titles:
        return get_games_by_titles(conn, recommended_titles)
    
    return []

def display_game_card(game):
    with st.container(border=True):
        col1, col2 = st.columns([1, 3])
        with col1:
            if game['image_url'] and game['image_url'] != "No disponible": st.image(game['image_url'])
        with col2:
            st.subheader(game['title'])
            st.link_button("✔️ Ver en la Tienda de Xbox", game['url'], use_container_width=True, type="primary")
            genres = game['genres'] if 'genres' in game.keys() and game['genres'] else "No especificado"
            st.caption(f"**Géneros:** {genres}")
            description = game['description'] if 'description' in game.keys() and game['description'] else "No hay descripción."
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
    st.success(f"Catálogo con **{total_games}** juegos. ¡Pregúntame lo que quieras!")
    
    user_input = st.text_input("¿Qué te apetece jugar?", placeholder="Ej: Halo, juegos de terror cooperativo, algo para relajarme...")
    
    if user_input:
        results = handle_search_request(conn, user_input)
        
        if results:
            st.write(f"---")
            for game in results:
                display_game_card(game)
        else:
            st.warning(f"Lo sentimos, no se encontraron resultados para '{user_input}'. ¡Intenta con otra idea!")
else:
    st.info("Iniciando y conectando a la base de datos...")

st.sidebar.markdown("---")
st.sidebar.header("Sobre este Proyecto")
st.sidebar.info("Esta herramienta usa un modelo híbrido: primero clasifica tu búsqueda con IA y luego decide si usar una búsqueda local rápida o pedir una recomendación más profunda para optimizar costos y velocidad.")
st.sidebar.markdown("Creado con ❤️ por [@TuUsuario](https://instagram.com/TuUsuario)")
