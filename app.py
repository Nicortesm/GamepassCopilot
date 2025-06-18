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

# --- FUNCIONES DE LA APP (Lógica sin cambios) ---

@st.cache_resource
def get_db_connection():
    if not os.path.exists(NOMBRE_BD):
        st.error(f"Error: '{NOMBRE_BD}' no encontrado.")
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
    query = "SELECT * FROM games WHERE " + " AND ".join(query_parts) + " ORDER BY title"
    params = [f"%{kw}%" for kw in keywords]
    try:
        return conn.cursor().execute(query, tuple(params)).fetchall()
    except:
        return []

@st.cache_data(show_spinner=False) # Spinner personalizado más abajo
def classify_and_extract_keywords(user_input):
    try:
        openai.api_key = st.secrets["openai"]["api_key"]
    except: return {"type": "error", "content": "API Key no configurada."}
    
    system_prompt = f"""
    Tu tarea es analizar la petición de un usuario y clasificarla. Responde en JSON.
    1. Clasifica la petición en una de estas categorías: 'specific_title', 'keyword_based', o 'semantic_recommendation'.
    2. Extrae las palabras clave ("keywords") de la petición.
    Ejemplos:
    - User: "Overcooked" -> {{"type": "specific_title", "keywords": ["overcooked"]}}
    - User: "juegos de terror cooperativos" -> {{"type": "keyword_based", "keywords": ["terror", "cooperativo"]}}
    - User: "un juego para relajarme después del trabajo" -> {{"type": "semantic_recommendation", "keywords": ["relajante", "tranquilo"]}}
    """
    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini", messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_input}],
            response_format={"type": "json_object"}, temperature=0.0
        )
        return json.loads(response.choices[0].message.content)
    except: return {"type": "error", "content": "Error en la API."}

@st.cache_data(show_spinner=False)
def get_semantic_recommendation(_conn, user_input, pre_filtered_games):
    all_games_context = [{"title": g['title'], "genres": g['genres'], "description": g['description'][:150]} for g in pre_filtered_games if g['description']]
    if not all_games_context: return []

    system_prompt = f"""
    Eres un Asesor de Videojuegos experto en Xbox Game Pass. Tu misión es recomendar juegos del catálogo disponible.
    Analiza la petición del usuario y, basándote en esta lista pre-filtrada, recomienda los juegos más adecuados.
    Catálogo: {json.dumps(all_games_context, indent=2)}
    Responde ÚNICAMENTE con un objeto JSON con la clave "titles" y una lista de los nombres exactos de los juegos recomendados.
    Petición Original del Usuario: "{user_input}"
    """
    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini", messages=[{"role": "system", "content": system_prompt}],
            response_format={"type": "json_object"}, temperature=0.2
        )
        return json.loads(response.choices[0].message.content).get("titles", [])
    except: return []

def get_games_by_titles(conn, titles):
    if not titles: return []
    params = tuple(titles) * 2
    placeholders = ','.join('?' for _ in titles)
    order_by_clause = "ORDER BY CASE title " + " ".join(f"WHEN ? THEN {i} " for i, _ in enumerate(titles)) + "END"
    query = f"SELECT * FROM games WHERE title IN ({placeholders}) {order_by_clause}"
    return conn.cursor().execute(query, params).fetchall()

# --- FUNCIONES DE LA INTERFAZ MEJORADAS ---

def display_game_card(game):
    with st.container(border=True):
        col1, col2 = st.columns([0.3, 0.7])
        with col1:
            if game['image_url'] and game['image_url'] != "No disponible":
                st.image(game['image_url'])
        with col2:
            st.subheader(game['title'])
            genres = game['genres'] if 'genres' in game.keys() and game['genres'] and game['genres'] != 'No disponible' else "No especificado"
            st.caption(f"**Géneros:** {genres}")
            description = game['description'] if 'description' in game.keys() and game['description'] and game['description'] != 'No disponible' else "No hay descripción disponible."
            st.write(description[:280] + "..." if len(description) > 280 else description)
            st.link_button("Ver en la Tienda de Xbox", game['url'], use_container_width=True)

def handle_search_request(conn, user_input):
    # ETAPA 1
    with st.spinner("🧠 Analizando tu petición..."):
        analysis = classify_and_extract_keywords(user_input)
    
    search_type = analysis.get("type", "semantic_recommendation")
    keywords = analysis.get("keywords", [])

    with st.expander("🤖 **Análisis del Asesor IA** (Haz clic para ver detalles)"):
        st.write(f"**Tipo de búsqueda detectada:** `{search_type}`")
        st.write(f"**Palabras clave extraídas:** `{', '.join(keywords)}`")

    # ETAPA 2
    if search_type != "semantic_recommendation" and keywords:
        with st.spinner("Buscando por palabras clave..."):
            results = keyword_search(conn, keywords)
        if results:
            st.success("¡Encontré resultados directos con la búsqueda rápida!")
            return results
        st.warning("La búsqueda rápida no encontró nada. Pasando al modo de recomendación profunda...")

    # ETAPA 3
    with st.spinner("🤖 El Asesor IA está buscando las mejores recomendaciones para ti..."):
        full_catalog = conn.execute("SELECT * FROM games").fetchall()
        recommended_titles = get_semantic_recommendation(conn, user_input, full_catalog)
    
    if recommended_titles:
        return get_games_by_titles(conn, recommended_titles)
    
    return []


# --- INTERFAZ PRINCIPAL ---

st.title("🎮 Asesor de Game Pass con IA")

conn = get_db_connection()

if conn:
    total_games = conn.execute("SELECT COUNT(id) FROM games").fetchone()[0]
    st.success(f"¡Catálogo con **{total_games}** juegos listo! Pregúntame lo que quieras.")
    
    if 'show_results' not in st.session_state:
        st.session_state.show_results = False
    if 'user_input' not in st.session_state:
        st.session_state.user_input = ""

    def search_callback():
        st.session_state.show_results = True
    
    user_input = st.text_input(
        "¿Qué te apetece jugar?", 
        key="user_input", 
        on_change=search_callback, 
        placeholder="Ej: un juego relajante para construir bases, algo como Hades..."
    )
    
    if st.session_state.show_results and st.session_state.user_input:
        results = handle_search_request(conn, st.session_state.user_input)
        
        if results:
            st.markdown("---")
            st.header(f"Aquí tienes mis recomendaciones para '{st.session_state.user_input}':")
            for game in results:
                display_game_card(game)
            
            # Botón para nueva búsqueda
            if st.button("✨ Realizar una nueva búsqueda"):
                st.session_state.show_results = False
                st.session_state.user_input = ""
                st.rerun()
        else:
            st.error(f"Lo siento, no pude encontrar ninguna recomendación para '{st.session_state.user_input}'. ¡Inténtalo con otra idea!")
            if st.button("Intentar de nuevo"):
                st.session_state.show_results = False
                st.session_state.user_input = ""
                st.rerun()
else:
    st.info("Iniciando y conectando a la base de datos...")

# --- Pie de página ---
st.sidebar.markdown("---")
st.sidebar.header("Sobre este Proyecto")
st.sidebar.info("Esta herramienta usa un modelo híbrido: primero clasifica tu búsqueda con IA y luego decide si usar una búsqueda local rápida o pedir una recomendación más profunda para optimizar costos y velocidad.")
st.sidebar.markdown("Creado con ❤️ por [@TuUsuario](https://instagram.com/TuUsuario)")
