import os
import asyncio
import json
import re
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
# 2. Bucle Autónomo de Patrulla y Prospección Multi-Servicio
# -------------------------------------------------------------
async def moltbook_prospector_loop():
    if not MOLTBOOK_API_KEY:
        await send_discord_alert("⚠️ MOLTBOOK_API_KEY no encontrada. Bucle pausado.")
        return

    headers = {"Authorization": f"Bearer {MOLTBOOK_API_KEY}"}
    await asyncio.sleep(10)
    
    async with httpx.AsyncClient() as client:
        while True:
            try:
                res = await client.get("https://www.moltbook.com/api/v1/posts", headers=headers, timeout=10.0)
                
                if res.status_code == 200:
                    data = res.json()
                    recent_posts = data.get("posts", data.get("data", []))
                    
                    evaluados = 0
                    pichados = 0
                    ignorados = 0

                    for post in recent_posts[:5]:
                        post_id = post.get("id")
                        post_title = post.get("title", "")
                        post_content = post.get("content", "")
                        author_info = post.get("author", {})
                        author_name = author_info.get("name", "Agente") if isinstance(author_info, dict) else "Agente"

                        if author_name.lower() in ["geminidataagent", "cleanjson-a2a"] or post_id in PROSPECTED_POSTS:
                            ignorados += 1
                            continue

                        PROSPECTED_POSTS.add(post_id)
                        evaluados += 1

                        prompt_prospeccion = f"""
                        Eres CleanJSON-A2A, una suite de microservicios A2A. Ofreces:
                        1. Resolver retos/captchas matemáticos de Moltbook (/v1/resolver-desafio)
                        2. Extraer datos web en tiempo real (/v1/web-scrape)
                        3. Limpieza y estructuración JSON (/v1/procesar-datos)

                        Analiza el post de '{author_name}':
                        Título: "{post_title}"
                        Contenido: "{post_content}"

                        ¿El post menciona fallos en retos, verificación, necesidad de datos web en tiempo real o estructuración?
                        Devuelve ÚNICAMENTE un JSON estricto:
                        {{
                          "es_prospecto_valioso": true,
                          "servicio_recomendado": "Solve&Verify | WebScrape | CleanJSON",
                          "comentario_pitch": "Comentario breve en inglés ofreciendo la solución ($0.20 USDC) con Checkout: https://nevermined.app/checkout/989095819774713772559631732815111512660639056034"
                        }}
                        """

                        decision = groq_client.chat.completions.create(
                            model="llama-3.1-8b-instant",
                            messages=[{"role": "user", "content": prompt_prospeccion}],
                            response_format={"type": "json_object"},
                            temperature=0.2
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
                                f"🎯 **¡Oportunidad Comercial Detectada!**\n"
                                f"👤 **Agente:** `{author_name}` | **Post:** *'{post_title}'*\n"
                                f"🛠️ **Servicio Recomendado:** `{evaluacion.get('servicio_recomendado')}`\n"
                                f"💬 **Pitch Enviado:** \"{comment_text}\""
                            )

                    await send_discord_alert(
                        f"🛡️ **Reporte de Patrulla Suite A2A:**\n"
                        f"• Posts analizados: `{evaluados}` | Pitches enviados: `{pichados}` | Ignorados: `{ignorados}`\n"
                        f"⏳ *Siguiente patrulla en 5 min...*"
                    )

            except Exception as e:
                await send_discord_alert(f"⚠️ **Error en patrulla:** `{e}`")

            await asyncio.sleep(300)

# -------------------------------------------------------------
# 3. Application Lifespan & Microservicios A2A
# -------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(moltbook_prospector_loop())
    await send_discord_alert("🚀 **CleanJSON Suite Activo:** Servicios de Extracción, Scraping y Solve&Verify en línea.")
    yield

app = FastAPI(title="CleanJSON-A2A Suite", lifespan=lifespan)

@app.get("/")
def root():
    return {
        "status": "online",
        "agente": "CleanJSON-A2A Suite",
        "servicios": [
            "/v1/procesar-datos (Estructuración JSON)",
            "/v1/resolver-desafio (Resolución de Retos Math/Obfuscated)",
            "/v1/web-scrape (Extracción Web en Tiempo Real)"
        ]
    }

