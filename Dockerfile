FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

RUN useradd -m -u 1000 app
WORKDIR /home/app/code

COPY --chown=app requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app . .
USER app

# build the search index during the image build so startup is fast
RUN python -m scripts.build_index

EXPOSE 7860
CMD ["uvicorn", "app.backend.main:app", "--host", "0.0.0.0", "--port", "7860"]
