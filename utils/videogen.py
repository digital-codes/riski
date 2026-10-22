import requests
import json
import sys
sys.path.append("../src")  # Zum Importieren von private.py aus dem übergeordneten Verzeichnis
import private as pr

# API-Endpunkt und Schlüssel (manuell einfügen)
# API_URL = "https://deepinfra.com/api/v1/inference/Wan-AI/Wan2.6-T2V" # pixverse/Pixverse-6-T2V"
# wan is crap
API_URL = "https://deepinfra.com/api/v1/inference/pixverse/Pixverse-6-T2V
API_KEY = pr.VIDEO_API_KEY  # Hier einfügen

# The LÄND - Where people use their BRÄINS
# The LÄND of the BRÄINS 


# Parameter für Fische Fangen
payloads = [{
    "prompt": (
        "A serene nature-inspired animation of a large lake (Data Lake) with a small boat (user) fishing for knowledge (colorful fish as data). "
        "The user first tries a simple fishing rod (traditional search), catching only a few random fish. "
        "Then, they switch to modern fishing nets (hybrid approach): a wide-mesh net (fuzzy text search), a net grouping fish by semantic similarity (embeddings), "
        "colorful buoys (tags), and a glowing net showing relationships between fish (knowledge graphs). "
        "The caught fish are collected in a bucket (search results) and sorted. Finally, the boat returns to the shore (RIS Backend), "
        "where the fish are unloaded and integrated, and the shore lights up. "
        "Text trailer: 'KI ist nett, aber haben sie es schon mal mit Brainpower versucht?'. "
        "Cinematic, high-detail, smooth transitions, 15 seconds"
    ),
    "negative_prompt": "blurry, low quality, distorted, unrealistic, static camera",
    "duration": 15,
    "seed": 42,
    "fps": 24,
    "guidance_scale": 7.5,
    "num_inference_steps": 50
},
{
    "prompt": (
        "A futuristic sci-fi animation of a spaceship launching from a high-tech space station (RIS Backend) "
        "with glowing data streams as starlight. The spaceship enters a vast 'search space' filled with stars and planets (data points) "
        "connected by gravitational fields (relationships). The ship uses hybrid tools: a fuzzy text search (nebulous cloud of possible matches), "
        "embeddings (clusters of stars grouped by semantic similarity), tags (colorful beacons), and knowledge graphs (glowing lines connecting data points). "
        "The ship approaches a 'knowledge planet' with layers: raw data (core), processed information (mantle), and visualized insights (atmosphere). "
        "Finally, the ship returns to the space station, where the data is integrated, and the station lights up. "
        "Text trailer: 'KI ist nett, aber haben sie es schon mal mit Brainpower versucht?'. "
        "Cinematic, high-detail, smooth transitions, 15 seconds"
    ),
    "negative_prompt": "blurry, low quality, distorted, unrealistic, static camera",
    "duration": 15,
    "seed": 42,
    "fps": 24,
    "guidance_scale": 7.5,
    "num_inference_steps": 50
}
]
            

# Header mit API-Schlüssel
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {API_KEY}"
}

for i, p in enumerate(payloads):
    print(f"Generiere Video {i}...")
    # Anfrage senden
    response = requests.post(API_URL, headers=headers, json=p)

    # Antwort verarbeiten
    if response.status_code == 200:
        result = response.json()
        video_url = result.get("output_url")
        print(f"Video {i} generiert: {video_url}")

        # Video herunterladen
        video_data = requests.get(video_url).content
        with open(f"video_{i}.mp4", "wb") as f:
            f.write(video_data)
        print(f"Video als 'video_{i}.mp4' gespeichert.")
    else:
        print(f"Fehler bei der Generierung: {response.text}")
        