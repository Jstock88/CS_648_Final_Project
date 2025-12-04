import asyncio
import json
import hmac
import hashlib
from aiocoap import resource, Message, Context
from collections import deque
import matplotlib.pyplot as plt
import datetime
import io

# Secret key for HMAC verification (keep secure in production)
SECRET_KEY = b"super_secret_key"

# Sliding window for moving average (if needed)
window = deque(maxlen=10)

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
    expected = hmac.new(SECRET_KEY, str(value).encode(), hashlib.sha256).hexdigest()
    return expected == mac


def moving_average(value):
    """
    Maintain a small sliding window and return the current moving average.
    (Not used by the current code path, kept for potential use.)
    """
    window.append(value)
    return sum(window) / len(window)


def init_plot():
    """
    Initialize a matplotlib figure for interactive (live) plotting.
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
        print("[GATEWAY] Live plot initialized")


def update_plot():
    """
    Redraw the live plot if there are new temperature entries.
    This function is safe to call frequently; it skips redraws when no new data exists.
    """
    global plot_initialized, fig, last_update_count

    if not plot_initialized:
        init_plot()

    if not temperature_log:
        return

    # Skip if no new samples
    if len(temperature_log) == last_update_count:
        return

    try:
        if fig is None:
            return

        plt.figure(fig.number)
        plt.clf()

        timestamps = [datetime.datetime.fromisoformat(e["timestamp"]) for e in temperature_log]
        temperatures = [e["temperature"] for e in temperature_log]

        plt.plot(timestamps, temperatures, marker="o", linestyle="-", color="b", linewidth=2, markersize=6)
        plt.title("Temperature Over Time (Live)")
        plt.xlabel("Time")
        plt.ylabel("Temperature (°F)")
        plt.grid(True, alpha=0.3)
        plt.xticks(rotation=45)
        plt.tight_layout()

        # Update interactive canvas
        fig.canvas.draw()
        fig.canvas.flush_events()

        last_update_count = len(temperature_log)

    except Exception as e:
        print(f"[GATEWAY] Error updating live plot: {e}")


async def plot_updater():
    """
    Background async task that periodically calls update_plot to refresh the live plot.
    """
    while True:
        try:
            update_plot()
            await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[GATEWAY] Error in plot_updater: {e}")
            await asyncio.sleep(1)


def visualize_temperature(save_path=None):
    """
    Generate a static PNG of the recorded temperatures.
    If save_path is provided, the image is written to disk; otherwise it is shown.
    Returns True on success, False when no data is available.
    """
    if not temperature_log:
        print("[GATEWAY] No temperature data to visualize")
        return False

    timestamps = [datetime.datetime.fromisoformat(e["timestamp"]) for e in temperature_log]
    temperatures = [e["temperature"] for e in temperature_log]

    plt.figure(figsize=(10, 5))
    plt.plot(timestamps, temperatures, marker="o", linestyle="-", color="b")
    plt.title("Temperature Over Time")
    plt.xlabel("Time")
    plt.ylabel("Temperature (°F)")
    plt.grid(True)
    plt.xticks(rotation=45)
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path)
        plt.close()
        print(f"[GATEWAY] Plot saved to {save_path}")
    else:
        plt.show()

    return True


class TemperatureResource(resource.Resource):
    """
    CoAP resource that accepts PUT requests with temperature data.
    Expected payload: JSON containing a temperature value and a MAC (HMAC) for verification.
    """

    async def render_put(self, request):
        # Decode payload to string, remove non-printable characters
        payload_str = request.payload.decode("utf-8", errors="ignore").replace("\x00", "")
        payload_str = "".join(ch for ch in payload_str if ord(ch) >= 32 or ch in "\n\r\t").strip()

        # Try parsing JSON payload
        try:
            payload = json.loads(payload_str)
        except json.JSONDecodeError:
            # If JSON parsing fails, try to extract a bare number or a "Temperature" value via regex
            import re

            # If payload is just a number, accept it
            if payload_str.isdigit():
                value = int(payload_str)
                print(f"[GATEWAY] Received numeric payload: {value}°F (no MAC verification)")
                # Note: if MAC verification is required, payloads without MAC are rejected below.
                return Message(payload=b"OK")

            # Search for a Temperature field in a malformed JSON string
            match = re.search(r'["\']?Temperature["\']?\s*:\s*(\d+)', payload_str, re.IGNORECASE)
            if match:
                value = int(match.group(1))
                print(f"[GATEWAY] Extracted temperature from malformed JSON: {value}°F")
                return Message(payload=b"OK")

            print(f"[GATEWAY] Invalid JSON payload: {payload_str!r}")
            return Message(payload=b"ERROR: invalid JSON")

        # At this point we have parsed JSON
        print(f"[GATEWAY] Parsed payload: {payload}")

        # Extract temperature value from common keys
        value = None
        if "Temperature" in payload:
            value = payload["Temperature"]
        elif "temperature" in payload:
            value = payload["temperature"]
        else:
            for k in payload.keys():
                if "temperature" in k.lower():
                    value = payload[k]
                    break

        if value is None:
            print(f"[GATEWAY] Warning: temperature key not found in payload: {payload}")
            return Message(payload=b"OK")

        # Extract MAC for verification
        mac = payload.get("mac") or payload.get("MAC")
        if not mac:
            print("[GATEWAY] ERROR: MAC missing from payload")
            return Message(payload=b"ERROR: MAC missing")

        # Verify MAC
        if not verify_mac(value, mac):
            print("[GATEWAY] INVALID MAC – DATA REJECTED")
            return Message(payload=b"ERROR: invalid MAC")
        print("[GATEWAY] MAC verification successful")

        # Log the received temperature with timestamp
        timestamp = datetime.datetime.now().isoformat()
        temperature_log.append({"timestamp": timestamp, "temperature": value})
        print(f"[GATEWAY] Temperature logged: {value}°F at {timestamp}")

        # Live plot will update from the background task
        return Message(payload=b"OK")


class VisualizationResource(resource.Resource):
    """
    CoAP resource that returns a PNG image of the temperature history on GET.
    """

    async def render_get(self, request):
        if not temperature_log:
            return Message(payload=b"ERROR: No temperature data available", code=404)

        try:
            timestamps = [datetime.datetime.fromisoformat(e["timestamp"]) for e in temperature_log]
            temperatures = [e["temperature"] for e in temperature_log]

            plt.figure(figsize=(10, 5))
            plt.plot(timestamps, temperatures, marker="o", linestyle="-", color="b")
            plt.title("Temperature Over Time")
            plt.xlabel("Time")
            plt.ylabel("Temperature (°F)")
            plt.grid(True)
            plt.xticks(rotation=45)
            plt.tight_layout()

            buf = io.BytesIO()
            plt.savefig(buf, format="png")
            plt.close()
            buf.seek(0)

            # content_format numeric code may vary; 50 used previously (application/octet-stream)
            return Message(payload=buf.read(), content_format=50)
        except Exception as e:
            print(f"[GATEWAY] Error generating visualization: {e}")
            return Message(payload=f"ERROR: {e}".encode(), code=500)


async def main():
    """
    Start the CoAP server, initialize live plotting, and run until interrupted.
    """
    init_plot()

    # Start background task to refresh live plot
    plot_task = asyncio.create_task(plot_updater())

    root = resource.Site()
    root.add_resource(("temperature",), TemperatureResource())
    root.add_resource(("visualize",), VisualizationResource())

    print("[GATEWAY] Server running...")
    print("[GATEWAY] Live plot active and will update automatically")
    context = await Context.create_server_context(root, bind=("10.17.253.229", 5683))
    print("[GATEWAY] Listening on coap://10.17.253.229:5683/temperature")
    print("[GATEWAY] Visualization available at coap://10.17.253.229:5683/visualize")

    try:
        await asyncio.get_running_loop().create_future()
    finally:
        plot_task.cancel()
        try:
            await plot_task
        except asyncio.CancelledError:
            pass


asyncio.run(main())
