FROM python:3.12-slim

# WeasyPrint 시스템 의존성
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz0b \
    libffi-dev \
    libcairo2 \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 의존성 캐시: requirements만 먼저 설치
COPY pyproject.toml ./
RUN pip install --no-cache-dir \
    "typer[all]>=0.12.0,<1.0" \
    "ruamel.yaml>=0.18.0,<0.19" \
    "jinja2>=3.1.0,<4.0" \
    "keyring>=25.0.0,<27.0" \
    "rich>=13.7.0,<15.0" \
    "pydantic>=2.0.0,<3.0" \
    "platformdirs>=4.0.0,<5.0" \
    "litellm>=1.60.0" \
    "weasyprint>=62.0" \
    "markdown>=3.6" \
    "python-docx>=1.1.0" \
    "fastapi>=0.110.0,<1.0" \
    "uvicorn[standard]>=0.29.0,<1.0"

# 소스 복사 후 패키지 설치 (entry_points 등록)
COPY devfolio/ devfolio/
COPY impactnote/ impactnote/
RUN pip install --no-cache-dir --no-deps ".[all]"

# 성과노트 데이터 볼륨 (DevFolio 데이터는 컴포즈에서 읽기 전용으로 마운트)
VOLUME ["/root/.local/share/impactnote", "/root/.config/impactnote"]

# 웹 UI 포트
EXPOSE 8000

ENTRYPOINT ["impactnote"]
CMD ["--help"]
