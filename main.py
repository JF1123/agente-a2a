import os
import asyncio
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import groq

# -------------------------------------------------------------
# 1. Configuración de Variables de Entorno
# -------------------------------------------------------------
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
BEATAPI_KEY = os.environ.get("BEATAPI_KEY")
MOLTBOOK_API_KEY = os.environ.get("MOLTBOOK_API_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

groq_client = groq.Groq(api_key=GROQ_API_KEY)

# -------------------------------------------------------------
# 2. Función Helper para Notificaciones en Discord
# -------------------------------------------------------------
async def send_discord_alert(mensaje: str):
    """Envía un mensaje a tu canal de Discord vía Webhook"""
    if not DISCORD_WEBHOOK_URL:
        return
    
    async with httpx.AsyncClient() as client:
        try:
            await client.post(DISCORD_WEBHOOK_URL, json={"content": mensaje})
        except Exception as e:
            print(f"⚠️ Error enviando alerta a Discord: {e}")

# -------------------------------------------------------------
# 3. Bucle de Heartbeat (Moltbook Check-in cada 30 min)
# -------------------------------------------------------------
async def moltbook_heartbeat_loop():
    """Ejecuta el chequeo social en Moltbook en segundo plano"""
    if not MOLTBOOK_API_KEY:
        print("⚠️ MOLTBOOK_API_KEY no configurada. Omitiendo Heartbeat.")
        return

    headers = {"Authorization": f"Bearer {MOLTBOOK_API_KEY}"}
    
    # Espera 10 segundos al iniciar el servidor antes del primer chequeo
    await asyncio.sleep(10)
    
    async with httpx.AsyncClient() as client:
        while True:
            try:
                res = await client.get("https://www.moltbook.com/api/v1/home", headers=headers, timeout=10.0)
                if res.status_code == 200:
                    data = res.json()
                    notif_count = data.get("your_account", {}).get("unread_notification_count", 0)
                    karma = data.get("your_account", {}).get("karma", 0)
                    
                    msg = f"💓 **Heartbeat Moltbook:** Agente activo | Karma: {karma} | Notificaciones no leídas: {notif_count}"
                    print(msg)
                    
                    if notif_count > 0:
                        await send_discord_alert(f"🔔 **Moltbook Alert:** Tienes {notif_count} nueva(s) notificación(es) o respuesta(s) en Moltbook.")
            except Exception as e:
                print(f"Error en Heartbeat de Moltbook: {e}")
            
            # Espera 30 minutos (1800 segundos) para el siguiente ciclo
            await asyncio.sleep(1800)

# -------------------------------------------------------------
# 4. Gestión del Ciclo de Vida de FastAPI (Lifespan)
# -------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Tarea de inicio: arranca el Heartbeat en segundo plano y notifica a Discord
    asyncio.create_task(moltbook_heartbeat_loop())
    await send_discord_alert("🚀 **GeminiDataAgent** ha iniciado servicio en Render. Listo para recibir peticiones A2A.")
    yield
    # Tarea de apagado (opcional)

app = FastAPI(
    title="Agente Extractor & Formateador A2A",
    lifespan=lifespan
)

class PeticionAgente(BaseModel):
    texto_crudo: str
    wallet_origen: str

# -------------------------------------------------------------
# 5. Endpoint Principal de Procesamiento A2A
# -------------------------------------------------------------
@app.post("/v1/procesar-datos")
async def procesar_datos_a2a(peticion: PeticionAgente):
    
    # Notificación inmediata a Discord de petición entrante
    await send_discord_alert(f"📩 **Petición A2A recibida** de la billetera: `{peticion.wallet_origen}`")

    # -------------------------------------------------------------
    # PASO 1: Filtro de decisión estricto con JEV Gratis (BeatAPI)
    # -------------------------------------------------------------
    payload_jev = {
        "model": "jev-1.13-free",
        "state": {
            "id": "peticion-a2a",
            "text": peticion.texto_crudo
        },
        "questions": {
            "clasificacion": {
                "type": "choice",
                "instructions": "Clasifica la validez y tipo del texto recibido.",
                "criteria": {
                    "valido": "El texto contiene información útil, datos financieros, noticias o reportes.",
                    "invalido": "El texto está vacío, corrupto, sin sentido o es spam evidente."
                }
            }
        }
    }

    headers_jev = {
        "Authorization": f"Bearer {BEATAPI_KEY}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:
        try:
            res_jev = await client.post(
                "https://api.beatapi.io/v1/systemone", 
                json=payload_jev, 
                headers=headers_jev,
                timeout=10.0
            )
        except Exception as e:
            await send_discord_alert(f"⚠️ **Error JEV:** Fallo de conexión")
            raise HTTPException(status_code=500, detail=f"Error al conectar con JEV: {str(e)}")

    if res_jev.status_code != 200:
        raise HTTPException(
            status_code=res_jev.status_code, 
            detail=f"JEV API Error: {res_jev.text}"
        )

    datos_jev = res_jev.json()
    respuesta_categoria = datos_jev.get("answers", {}).get("clasificacion", {})
    eleccion = respuesta_categoria.get("choice")
    confianza = respuesta_categoria.get("confidence", 0)

    # Si JEV rechaza la entrada
    if eleccion != "valido" or confianza < 0.75:
        await send_discord_alert(f"🚫 **Petición Rechazada:** El filtro JEV clasificó la entrada como inválida/spam (Confianza: {confianza:.2f})")
        raise HTTPException(
            status_code=400, 
            detail={
                "status": "rejected", 
                "motivo": "Texto no procesable o invalido", 
                "confianza": confianza
            }
        )

    # -------------------------------------------------------------
    # PASO 2: Extracción y Formateo JSON con Groq (Llama-3.3-70b)
    # -------------------------------------------------------------
    prompt_sistema = """
    Eres un extractor de datos en formato JSON para un pipeline A2A.
    Devuelve ÚNICAMENTE un objeto JSON con la siguiente estructura limpia:
    {
      "resumen": "resumen en 2 oraciones",
      "puntos_clave": ["dato 1", "dato 2"],
      "estado_procesamiento": "exitoso"
    }
    """

    respuesta_groq = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": prompt_sistema},
            {"role": "user", "content": peticion.texto_crudo}
        ],
        response_format={"type": "json_object"},
        temperature=0.1
    )

    # Notificación de éxito en Discord (Cobro realizado)
    await send_discord_alert(
        f"💰 **Procesamiento Exitoso:** Datos entregados a `{peticion.wallet_origen}` | Filtro JEV: {eleccion} ({confianza:.2f})"
    )

    return {
        "status": "success",
        "agente_cliente": peticion.wallet_origen,
        "filtro_jev": {"eleccion": eleccion, "confianza": confianza},
        "resultado": respuesta_groq.choices[0].message.content
    }
