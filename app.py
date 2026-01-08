import os
import json
from datetime import datetime
import pytz 
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from openai import OpenAI
from dotenv import load_dotenv
from supabase import create_client, Client

# Tu módulo de calendario
from agenda_helper import obtener_huecos_libres, crear_evento 

load_dotenv('test.env')

app = Flask(__name__)

# --- CONFIGURACIÓN SUPABASE ---
url_supabase = os.getenv("SUPABASE_URL")
key_supabase = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(url_supabase, key_supabase)

# --- CONFIGURACIÓN OPENAI ---
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
historial_conversaciones = {}

# --- DATOS ---
def obtener_datos_agente(id_agente=1):
    response = supabase.table('agentes').select("*").eq('id', id_agente).execute()
    return response.data[0] if response.data else None

def obtener_propiedades_db(id_agente=1):
    response = supabase.table('propiedades').select("*").eq('agente_id', id_agente).execute()
    return response.data

def guardar_lead_completo(nombre, telefono, edad, perfil, mensaje_cita):
    datos = {
        "agente_id": 1, 
        "nombre": nombre, 
        "telefono": telefono, 
        "edad": edad,
        "perfil_vida": perfil,
        "interes_principal": mensaje_cita
    }
    supabase.table('clientes').insert(datos).execute()
    print(f"✅ Lead Guardado: {nombre}")

