import os
import httpx
import asyncio
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from retell import Retell
from dotenv import load_dotenv
import telnyx

# .env-Datei laden
load_dotenv(override=True)

app = FastAPI()
retell = Retell(api_key=os.getenv("RETELL_API_KEY"))
telnyx.api_key = os.getenv("TELNYX_API_KEY")
AGENT_PHONE_NUMBER = os.getenv("AGENT_PHONE_NUMBER")

# Model für externe API-Aufrufe
class Item(BaseModel):
    phone: str

async def send_data(url, item: Item):
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=item.model_dump())
        if response.status_code not in range(200, 300):
            raise HTTPException(status_code=response.status_code, detail="Error calling external API")
        return response.json()

@app.post("/webhook")
async def handle_telnyx_webhook(request: Request):
    try:
        data = await request.json()
    except Exception as e:
        print(f"Error parsing JSON: {e}")
        return JSONResponse(status_code=400, content={"message": "Invalid JSON"})

    event_type = data.get('data', {}).get('event_type')
    call_control_id = data.get('data', {}).get('call_control_id')
    call_id = data.get('data', {}).get('call_id')
    from_number = data.get('data', {}).get('from')
    to_number = data.get('data', {}).get('to')

    print(f"Received event: {event_type}, Call Control ID: {call_control_id}")

    if event_type in ['call.initiated', 'call.answered']:
        try:
            call_response = retell.call.register(
                agent_id=os.getenv("RETELL_AGENT_ID"),
                audio_websocket_protocol="telnyx",
                audio_encoding="mulaw",
                sample_rate=8000,
                from_number=from_number,
                to_number=to_number,
                metadata={"telnyx_call_control_id": call_control_id}
            )
            return JSONResponse({
                "status": "success",
                "call_id": call_response.call_id,
                "instruction": "Telnyx should handle the WebSocket connection based on call_control_id"
            })
        except Exception as e:
            print(f"Error registering call with Retell.ai: {e}")
            return JSONResponse(status_code=500, content={"message": "Internal Server Error"})

    elif event_type == 'call.transfer':
        try:
            call = telnyx.Call.retrieve(call_control_id)
            call.transfer(to=AGENT_PHONE_NUMBER)
            print(f"Call {call_control_id} transferred to {AGENT_PHONE_NUMBER}")
            return JSONResponse({"status": "success"})
        except Exception as e:
            print(f"Error transferring call: {e}")
            return JSONResponse(status_code=500, content={"message": str(e)})

    return JSONResponse({"status": "ignored"})

@app.post("/transfer")
async def manual_transfer(request: Request):
    data = await request.json()
    call_control_id = data.get('call_control_id')

    if call_control_id:
        try:
            call = telnyx.Call.retrieve(call_control_id)
            call.transfer(to=AGENT_PHONE_NUMBER)
            print(f"Call {call_control_id} transferred to {AGENT_PHONE_NUMBER}")
            return JSONResponse({"status": "success"})
        except Exception as e:
            print(f"Error transferring call: {e}")
            return JSONResponse(status_code=500, content={"message": str(e)})
    return JSONResponse(status_code=400, content={"status": "error", "message": "Call control ID missing"})

@app.get("/test")
async def test_route():
    return {"message": "Server is working!"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
