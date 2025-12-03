import asyncio
import json
import hmac, hashlib
from aiocoap import resource, Message, Context
from collections import deque
import datetime
import matplotlib.pyplot as plt

SECRET_KEY = b"super_secret_key"
window = deque(maxlen=10)
temperature_log = []

def verify_mac(value, mac):
    expected = hmac.new(SECRET_KEY,
                        str(value).encode(),
                        hashlib.sha256).hexdigest()
    return expected == mac

def moving_average(value):
    window.append(value)
    return sum(window) / len(window)

class TemperatureResource(resource.Resource):


    async def render_put(self, request):
        try:
            payload_str = request.payload.decode('utf-8', errors='ignore').strip()
           
            # Pulisci il payload da caratteri non validi
            payload_str = payload_str.strip()
            # Rimuovi eventuali caratteri null
            payload_str = payload_str.replace('\x00', '')
            # Rimuovi eventuali caratteri di controllo
            payload_str = ''.join(char for char in payload_str if ord(char) >= 32 or char in '\n\r\t')
           
            # Prova a parsare come JSON
            try:
                payload = json.loads(payload_str)
            except json.JSONDecodeError:
                # Se fallisce, prova a estrarre manualmente il valore
                # Cerca pattern come {"Temperature": 75} o simili
                import re
                match = re.search(r'["\']?Temperature["\']?\s*:\s*(\d+)', payload_str, re.IGNORECASE)
                if match:
                    value = int(match.group(1))
                    print(f"[GATEWAY] Extracted temperature from malformed JSON: {value}°F")
                    return Message(payload=b"OK")
                else:
                    raise  # Rilancia l'eccezione originale
            print(f"[GATEWAY] Parsed payload: {payload}")
           
            # Estrai il valore della temperatura
            value = None
            if "Temperature" in payload:
                value = payload["Temperature"]
            elif "temperature" in payload:
                value = payload["temperature"]
            else:
                # Cerca qualsiasi chiave che contenga "temperature"
                for key in payload.keys():
                    if "temperature" in key.lower():
                        value = payload[key]
                        break
           
            if value is not None:
                print(f"[GATEWAY] Temperature value: {value}°F")
            else:
                print(f"[GATEWAY] Warning: Could not find temperature key in {payload}")
                return Message(payload=b"OK")
           
            # Estrai il MAC dal payload
            mac = payload.get("mac") or payload.get("MAC")
            if not mac:
                print("[GATEWAY] ERROR: MAC missing from payload")
                return Message(payload=b"ERROR: MAC missing")
        except json.JSONDecodeError as e:
            print(f"[GATEWAY] Error decoding JSON: {e}")
            print(f"[GATEWAY] Raw payload (bytes): {request.payload}")
            print(f"[GATEWAY] Raw payload (hex): {request.payload.hex()}")
            # Prova a parsare come stringa semplice se non è JSON
            try:
                # Se il payload è solo un numero
                if payload_str.isdigit():
                    value = int(payload_str)
                    print(f"[GATEWAY] Interpreted as integer: {value}°F")
                    return Message(payload=b"OK")
            except:
                pass
            return Message(payload=b"ERROR: invalid JSON")
        except Exception as e:
            print(f"[GATEWAY] Error processing request: {e}")
            return Message(payload=b"ERROR")

        # SECURITY - Verifica MAC
        if not verify_mac(value, mac):
            print("[GATEWAY] INVALID MAC – DATA REJECTED")
            return Message(payload=b"ERROR: invalid MAC")
        
        #data collection for visual
        timestamp = datetime.datetime.now().isoformat()
        log_entry = {"timestamp": timestamp, "temperature": value}
        temperature_log.append(log_entry)

        timestamps = [datetime.datetime.fromisoformat(entry["timestamp"]) for entry in temperature_log]
        temperatures = [entry["temperature"] for entry in temperature_log]

        plt.figure(figsize=(10, 5))
        plt.plot(timestamps, temperatures, marker='o', linestyle='-', color='b')
        plt.title("Temperature Over Time")
        plt.xlabel("Time")
        plt.ylabel("Temperature (°F)")
        plt.grid(True)
        plt.xticks(rotation=45)
        plt.tight_layout()

        plt.show()
       
        print("[GATEWAY] MAC verification successful")

        # EDGE PROCESSING
        #avg = round(moving_average(value), 2)

        # LOGGING
        #print(f"[GATEWAY] VALID | Temp: {value}°C | Avg: {avg}°C")

        return Message(payload=b"OK")

async def main():
    root = resource.Site()
    root.add_resource(('temperature',), TemperatureResource())

    print("[GATEWAY] Server running...")
    context = await Context.create_server_context(root, bind=('10.17.253.229', 5683))
    print(f"[GATEWAY] Listening on coap://10.17.253.229:5683/temperature")
    await asyncio.get_running_loop().create_future()

asyncio.run(main())