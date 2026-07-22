FROM python:3.11-slim

ARG BOT_TOKEN=""
ARG API_ID=""
ARG API_HASH=""
ARG OWNER_ID=""
ARG DATA_DIR="compresor_data"

ENV BOT_TOKEN=${BOT_TOKEN} \
    API_ID=${API_ID} \
    API_HASH=${API_HASH} \
    OWNER_ID=${OWNER_ID} \
    DATA_DIR=${DATA_DIR}

RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python3", "compresor_bot.py"]
