import os
import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from dateutil import parser
import pytz

# Configuración
SCOPES = ['https://www.googleapis.com/auth/calendar']
ARCHIVO_KEY = 'google_key.json'

def conectar_calendar():
    creds = service_account.Credentials.from_service_account_file(
        ARCHIVO_KEY, scopes=SCOPES
    )
    service = build('calendar', 'v3', credentials=creds)
    return service

def obtener_huecos_libres(calendario_id):
    """Revisa los próximos 5 días y busca espacios libres en horario laboral (9am-6pm)"""
    service = conectar_calendar()
    zona_horaria = pytz.timezone('America/Mexico_City') # Ajusta a tu zona
    
    ahora = datetime.datetime.now(zona_horaria)
    inicio_semana = ahora.isoformat()
    fin_semana = (ahora + datetime.timedelta(days=5)).isoformat()
    
    # 1. Preguntar a Google: ¿Cuándo está OCUPADO este agente?
    eventos_result = service.events().list(
        calendarId=calendario_id, 
        timeMin=inicio_semana,
        timeMax=fin_semana,
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    eventos = eventos_result.get('items', [])

    # 2. Calcular huecos libres
    agenda_texto = "📅 *Horarios Disponibles esta semana:*\n"
    dias_revisados = 0
    
    # Revisamos día por día (Próximos 3 días para no saturar texto)
    for i in range(3): 
        dia_revision = ahora + datetime.timedelta(days=i)
        dia_str = dia_revision.strftime("%Y-%m-%d")
        dia_nombre = dia_revision.strftime("%A") # Ej: Monday
        
        # Horario laboral: 9:00 AM a 6:00 PM
        hora_inicio = dia_revision.replace(hour=9, minute=0, second=0, microsecond=0)
        hora_fin = dia_revision.replace(hour=18, minute=0, second=0, microsecond=0)
        
        # Filtramos eventos de ESE día
        ocupado = []
        for e in eventos:
            inicio_e = parser.parse(e['start'].get('dateTime', e['start'].get('date')))
            if inicio_e.date() == dia_revision.date():
                ocupado.append(inicio_e)
        
        # Lógica simplificada: Si tiene menos de 3 eventos, decimos que tiene espacio
        # (Para un algoritmo exacto de huecos minuto a minuto se requiere más código, 
        #  por ahora usaremos una lógica conversacional).
        
        if len(ocupado) == 0:
            agenda_texto += f"- {dia_nombre}: ✅ Todo el día libre (9am - 6pm)\n"
        elif len(ocupado) > 4:
            agenda_texto += f"- {dia_nombre}: 🔴 Día muy lleno\n"
        else:
            agenda_texto += f"- {dia_nombre}: ⚠️ Quedan espacios (tiene {len(ocupado)} citas)\n"
            
    return agenda_texto

def crear_evento(calendario_id, nombre_cliente, fecha_hora_str):
    """Crea la cita real en el calendario"""
    # fecha_hora_str debe ser formato: "2024-01-20 16:00"
    service = conectar_calendar()
    
    # Convertimos texto a objeto fecha
    fecha_dt = parser.parse(fecha_hora_str) 
    
    # Duración cita: 1 hora
    fin_dt = fecha_dt + datetime.timedelta(hours=1)
    
    evento = {
        'summary': f'Visita: {nombre_cliente}',
        'location': 'Ubicación de la Propiedad',
        'description': f'Cita agendada por InmoBot SaaS para {nombre_cliente}',
        'start': {
            'dateTime': fecha_dt.isoformat(),
            'timeZone': 'America/Mexico_City',
        },
        'end': {
            'dateTime': fin_dt.isoformat(),
            'timeZone': 'America/Mexico_City',
        },
    }

    event = service.events().insert(calendarId=calendario_id, body=evento).execute()
    return event.get('htmlLink')