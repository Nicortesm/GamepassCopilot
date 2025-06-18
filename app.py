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
        --dark-grey: #1a1a1a;
        --medium-grey: #2e2e2e;
        --light-grey: #3c3c3c;
        --text-color: #f0f0f0;
    }

    /* Fondo de la app */
    .stApp {
        background-color: var(--dark-grey);
        color: var(--text-color);
    }
    
    /* Título principal */
    h1 {
        color: var(--text-color);
        font-size: 2.8rem !important;
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
        max-width: 650px;
        margin: auto;
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
        font-size: 1.05rem;
    }
    
    /* Botones */
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

@st.cache_data(show_spinner="🧠 El Asesor IA está pensando en tu recomendación...")
def get_ai_recommendations(_conn, user_input):
    """Usa un modelo de IA avanzado con un prompt flexible para entender la intención del usuario."""
    try:
        openai.api_key = st.secrets["openai"]["api_key"]
    except:
        st.error("Clave de API de OpenAI no configurada en los Secrets de Streamlit.")
        return []

    # Proporciona un contexto rico a la IA
    all_games_context = _conn.execute(
        "SELECT title, genres, description, features FROM games"
    ).fetchall()
    
    game_list_for_prompt = [
        {
            "title": g['title'],
            "genres": g['genres'] if g['genres'] and g['genres'] != 'No disponible' else 'Varios',
            "description_snippet": (g['description'][:200] + "...") if g['description'] and g['description'] != 'No disponible' else "",
            "features": g['features'] if g['features'] and g['features'] != 'No disponible' else ""
        } 
        for g in all_games_context
    ]
    
    if not game_list_for_prompt:
        st.warning("La base de datos no contiene suficiente información para la IA.")
        return []

    json_example_str = json.dumps({"titles": ["Overcooked! 2", "Golf With Your Friends"]})
    
    system_prompt = f"""
    Eres "Game Pass Guru", un recomendador de videojuegos amigable y experto. Tu única fuente de conocimiento sobre los juegos disponibles es el siguiente catálogo en formato JSON.

    **Tu Misión:**
    1.  **Entiende la intención del usuario:** Lee su petición y comprende qué tipo de experiencia está buscando (ej: "algo relajante", "un reto difícil", "una buena historia", "para jugar con amigos", "juegos que acaben amistades").
    2.  **Analiza el catálogo:** Revisa la lista de juegos que te proporciono. Usa el título, los géneros, la descripción y las características para encontrar las mejores coincidencias.
    3.  **Recomienda los mejores juegos:** Devuelve una lista de los títulos que mejor se ajustan a la intención del usuario.

    **Catálogo de Juegos Disponibles:**
    {json.dumps(game_list_for_prompt, indent=2)}

    **Regla de Oro para tu Respuesta:**
    Tu respuesta DEBE ser únicamente un objeto JSON válido con una sola clave, "titles", que contenga una lista de strings con los NOMBRES EXACTOS de los juegos que recomiendas. No escribas nada más.
    Si no encuentras ninguna buena recomendación, devuelve una lista vacía: {{"titles": []}}

    **Ejemplo de Petición:** "Quiero un juego que me haga reír y que pueda jugar con mi pareja en el sofá"
    **Tu Respuesta Ejemplo (formato exacto):** {json_example_str}
    """
    
    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        return json.loads(response.choices[0].message.content).get("titles", [])
    except Exception as e:
        st.error(f"Ocurrió un error al comunicarse con el Asesor de IA: {e}")
        return []

def get_games_by_titles(conn, titles):
    if not titles: return []
    # Usamos una lista de parámetros simple para la cláusula IN, ya que el orden ya lo da la IA
    placeholders = ','.join('?' for _ in titles)
    query = f"SELECT * FROM games WHERE title IN ({placeholders})"
    
    # Mapeamos los resultados a un diccionario para poder ordenarlos fácilmente
    results_map = {game['title']: game for game in conn.cursor().execute(query, tuple(titles)).fetchall()}
    
    # Devolvemos los juegos en el mismo orden que los recomendó la IA
    ordered_results = [results_map[title] for title in titles if title in results_map]
    return ordered_results

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

# --- INTERFAZ PRINCIPAL ---

st.title("Asesor de Game Pass con IA")
st.markdown("<p style='text-align: center; font-size: 1.2rem; color: #a0a0a0;'>Tu copiloto personal para descubrir tu próximo juego favorito en el catálogo de Xbox.</p>", unsafe_allow_html=True)

conn = get_db_connection()

if conn:
    total_games = conn.execute("SELECT COUNT(id) FROM games").fetchone()[0]
    st.success(f"Catálogo con **{total_games}** juegos. ¡Listo para recibir tus recomendaciones!", icon="🎮")
    
    st.markdown("---")
    
    # Usamos el estado de sesión para manejar el ciclo de búsqueda
    if "user_input" not in st.session_state:
        st.session_state.user_input = ""
    
    def submit_search():
        st.session_state.user_input_submitted = st.session_state.widget_input
    
    user_input = st.text_input(
        "¿Qué te apetece jugar hoy?",
        key="widget_input",
        on_change=submit_search,
        placeholder="Ej: un juego de terror para jugar con amigos, algo como Stardew Valley, un shooter rápido..."
    )
    
    if "user_input_submitted" in st.session_state and st.session_state.user_input_submitted:
        recommended_titles = get_ai_recommendations(conn, st.session_state.user_input_submitted)
        
        if recommended_titles:
            results = get_games_by_titles(conn, recommended_titles)
            st.markdown("---")
            st.header(f"Aquí tienes mis recomendaciones para '{st.session_state.user_input_submitted}':")
            for game in results:
                display_game_card(game)
        else:
            st.warning(f"Lo siento, no encontré una recomendación clara para '{st.session_state.user_input_submitted}'. ¡Intenta describirlo de otra manera!")

else:
    st.info("Iniciando y conectando a la base de datos...")

# --- Pie de página ---
st.sidebar.markdown("---")
st.sidebar.header("Sobre este Proyecto")
st.sidebar.info("Esta herramienta usa IA (GPT-4o mini de OpenAI) para analizar tu petición y recomendarte juegos del catálogo de Game Pass, entendiendo lo que buscas más allá de las palabras clave.")
st.sidebar.markdown("Creado con ❤️ por [@soynicotech](https://www.instagram.com/soynicotech/)")
