FROM python:3.11-slim

WORKDIR /app

# (선택) 빌드에 필요한 패키지 - numpy만이면 보통 없어도 되지만,
# 나중에 opencv 같은 거 붙이면 필요할 수 있음
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# 서버 코드를 컨테이너로 복사
COPY . /app

EXPOSE 8001

# FastAPI 실행 (backend.app:app 이 경로는 프로젝트에 맞게 조정)
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8001"]