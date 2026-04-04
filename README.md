# 🖼️ Image Processing Distributed System

A distributed system for batch image processing built with FastAPI, RabbitMQ, and scalable worker nodes.

The system allows users to upload a batch of images along with transformation instructions, processes them in parallel, and returns the results efficiently.

---

## 🚀 Features

* Batch image processing (ZIP upload)
* Multiple transformations per image
* Distributed processing using worker nodes
* RabbitMQ-based task queue
* Real-time batch status tracking
* Download processed results as ZIP
* Relational database for tracking tasks, logs, and results

---

## 🏗️ Architecture

* API (FastAPI): Receives requests, validates data, stores metadata
* RabbitMQ: Message broker for distributing tasks
* Workers: Process images in parallel
* SQLite DB: Tracks batches, images, tasks, logs
* Storage: Handles input/output images

---

## 📂 Project Structure

image-processing-system/

├── api/        # FastAPI backend
├── worker/     # Worker node logic
├── scripts/    # Utilities (batch generator)
├── docs/       # Diagrams and documentation
├── .gitignore
└── README.md

---

## ⚙️ Installation

### 1. Clone repo

git clone https://github.com/your-user/image-processing-system.git
cd image-processing-system

---

### 2. Install dependencies

pip install fastapi uvicorn pika pillow

---

### 3. Run RabbitMQ (Docker)

docker run -d --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:3-management

Dashboard: http://localhost:15672
User: guest
Password: guest

---

## ▶️ Run the system

### Terminal 1 — API

cd api
uvicorn main:app --reload

---

### Terminal 2 — Worker (Node 1)

cd worker
python worker.py

---

### Terminal 3 — Worker (Node 2)

cd worker
python worker.py

---

## 📤 Usage

### Upload batch

POST /lote

Send a ZIP containing:

img1.jpg
img1.json
img2.jpg
img2.json

---

### JSON format example

{
"transformaciones": [
{ "tipo": "resize", "width": 300, "height": 300 },
{ "tipo": "grayscale" },
{ "tipo": "rotate", "angle": 90 }
]
}

---

## 🔍 Available transformations

resize → width, height
grayscale → none
rotate → angle

---

## 📊 Check batch status

GET /lote/{id}

---

## 📥 Download results

GET /lote/{id}/resultado

Returns a ZIP file with processed images.

---

## 🧠 How it works

1. Client uploads batch
2. API stores metadata and images
3. Tasks are sent to RabbitMQ
4. Workers consume tasks
5. Images are processed in parallel
6. Results are stored and tracked
7. User downloads final batch

---

## 🧪 Testing

python scripts/generarbatch.py 10

---

## 📌 Notes

* Database is recreated on startup
* Storage folders are ignored in Git
* Designed for distributed deployment

---

## 🚧 Future Improvements

* UI dashboard
* Cloud storage (S3)
* Authentication
* Priority queues
* Horizontal scaling

---

## 👨‍💻 Author

Camilo Castro
