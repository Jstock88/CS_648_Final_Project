import asyncio
import json
import hmac, hashlib
from aiocoap import resource, Message, Context
import matplotlib.pyplot as plt
import datetime
import re

# Secret key for HMAC verification (keep secure in production)
SECRET_KEY = b"super_secret_key"

# In-memory log of received temperature samples
temperature_log = []

# Plot state for live display
plot_initialized = False
fig = None
last_update_count = 0

def verify_mac(value, mac):
    """
    Verify HMAC-SHA256 of the numeric value using SECRET_KEY.
    Returns True if the provided mac matches the expected value.
    """
    expected = hmac.new(SECRET_KEY,
                        str(value).encode(),
                        hashlib.sha256).hexdigest()
    return expected == mac


def init_plot():
    """
    Initialize a matplotlib figure for interactive plotting.
    This enables real-time updates when update_plot is called frequently.
    """
    global plot_initialized, fig
    if not plot_initialized:
        plt.ion()
        fig = plt.figure(figsize=(10, 5))
        plt.title("Temperature Over Time (Live)")
        plt.xlabel("Time")
        plt.ylabel("Temperature (°F)")
        plt.grid(True)
        plot_initialized = True

def update_plot():
    """
    Redraw the live plot if there are new temperature entries.
    """
    global plot_initialized, fig, last_update_count
    if not plot_initialized:
        init_plot()
    
    if not temperature_log:
        return
    
    if len(temperature_log) == last_update_count:
        return
    
    try:
        if fig is None:
            return
        
        plt.figure(fig.number)
        plt.clf()
        
        timestamps = [datetime.datetime.fromisoformat(entry["timestamp"]) for entry in temperature_log]
        temperatures = [entry["temperature"] for entry in temperature_log]
        
        plt.plot(timestamps, temperatures, marker='o', linestyle='-', color='b', linewidth=2, markersize=6)
        plt.title("Temperature Over Time (Live)")
        plt.xlabel("Time")
        plt.ylabel("Temperature (°F)")
        plt.grid(True, alpha=0.3)
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        fig.canvas.draw()
        fig.canvas.flush_events()
        
        last_update_count = len(temperature_log)
        
    except Exception as e:
        print(f"Error with updating plot: {e}")

#updates plot ayschonously every 0.5 seconds
async def plot_updater():
    while True:
        try:
            update_plot()
            await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Error : {e}")
            await asyncio.sleep(1)


class TemperatureResource(resource.Resource):
    """
    CoAP resource that accepts PUT requests with temperature data.
    Expected payload: JSON containing a temperature value and a MAC (HMAC) for verification.
    """

    async def render_put(self, request):
        try:
            payload_str = request.payload.decode('utf-8', errors='ignore').strip()
            
            payload_str = payload_str.strip()
            payload_str = payload_str.replace('\x00', '')
            payload_str = ''.join(char for char in payload_str if ord(char) >= 32 or char in '\n\r\t')
            
            try:
                payload = json.loads(payload_str)
            except json.JSONDecodeError:
                match = re.search(r'["\']?Temperature["\']?\s*:\s*(\d+)', payload_str, re.IGNORECASE)
                if match:
                    value = int(match.group(1))
                    print(f"[GATEWAY] Extracted temperature from malformed JSON: {value}°F")
                    return Message(payload=b"OK")
                else:
                    raise
            print(f"[GATEWAY] Parsed payload: {payload}")
            
            value = None
            if "Temperature" in payload:
                value = payload["Temperature"]
            elif "temperature" in payload:
                value = payload["temperature"]
            else:
                for key in payload.keys():
                    if "temperature" in key.lower():
                        value = payload[key]
                        break
            
            if value is not None:
                print(f"[GATEWAY] Temperature value: {value}°F")
            else:
                print(f"[GATEWAY] Warning: Could not find temperature key in {payload}")
                return Message(payload=b"OK")
            
            mac = payload.get("mac") or payload.get("MAC")
            if not mac:
                print("[GATEWAY] ERROR: MAC missing from payload")
                return Message(payload=b"ERROR: MAC missing")
        except json.JSONDecodeError as e:
            print(f"[GATEWAY] Error decoding JSON: {e}")
            print(f"[GATEWAY] Raw payload (bytes): {request.payload}")
            print(f"[GATEWAY] Raw payload (hex): {request.payload.hex()}")
            try:
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

        if not verify_mac(value, mac):
            print("[GATEWAY] INVALID MAC – DATA REJECTED")
            return Message(payload=b"ERROR: invalid MAC")
        
        print("[GATEWAY] MAC verification successful")
        
        timestamp = datetime.datetime.now().isoformat()
        temperature_log.append({
            "timestamp": timestamp,
            "temperature": value
        })
        print(f"[GATEWAY] Temperature logged: {value}°F at {timestamp}")
        

        return Message(payload=b"OK")


async def main():
    """
    Start the CoAP server, initialize live plotting, and run until interrupted.
    """
    init_plot()
    
    plot_task = asyncio.create_task(plot_updater())
    
    root = resource.Site()
    root.add_resource(('temperature',), TemperatureResource())

    print("[GATEWAY] Server running...")
    context = await Context.create_server_context(root, bind=('10.127.57.25', 5683))
    print(f"[GATEWAY] Listening on coap://10.127.57.25:5683/temperature")
    
    try:
        await asyncio.get_running_loop().create_future()
    finally:
        plot_task.cancel()
        try:
            await plot_task
        except asyncio.CancelledError:
            pass

asyncio.run(main())
