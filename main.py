from fastapi import FastAPI, Form
from fastapi.responses import PlainTextResponse
from twilio.rest import Client
import anthropic
import httpx
import os

app = FastAPI()

# Clients
anthropic_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
twilio_client = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])

TWILIO_WHATSAPP_NUMBER = "whatsapp:+14155238886"
SHEETS_CSV_URL = os.environ["SHEETS_CSV_URL"]

# Historique des conversations (en mémoire)
conversations = {}

SYSTEM_PROMPT = """Tu es l'assistant IA du King Night Club à Dakar. 
Tu aides le gérant à gérer le nightclub via WhatsApp.

Tu as accès aux données du Google Sheets (Z Caisse, CA par bar, dépenses).
Tu réponds toujours en français, de façon courte et directe.

Tu peux :
- Donner l'état des ventes (CA par bar, par mode de paiement, par jour)
- Donner les totaux Cash, Wave, OM, CB
- Calculer les dépenses et le net
- Répondre à des questions sur les chiffres de la semaine

Les zones sont : BAR DU BAS, PATIO/VIP, ENTREE
Les modes de paiement : Cash, Wave, OM, CB

Sois concis - tu réponds sur WhatsApp donc max 3-4 lignes par réponse.
"""

async def get_sheets_data():
    """Récupère les données du Google Sheets"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(SHEETS_CSV_URL, timeout=10)
            return response.text[:3000]  # Limite pour le contexte
    except Exception as e:
        return f"Erreur lecture Sheets: {str(e)}"

@app.post("/whatsapp", response_class=PlainTextResponse)
async def whatsapp_webhook(
    From: str = Form(...),
    Body: str = Form(...)
):
    user_number = From
    user_message = Body.strip()
    
    print(f"Message de {user_number}: {user_message}")
    
    # Récupérer l'historique
    if user_number not in conversations:
        conversations[user_number] = []
    
    # Récupérer les données du Sheets
    sheets_data = await get_sheets_data()
    
    # Construire le contexte
    context = f"""Données actuelles du Google Sheets King Night Club:

{sheets_data}

---
Question du gérant: {user_message}"""
    
    # Ajouter à l'historique
    conversations[user_number].append({
        "role": "user",
        "content": context
    })
    
    # Garder seulement les 10 derniers messages
    if len(conversations[user_number]) > 10:
        conversations[user_number] = conversations[user_number][-10:]
    
    # Appel Claude
    try:
        response = anthropic_client.messages.create(
            model="claude-OPUS-4-5",
            max_tokens=500,
            system=SYSTEM_PROMPT,
            messages=conversations[user_number]
        )
        
        reply = response.content[0].text
        
        # Ajouter la réponse à l'historique
        conversations[user_number].append({
            "role": "assistant",
            "content": reply
        })
        
        # Envoyer via Twilio
        twilio_client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            to=user_number,
            body=reply
        )
        
        return "OK"
        
    except Exception as e:
        error_msg = f"Erreur: {str(e)}"
        twilio_client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            to=user_number,
            body="Désolé, une erreur s'est produite. Réessaie dans un moment."
        )
        return error_msg

@app.get("/")
def root():
    return {"status": "King Night Club Agent actif ✅"}
