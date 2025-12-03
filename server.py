import asyncio
import json
import hmac, hashlib
from aiocoap import resource, Message, Context
from collections import deque
import matplotlib.pyplot as plt
import datetime

SECRET_KEY = b"super_secret_key"
window = deque(maxlen=10)
temperature_log = []
plot_initialized = False
fig = None
last_update_count = 0

def verify_mac(value, mac):
    expected = hmac.new(SECRET_KEY,
                        str(value).encode(),
                        hashlib.sha256).hexdigest()
    return expected == mac

def moving_average(value):
    window.append(value)
    return sum(window) / len(window)

def init_plot():
    """Inizializza il grafico in modalità interattiva"""
    global plot_initialized, fig
    if not plot_initialized:
        plt.ion()  # Modalità interattiva
        fig = plt.figure(figsize=(10, 5))
        plt.title("Temperature Over Time (Live)")
        plt.xlabel("Time")
        plt.ylabel("Temperature (°F)")
        plt.grid(True)
        plot_initialized = True
        print("[GATEWAY] Grafico inizializzato in modalità live")

def update_plot():
    """Aggiorna il grafico con i dati più recenti"""
    global plot_initialized, fig, last_update_count
    if not plot_initialized:
        init_plot()
    
    if not temperature_log:
        return
    
    # Controlla se ci sono nuovi dati da visualizzare
    if len(temperature_log) == last_update_count:
        return
    
    try:
        if fig is None:
            return
        
        plt.figure(fig.number)  # Usa la figura specifica
        plt.clf()  # Pulisce la figura
        
        timestamps = [datetime.datetime.fromisoformat(entry["timestamp"]) for entry in temperature_log]
        temperatures = [entry["temperature"] for entry in temperature_log]
        
        plt.plot(timestamps, temperatures, marker='o', linestyle='-', color='b', linewidth=2, markersize=6)
        plt.title("Temperature Over Time (Live)")
        plt.xlabel("Time")
        plt.ylabel("Temperature (°F)")
        plt.grid(True, alpha=0.3)
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        # Aggiorna la finestra
        fig.canvas.draw()
        fig.canvas.flush_events()
        
        last_update_count = len(temperature_log)
        
    except Exception as e:
        print(f"[GATEWAY] Errore nell'aggiornamento del grafico: {e}")

async def plot_updater():
    """Task asincrono che aggiorna periodicamente il grafico"""
    while True:
        try:
            update_plot()
            await asyncio.sleep(0.5)  # Aggiorna ogni 500ms
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[GATEWAY] Errore nel plot_updater: {e}")
            await asyncio.sleep(1)

def visualize_temperature(save_path=None):
    """Genera e mostra un grafico delle temperature registrate"""
    if not temperature_log:
        print("[GATEWAY] Nessun dato di temperatura da visualizzare")
        return False
    
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
    
    if save_path:
        plt.savefig(save_path)
        plt.close()
        print(f"[GATEWAY] Grafico salvato in {save_path}")
    else:
        plt.show()
    
    return True

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
        
        print("[GATEWAY] MAC verification successful")
        
        # Aggiungi il dato al log per la visualizzazione
        timestamp = datetime.datetime.now().isoformat()
        temperature_log.append({
            "timestamp": timestamp,
            "temperature": value
        })
        print(f"[GATEWAY] Temperature logged: {value}°F at {timestamp}")
        
        # Il grafico verrà aggiornato automaticamente dal task plot_updater

        return Message(payload=b"OK")

class VisualizationResource(resource.Resource):
    """Risorsa per generare e restituire il grafico delle temperature"""
    
    async def render_get(self, request):
        """Genera il grafico e lo salva come PNG"""
        if not temperature_log:
            return Message(payload=b"ERROR: No temperature data available", code=404)
        
        try:
            # Genera il grafico e salvalo
            import io
            import base64
            
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
            
            # Salva in un buffer
            buf = io.BytesIO()
            plt.savefig(buf, format='png')
            plt.close()
            buf.seek(0)
            
            return Message(payload=buf.read(), content_format=50)  # 50 = application/octet-stream
        except Exception as e:
            print(f"[GATEWAY] Error generating visualization: {e}")
            return Message(payload=f"ERROR: {str(e)}".encode(), code=500)

async def main():
    # Inizializza il grafico all'avvio
    init_plot()
    
    # Avvia il task per aggiornare il grafico periodicamente
    plot_task = asyncio.create_task(plot_updater())
    
    root = resource.Site()
    root.add_resource(('temperature',), TemperatureResource())
    root.add_resource(('visualize',), VisualizationResource())

    print("[GATEWAY] Server running...")
    print("[GATEWAY] Grafico live attivo - si aggiornerà automaticamente")
    context = await Context.create_server_context(root, bind=('10.17.253.229', 5683))
    print(f"[GATEWAY] Listening on coap://10.17.253.229:5683/temperature")
    print(f"[GATEWAY] Visualization available at coap://10.17.253.229:5683/visualize")
    
    try:
        await asyncio.get_running_loop().create_future()
    finally:
        plot_task.cancel()
        try:
            await plot_task
        except asyncio.CancelledError:
            pass

asyncio.run(main())
