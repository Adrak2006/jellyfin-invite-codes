FROM python:3.12-alpine
WORKDIR /app
COPY app.py .
EXPOSE 8057
VOLUME /config
CMD ["python3", "-u", "app.py"]
