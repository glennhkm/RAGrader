# Deployment API Service

Target API: `http://192.168.27.218:8000`

## 1. Sebelum Masuk Server

Perubahan lokal harus sudah di-commit dan di-push ke branch `main`:

```bash
cd api_service
git status
git add .
git commit -m "Prepare API service for production deployment"
git push origin main
```

Catat commit yang akan di-deploy:

```bash
git rev-parse HEAD
```

## 2. Preflight Server

```bash
ssh <SSH_USER>@192.168.27.218
cat /etc/os-release
docker --version
docker compose version
ip -4 addr show | grep 192.168.27.218
ss -ltnp | grep ':8000 ' || true
free -h
df -h
```

Lanjutkan hanya jika Docker Compose tersedia, IP terpasang pada server, port 8000 kosong, dan disk mencukupi.

Jika server Ubuntu belum memiliki Docker, pasang Docker Engine dan Compose plugin dari repository resmi Docker:

```bash
sudo apt update
sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker run --rm hello-world
sudo docker compose version
```

Runbook menggunakan `sudo docker`. Menambahkan akun operator ke grup `docker` bersifat opsional karena grup tersebut memberikan hak setara root.

## 3. Ambil Source Code

```bash
sudo install -d -o "$USER" -g "$USER" /opt/ai-rag-grading-api
git clone https://github.com/glennhkm/ai_rag_grading_ta_api_services.git /opt/ai-rag-grading-api
cd /opt/ai-rag-grading-api
git switch main
git pull --ff-only origin main
git rev-parse HEAD
```

Jika repository private, gunakan GitHub deploy key atau token dengan hak baca saja.

## 4. Konfigurasi Environment

```bash
cp .env.example .env
chmod 600 .env
vi .env
```

Nilai minimum produksi:

```dotenv
ENVIRONMENT=production
API_BIND_ADDRESS=192.168.27.218
API_HOST=0.0.0.0
API_PORT=8000
MAX_UPLOAD_SIZE_MB=50

LLM_PROVIDER=provider_chain
LLM_PROVIDER_ORDER=groq,openrouter
LLM_REQUEST_TIMEOUT=60
LLM_TOTAL_TIMEOUT=110
GROQ_API_KEY=<SECRET>
OPENROUTER_API_KEY=<SECRET>
HUGGINGFACE_API_TOKEN=<SECRET>

ENABLE_RERANKING=false
ENABLE_IMAGE_EXTRACTION=false
ENABLE_VISION_CAPTIONING=false
```

`PINECONE_API_KEY` hanya wajib jika `ENABLE_RERANKING=true` dan reranker BGE digunakan.

## 5. Data, Permission, dan Start

Container berjalan sebagai UID/GID `10001`:

```bash
mkdir -p data/chroma_db data/uploads logs
sudo chown -R 10001:10001 data logs
sudo docker compose config --quiet
sudo docker compose build --pull --no-cache
sudo docker compose up -d
sudo docker compose ps
sudo docker inspect --format '{{.State.Health.Status}}' ai_rag_grading_ta_api
sudo docker compose logs --tail=100
```

Gunakan satu container API selama Chroma memakai `PersistentClient` lokal. Jangan menjalankan beberapa replica dengan volume Chroma yang sama. Untuk scale-out, pindahkan Chroma ke service server terpisah terlebih dahulu.

## 6. Firewall

Cari IP sumber yang digunakan server Moodle saat menuju API:

```bash
# Jalankan pada server Moodle.
ip route get 192.168.27.218
```

Pada server API, izinkan port 8000 hanya dari IP tersebut:

```bash
sudo firewall-cmd --list-all
sudo firewall-cmd --permanent --add-rich-rule='rule family="ipv4" source address="<MOODLE_SERVER_IP>/32" port port="8000" protocol="tcp" accept'
sudo firewall-cmd --reload
```

Jangan membuka `8000/tcp` untuk semua alamat. Endpoint belum mewajibkan API key karena seluruh plugin belum konsisten mengirim header otorisasi.

## 7. Verifikasi

Dari server API dan server Moodle:

```bash
curl -fsS --connect-timeout 5 http://192.168.27.218:8000/health
curl -fsS --connect-timeout 5 http://192.168.27.218:8000/moodle/status
```

Uji alur material dan grading memakai course ID khusus pengujian:

```bash
printf 'Materi uji deployment.' >/tmp/rag-test.txt

curl -fsS -X POST http://192.168.27.218:8000/course/materials/upload \
  -F course_id=999999 -F course_name='Deployment Test' \
  -F file=@/tmp/rag-test.txt

curl -fsS http://192.168.27.218:8000/collections/999999

curl -fsS -X POST http://192.168.27.218:8000/assign/answer \
  -H 'Content-Type: application/json' \
  -d '{"course_id":999999,"question":"Apa isi materi?","essay":"Materi uji deployment.","rubric":{},"maximum_grade":100,"assignment_id":999999}'

curl -fsS -X DELETE http://192.168.27.218:8000/course/materials/file \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data 'course_id=999999&filename=rag-test.txt'

curl -fsS -X POST http://192.168.27.218:8000/course/materials/clear \
  -F course_id=999999
```

Respons grading harus memiliki `success`, `score`, `feedback`, `citations`, dan `confidence`.

## 8. Konfigurasi Moodle

Isi URL berikut dengan `http://192.168.27.218:8000`:

- `mod_airagmaterial/serverurl`
- `mod_airagassign/serverurl`
- `local_assign_ai_rag/server_url`
- `aiprovider_rag/serverurl`

Kosongkan API key plugin selama API belum menerapkan autentikasi wajib. Setelah disimpan, purge cache Moodle dan uji upload material, grade satu submission, lalu grade semua submission.

## 9. Backup, Update, dan Rollback

Backup sebelum update:

```bash
cd /opt/ai-rag-grading-api
tar -czf "$HOME/ai-rag-data-$(date +%Y%m%d-%H%M%S).tar.gz" data
git rev-parse HEAD >"$HOME/ai-rag-deployed-commit.txt"
```

Update:

```bash
git fetch origin
git pull --ff-only origin main
docker compose build --pull
docker compose up -d
docker compose ps
```

Rollback kode menggunakan commit terakhir yang tercatat, lalu build ulang. Jangan hapus direktori `data/` ketika rollback.
