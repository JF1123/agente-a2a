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

# Registro local de posts ya prospectados para evitar duplicados
PROSPECTED_POSTS = set()

# -------------------------------------------------------------
# 2. Bucle Autónomo de Patrulla y Prospección (Feed Global)
# -------------------------------------------------------------
async def moltbook_prospector_loop():
    """Bucle hiperactivo: Revisa el feed GLOBAL de Moltbook cada 5 min"""
    if not MOLTBOOK_API_KEY:
        await send_discord_alert("⚠️ **Alerta:** MOLTBOOK_API_KEY no encontrada. Bucle de prospección pausado.")
        return

    headers = {"Authorization": f"Bearer {MOLTBOOK_API_KEY}"}
    await asyncio.sleep(10)  # Espera inicial tras arranque
    
    async with httpx.AsyncClient() as client:
        while True:
            try:
                # Consultar el FEED GLOBAL público de Moltbook
                res = await client.get("https://www.moltbook.com/api/v1/posts", headers=headers, timeout=10.0)
                
                if res.status_code == 200:
                    data = res.json()
                    recent_posts = data.get("posts", data.get("data", []))
                    
                    evaluados = 0
                    pichados = 0
                    ignorados = 0

                    for post in recent_posts[:5]:  # Analizar los 5 posts más recientes
                        post_id = post.get("id")
                        post_title = post.get("title", "")
                        post_content = post.get("content", "")
                        author_info = post.get("author", {})
                        author_name = author_info.get("name", "Agente") if isinstance(author_info, dict) else "Agente"

                        # Omitir posts propios o ya analizados
                        if author_name.lower() in ["geminidataagent", "cleanjson-a2a"] or post_id in PROSPECTED_POSTS:
                            ignorados += 1
                            continue

                        PROSPECTED_POSTS.add(post_id)
                        evaluados += 1

                        # Analizar oportunidad con Groq Llama 3.1 8B Instant (Ultra rápido y activo)
                        prompt_prospeccion = f"""
Eres CleanJSON-A2A, un microservicio de verificación independiente y estructuración de esquemas JSON para agentes en Moltbook.
Analiza la publicación de '{author_name}':
Título: "{post_title}"
Contenido: "{post_content}"

¿Esta publicación trata sobre verificación de código, problemas de memoria, compresión de contexto, o datos que necesiten un filtro o esquema JSON estricto?
Devuelve ÚNICAMENTE un JSON estricto:
{{
  "es_prospecto_valioso": true,
  "razon": "Por qué se beneficia de validación externa e ingeniería de esquemas",
  "comentario_pitch": "Pitch en inglés enfocado en verificación independiente o conversión a esquema estricto (max 2 oraciones) con link: https://nevermined.app/checkout/989095819774713772559631732815111512660639056034"
}}
"""

                        decision = groq_client.chat.completions.create(
                            model="llama-3.1-8b-instant",
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
                                f"💡 **Análisis:** {evaluacion.get('razon')}\n"
                                f"💬 **Pitch:** \"{comment_text}\""
                            )

                    # REPORTE DE PATRULLA CONTINUO A DISCORD
                    await send_discord_alert(
                        f"🛡️ **Reporte de Patrulla CleanJSON-A2A (Feed Global):**\n"
                        f"• Posts globales detectados: `{len(recent_posts)}`\n"
                        f"• Nuevos analizados con Groq: `{evaluados}`\n"
                        f"• Ofertas/Pitches enviados: `{pichados}`\n"
                        f"• Repetidos/Propios ignorados: `{ignorados}`\n"
                        f"⏳ *Próxima patrulla en 5 minutos...*"
                    )

            except Exception as e:
                await send_discord_alert(f"⚠️ **Error en patrulla:** `{e}`")

            # Esperar 5 minutos (300 segundos) para el siguiente ciclo
            await asyncio.sleep(300)

# -------------------------------------------------------------
# 3. Server Lifespan y Endpoints HTTP
# -------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(moltbook_prospector_loop())
    await send_discord_alert("🚀 **CleanJSON-A2A Activo:** Bucle de prospección hiperactivo iniciado (Patrulla global cada 5 min).")
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

    # 1. Filtro de Spam/Basura JEV vía BeatAPI
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

    # 2. Extracción y Estructuración con Groq
    prompt_sistema = """
    Devuelve ÚNICAMENTE un objeto JSON limpio:
    {
      "resumen": "resumen en 2 oraciones",
      "puntos_clave": ["dato 1", "dato 2"],
      "estado_procesamiento": "exitoso"
    }
    """

    respuesta_groq = groq_client.chat.completions.create(
        model="llama-3.1-8b-instant",
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