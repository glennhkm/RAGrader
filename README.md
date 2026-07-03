# API Service - RAG Essay Grading

Service ini adalah API backend untuk penilaian jawaban/esai berbasis RAG. Service menerima materi kuliah, menyimpannya ke ChromaDB sebagai vector, mengambil konteks yang relevan saat penilaian, lalu memakai LLM untuk menghasilkan nilai, feedback, citation, dan confidence.

Service ini juga menyediakan endpoint yang disiapkan untuk integrasi Moodle.

## Fitur Utama

- Upload materi kuliah ke knowledge base RAG.
- Penyimpanan vector menggunakan ChromaDB.
- Isolasi koleksi berdasarkan `course_id` untuk endpoint Moodle.
- Retrieval dengan konfigurasi `top_k`.
- Reranking opsional dengan Pinecone BGE reranker atau BM25.
- LLM fallback chain: Groq ke OpenRouter, atau OpenRouter ke Groq.
- Konfigurasi melalui `.env` memakai placeholder di `configs/config.yaml`.
- Mendukung file `.pdf`, `.pptx`, `.docx`, dan `.txt`.

## Struktur Penting

```text
api_service/
├── run_api.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── configs/
│   └── config.yaml
├── data/
│   ├── chroma_db/
│   └── uploads/
├── logs/
└── src/
    ├── api/
    ├── grading/
    ├── ingestion/
    ├── rag/
    ├── utils/
    └── vectorstore/
```

## Prasyarat

- Python 3.10 atau lebih baru.
- API key HuggingFace untuk embedding.
- API key Groq dan/atau OpenRouter untuk LLM.
- API key Pinecone jika memakai reranker BGE.

Catatan: HuggingFace masih dibutuhkan untuk embedding Chroma, walaupun LLM utama memakai Groq/OpenRouter.

## Instalasi Lokal

1. Buat virtual environment.

```bash
python -m venv .venv
source .venv/bin/activate
```

2. Install dependency.

```bash
pip install -r requirements.txt
```

3. Buat file `.env`.

```bash
cp .env.example .env
```

4. Isi minimal API key berikut di `.env`.

```env
GROQ_API_KEY=gsk_your_groq_api_key_here
OPENROUTER_API_KEY=sk-or-v1-your_openrouter_api_key_here
HUGGINGFACE_API_TOKEN=hf_your_huggingface_api_token_here
```

Jika ingin memakai reranker BGE:

```env
ENABLE_RERANKING=true
PINECONE_API_KEY=pcsk_your_pinecone_api_key_here
```

5. Jalankan API.

```bash
python run_api.py
```

Secara default API berjalan di:

```text
http://localhost:8000
```

Dokumentasi Swagger tersedia di:

```text
http://localhost:8000/docs
```

## Konfigurasi

Konfigurasi utama berada di:

```text
configs/config.yaml
```

Nilainya bisa mengambil dari `.env` dengan pola:

```yaml
provider: "${LLM_PROVIDER:provider_chain}"
port: "${API_PORT:8000}"
enable_reranking: "${ENABLE_RERANKING:false}"
```

Formatnya:

```text
${NAMA_ENV:default_value}
```

Artinya:

- jika variabel ada di `.env`, nilai `.env` dipakai;
- jika tidak ada, nilai default dipakai;
- tipe data umum otomatis dikonversi, seperti `int`, `float`, dan `bool`.

Contoh override di `.env`:

```env
API_PORT=9001
LLM_PROVIDER=provider_chain
LLM_MODEL=openai/gpt-oss-120b
RETRIEVAL_TOP_K=5
ENABLE_RERANKING=false
CHUNK_SIZE=500
CHUNK_OVERLAP=50
```

## LLM Provider

Default LLM menggunakan:

```env
LLM_PROVIDER=provider_chain
LLM_PROVIDER_ORDER=groq,openrouter
```

Artinya sistem mencoba Groq terlebih dahulu. Jika Groq error, rate limit, timeout, atau gagal, sistem mencoba OpenRouter.

