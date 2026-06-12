FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY openclaw/ ./openclaw/
ENV PYTHONUNBUFFERED=1
ENV GATEWAY_HOST=0.0.0.0
ENV GATEWAY_PORT=18888
EXPOSE 18888
CMD ["python", "-m", "openclaw.gateway"]
