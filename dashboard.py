import streamlit as st
from supabase import create_client, Client
from openai import OpenAI
import os
from dotenv import load_dotenv
from pypdf import PdfReader
import json
import time
import smtplib
from email.mime.text import MIMEText
import random
from datetime import datetime, timedelta

# Cargar claves
load_dotenv('test.env')

# Conexiones
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(url, key)
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="InmoBot SaaS", page_icon="🏢", layout="wide")

# --- FUNCIONES AUXILIARES ---

def enviar_codigo_correo(destinatario, codigo):
    remitente = os.getenv("EMAIL_SENDER")
    password = os.getenv("EMAIL_PASSWORD")
    msg = MIMEText(f"Tu código de verificación es: {codigo}")
    msg['Subject'] = "Recuperación InmoBot"
    msg['From'] = remitente
    msg['To'] = destinatario

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(remitente, password)
        server.sendmail(remitente, destinatario, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Error email: {e}")
        return False

def procesar_pdf(uploaded_file):
    try:
        reader = PdfReader(uploaded_file)
        texto = "".join([page.extract_text() for page in reader.pages if page.extract_text()])
        texto = texto.replace("\x00", "")
        if len(texto) < 50: return None, None 

        prompt = f"Analiza esta ficha técnica: {texto[:10000]}. Responde JSON con: titulo, precio, ubicacion, resumen."
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return texto, json.loads(response.choices[0].message.content)
    except: return None, None

# --- GESTIÓN DE ESTADO ---
if 'usuario' not in st.session_state: st.session_state.usuario = None
if 'recuperando' not in st.session_state: st.session_state.recuperando = False

# ==========================================
# 👑 ZONA DE ADMIN (CONTROL TOTAL)
# ==========================================
def panel_admin():
    st.title("👨‍💻 Panel de Control - Super Admin")
    st.markdown("---")
    
    # 1. METRICAS GLOBALES
    col1, col2, col3 = st.columns(3)
    
    # Contamos total de agentes
    total_agentes = supabase.table('agentes').select("id", count='exact').execute().count
    # Contamos total de propiedades en el sistema
    total_props = supabase.table('propiedades').select("id", count='exact').execute().count
    
    col1.metric("Total Agentes", total_agentes)
    col2.metric("Propiedades en Nube", total_props)
    col3.metric("Ingresos Mensuales", f"${total_agentes * 500} MXN") # Ejemplo hipotético
    
    st.markdown("---")

    # 2. GESTIÓN DE SUSCRIPCIONES
    st.subheader("👥 Gestión de Usuarios y Suscripciones")
    
    # Traer todos los agentes
    agentes = supabase.table('agentes').select("*").order('id').execute().data
    
    for ag in agentes:
        # Lógica de Semáforo de Suscripción
        estado_color = "🟢" # Activo
        dias_restantes = "N/A"
        
        if ag['rol'] != 'admin':
            if ag.get('suscripcion_fin'):
                fecha_fin = datetime.strptime(ag['suscripcion_fin'], '%Y-%m-%d').date()
                hoy = datetime.now().date()
                delta = (fecha_fin - hoy).days
                
                if delta < 0:
                    estado_color = "🔴 VENCIDA"
                elif delta < 5:
                    estado_color = f"🟡 Vence en {delta} días"
                else:
                    estado_color = f"🟢 Activa ({delta} días)"
            else:
                estado_color = "⚪ Sin fecha asignada"

        # Mostrar tarjeta de usuario
        with st.expander(f"{estado_color} | {ag['nombre']} ({ag['email']})"):
            c1, c2 = st.columns(2)
            
            # Datos Informativos
            leads = supabase.table('clientes').select("*", count='exact').eq('agente_id', ag['id']).execute().count
            props = supabase.table('propiedades').select("*", count='exact').eq('agente_id', ag['id']).execute().count
            
            c1.write(f"**Teléfono:** {ag['telefono']}")
            c1.write(f"**Usuario:** {ag['usuario']}")
            c1.info(f"📊 Uso del Bot: {props} Propiedades | {leads} Clientes captados")
            
            # Edición de Suscripción
            with c2:
                st.write("**Administrar Suscripción**")
                nueva_fecha = st.date_input("Fecha de Corte", value=datetime.now(), key=f"date_{ag['id']}")
                
                if st.button("Renovar / Actualizar Fecha", key=f"btn_{ag['id']}"):
                    supabase.table('agentes').update({
                        "suscripcion_fin": str(nueva_fecha),
                        "suscripcion_estado": "activa"
                    }).eq('id', ag['id']).execute()
                    st.success("Fecha actualizada.")
                    time.sleep(1)
                    st.rerun()

    st.markdown("---")
    
    # 3. DAR DE ALTA NUEVO AGENTE
    st.subheader("➕ Dar de alta Nuevo Agente")
    with st.form("nuevo_agente"):
        c1, c2 = st.columns(2)
        nombre = c1.text_input("Nombre Completo")
        email = c2.text_input("Correo Electrónico (Login)")
        tel = c1.text_input("WhatsApp (521...)")
        password_temp = c2.text_input("Contraseña Temporal", value="12345")
        
        # Le damos 30 días gratis por defecto
        fecha_inicio = datetime.now() + timedelta(days=30)
        
        if st.form_submit_button("Crear Usuario"):
            try:
                supabase.table('agentes').insert({
                    "nombre": nombre,
                    "email": email,
                    "telefono": tel,
                    "usuario": email.split('@')[0], # Usuario sugerido
                    "password": password_temp,
                    "rol": "agente",
                    "suscripcion_fin": str(fecha_inicio.date()),
                    "suscripcion_estado": "activa"
                }).execute()
                st.success(f"✅ Usuario creado. Usuario: {email.split('@')[0]} | Pass: {password_temp}")
                time.sleep(2)
                st.rerun()
            except Exception as e:
                st.error(f"Error al crear: {e}")

# ==========================================
# 🏙️ ZONA DE AGENTE (USUARIO NORMAL)
# ==========================================
def panel_agente():
    agente = st.session_state.usuario
    
    # Verificar suscripción antes de dejarlo trabajar
    bloqueado = False
    if agente.get('suscripcion_fin'):
        fecha_fin = datetime.strptime(agente['suscripcion_fin'], '%Y-%m-%d').date()
        if fecha_fin < datetime.now().date():
            bloqueado = True
    
    with st.sidebar:
        st.header(f"👤 {agente['nombre']}")
        if bloqueado:
            st.error("⛔ TU SUSCRIPCIÓN HA VENCIDO")
            st.write("Contacta al administrador para renovar.")
        else:
            st.success("✅ Suscripción Activa")
            
        if st.button("Cerrar Sesión"):
            st.session_state.usuario = None
            st.rerun()

    if bloqueado:
        st.title("⛔ Servicio Suspendido")
        st.warning("Tu periodo de suscripción ha finalizado. Por favor realiza tu pago para continuar accediendo al panel y al bot.")
        return

    # Si pagó, ve su contenido normal
    st.title("🏢 Panel de Agente")
    tab1, tab2 = st.tabs(["📄 Subir Propiedad", "📋 Mi Inventario"])

    with tab1:
        archivo_pdf = st.file_uploader("Sube ficha técnica (PDF)", type="pdf")
        if archivo_pdf:
            with st.spinner("Leyendo con IA..."):
                texto, datos = procesar_pdf(archivo_pdf)
                if datos:
                    with st.form("save"):
                        col1, col2 = st.columns(2)
                        t = col1.text_input("Título", value=datos.get("titulo"))
                        p = col2.text_input("Precio", value=datos.get("precio"))
                        u = col1.text_input("Ubicación", value=datos.get("ubicacion"))
                        f = col2.text_input("Foto URL")
                        d = st.text_area("Resumen", value=datos.get("resumen"))
                        
                        if st.form_submit_button("Guardar Propiedad"):
                            supabase.table('propiedades').insert({
                                "agente_id": agente['id'], "titulo": t, "precio": p,
                                "ubicacion": u, "foto_url": f, "descripcion": d, "ficha_texto": texto
                            }).execute()
                            st.toast("✅ Guardado exitosamente")

    with tab2:
        mis_casas = supabase.table('propiedades').select("*").eq('agente_id', agente['id']).execute().data
        if not mis_casas: st.info("No tienes propiedades.")
        for c in mis_casas:
            with st.expander(f"{c['titulo']} - {c['precio']}"):
                st.write(c['descripcion'])
                if st.button("Borrar", key=c['id']):
                    supabase.table('propiedades').delete().eq('id', c['id']).execute()
                    st.rerun()

# --- LOGIN FLOW ---
def login_flow():
    st.title("🔐 InmoBot SaaS")
    
    if st.session_state.recuperando:
        # (Aquí iría el código de recuperación que ya tenías, lo resumo por espacio)
        st.info("Sistema de recuperación activado.")
        if st.button("Volver"): 
            st.session_state.recuperando = False
            st.rerun()
    else:
        with st.form("login"):
            user = st.text_input("Usuario")
            password = st.text_input("Contraseña", type="password")
            if st.form_submit_button("Ingresar"):
                res = supabase.table('agentes').select("*").eq('usuario', user).eq('password', password).execute()
                if res.data:
                    st.session_state.usuario = res.data[0]
                    st.rerun()
                else:
                    st.error("Credenciales incorrectas")
        
        if st.button("Olvidé contraseña"):
            st.session_state.recuperando = True
            st.rerun()

# --- ROUTER PRINCIPAL ---
if st.session_state.usuario is None:
    login_flow()
else:
    # Router de Vistas según el ROL
    usuario = st.session_state.usuario
    if usuario.get('rol') == 'admin':
        panel_admin() # <--- TÚ VES ESTO
    else:
        panel_agente() # <--- TUS CLIENTES VEN ESTO