import streamlit as st
from supabase import create_client, Client
from openai import OpenAI
import os
from dotenv import load_dotenv
from pypdf import PdfReader
import json

# Cargar claves
load_dotenv('test.env')

# Conexiones
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(url, key)

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# --- FUNCIÓN MEJORADA Y LIMPIA (Anti-Error \u0000) ---
def procesar_pdf(uploaded_file):
    try:
        # 1. Extraer texto de TODAS las páginas
        reader = PdfReader(uploaded_file)
        texto_completo = ""
        for page in reader.pages:
            texto_extraido = page.extract_text()
            if texto_extraido:
                texto_completo += texto_extraido + "\n"
        
        # --- LIMPIEZA CRÍTICA (ESTO ARREGLA TU ERROR) ---
        # Eliminamos los bytes nulos que rompen la base de datos
        texto_completo = texto_completo.replace("\x00", "")
        # ------------------------------------------------

        # Advertencia si el PDF es una imagen escaneada
        if len(texto_completo) < 50:
            return None, None 

        # 2. Prompt para la IA
        prompt = f"""
        Eres un experto inmobiliario. Analiza esta ficha técnica completa y extrae los datos clave.
        
        TEXTO DEL DOCUMENTO:
        {texto_completo}
        
        INSTRUCCIONES:
        Responde SOLO un objeto JSON válido con esta estructura exacta:
        {{
            "titulo": "Un título corto y comercial (Ej: Casa Moderna en Zona Norte)",
            "precio": "El precio encontrado (Ej: $2,500,000)",
            "ubicacion": "La ubicación o zona aproximada",
            "resumen": "Redacta una descripción vendedora y atractiva de 3 líneas basada en las características reales."
        }}
        """
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        
        contenido = response.choices[0].message.content
        datos_json = json.loads(contenido)
        return texto_completo, datos_json

    except Exception as e:
        print(f"Error leyendo PDF: {e}")
        return None, None

# --- INTERFAZ GRÁFICA ---
st.set_page_config(page_title="InmoBot Admin", page_icon="🏢")
st.title("🏢 InmoBot - Carga Inteligente")
st.markdown("Sube tu **Ficha Técnica (PDF)**. Ahora leo el documento completo.")

# --- SIDEBAR ---
with st.sidebar:
    st.header("👤 Tu Cuenta")
    agente_id = st.number_input("ID de Agente", value=1, step=1)

# --- PESTAÑAS ---
tab1, tab2 = st.tabs(["📄 Subir PDF", "📋 Ver Mis Propiedades"])

with tab1:
    archivo_pdf = st.file_uploader("Arrastra tu PDF aquí", type="pdf")
    
    if archivo_pdf is not None:
        with st.spinner("🤖 Leyendo documento completo..."):
            texto_pdf, datos_ia = procesar_pdf(archivo_pdf)
            
            if datos_ia:
                st.success("¡Lectura exitosa!")
                
                with st.form("form_auto", clear_on_submit=True):
                    col1, col2 = st.columns(2)
                    with col1:
                        nuevo_titulo = st.text_input("Título", value=datos_ia.get("titulo", ""))
                        nuevo_precio = st.text_input("Precio", value=datos_ia.get("precio", ""))
                    with col2:
                        nueva_ubicacion = st.text_input("Ubicación", value=datos_ia.get("ubicacion", ""))
                        # Campo para foto manual (importante llenarlo para que salgan las imagenes)
                        foto_manual = st.text_input("Link Foto (Opcional)", placeholder="Pega URL de imagen...")
                    
                    nuevo_resumen = st.text_area("Descripción/Resumen", value=datos_ia.get("resumen", ""), height=100)
                    
                    submitted = st.form_submit_button("💾 Guardar Propiedad")
                    
                    if submitted:
                        payload = {
                            "agente_id": agente_id,
                            "titulo": nuevo_titulo,
                            "precio": nuevo_precio,
                            "ubicacion": nueva_ubicacion,
                            "descripcion": nuevo_resumen,
                            "foto_url": foto_manual,
                            "ficha_texto": texto_pdf
                        }
                        supabase.table('propiedades').insert(payload).execute()
                        st.toast("✅ ¡Propiedad guardada correctamente!")
            elif texto_pdf is None:
                st.error("⚠️ Error: El PDF parece ser una imagen escaneada o está vacío. Intenta convertirlo a texto primero.")
            else:
                st.error("No pude estructurar los datos, pero puedes llenarlos manual.")

with tab2:
    if st.button("🔄 Refrescar"):
        st.rerun()
    data = supabase.table('propiedades').select("*").eq('agente_id', agente_id).execute().data
    for p in data:
        with st.expander(f"{p['titulo']} ({p['precio']})"):
            st.write(p['descripcion'])
            if p.get('foto_url'):
                st.image(p['foto_url'], width=200)
            if st.button("Borrar", key=p['id']):
                supabase.table('propiedades').delete().eq('id', p['id']).execute()
                st.rerun()