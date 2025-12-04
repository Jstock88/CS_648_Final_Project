import matplotlib.pyplot as plt
import datetime

# Sample temperature_log
temperature_log = [
    {"timestamp": "2025-12-03T15:00:00", "temperature": 72},
    {"timestamp": "2025-12-03T15:05:00", "temperature": 73},
    {"timestamp": "2025-12-03T15:10:00", "temperature": 75},
    {"timestamp": "2025-12-03T15:15:00", "temperature": 74},
    {"timestamp": "2025-12-03T15:20:00", "temperature": 76},
]


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