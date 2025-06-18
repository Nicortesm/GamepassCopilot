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

# --- ESTILOS CSS PERSONALIZADOS (Look & Feel Gamer) ---
st.markdown("""
    <style>
    /* Colores principales */
    :root {
        --xbox-green: #107C10;
        --dark-grey: #1a1a1a; /* Un negro más suave */
        --medium-grey: #2e2e2e;
        --light-grey: #3c3c3c;
        --text-color: #f0f0f0; /* Un blanco menos brillante */
    }

    /* Fondo de la app */
    .stApp {
        background-color: var(--dark-grey);
        color: var(--text-color);
    }
    
    /* Título principal */
    h1 {
        color: var(--text-color); /* Blanco para el título principal */
        font-size: 3rem !important; /* Más grande */
        font-weight: 700;
        text-align: center;
        padding-top: 1rem;
        padding-bottom: 0.5rem;
    }
    
    /* Subtítulo debajo del título principal */
    .st-emotion-cache-16idsys p {
        text-align: center;
        font-size: 1.1rem;
        color: #a0a0a0;
    }

    /* Contenedores de tarjetas de juegos */
    .st-emotion-cache-1r4qj8v {
        border: 1px solid var(--light-grey);
        border-radius: 12px;
        background-color: var(--medium-grey);
        padding: 1.5rem !important;
        transition: transform 0.2s ease-in-out, box-shadow 0.2s ease-in-out;
    }
    .st-emotion-cache-1r4qj8v:hover {
        transform: translateY(-5px);
        box-shadow: 0 8px 30px rgba(0, 255, 80, 0.1);
    }
    
    /* Subtítulos de las tarjetas */
    h3 {
        color: var(--xbox-green) !important;
        font-weight: 600;
    }
    
    /* Texto general */
    .st-emotion-cache-1629p8f, .st-emotion-cache-1y4p8pa, p {
        font-size: 1.05rem; /* Letra un poco más grande */
    }
    
    /* Botón "Nueva Búsqueda" */
    .stButton > button {
        font-weight: 600;
        border-radius: 8px;
    }
    </style>
    """, unsafe_allow_html=True)


# --- CONFIGURACIÓN DE LA APP ---
NOMBRE_BD = "gamepass_catalog.db"

# --- FUNCIONES DE LA APP ---
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
    keywords = [word for word in re.split(r'[\s,;]+', search_term.lower()) if word and word not in stop_words]
    if not keywords: return []
    query_parts = ["search_keywords LIKE ?"] * len(keywords)
    query = "SELECT * FROM games WHERE " + " AND ".join(query_parts) + " ORDER BY title"
    params = [f"%{kw}%" for kw in keywords]
    try:
        return conn.cursor().execute(query, tuple(params)).fetchall()
    except sqlite3.Error:
        return []

@st.cache_data(show_spinner="🧠 Analizando tu petición...")
def get_ai_recommendations(_conn, user_input):
    try:
        openai.api_key = st.secrets["openai"]["api_key"]
    except:
        return {"error": "API Key no configurada."}

    all_games_context = _conn.execute("SELECT title, genres, description, features FROM games").fetchall()
    game_list_for_prompt = [{"title": g['title'], "genres": g['genres'], "description_snippet": g['description'][:150] if g['description'] else ""} for g in all_games_context]
    
    system_prompt = f"""
    Eres un Asesor de Videojuegos experto en Xbox Game Pass. Tu misión es actuar como un recomendador inteligente y amigable.
    Analiza la petición del usuario y, basándote en el catálogo completo que te proporciono, recomienda los juegos más adecuados.
    Considera el título, los géneros y la descripción para entender la esencia de cada juego.

    Catálogo disponible: {json.dumps(game_list_for_prompt, indent=2)}

    Reglas de respuesta:
    1. Tu ÚNICA salida debe ser un objeto JSON.
    2. El objeto JSON debe contener una única clave: "titles".
    3. El valor de "titles" debe ser una lista de strings con los NOMBRES EXACTOS de los juegos del catálogo.
    4. No añadas explicaciones. No inventes juegos. Si no encuentras nada, devuelve una lista vacía: {{"titles": []}}.
    """
    
    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini", messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_input}],
            response_format={"type": "json_object"}, temperature=0.2
        )
        return json.loads(response.choices[0].message.content).get("titles", [])
    except Exception as e:
        return {"error": f"Error en la API: {e}"}

