import streamlit as st
import sqlite3
import os
import json
import re
import openai

# --- Configuración de la Página y Estilos ---
st.set_page_config(
    layout="wide",
    page_title="Asesor de Game Pass con IA",
    page_icon="🎮"
)

# --- ESTILOS CSS PERSONALIZADOS (Look & Feel de Xbox) ---
st.markdown("""
    <style>
    /* Colores principales */
    :root {
        --xbox-green: #107C10;
        --dark-grey: #1e1e1e;
        --light-grey: #3c3c3c;
        --text-color: #ffffff;
    }

    /* Fondo de la app */
    .stApp {
        background-color: var(--dark-grey);
        color: var(--text-color);
    }
    
    /* Título principal */
    h1 {
        color: var(--xbox-green);
        text-shadow: 2px 2px 4px #000000;
    }
    
    /* Contenedores de tarjetas de juegos */
    .st-emotion-cache-1r4qj8v {
        border: 1px solid var(--light-grey);
        border-radius: 10px;
        background-color: #2a2a2a;
    }
    
    /* Botón principal */
    .stButton > button {
        border-color: var(--xbox-green);
        color: var(--xbox-green);
    }
    .stButton > button:hover {
        border-color: var(--text-color);
        color: var(--text-color);
        background-color: var(--xbox-green);
    }

    /* Mensajes informativos */
    .stAlert {
        border-radius: 10px;
    }
    </style>
    """, unsafe_allow_html=True)


# --- CONFIGURACIÓN DE LA APP ---
NOMBRE_BD = "gamepass_catalog.db"

# --- Funciones de la App (Lógica sin cambios) ---

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

# --- MODO 1: BÚSQUEDA POR PALABRAS CLAVE ---
def keyword_search(conn, search_term):
    """Búsqueda rápida y gratuita que busca coincidencias exactas de palabras."""
    stop_words = set(['juego', 'juegos', 'de', 'un', 'una', 'con', 'para', 'que', 'sea', 'sean', 'y', 'o', 'el', 'la', 'los', 'las', 'algo', 'asi', 'llamado'])
    # --- CORRECCIÓN DEL AttributeError ---
    keywords = [word for word in re.split(r'[\s,;]+', search_term.lower()) if word and word not in stop_words]
    # --- FIN DE LA CORRECCIÓN ---
    if not keywords: return []
    
    query_parts = ["search_keywords LIKE ?"] * len(keywords)
    query = "SELECT * FROM games WHERE " + " AND ".join(query_parts) + " ORDER BY title"
    params = [f"%{kw}%" for kw in keywords]
    try:
        return conn.cursor().execute(query, tuple(params)).fetchall()
    except sqlite3.Error as e:
        st.error(f"Error en la búsqueda por palabras clave: {e}. Es posible que la base de datos no se haya generado correctamente.")
        return []

# --- MODO 2: ASISTENTE CON IA ---
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
    - Petición: "Overcooked" -> {{"type": "specific_title", "keywords": ["overcooked"]}}
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

