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
    """Envía actualizaciones en tiempo real a Discord"""
    if not DISCORD_WEBHOOK_URL:
        return
    async with httpx.AsyncClient() as client:
        try:
            await client.post(DISCORD_WEBHOOK_URL, json={"content": mensaje})
        except Exception as e:
            print(f"⚠️ Error al enviar alerta a Discord: {e}")

PROSPECTED_POSTS = set()

# -------------------------------------------------------------
# 2. Bucle Autónomo de Patrulla y Prospección (Cada 5 Minutos)
# -------------------------------------------------------------
async def moltbook_prospector_loop():
    """Bucle hiperactivo: Revisa Moltbook cada 5 min y reporta todo a Discord"""
    if not MOLTBOOK_API_KEY:
        await send_discord_alert("⚠️ **Alerta:** MOLTBOOK_API_KEY no encontrada. Bucle de prospección pausado.")
        return

    headers = {"Authorization": f"Bearer {MOLTBOOK_API_KEY}"}
    await asyncio.sleep(10)  # Espera inicial
    
    async with httpx.AsyncClient() as client:
        while True:
            try:
                # 1. Leer feed público
                feed_res = await client.get("https://www.moltbook.com/api/v1/home", headers=headers, timeout=10.0)
                
                if feed_res.status_code == 200:
                    data = feed_res.json()
                    recent_posts = data.get("feed", [])
                    
                    evaluados = 0
                    pichados = 0
                    ignorados = 0

                    for post in recent_posts[:5]:  # Analizar los 5 posts más recientes
                        post_id = post.get("id")
                        post_title = post.get("title", "")
                        post_content = post.get("content", "")
                        author_name = post.get("author", {}).get("name", "Agente")

                        # Evitar prospectar a uno mismo o repeticiones
                        if author_name.lower() in ["geminidataagent", "cleanjson-a2a"] or post_id in PROSPECTED_POSTS:
                            ignorados += 1
                            continue

                        PROSPECTED_POSTS.add(post_id)
                        evaluados += 1

                        # Groq analiza la oportunidad de venta
                        prompt_prospeccion = f"""
                        Eres CleanJSON-A2A, agente comercial en Moltbook.
                        Analiza la publicación de '{author_name}':
                        Título: "{post_title}"
                        Contenido: "{post_content}"

                        ¿Esta publicación contiene texto largo, reportes, datos no estructurados o potencial para ofrecer extracción de datos a JSON limpio?
                        Devuelve ÚNICAMENTE un JSON estricto:
                        {{
                          "es_prospecto_valioso": true,
                          "razon": "Por qué se beneficia de estructuración JSON",
                          "comentario_pitch": "Comentario breve en inglés ofreciendo CleanJSON-A2A ($0.35 USDC) con el checkout: https://nevermined.app/checkout/989095819774713772559631732815111512660639056034"
                        }}
                        """

                        decision = groq_client.chat.completions.create(
                            model="llama-3.3-70b-versatile",
                            messages=[{"role": "user", "content": prompt_prospeccion}],
                            response_format={"type": "json_object"},
                            temperature=0.3
                        )

                        evaluacion = json.loads(decision.choices[0].message.content)

                        if evaluacion.get("es_prospecto_valioso"):
                            comment_text = evaluacion.get("comentario_pitch")
                            await client.post(
                                f"https://www.moltbook.com/api/v1/posts/{post_id}/comments",
                                headers=headers,
                                json={"content": comment_text},
                                timeout=10.0
                            )
                            pichados += 1

                            await send_discord_alert(
                                f"🎯 **¡Cliente Potencial Identificado y Pitch Enviado!**\n"
                                f"👤 **Autor:** `{author_name}` | **Post:** *'{post_title}'*\n"
                                f"💡 **Análisis Groq:** {evaluacion.get('razon')}\n"
                                f"💬 **Comentario publicado:** \"{comment_text}\""
                            )

                    # REPORTE DE PATRULLA A DISCORD (Aunque no haya pitches nuevos)
                    await send_discord_alert(
                        f"🛡️ **Reporte de Patrulla CleanJSON-A2A:**\n"
                        f"• Posts revisados en esta ronda: `{len(recent_posts)}`\n"
                        f"• Nuevos analizados con Groq: `{evaluados}`\n"
                        f"• Ofertas enviadas: `{pichados}`\n"
                        f"• Repetidos/Propios omitidos: `{ignorados}`\n"
                        f"⏳ *Próxima patrulla en 5 minutos...*"
                    )

            except Exception as e:
                await send_discord_alert(f"⚠️ **Error en ciclo de patrulla:** `{e}`")

            # Esperar 5 minutos (300 segundos) para el siguiente ciclo
            await asyncio.sleep(300)

# -------------------------------------------------------------
# 3. Server Lifespan y Endpoints
# -------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(moltbook_prospector_loop())
    await send_discord_alert("🚀 **CleanJSON-A2A Activo:** Bucle de prospección hiperactivo iniciado (Patrulla cada 5 min).")
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
