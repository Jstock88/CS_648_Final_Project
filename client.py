import asyncio
import json
import hmac
import hashlib
import random
from aiocoap import Context, Message, PUT

SECRET_KEY = b"super_secret_key"

# Function to calculate HMAC for security
def generate_mac(value):
    return hmac.new(SECRET_KEY, str(value).encode(), hashlib.sha256).hexdigest()

# Send a PUT request to the server to update the temperature
async def send_temperature(temperature_value):
    # Prepare the payload with a temperature value and its MAC
    payload = {
        "Temperature": temperature_value,
        "mac": generate_mac(temperature_value)
    }
    
    # Create a message
    message = Message(code=PUT, payload=json.dumps(payload).encode())
    message.set_request_uri("coap://10.127.57.25:5683/temperature")

    # Create a CoAP context and send the message
    context = await Context.create_client_context()
    await context.request(message).response()  # Send request, no need to capture the response

    # Print the sent temperature
    print(f"Sent temperature: {temperature_value}°F")

# Send 20 random temperatures to the server
async def send_random_temperatures():
    for _ in range(20):
        # Generate a random temperature value between 60 and 100°F
        temperature = random.randint(60, 100)
        await send_temperature(temperature)
        await asyncio.sleep(1)  # Wait for 1 second before sending the next temperature

# Run the client to send random temperatures
asyncio.run(send_random_temperatures())