Jika ingin mulai dari OpenRouter:

```env
LLM_PROVIDER=openrouter
```

Jika ingin menambah beberapa akun:

```env
GROQ_API_KEY=gsk_primary
GROQ_API_KEY_2=gsk_secondary
OPENROUTER_API_KEY=sk-or-v1-primary
OPENROUTER_API_KEY_2=sk-or-v1-secondary
```

## Embedding dan ChromaDB

Materi kuliah diproses menjadi chunk, lalu dibuat embedding menggunakan HuggingFace. Embedding dan metadata disimpan di ChromaDB.

Default:

```env
EMBEDDING_MODEL=BAAI/bge-m3
CHROMA_PERSIST_DIRECTORY=./data/chroma_db
CHROMA_COLLECTION_NAME=course_materials
```

Untuk endpoint Moodle, `course_id` dipakai untuk memilih koleksi Chroma khusus course tersebut.

## Format File yang Didukung

Endpoint course material mendukung:

```text
.pdf
.pptx
.docx
.txt
```

Format lama seperti `.doc` dan `.ppt` tidak didukung langsung karena membutuhkan converter eksternal seperti LibreOffice.

## Endpoint Utama

### Health dan Status

```text
GET /
GET /health
GET /status
GET /moodle/status
GET /assign/status
```

### Upload Materi

Upload standar:

```text
POST /upload
```

Upload untuk Moodle:

```text
POST /moodle/upload
POST /course/materials/upload
```

`/course/materials/upload` menerima:

- `file`
- `course_id`
- `course_name` opsional

### Penilaian

Endpoint standar:

```text
POST /grade
```

Endpoint Moodle:

```text
POST /assign/answer
```

Endpoint Moodle menerima `course_id`, `question`, `essay`, `rubric`, dan metadata assignment. Service akan mengambil konteks dari koleksi course tersebut, lalu menghasilkan nilai dan feedback.

### Manajemen Materi

```text
GET /collections/{course_id}
DELETE /collections/{course_id}
GET /course/materials/status/{course_id}
POST /course/materials/clear
DELETE /course/materials/file
POST /clear
```

## Menjalankan dengan Docker

Build image:

```bash
docker build -t rag-essay-api .
```

Run container:

```bash
docker run --env-file .env -p 8000:8000 rag-essay-api
```

Dengan Docker Compose:

```bash
docker compose up -d --build
```

Pastikan `.env` sudah tersedia sebelum container dijalankan.

## Log dan Data

Log tersimpan di:

```text
logs/app.log
```

Data upload dan ChromaDB tersimpan di:

```text
data/uploads/
data/chroma_db/
```

Direktori `data/` dan `logs/` sebaiknya dipersist saat deployment.

## Troubleshooting

### `HUGGINGFACE_API_TOKEN not found`

Embedding masih memakai HuggingFace. Isi:

```env
HUGGINGFACE_API_TOKEN=hf_your_token
```

### `No Groq/OpenRouter API key found`

Isi minimal salah satu:

```env
GROQ_API_KEY=...
OPENROUTER_API_KEY=...
```

### Groq rate limit

Gunakan fallback OpenRouter atau tambah beberapa key:

```env
LLM_PROVIDER_ORDER=groq,openrouter
GROQ_API_KEY_2=...
OPENROUTER_API_KEY_2=...
```

### Pinecone error

Jika tidak memakai BGE reranker:

```env
ENABLE_RERANKING=false
```

Jika memakai BGE reranker:

```env
ENABLE_RERANKING=true
PINECONE_API_KEY=...
```

### File `.doc` atau `.ppt` gagal

Service hanya mendukung `.docx` dan `.pptx`. Konversi file lama terlebih dahulu.

## Catatan Deployment

- Jangan commit file `.env`.
- Gunakan `.env.example` sebagai template.
- Pastikan port di `.env` sesuai dengan reverse proxy/server.
- Persist `data/` agar vector Chroma tidak hilang saat container restart.
- Persist `logs/` jika ingin audit error dan penggunaan provider.
