FROM python:3.12-slim

# WeasyPrint 시스템 의존성
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz0b \
    libffi-dev \
    libcairo2 \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 의존성 먼저 복사 (레이어 캐시 최적화)
COPY pyproject.toml ./
RUN pip install --no-cache-dir ".[all]"

# 소스 복사
COPY devfolio/ devfolio/

# DevFolio 데이터 볼륨 마운트 포인트
VOLUME ["/root/.local/share/devfolio", "/root/.config/devfolio"]

ENTRYPOINT ["devfolio"]
CMD ["--help"]
