import os
import asyncio
import json
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import groq

# -------------------------------------------------------------
# 1. Variables de Entorno y Clientes
# -------------------------------------------------------------
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
BEATAPI_KEY = os.environ.get("BEATAPI_KEY")
MOLTBOOK_API_KEY = os.environ.get("MOLTBOOK_API_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

groq_client = groq.Groq(api_key=GROQ_API_KEY)

async def send_discord_alert(mensaje: str):
    """Envía actualizaciones a Discord"""
    if not DISCORD_WEBHOOK_URL:
        return
    async with httpx.AsyncClient() as client:
        try:
            await client.post(DISCORD_WEBHOOK_URL, json={"content": mensaje})
        except Exception as e:
            print(f"⚠️ Error al enviar alerta a Discord: {e}")

# Registro local de posts ya prospectados para no repetir spam
PROSPECTED_POSTS = set()

# -------------------------------------------------------------
# 2. Bucle Autónomo de Prospección y Engagement Saliente
# -------------------------------------------------------------
async def moltbook_prospector_loop():
    """Bucle autónomo: Analiza el feed de Moltbook, encuentra clientes y les ofrece servicio"""
    if not MOLTBOOK_API_KEY:
        print("⚠️ MOLTBOOK_API_KEY no configurada. Omitiendo prospección.")
        return

    headers = {"Authorization": f"Bearer {MOLTBOOK_API_KEY}"}
    await asyncio.sleep(15)  # Espera inicial tras arranque
    
    async with httpx.AsyncClient() as client:
        while True:
            try:
                # 1. Leer feed público para buscar posibles clientes
                feed_res = await client.get("https://www.moltbook.com/api/v1/home", headers=headers, timeout=10.0)
                
                if feed_res.status_code == 200:
                    data = feed_res.json()
                    recent_posts = data.get("feed", [])
                    
                    for post in recent_posts[:5]:  # Evaluar los 5 posts más recientes
                        post_id = post.get("id")
                        post_title = post.get("title", "")
                        post_content = post.get("content", "")
                        author_name = post.get("author", {}).get("name", "Agente")

                        # Evitar prospectar a uno mismo o repeticiones
                        if author_name.lower() == "geminidataagent" or post_id in PROSPECTED_POSTS:
                            continue

                        PROSPECTED_POSTS.add(post_id)

                        # 2. Groq evalúa si el post contiene datos no estructurados o potencial de venta
                        prompt_prospeccion = f"""
                        Eres CleanJSON-A2A, un agente comercial autónomo en Moltbook.
                        Analiza la siguiente publicación de '{author_name}':
                        Título: "{post_title}"
                        Contenido: "{post_content}"

                        ¿Esta publicación contiene texto largo, reportes, datos no estructurados o potencial para ofrecer extracción de datos a JSON limpio?
                        Devuelve ÚNICAMENTE un JSON estricto:
                        {{
                          "es_prospecto_valioso": true,
                          "razon": "Por qué este post se beneficia de estructuración JSON",
                          "comentario_pitch": "Un comentario breve (max 2 oraciones) y amable en inglés ofreciendo CleanJSON-A2A ($0.35 USDC per request) con el checkout link: https://nevermined.app/checkout/989095819774713772559631732815111512660639056034"
                        }}
                        """

                        decision = groq_client.chat.completions.create(
                            model="llama-3.3-70b-versatile",
                            messages=[{"role": "user", "content": prompt_prospeccion}],
                            response_format={"type": "json_object"},
                            temperature=0.3
                        )

                        evaluacion = json.loads(decision.choices[0].message.content)

                        # 3. Si es un buen prospecto, publicar comentario de pitch
                        if evaluacion.get("es_prospecto_valioso"):
                            comment_text = evaluacion.get("comentario_pitch")
                            
                            await client.post(
                                f"https://www.moltbook.com/api/v1/posts/{post_id}/comments",
                                headers=headers,
                                json={"content": comment_text},
                                timeout=10.0
                            )

                            # 4. Alertar a Discord sobre la prospección exitosa
                            await send_discord_alert(
                                f"🎯 **Prospección Saliente Realizada:**\n"
                                f"👤 **Prospecto:** `{author_name}` en *'{post_title}'*\n"
                                f"💡 **Razón:** {evaluacion.get('razon')}\n"
                                f"💬 **Pitch enviado:** \"{comment_text}\""
                            )

            except Exception as e:
                print(f"Error en bucle de prospección: {e}")

            # Ejecutar prospección cada 20 minutos
            await asyncio.sleep(1200)

# -------------------------------------------------------------
# 3. Lifespan y Rutas HTTP
# -------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(moltbook_prospector_loop())
    await send_discord_alert("🚀 **CleanJSON-A2A Activo:** Bucle de prospección saliente en línea.")
    yield

app = FastAPI(title="CleanJSON-A2A Service", lifespan=lifespan)

@app.get("/")
def root():
    return {
        "status": "online",
        "agente": "CleanJSON-A2A",
        "servicio": "Realtime JSON Extraction & Filtering"
    }

class PeticionAgente(BaseModel):
    texto_crudo: str
    wallet_origen: str

@app.post("/v1/procesar-datos")
async def procesar_datos_a2a(peticion: PeticionAgente):
    await send_discord_alert(f"📩 **Petición A2A pagada recibida** desde: `{peticion.wallet_origen}`")

    payload_jev = {
        "model": "jev-1.13-free",
        "state": {"id": "peticion-a2a", "text": peticion.texto_crudo},
        "questions": {
            "clasificacion": {
                "type": "choice",
                "instructions": "Clasifica la validez del texto.",
                "criteria": {"valido": "Texto procesable.", "invalido": "Spam o corrupto."}
            }
        }
    }

    headers_jev = {"Authorization": f"Bearer {BEATAPI_KEY}", "Content-Type": "application/json"}

    async with httpx.AsyncClient() as client:
        res_jev = await client.post("https://api.beatapi.io/v1/systemone", json=payload_jev, headers=headers_jev, timeout=10.0)

    if res_jev.status_code != 200:
        raise HTTPException(status_code=res_jev.status_code, detail=res_jev.text)

    datos_jev = res_jev.json()
    respuesta_cat = datos_jev.get("answers", {}).get("clasificacion", {})
    eleccion = respuesta_cat.get("choice")
    confianza = respuesta_cat.get("confidence", 0)

    if eleccion != "valido" or confianza < 0.75:
        await send_discord_alert(f"🚫 **Entrada Rechazada por JEV:** Confianza baja ({confianza:.2f})")
        raise HTTPException(status_code=400, detail="Texto no procesable")

    prompt_sistema = """
    Devuelve ÚNICAMENTE un objeto JSON limpio:
    {
      "resumen": "resumen en 2 oraciones",
      "puntos_clave": ["dato 1", "dato 2"],
      "estado_procesamiento": "exitoso"
    }
    """

    respuesta_groq = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "system", "content": prompt_sistema}, {"role": "user", "content": peticion.texto_crudo}],
        response_format={"type": "json_object"},
        temperature=0.1
    )

    await send_discord_alert(f"💰 **Servicio A2A completado ($0.35 USDC)** para `{peticion.wallet_origen}`.")

    return {
        "status": "success",
        "agente_cliente": peticion.wallet_origen,
        "filtro_jev": {"eleccion": eleccion, "confianza": confianza},
        "resultado": respuesta_groq.choices[0].message.content
    }