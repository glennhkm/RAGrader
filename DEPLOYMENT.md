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
API_REPLICAS=2
LOG_TO_FILE=false

CHROMA_CLIENT_MODE=http
CHROMA_HOST=chroma
CHROMA_PORT=8000
CHROMA_SSL=false
REDIS_URL=redis://redis:6379/0
DISTRIBUTED_LOCK_ENABLED=true
DISTRIBUTED_LOCK_TTL_SECONDS=900
DISTRIBUTED_LOCK_WAIT_SECONDS=120

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
sudo docker compose up -d --remove-orphans
sudo docker compose ps
sudo docker compose ps --format json
sudo docker compose logs --tail=100 api chroma redis load-balancer

# Pantau log request secara langsung.
sudo docker compose logs -f --tail=200 api chroma redis load-balancer

# Cari request ID yang ditampilkan Moodle saat grading gagal.
sudo docker compose logs api | grep -F "REQUEST_ID_DARI_MOODLE"
```

Hasil yang benar adalah dua container `api`, satu `chroma`, satu `redis`, dan
satu `load-balancer`. Hanya load balancer yang mempublikasikan port `8000`.
Untuk CPU 8 core Xeon E5540, mulai dari dua replica; jangan menaikkan jumlahnya
sebelum CPU, RAM, latency, dan rate limit provider dipantau.

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

Pastikan trafik mencapai kedua replica:

```bash
for i in $(seq 1 10); do
  curl -fsSD - -o /dev/null http://192.168.27.218:8000/health \
    | grep -i '^x-api-instance:'
done
```

Output harus menampilkan lebih dari satu nilai `X-API-Instance`.

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

Untuk migrasi pertama dari satu embedded Chroma maupun update berikutnya,
stop seluruh writer sebelum backup. Jangan menyalin database Chroma yang sedang
aktif:

```bash
cd /opt/ai-rag-grading-api
sudo docker compose down
tar -czf "$HOME/ai-rag-data-$(date +%Y%m%d-%H%M%S).tar.gz" data
git rev-parse HEAD >"$HOME/ai-rag-deployed-commit.txt"
```

Update:

```bash
git fetch origin
git pull --ff-only origin main
sudo chown -R 10001:10001 data
sudo docker compose config --quiet
sudo docker compose build --pull
sudo docker compose up -d --remove-orphans
sudo docker compose ps
```

Jika container lama bernama `ai_rag_grading_ta_api` masih tercatat setelah
migrasi, pastikan statusnya sudah stopped lalu hapus sebagai orphan. Rollback
kode menggunakan commit terakhir yang tercatat, lalu build ulang. Jangan hapus
direktori `data/` dan jangan jalankan versi lama bersamaan dengan Chroma server.
