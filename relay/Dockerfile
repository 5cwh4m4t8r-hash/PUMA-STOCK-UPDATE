FROM python:3.12-slim
WORKDIR /app
COPY puma_relay_server.py /app/puma_relay_server.py
ENV PYTHONUNBUFFERED=1
ENV PORT=8787
EXPOSE 8787
CMD ["python", "/app/puma_relay_server.py"]
