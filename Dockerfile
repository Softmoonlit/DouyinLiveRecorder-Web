FROM python:3.11-slim

WORKDIR /app

COPY . /app

ENV DOUYIN_WEB_UI_ALLOWED=v1,v2
ENV DOUYIN_WEB_UI_DEFAULT=v1

RUN apt-get update && \
    apt-get install -y curl gnupg && \
    curl -sL https://deb.nodesource.com/setup_20.x  | bash - && \
    apt-get install -y nodejs

RUN npm --prefix web_v2 install --no-audit --no-fund && \
    npm --prefix web_v2 run build

RUN pip install --no-cache-dir -r requirements.txt

RUN apt-get update && \
    apt-get install -y ffmpeg tzdata && \
    ln -fs /usr/share/zoneinfo/Asia/Shanghai /etc/localtime && \
    dpkg-reconfigure -f noninteractive tzdata

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-graceful-shutdown", "30"]
