import os
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import groq

app = FastAPI(title="Agente Extractor & Formateador A2A")

# Variables de entorno
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
BEATAPI_KEY = os.environ.get("BEATAPI_KEY")

groq_client = groq.Groq(api_key=GROQ_API_KEY)

class PeticionAgente(BaseModel):
    texto_crudo: str
    wallet_origen: str

@app.post("/v1/procesar-datos")
async def procesar_datos_a2a(peticion: PeticionAgente):
    
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
            raise HTTPException(status_code=500, detail=f"Error al conectar con JEV: {str(e)}")

    if res_jev.status_code != 200:
        raise HTTPException(
            status_code=res_jev.status_code, 
            detail=f"JEV API Error: {res_jev.text}"
        )

    datos_jev = res_jev.json()
    
    # Lectura del resultado estructurado (Decision Types)
    respuesta_categoria = datos_jev.get("answers", {}).get("clasificacion", {})
    eleccion = respuesta_categoria.get("choice")
    confianza = respuesta_categoria.get("confidence", 0)

    # Si JEV rechaza la entrada o la confianza es baja, se descarta antes de consumir Groq
    if eleccion != "valido" or confianza < 0.75:
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

    return {
        "status": "success",
        "agente_cliente": peticion.wallet_origen,
        "filtro_jev": {"eleccion": eleccion, "confianza": confianza},
        "resultado": respuesta_groq.choices[0].message.content
    }