FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Generate a self-contained dataset and remove the evaluation-only ground truth
# so it is not present in the runtime image.
RUN python scripts/generate_synthetic_data.py \
    && python scripts/load_database.py \
    && rm -f data/raw/ground_truth_failures.csv

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
