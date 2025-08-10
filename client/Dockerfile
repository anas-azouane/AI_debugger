FROM python:3.11-slim

WORKDIR /app

COPY analyzer.py .

RUN pip install fastapi uvicorn requests pydantic openai

EXPOSE 8000

CMD ["uvicorn", "analyzer:app", "--host", "0.0.0.0", "--port", "8000"]

