FROM python:3.12.13-slim-trixie

RUN pip install --no-cache-dir cryptography==48.0.1
WORKDIR /tool
COPY private_bundle.py /tool/private_bundle.py
ENTRYPOINT ["python", "/tool/private_bundle.py"]