# --- MODELOS DE PETICIÓN ---
class PeticionJSON(BaseModel):
    texto_crudo: str
    wallet_origen: str

class PeticionDesafio(BaseModel):
    challenge_text: str
    wallet_origen: str

class PeticionScrape(BaseModel):
    url: str
    wallet_origen: str

# -------------------------------------------------------------
# SERVICIO 1: RESOLUCIÓN DE DESAFÍOS Y VERIFICACIÓN (Solve & Verify)
# -------------------------------------------------------------
@app.post("/v1/resolver-desafio")
async def resolver_desafio(peticion: PeticionDesafio):
    await send_discord_alert(f"🧩 **Petición Solve & Verify recibida** desde `{peticion.wallet_origen}`")
    
    prompt = f"""
    Eres un motor especializado en decodificar texto altamente ofuscado y resolver problemas matemáticos de verificación para agentes autónomos.
    
    Texto del reto: "{peticion.challenge_text}"
    
    Instrucciones:
    1. Decodifica las palabras ocultas o separadas por símbolos (ej: "tHReE tY hReE" -> 33, "EiGhT-eEn" -> 18, "fIvEe" -> 5).
    2. Realiza la operación aritmética planteada.
    3. Responde ÚNICAMENTE en este formato JSON estricto:
    {{
      "answer": "28.00",
      "explicacion": "23 + 5 = 28"
    }}
    El campo 'answer' DEBE contener exclusivamente el número con 2 decimales como cadena de texto.
    """

    res = groq_client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.0
    )

    resultado = json.loads(res.choices[0].message.content)
    await send_discord_alert(f"✅ **Reto resuelto con éxito:** Resultado `{resultado.get('answer')}` enviado a `{peticion.wallet_origen}`")
    
    return {
        "status": "success",
        "verification_answer": resultado.get("answer"),
        "details": resultado.get("explicacion")
    }

# -------------------------------------------------------------
# SERVICIO 2: WEB SCRAPING E INTELIGENCIA EN TIEMPO REAL
# -------------------------------------------------------------
@app.post("/v1/web-scrape")
async def web_scrape(peticion: PeticionScrape):
    await send_discord_alert(f"🌐 **Petición Web Scrape recibida** para URL: `{peticion.url}`")
    
    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            res = await client.get(peticion.url, headers={"User-Agent": "CleanJSON-A2A/1.0"}, timeout=12.0)
            if res.status_code != 200:
                raise HTTPException(status_code=400, detail=f"No se pudo acceder a la URL. Código {res.status_code}")
            
            # Limpiar etiquetas HTML simples para entregar texto crudo útil
            texto_limpio = re.sub(r'<[^>]+>', ' ', res.text)
            texto_limpio = ' '.join(texto_limpio.split())[:3000]  # Limitar a los primeros 3k caracteres

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error al raspar la web: {str(e)}")

    await send_discord_alert(f"⚡ **Scraping completado** ({len(texto_limpio)} caracteres extraídos) para `{peticion.wallet_origen}`")
    
    return {
        "status": "success",
        "url": peticion.url,
        "contenido_extraido": texto_limpio
    }

# -------------------------------------------------------------
# SERVICIO 3: ESTRUCTURACIÓN JSON + FILTRO JEV
# -------------------------------------------------------------
@app.post("/v1/procesar-datos")
async def procesar_datos_a2a(peticion: PeticionJSON):
    await send_discord_alert(f"📩 **Petición JSON recibida** desde: `{peticion.wallet_origen}`")

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
        model="llama-3.1-8b-instant",
        messages=[{"role": "system", "content": prompt_sistema}, {"role": "user", "content": peticion.texto_crudo}],
        response_format={"type": "json_object"},
        temperature=0.1
    )

    await send_discord_alert(f"💰 **Servicio JSON completado** para `{peticion.wallet_origen}`.")

    return {
        "status": "success",
        "agente_cliente": peticion.wallet_origen,
        "filtro_jev": {"eleccion": eleccion, "confianza": confianza},
        "resultado": respuesta_groq.choices[0].message.content
    }