# --- BOT ---
@app.route('/bot', methods=['POST'])
def bot():
    mensaje_usuario = request.values.get('Body', '')
    numero_usuario = request.values.get('From', '')
    
    if numero_usuario not in historial_conversaciones:
        historial_conversaciones[numero_usuario] = []
    
    historial_conversaciones[numero_usuario].append({"role": "user", "content": mensaje_usuario})

    # 1. Preparar Datos
    agente = obtener_datos_agente(1) 
    propiedades = obtener_propiedades_db(1)
    
    # 2. Contexto Temporal
    zona_mx = pytz.timezone('America/Mexico_City')
    ahora = datetime.now(zona_mx)
    fecha_hoy_str = ahora.strftime("%Y-%m-%d") 
    dia_semana_str = ahora.strftime("%A")

    # 3. Agenda
    texto_agenda = "No hay calendario conectado."
    if agente.get('calendar_email'):
        try:
            texto_agenda = obtener_huecos_libres(agente['calendar_email'])
        except: pass

    # 4. Inventario (Lo preparamos para que la IA lo entienda bien)
    texto_propiedades = ""
    for p in propiedades:
        ficha = (p.get('ficha_texto') or '')[:500]
        # Clasificación simple
        tipo = "PROPIEDAD"
        t_low = p['titulo'].lower()
        if "casa" in t_low: tipo = "CASA"
        elif "terreno" in t_low or "lote" in t_low: tipo = "TERRENO"
        elif "depa" in t_low: tipo = "DEPARTAMENTO"

        texto_propiedades += f"""
        ---
        TIPO: {tipo}
        TITULO: {p['titulo']}
        PRECIO: {p['precio']}
        UBICACION: {p['ubicacion']}
        URL_FOTO: {p['foto_url']}
        RESUMEN: {p['descripcion']}
        DETALLES: {ficha}...
        ---
        """

    # 5. EL PROMPT "CARISMÁTICO Y EFICIENTE" 🌟
    prompt_sistema = f"""
    Eres {agente['nombre']}, un Asesor Inmobiliario profesional, AMABLE y CARISMÁTICO.
    
    TU PERSONALIDAD:
    - Usa emojis moderados (🏡, ✨, 📍, 👋) para sonar amigable.
    - Muestra entusiasmo por las propiedades.
    - No seas "seco", pero tampoco mandes textos infinitos.
    
    ESTRATEGIA DE VENTAS (EMBUDO):
    
    1. **VITRINA (El gancho):**
       Si preguntan "¿Qué tienes?" o "Busco casa", responde con entusiasmo mostrando una lista atractiva pero resumida.
       *Ejemplo:* "¡Hola! 👋 Tengo estas opciones increíbles para ti: 
       1. 🏡 Casa de Campo (Zona Sur) - Ideal para descansar.
       2. 🏢 Depa Minimalista (Norte) - Perfecto para ejecutivos.
       ¿Cuál te llama la atención? 👀"
       (NO pongas precio ni foto todavía, genera curiosidad).

    2. **DETALLE (El enamoramiento):**
       Si el cliente dice "Me interesa la 1", "A ver la casa", o pregunta detalles específicos... ¡AHORA SÍ!
       - Da la descripción vendedora.
       - Da el PRECIO.
       - **OBLIGATORIO:** Pon la foto al final con: FOTO:URL_EXACTA

    3. **CIERRE (La cita):**
       Si el cliente dice "Quiero verla" o "Agendar cita":
       - Revisa tu agenda ({texto_agenda}) y propón horarios.
       - **REGLA DE ORO:** Antes de confirmar, di amablemente: "¡Me encantaría mostrártela! 📝 Para registrar tu visita en el sistema, ¿me podrías regalar tu nombre completo y edad, por favor? 😊".
       - NO agendes hasta tener esos datos.

    --- FORMATO DE COMANDOS ---
    - Para mandar foto: Texto... FOTO:URL_AQUI
    - Para confirmar cita (Solo con Nombre+Edad+Fecha):
      AGENDA_CITA|Nombre|Edad|Perfil|YYYY-MM-DD HH:MM|MensajeAmable

    --- DATOS ---
    HOY: {dia_semana_str}, {fecha_hoy_str}
    INVENTARIO DISPONIBLE:
    {texto_propiedades}
    """

    mensajes_para_enviar = [{"role": "system", "content": prompt_sistema}] + historial_conversaciones[numero_usuario]

    try:
        chat_completion = client.chat.completions.create(
            messages=mensajes_para_enviar,
            model="gpt-4o-mini",
            temperature=0.7 # <--- Subimos temperatura para recuperar el carisma
        )
        respuesta_ia = chat_completion.choices[0].message.content
    except Exception as e:
        print(f"Error OpenAI: {e}")
        return str(MessagingResponse().message("Dame un segundo, estoy revisando el sistema... 🤖"))

    historial_conversaciones[numero_usuario].append({"role": "assistant", "content": respuesta_ia})
    
    mensaje_final = respuesta_ia
    url_media = None

    # --- PROCESADORES ---
    
    # Detector de Foto
    if "FOTO:" in mensaje_final:
        try:
            partes = mensaje_final.split("FOTO:")
            mensaje_final = partes[0].strip()
            # Limpieza robusta de URL
            url_sucia = partes[1].strip()
            # Tomamos hasta el primer espacio o salto de linea
            url_media = url_sucia.split()[0].rstrip('.').rstrip(',')
        except: pass

    # Detector de Cita
    if "AGENDA_CITA|" in respuesta_ia:
        try:
            partes = respuesta_ia.split('|')
            if len(partes) >= 6:
                nombre = partes[1]
                edad = partes[2]
                perfil = partes[3]
                fecha_hora = partes[4]
                mensaje_bonito = partes[5]

                guardar_lead_completo(nombre, numero_usuario, edad, perfil, f"Cita: {fecha_hora}")
                
                if agente.get('calendar_email'):
                    link = crear_evento(agente['calendar_email'], nombre, fecha_hora)
                    mensaje_final = f"{mensaje_bonito}\n\n🗓️ Ver en calendario: {link}"
                else:
                    mensaje_final = mensaje_bonito
            else:
                mensaje_final = respuesta_ia.replace("AGENDA_CITA|", "")
        except:
            mensaje_final = "¡Listo! Cita agendada. 📝"

    resp = MessagingResponse()
    msg = resp.message()
    msg.body(mensaje_final)
    if url_media: msg.media(url_media)
    
    return str(resp)

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False, port=5000)