import os
import json
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from openai import OpenAI
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv('test.env')

app = Flask(__name__)

# Configuración Supabase
url_supabase = os.getenv("SUPABASE_URL")
key_supabase = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(url_supabase, key_supabase)

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
historial_conversaciones = {}

def obtener_propiedades_db():
    response = supabase.table('propiedades').select("*").eq('agente_id', 1).execute()
    return response.data

def guardar_lead_db(nombre, telefono, mensaje):
    datos = {"agente_id": 1, "nombre": nombre, "telefono": telefono, "interes_principal": mensaje}
    supabase.table('clientes').insert(datos).execute()
    print(f"✅ Lead guardado: {nombre}")

@app.route('/bot', methods=['POST'])
def bot():
    mensaje_usuario = request.values.get('Body', '')
    numero_usuario = request.values.get('From', '')
    
    if numero_usuario not in historial_conversaciones:
        historial_conversaciones[numero_usuario] = []
    
    historial_conversaciones[numero_usuario].append({"role": "user", "content": mensaje_usuario})

    # 1. Obtener casas y preparar texto
    propiedades = obtener_propiedades_db()
    texto_propiedades = ""
    for p in propiedades:
        ficha_texto = p.get('ficha_texto') or ''
        # Enviamos más contexto a la IA (1500 chars)
        info_extra = ficha_texto[:1500] 
        
        texto_propiedades += f"""
        - ID: {p['id']}
          TITULO: {p['titulo']}
          PRECIO: {p['precio']}
          UBICACION: {p['ubicacion']}
          LINK_FOTO: {p['foto_url']}
          RESUMEN: {p['descripcion']}
          DETALLES: {info_extra}...
        """

    prompt_sistema = f"""
    Eres un asistente inmobiliario virtual experto.
    
    TUS PROPIEDADES:
    {texto_propiedades}
    
    REGLAS DE IMAGENES:
    Si recomiendas una propiedad específica, DEBES poner al final de tu respuesta esta etiqueta:
    FOTO:URL_DE_LA_FOTO
    (Copia exactamente el LINK_FOTO de la lista de arriba).
    
    REGLA DE CITAS:
    Si tienes Nombre y Fecha confirmados, responde SOLO:
    AGENDA_CITA|Nombre|Fecha|Mensaje amable
    """

    mensajes_para_enviar = [{"role": "system", "content": prompt_sistema}] + historial_conversaciones[numero_usuario]

    try:
        chat_completion = client.chat.completions.create(
            messages=mensajes_para_enviar,
            model="gpt-4o-mini",
        )
        respuesta_ia = chat_completion.choices[0].message.content
    except Exception as e:
        print(f"Error OpenAI: {e}")
        return str(MessagingResponse().message("Dame un momento, procesando..."))

    historial_conversaciones[numero_usuario].append({"role": "assistant", "content": respuesta_ia})
    
    mensaje_final = respuesta_ia
    url_media = None

    # Lógica 1: Detectar Citas
    if "AGENDA_CITA|" in respuesta_ia:
        try:
            partes = respuesta_ia.split('|')
            if len(partes) >= 4:
                guardar_lead_db(partes[1], numero_usuario, partes[2])
                mensaje_final = partes[3]
            else:
                mensaje_final = respuesta_ia.replace("AGENDA_CITA|", "")
        except:
            pass

    # Lógica 2: Detectar Fotos (Para mandar imagen real)
    if "FOTO:" in mensaje_final:
        # Separamos el texto de la URL
        partes_foto = mensaje_final.split("FOTO:")
        mensaje_texto = partes_foto[0].strip()
        url_detectada = partes_foto[1].strip()
        
        # Limpiamos posibles caracteres extra que ponga la IA
        url_detectada = url_detectada.split()[0]  # Toma solo la primera palabra (la URL)
        
        mensaje_final = mensaje_texto
        url_media = url_detectada
        print(f"📸 Enviando imagen: {url_media}")

    # Enviar respuesta a Twilio
    resp = MessagingResponse()
    msg = resp.message()
    msg.body(mensaje_final)
    
    if url_media:
        msg.media(url_media) # <--- ¡Aquí está la magia visual!

    return str(resp)

if __name__ == '__main__':
    # Mantenemos use_reloader=False para estabilidad
    app.run(debug=True, use_reloader=False, port=5000)