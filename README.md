# Rakshak AI  Intelligent CCTV Surveillance System

Rakshak AI is a software layer that transforms existing CCTV cameras into an intelligent surveillance system. It provides real-time object detection, weapon detection, and person journey tracking across multiple camera feeds.

```text
Video Feeds ──► AI Detection (YOLOv8) ──► Journey Tracker ──► Operations Console (Web UI)
```

## 🚀 Key Features

- **Real-Time Threat Monitoring**: Automatically detects weapons (guns, knives, explosives) in live video feeds and triggers immediate visual and audible alarms.
- **Cross-Camera Journey Tracking**: Assigns a unique ID to every person and tracks their movement seamlessly across different cameras in the building.
- **Live Camera Integration**: Connect any RTSP stream, USB webcam, or even use your smartphone camera wirelessly via a QR code.
- **Operations Console**: A central dashboard to view live feeds, manage active threats (assign security personnel, resolve incidents), and check camera health.
- **All-Weather Detection**: The system is tested and works in challenging conditions like Night, Thermal, Fog, Rain, and Snow.

## 💻 Tech Stack

- **Backend**: Python, FastAPI, WebSockets
- **AI/ML**: Ultralytics YOLOv8 (Object & Weapon Detection), OSNet (Person Re-identification), ONNX Runtime
- **Frontend**: Vanilla HTML, CSS, JavaScript (No complex build tools needed)

## 🛠️ How to Run Locally

Requires Python 3.10+. Tested on a laptop CPU (no GPU needed).

```bash
# 1. Create a virtual environment
python -m venv .venv
.venv\Scripts\activate            # Linux/macOS: source .venv/bin/activate

# 2. Install dependencies (CPU version of PyTorch for smaller size)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt

# 3. Download demo videos and AI models (~1.4 GB)
python scripts/fetch_assets.py

# 4. Start the server
uvicorn app.server:app --port 8000
```

Once running, open `http://localhost:8000` for the landing page, or `http://localhost:8000/app` for the Operations Console.

## 📊 Operations Console (Dashboard)

- **Overview Tab**: Shows the overall threat score, active threats, and camera health status.
- **Cameras Tab**: View all live feeds in a grid. Click any feed to see a detailed view with detected objects and confidence scores. People are highlighted in green, objects in amber, and weapons in red.
- **People Tab**: A searchable list of all detected people. Click a person to see their exact journey (e.g., `Plaza → Lobby → Stairwell`) and how much time they spent in each area.
- **Reports Tab**: A complete history of all security incidents and actions taken. Exportable as a CSV file.
