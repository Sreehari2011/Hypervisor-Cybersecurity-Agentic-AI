FROM kalilinux/kali-rolling

ARG HTTP_PROXY
ARG HTTPS_PROXY

RUN echo "deb http://kali.download/kali kali-rolling main contrib non-free non-free-firmware" > /etc/apt/sources.list

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    kali-linux-headless \
    python3 \
    python3-pip \
    python3-venv \
    iproute2 \
    iputils-ping \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip3 install -r requirements.txt --break-system-packages

COPY . .

CMD ["python3", "main.py"]