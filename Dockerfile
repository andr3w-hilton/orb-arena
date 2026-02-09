FROM python:3.11-slim

WORKDIR /app

# Install websockets
RUN pip install websockets

# Copy all game files
COPY . /app

# Expose both ports
EXPOSE 8080 8765

# Run the game server
CMD ["python", "server.py"]
