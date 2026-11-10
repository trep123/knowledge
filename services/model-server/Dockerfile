FROM python:3.12-slim

WORKDIR /app

# Tesla P4 = Pascal (sm_61)。PyPI 上的 torch 2.6.0 Linux 轮子即 cu124 构建，支持 sm_50–sm_90。
# download.pytorch.org 在本网络不可达，统一走清华 PyPI 镜像。
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple \
        torch==2.6.0 \
    && pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple \
        fastapi==0.115.6 uvicorn==0.34.0 sentence-transformers==3.3.1

COPY main.py .

ENV MODEL_TYPE=embedding \
    MODEL_PATH=/models/bge-m3 \
    PORT=8001 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

EXPOSE 8001 8002

CMD ["sh", "-c", "python main.py"]
