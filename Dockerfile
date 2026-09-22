FROM python:3.11-slim

# Install system dependencies required by OpenCV and MediaPipe (OpenGL ES, GL, EGL, GLib)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgles2 \
    libgl1 \
    libegl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Expose ports for Streamlit and Flask
EXPOSE 8501 5000

# Default entrypoint for Streamlit app
CMD ["streamlit", "run", "streamlit_app/streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