def get_games_by_titles(conn, titles):
    if not titles: return []
    params = tuple(titles) + tuple(titles)
    placeholders = ','.join('?' for _ in titles)
    order_by_clause = "ORDER BY CASE title " + " ".join(f"WHEN ? THEN {i} " for i, _ in enumerate(titles)) + "END"
    query = f"SELECT * FROM games WHERE title IN ({placeholders}) {order_by_clause}"
    return conn.cursor().execute(query, params).fetchall()

def display_game_card(game):
    with st.container(border=True):
        col1, col2 = st.columns([0.3, 0.7])
        with col1:
            if game['image_url'] and game['image_url'] != "No disponible":
                st.image(game['image_url'])
        with col2:
            st.subheader(game['title'])
            genres = game['genres'] if 'genres' in game.keys() and game['genres'] else "No especificado"
            st.caption(f"**Géneros:** {genres}")
            description = game['description'] if 'description' in game.keys() and game['description'] else "No hay descripción."
            st.write(description[:280] + "..." if len(description) > 280 else description)
            st.link_button("Ver en la Tienda de Xbox", game['url'], use_container_width=True)

# --- INTERFAZ PRINCIPAL ---

st.title("Asesor de Game Pass con IA")
st.markdown("<p style='text-align: center; font-size: 1.2rem; color: #a0a0a0;'>Tu copiloto personal para descubrir tu próximo juego favorito en el catálogo de Xbox.</p>", unsafe_allow_html=True)

conn = get_db_connection()

if conn:
    total_games = conn.execute("SELECT COUNT(id) FROM games").fetchone()[0]
    st.success(f"Catálogo con **{total_games}** juegos. ¡Listo para recibir tus recomendaciones!", icon="🎮")
    
    st.markdown("---")
    
    user_input = st.text_input("¿Qué te apetece jugar hoy?", placeholder="Ej: un juego de terror para jugar con amigos, algo como Stardew Valley, un shooter rápido...")
    
    if user_input:
        with st.spinner("Buscando las mejores recomendaciones para ti..."):
            # En esta versión, siempre usamos la IA para la mejor experiencia
            recommended_titles = get_ai_recommendations(conn, user_input)
            if isinstance(recommended_titles, dict) and "error" in recommended_titles:
                st.error(f"Error del Asistente: {recommended_titles['content']}")
                results = []
            elif recommended_titles:
                results = get_games_by_titles(conn, recommended_titles)
            else:
                results = []
        
        if results:
            st.markdown("---")
            st.header(f"Aquí tienes mis recomendaciones para '{user_input}':")
            for game in results:
                display_game_card(game)
        else:
            st.warning(f"Lo siento, no encontré una recomendación clara para '{user_input}'. ¡Intenta describirlo de otra manera!")

    st.markdown("---")
    if st.button("✨ Empezar una Nueva Búsqueda"):
        # Esto no es necesario con el enfoque actual, pero lo dejamos por si se quiere añadir funcionalidad
        st.info("Simplemente escribe una nueva búsqueda arriba para empezar de nuevo.")

else:
    st.info("Iniciando y conectando a la base de datos...")

# --- Pie de página ---
st.sidebar.markdown("---")
st.sidebar.header("Sobre este Proyecto")
st.sidebar.info("Esta herramienta usa IA (GPT-4o mini de OpenAI) para analizar tu petición y recomendarte juegos del catálogo de Game Pass, entendiendo lo que buscas más allá de las palabras clave.")
st.sidebar.markdown("Creado con ❤️ por [@soynicotech](https://www.instagram.com/soynicotech/)")
