FROM python:3.11-slim

# نثبّت شوية حاجات أساسية
RUN apt-get update && apt-get install -y \
    wget gnupg unzip curl \
    chromium chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# نجهّز فولدر العمل
WORKDIR /app

# ننسخ ملفات المشروع
COPY . /app

# نثبّت المكتبات البايثون
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Railway بيبعت PORT في متغير بيئة
ENV PORT=5000

# الأمر الذي يشغّل التطبيق
CMD ["python", "app.py"]
