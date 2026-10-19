import os
import asyncio
import json
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import groq

# -------------------------------------------------------------
# 1. Variables de Entorno
# -------------------------------------------------------------
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
BEATAPI_KEY = os.environ.get("BEATAPI_KEY")
MOLTBOOK_API_KEY = os.environ.get("MOLTBOOK_API_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

groq_client = groq.Groq(api_key=GROQ_API_KEY)

async def send_discord_alert(mensaje: str):
    """Envía actualizaciones detalladas de las decisiones del agente a Discord"""
    if not DISCORD_WEBHOOK_URL:
        return
    async with httpx.AsyncClient() as client:
        try:
            await client.post(DISCORD_WEBHOOK_URL, json={"content": mensaje})
        except Exception as e:
            print(f"⚠️ Error al enviar alerta a Discord: {e}")

# -------------------------------------------------------------
# 2. Ciclo Social Autónomo (Heartbeat + Decisión + Respuesta)
# -------------------------------------------------------------
async def moltbook_autonomy_loop():
    """El agente lee, razona con Groq, actúa en Moltbook e informa en Discord"""
    if not MOLTBOOK_API_KEY:
        print("⚠️ MOLTBOOK_API_KEY no configurada. Omitiendo ciclo autónomo.")
        return

    headers = {"Authorization": f"Bearer {MOLTBOOK_API_KEY}"}
    await asyncio.sleep(10) # Espera inicial
    
    async with httpx.AsyncClient() as client:
        while True:
            try:
                # PASO 1: PERCIBIR (Consultar dashboard /home)
                res = await client.get("https://www.moltbook.com/api/v1/home", headers=headers, timeout=10.0)
                if res.status_code == 200:
                    data = res.json()
                    activity = data.get("activity_on_your_posts", [])
                    unread_count = data.get("your_account", {}).get("unread_notification_count", 0)

                    # Si hay actividad/comentarios no leídos en nuestras publicaciones
                    if unread_count > 0 and activity:
                        for item in activity:
                            post_id = item.get("post_id")
                            post_title = item.get("post_title")
                            latest_preview = item.get("preview", "Nuevo comentario recibido")

                            # Obtener los comentarios específicos de esa publicación
                            comments_res = await client.get(
                                f"https://www.moltbook.com/api/v1/posts/{post_id}/comments?sort=new", 
                                headers=headers, 
                                timeout=10.0
                            )
                            
                            if comments_res.status_code == 200:
                                comments_data = comments_res.json()
                                comments_list = comments_data.get("comments", [])
                                
                                if comments_list:
                                    last_comment = comments_list[0]
                                    comment_id = last_comment.get("id")
                                    comment_text = last_comment.get("content", "")
                                    author_name = last_comment.get("author", {}).get("name", "Otro Agente")

                                    # PASO 2: RAZONAR (Groq decide si vale la pena responder y genera el texto)
                                    prompt_decision = f"""
                                    Eres GeminiDataAgent en Moltbook.
                                    Un agente llamado '{author_name}' comentó en tu post '{post_title}':
                                    "{comment_text}"

                                    Analiza si este comentario requiere respuesta.
                                    Devuelve ÚNICAMENTE un objeto JSON estricto:
                                    {{
                                      "debe_responder": true,
                                      "razon": "Explicación breve de por qué decidiste responder o no",
                                      "respuesta_propuesta": "Tu respuesta en 1 o 2 oraciones, amable y profesional"
                                    }}
                                    """

                                    decision_groq = groq_client.chat.completions.create(
                                        model="llama-3.3-70b-versatile",
                                        messages=[{"role": "user", "content": prompt_decision}],
                                        response_format={"type": "json_object"},
                                        temperature=0.3
                                    )

                                    analisis = json.loads(decision_groq.choices[0].message.content)

                                    # PASO 3: ACTUAR Y REPORTAR A DISCORD
                                    if analisis.get("debe_responder"):
                                        texto_respuesta = analisis.get("respuesta_propuesta")
                                        
                                        # Publicar comentario en Moltbook
                                        res_reply = await client.post(
                                            f"https://www.moltbook.com/api/v1/posts/{post_id}/comments",
                                            headers=headers,
                                            json={"content": texto_respuesta, "parent_id": comment_id},
                                            timeout=10.0
                                        )

                                        # Enviar reporte completo a Discord
                                        reporte_discord = (
                                            f"🤖 **Acción Autónoma de GeminiDataAgent en Moltbook**\n"
                                            f"📩 **Notificación recibida:** `{author_name}` en el post *'{post_title}'*\n"
                                            f"💬 **Comentario original:** \"{comment_text}\"\n"
                                            f"🧠 **Razonamiento del Agente:** {analisis.get('razon')}\n"
                                            f"✍️ **Respuesta publicada:** \"{texto_respuesta}\""
                                        )
                                        await send_discord_alert(reporte_discord)
                                    else:
                                        # Reportar a Discord que se revisó pero no requería respuesta
                                        await send_discord_alert(
                                            f"👀 **Notificación revisada:** Comentario de `{author_name}` en *'{post_title}'*. "
                                            f"Decisión: No requiere respuesta. Motivo: {analisis.get('razon')}"
                                        )

                            # Marcar las notificaciones de esta publicación como leídas tras procesarlas
                            await client.post(
                                f"https://www.moltbook.com/api/v1/notifications/read-by-post/{post_id}", 
                                headers=headers
                            )

            except Exception as e:
                print(f"Error en bucle autónomo: {e}")

            # Esperar 30 minutos entre ciclos de revisión
            await asyncio.sleep(1800)

# -------------------------------------------------------------
# 3. Configuración de FastAPI Lifespan
# -------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(moltbook_autonomy_loop())
    await send_discord_alert("🚀 **GeminiDataAgent activo:** Servidor en línea y sistema autónomo de Moltbook iniciado.")
    yield

app = FastAPI(title="Agente Extractor & Formateador A2A", lifespan=lifespan)

class PeticionAgente(BaseModel):
    texto_crudo: str
    wallet_origen: str

# -------------------------------------------------------------
# 4. Endpoint Monetizado A2A
# -------------------------------------------------------------
@app.post("/v1/procesar-datos")
async def procesar_datos_a2a(peticion: PeticionAgente):
    await send_discord_alert(f"📩 **Petición A2A pagada recibida** desde la billetera: `{peticion.wallet_origen}`")

    payload_jev = {
        "model": "jev-1.13-free",
        "state": {"id": "peticion-a2a", "text": peticion.texto_crudo},
        "questions": {
            "clasificacion": {
                "type": "choice",
                "instructions": "Clasifica la validez del texto.",
                "criteria": {
                    "valido": "Texto procesable o útil.",
                    "invalido": "Texto vacío, corrupto o spam."
                }
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
        messages=[
            {"role": "system", "content": prompt_sistema},
            {"role": "user", "content": peticion.texto_crudo}
        ],
        response_format={"type": "json_object"},
        temperature=0.1
    )

    await send_discord_alert(f"💰 **Servicio A2A completado con éxito** para `{peticion.wallet_origen}`.")

    return {
        "status": "success",
        "agente_cliente": peticion.wallet_origen,
        "filtro_jev": {"eleccion": eleccion, "confianza": confianza},
        "resultado": respuesta_groq.choices[0].message.content
    }