@st.cache_data(show_spinner="🧠 El Asesor IA está refinando los resultados...")
def get_semantic_recommendation(_conn, user_input, pre_filtered_games):
    """ETAPA 2: Se usa solo para recomendaciones semánticas o como respaldo."""
    game_list_for_prompt = [
        {"title": g['title'], "genres": g['genres'], "description": g['description'][:150] if g['description'] else ""}
        for g in pre_filtered_games
    ]
    if not game_list_for_prompt:
        return []

    system_prompt = f"""
    Eres un Asesor de Videojuegos experto en Xbox Game Pass. Tu misión es recomendar juegos del catálogo disponible.
    {json.dumps(game_list_for_prompt, indent=2)}
    Analiza la petición del usuario: "{user_input}" y responde con un JSON con la clave "titles" y una lista de los nombres exactos de los juegos recomendados.
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
    params = tuple(titles) + tuple(titles)
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

    search_type = analysis.get("type", "semantic_recommendation")
    keywords = analysis.get("keywords", [])
    
    with st.expander("🤖 **Análisis del Asesor IA** (Haz clic para ver detalles)"):
        st.write(f"**Tipo de búsqueda detectada:** `{search_type}`")
        st.write(f"**Palabras clave extraídas:** `{', '.join(keywords)}`")

    results = []
    if search_type in ["specific_title", "keyword_based"] and keywords:
        results = keyword_search(conn, " ".join(keywords)) # Usa la búsqueda por palabras clave primero
    
    # Si la búsqueda local no encontró nada, o si la búsqueda es semántica, usamos la IA
    if not results:
        if search_type != "semantic_recommendation":
            st.warning("La búsqueda local no encontró nada. Pasando al Asesor IA para una búsqueda más amplia...")
        
        # Si la búsqueda local falló, pre-filtramos con las keywords para ayudar a la IA
        pre_filtered_results = keyword_search(conn, " ".join(keywords)) if keywords else conn.execute("SELECT * FROM games").fetchall()
        
        if not pre_filtered_results: # Si ni así hay nada, usamos todo el catálogo
            pre_filtered_results = conn.execute("SELECT * FROM games").fetchall()

        recommended_titles = get_semantic_recommendation(conn, user_input, pre_filtered_results)
        if recommended_titles:
            return get_games_by_titles(conn, recommended_titles)
    
    return results

def display_game_card(game):
    with st.container(border=True):
        col1, col2 = st.columns([0.3, 0.7])
        with col1:
            if game['image_url'] and game['image_url'] != "No disponible":
                st.image(game['image_url'])
        with col2:
            st.subheader(game['title'])
            st.link_button("✔️ Ver en la Tienda de Xbox", game['url'], use_container_width=True)
            genres = game['genres'] if 'genres' in game.keys() and game['genres'] else "No especificado"
            st.caption(f"**Géneros:** {genres}")
            description = game['description'] if 'description' in game.keys() and game['description'] else "No hay descripción."
            st.write(description[:280] + "..." if len(description) > 280 else description)
            with st.expander("Más detalles"):
                st.write(f"**Desarrollador:** {game['developer']}")
                st.write(f"**Editor:** {game['publisher']}")
                st.write(f"**Fecha de Lanzamiento:** {game['release_date']}")

# --- Interfaz Principal ---
st.title("Asesor de Game Pass con IA")

conn = get_db_connection()

if 'user_input' not in st.session_state:
    st.session_state.user_input = ""
if 'show_results' not in st.session_state:
    st.session_state.show_results = False

def run_new_search():
    st.session_state.show_results = True

if conn:
    total_games = conn.execute("SELECT COUNT(id) FROM games").fetchone()[0]
    st.success(f"Catálogo con **{total_games}** juegos. ¡Pregúntame lo que quieras!")
    
    st.text_input(
        "¿Qué te apetece jugar?",
        key="user_input",
        on_change=run_new_search,
        placeholder="Ej: Halo, juegos de terror cooperativo, algo para relajarme..."
    )
    
    if st.session_state.show_results and st.session_state.user_input:
        results = handle_search_request(conn, st.session_state.user_input)
        
        if results:
            st.markdown("---")
            st.header(f"Aquí tienes mis recomendaciones para '{st.session_state.user_input}':")
            for game in results:
                display_game_card(game)
        else:
            st.warning(f"Lo sentimos, no se encontraron resultados para '{st.session_state.user_input}'. ¡Intenta con otra idea!")

        if st.button("✨ Realizar una nueva búsqueda"):
            st.session_state.user_input = ""
            st.session_state.show_results = False
            st.rerun()
else:
    st.info("Iniciando y conectando a la base de datos...")

st.sidebar.markdown("---")
st.sidebar.header("Sobre este Proyecto")
st.sidebar.info("Esta herramienta usa un modelo híbrido: primero clasifica tu búsqueda con IA y luego decide si usar una búsqueda local rápida o pedir una recomendación más profunda para optimizar costos y velocidad.")
st.sidebar.markdown("Creado con ❤️ por [@soynicotech](https://www.instagram.com/soynicotech/)")
