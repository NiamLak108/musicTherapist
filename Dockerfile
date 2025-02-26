# First stage: Install dependencies
FROM python:3.11-slim as builder
WORKDIR /install
COPY requirements.txt .
RUN pip install --prefix=/install --no-cache-dir -r requirements.txt

# Second stage: Create the final lightweight image
FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /install /usr/local
COPY . /app
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8080"]
