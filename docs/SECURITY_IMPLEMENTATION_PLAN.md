# Golsinyali API - Güvenlik Düzeltme Implementation Plan

**Tarih:** 2026-02-25
**Hazırlayan:** Shannon AI Pentest + Manuel Analiz
**Toplam Bulgu:** 24 güvenlik açığı
**Tahmini Toplam Süre:** ~3-4 gün (acil düzeltmeler 1 gün)

---

## İçindekiler

- [Faz 1: Acil Müdahale (İlk 24 Saat)](#faz-1-acil-müdahale-ilk-24-saat)
  - [1.1 Secret Rotation](#11-secret-rotation)
  - [1.2 Admin Endpoint'lere Auth Ekleme](#12-admin-endpointlere-auth-ekleme)
  - [1.3 CORS Düzeltme](#13-cors-düzeltme)
  - [1.4 .env Güvenliği](#14-env-güvenliği)
- [Faz 2: Yüksek Öncelik (2-3. Gün)](#faz-2-yüksek-öncelik-2-3-gün)
  - [2.1 HTTPS Etkinleştirme](#21-https-etkinleştirme)
  - [2.2 Redis Şifreleme](#22-redis-şifreleme)
  - [2.3 Rate Limiting Düzeltmeleri](#23-rate-limiting-düzeltmeleri)
  - [2.4 HTTP Redirect Güvenliği](#24-http-redirect-güvenliği)
  - [2.5 Source URL Validasyonu](#25-source-url-validasyonu)
  - [2.6 Security Headers Tamamlama](#26-security-headers-tamamlama)
- [Faz 3: Orta Vade (1 Hafta)](#faz-3-orta-vade-1-hafta)
  - [3.1 JWT Token Güvenliği](#31-jwt-token-güvenliği)
  - [3.2 RBAC Implementasyonu](#32-rbac-implementasyonu)
  - [3.3 Audit Logging](#33-audit-logging)
  - [3.4 IP Spoofing Koruması](#34-ip-spoofing-koruması)
- [Faz 4: Uzun Vade (1 Ay)](#faz-4-uzun-vade-1-ay)
  - [4.1 Dependency Pinning](#41-dependency-pinning)
  - [4.2 Upstream Veri Sanitizasyonu](#42-upstream-veri-sanitizasyonu)
  - [4.3 Server Hardening](#43-server-hardening)
- [Test Planı](#test-planı)
- [Rollback Planı](#rollback-planı)

---

## Faz 1: Acil Müdahale (İlk 24 Saat)

### 1.1 Secret Rotation

**Çözdüğü açıklar:** #1 (Secret sızıntısı), #10 (JWT sahteciliği)
**Dosyalar:** `.env`, AWS Console, Sentry Dashboard
**Risk:** Hiçbir kod değişikliği gerektirmez, sadece environment value'lar değişir

#### Adım 1.1.1: Yeni secret'lar oluştur (Lokal)

```bash
# Yeni key'ler oluştur
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))"
python3 -c "import secrets; print('API_SECRET_KEY=' + secrets.token_urlsafe(48))"
python3 -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_urlsafe(48))"
```

#### Adım 1.1.2: AWS key'lerini devre dışı bırak

```
1. AWS Console → IAM → Users → golsinyali-api kullanıcısı
2. Security Credentials sekmesi
3. Mevcut Access Key'i → "Make Inactive" yap (silme, önce test et)
4. "Create Access Key" ile yeni key oluştur
5. Yeni key'i .env'ye yaz
```

#### Adım 1.1.3: Sunucuda .env güncelle

> **DİKKAT:** JWT_SECRET_KEY değiştiğinde mevcut tüm JWT token'lar geçersiz olur. Bu client uygulamaların yeniden token almasını gerektirir. Düşük trafikli bir saatte yapılmalıdır.

```bash
ssh user@72.61.105.107
cd /var/www/golsinyali_api  # veya deployment dizini

# TAM YEDEK AL (kod + config)
cp .env .env.backup.$(date +%Y%m%d)
cp -r . /tmp/golsinyali_backup_$(date +%Y%m%d)

# Yeni key'leri güncelle
nano .env
# SECRET_KEY=<yeni-key>
# API_SECRET_KEY=<yeni-key>
# JWT_SECRET_KEY=<yeni-key>
# AWS_ACCESS_KEY=<yeni-key>
# AWS_SECRET_KEY=<yeni-key>

# Servisi yeniden başlat
sudo systemctl restart golsinyali-api
```

#### Adım 1.1.4: Sentry DSN'i yenile

```
1. Sentry Dashboard → Settings → Projects → golsinyali-api
2. Client Keys (DSN) → "Generate New Key"
3. Eski key'i devre dışı bırak
4. Yeni DSN'i .env'ye yaz
```

#### Adım 1.1.5: Doğrulama

```bash
# API hala çalışıyor mu?
curl http://72.61.105.107:8000/api/v1/health

# Eski key ile erişim engellenmiş mi?
curl -H "X-API-Key: ESKİ_KEY" http://72.61.105.107:8000/api/v1/auth/token
# Beklenen: 403 Forbidden

# Yeni key çalışıyor mu?
curl -X POST http://72.61.105.107:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"api_key": "YENİ_KEY"}'
# Beklenen: 200 OK + JWT token
```

---

### 1.2 Admin Endpoint'lere Auth Ekleme

**Çözdüğü açıklar:** #2 (Admin endpoint'ler auth'suz), #14 (SSRF source değiştirme)
**Dosya:** `routes/health.py`
**Değişiklik:** 4 endpoint'e `@require_api_key` decorator ekleme

#### Adım 1.2.1: routes/health.py'yi düzenle

**Dosya başına import ekle** (`routes/health.py` satır 1-10 civarı):

```python
# Mevcut import'ların yanına ekle:
from security import require_api_key
```

**Endpoint 1: `/cache/clear`** (satır ~59):

```python
# ÖNCE (mevcut):
@health_bp.route('/cache/clear', methods=['POST'])
def clear_cache():

# SONRA (düzeltilmiş):
@health_bp.route('/cache/clear', methods=['POST'])
@require_api_key
def clear_cache():
```

**Endpoint 2: `/cache/stats/reset`** (satır ~126):

```python
# ÖNCE:
@health_bp.route('/cache/stats/reset', methods=['POST'])
def reset_cache_stats():

# SONRA:
@health_bp.route('/cache/stats/reset', methods=['POST'])
@require_api_key
def reset_cache_stats():
```

**Endpoint 3: `/sources/force-primary`** (satır ~197):

```python
# ÖNCE:
@health_bp.route('/sources/force-primary', methods=['POST'])
def force_primary_source():

# SONRA:
@health_bp.route('/sources/force-primary', methods=['POST'])
@require_api_key
def force_primary_source():
```

**Endpoint 4: `/sources/reset-metrics`** (satır ~239):

```python
# ÖNCE:
@health_bp.route('/sources/reset-metrics', methods=['POST'])
def reset_source_metrics():

# SONRA:
@health_bp.route('/sources/reset-metrics', methods=['POST'])
@require_api_key
def reset_source_metrics():
```

#### Adım 1.2.2: require_api_key decorator'ında fonksiyon imzası kontrolü

`security.py` satır 58-75'teki `require_api_key` decorator'ı `*args, **kwargs` ile çağrı yaptığı için mevcut fonksiyon imzalarıyla uyumlu. Ek değişiklik gerekmez.

#### Adım 1.2.3: Doğrulama

```bash
# Auth olmadan → 401 beklenir
curl -X POST http://72.61.105.107:8000/api/v1/cache/clear
# Beklenen: {"error": "API key is required"}

curl -X POST http://72.61.105.107:8000/api/v1/sources/force-primary \
  -H "Content-Type: application/json" \
  -d '{"source_url": "https://www.goaloo.com"}'
# Beklenen: {"error": "API key is required"}

# Auth ile → 200 beklenir
curl -X POST http://72.61.105.107:8000/api/v1/cache/clear \
  -H "X-API-Key: YENİ_API_KEY"
# Beklenen: {"success": true, "data": {"message": "Cache başarıyla temizlendi"}}
```

---

### 1.3 CORS Düzeltme

**Çözdüğü açıklar:** #5 (CORS wildcard)
**Dosya:** `.env` (sunucuda)

#### Adım 1.3.1: .env'de CORS ayarını değiştir

```bash
# ÖNCE (.env satır 29):
ALLOWED_ORIGINS=*

# SONRA:
ALLOWED_ORIGINS=https://golsinyali.com,https://www.golsinyali.com
```

#### Adım 1.3.2: app.py'deki localhost wildcard'ı düzelt

**Dosya:** `app.py` satır 228-239

```python
# ÖNCE:
allowed_origins = [
    'http://localhost:*',         # Wildcard - güvensiz
    'http://127.0.0.1:*',        # Wildcard - güvensiz
    'https://golsinyali.com',
    'https://www.golsinyali.com',
    'http://golsinyali.com',
    'http://www.golsinyali.com'
]

# SONRA:
allowed_origins = [
    'http://localhost:3000',      # Sadece dev portu
    'http://localhost:8000',      # Sadece API portu
    'http://127.0.0.1:3000',
    'http://127.0.0.1:8000',
    'https://golsinyali.com',
    'https://www.golsinyali.com',
]
```

#### Adım 1.3.3: Doğrulama

```bash
# Kötü origin → CORS header OLMAMALI
curl -s -I -H "Origin: https://evil-hacker.com" \
  http://72.61.105.107:8000/api/v1/health | grep Access-Control
# Beklenen: Boş (header yok)

# İyi origin → CORS header OLMALI
curl -s -I -H "Origin: https://golsinyali.com" \
  http://72.61.105.107:8000/api/v1/health | grep Access-Control
# Beklenen: Access-Control-Allow-Origin: https://golsinyali.com
```

---

### 1.4 .env Güvenliği

**Çözdüğü açıklar:** #1 (Secret sızıntısı - git geçmişinden temizleme)
**Dosya:** `.gitignore`, git history

#### Adım 1.4.1: .gitignore'u doğrula

`.gitignore`'da `.env` zaten var (satır 129 ve 202). Ek işlem gerekmez.

#### Adım 1.4.2: Git geçmişinden .env'yi temizle

```bash
# BFG Repo Cleaner ile (daha güvenli)
brew install bfg  # macOS
bfg --delete-files .env
git reflog expire --expire=now --all
git gc --prune=now --aggressive
git push --force

# VEYA git filter-branch ile
git filter-branch --force --index-filter \
  'git rm --cached --ignore-unmatch .env' \
  --prune-empty --tag-name-filter cat -- --all
git push --force
```

> **DİKKAT:** `--force` push yapılıyor. Tüm ekip üyelerini bilgilendir ve yeni clone yaptır.

#### Adım 1.4.3: config.py default secret'ları güçlendir

**Dosya:** `config.py` satır 12, 15, 19

```python
# ÖNCE:
SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
API_SECRET_KEY = os.getenv('API_SECRET_KEY', 'your-super-secret-api-key-change-in-production')
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'jwt-secret-key-change-in-production')

# SONRA:
SECRET_KEY = os.getenv('SECRET_KEY')
API_SECRET_KEY = os.getenv('API_SECRET_KEY')
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY')

# Startup'ta kontrol et (app.py'ye eklenecek):
if not all([app.config['SECRET_KEY'], app.config['API_SECRET_KEY'], app.config['JWT_SECRET_KEY']]):
    raise RuntimeError("CRITICAL: SECRET_KEY, API_SECRET_KEY, JWT_SECRET_KEY environment variables must be set!")
```

**Dosya:** `app.py` (Flask app oluşturduktan sonra, blueprint'ler yüklenmeden önce):

```python
# Secret kontrolü ekle
if not app.debug:
    required_secrets = ['SECRET_KEY', 'API_SECRET_KEY', 'JWT_SECRET_KEY']
    missing = [s for s in required_secrets if not app.config.get(s)]
    if missing:
        raise RuntimeError(f"CRITICAL: Missing required secrets: {', '.join(missing)}")
```

---

## Faz 2: Yüksek Öncelik (2-3. Gün)

### 2.1 HTTPS Etkinleştirme

**Çözdüğü açıklar:** #9 (HTTP plaintext), #15 (HSTS etkisiz)
**Dosyalar:** Sunucu konfigürasyonu, Nginx, gunicorn_config.py

#### Adım 2.1.1: Domain al ve DNS ayarla

```
1. api.golsinyali.com subdomain'i oluştur
2. DNS A kaydı: api.golsinyali.com → 72.61.105.107
3. DNS yayılmasını bekle (5-30 dakika)
```

#### Adım 2.1.2: Nginx kur ve yapılandır

```bash
ssh user@72.61.105.107

# Nginx kur
sudo apt update && sudo apt install nginx -y

# SSL sertifikası al
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d api.golsinyali.com
```

#### Adım 2.1.3: Nginx konfigürasyonu

```bash
sudo nano /etc/nginx/sites-available/golsinyali-api
```

```nginx
# HTTP → HTTPS yönlendirme
server {
    listen 80;
    server_name api.golsinyali.com;
    return 301 https://$host$request_uri;
}

# HTTPS reverse proxy
server {
    listen 443 ssl http2;
    server_name api.golsinyali.com;

    # SSL sertifikaları (Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/api.golsinyali.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.golsinyali.com/privkey.pem;

    # Modern SSL konfigürasyonu
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:10m;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;

    # Server header gizle
    server_tokens off;

    # Request boyut limiti (büyük payload saldırılarını engelle)
    client_max_body_size 1m;

    # Nginx seviyesinde rate limiting (defense in depth)
    limit_req_zone $binary_remote_addr zone=api:10m rate=30r/s;
    limit_req zone=api burst=50 nodelay;

    # Proxy
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 90s;

        # Proxy header'larını temizle (IP spoofing önleme)
        proxy_set_header X-Forwarded-For $remote_addr;
    }
}
```

```bash
# Aktif et ve test et
sudo ln -s /etc/nginx/sites-available/golsinyali-api /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

#### Adım 2.1.7: SSL sertifika otomatik yenileme

Let's Encrypt sertifikaları 90 günde expire olur. Otomatik yenileme kur:

```bash
# Certbot otomatik yenileme zaten cron'a eklenir, ama doğrula:
sudo certbot renew --dry-run

# Manuel cron eklemek istersen:
echo "0 3 * * * certbot renew --quiet --post-hook 'systemctl reload nginx'" | sudo tee /etc/cron.d/certbot-renew
```

#### Adım 2.1.4: Gunicorn'u sadece localhost'a bağla

**Dosya:** `gunicorn_config.py` satır 11

```python
# ÖNCE:
bind = f"0.0.0.0:{port}"

# SONRA (Nginx arkasında):
bind = f"127.0.0.1:{port}"
```

#### Adım 2.1.5: Firewall - 8000 portunu kapat

```bash
# Sadece 80 ve 443'e izin ver
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw deny 8000/tcp
sudo ufw enable
```

#### Adım 2.1.6: Doğrulama

```bash
# HTTPS çalışıyor mu?
curl https://api.golsinyali.com/api/v1/health
# Beklenen: 200 OK

# HTTP → HTTPS yönlendirme
curl -I http://api.golsinyali.com/api/v1/health
# Beklenen: 301 → https://...

# Eski port kapalı mı?
curl http://72.61.105.107:8000/api/v1/health
# Beklenen: Connection refused
```

---

### 2.2 Redis Şifreleme

**Çözdüğü açıklar:** #7 (Redis şifresiz)
**Dosyalar:** `redis.conf`, `.env`, `config.py`

#### Adım 2.2.1: Redis şifre oluştur

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
# Örnek: xK7mN2pQ9rT4vW6yB8dF3hJ5kL0sA1
```

#### Adım 2.2.2: Redis konfigürasyonu

```bash
sudo nano /etc/redis/redis.conf
```

```
# Ekle:
requirepass xK7mN2pQ9rT4vW6yB8dF3hJ5kL0sA1

# Sadece localhost'tan erişim (zaten olmalı):
bind 127.0.0.1
```

```bash
sudo systemctl restart redis
```

#### Adım 2.2.3: .env'ye Redis şifresi ekle

```bash
# .env'ye ekle:
CACHE_REDIS_PASSWORD=xK7mN2pQ9rT4vW6yB8dF3hJ5kL0sA1
```

#### Adım 2.2.4: config.py'yi güncelle

**Dosya:** `config.py` Redis konfigürasyon bölümü

```python
# ÖNCE:
CACHE_REDIS_HOST = os.getenv('CACHE_REDIS_HOST', 'localhost')
CACHE_REDIS_PORT = int(os.getenv('CACHE_REDIS_PORT', 6379))
CACHE_REDIS_DB = int(os.getenv('CACHE_REDIS_DB', 0))

# SONRA (ekle):
CACHE_REDIS_HOST = os.getenv('CACHE_REDIS_HOST', 'localhost')
CACHE_REDIS_PORT = int(os.getenv('CACHE_REDIS_PORT', 6379))
CACHE_REDIS_DB = int(os.getenv('CACHE_REDIS_DB', 0))
CACHE_REDIS_PASSWORD = os.getenv('CACHE_REDIS_PASSWORD', None)
```

#### Adım 2.2.5: app.py'deki Redis connection pool'u güncelle

**Dosya:** `app.py` - Redis connection pool bölümü

```python
# CACHE_REDIS_CONNECTION_POOL ayarlarına ekle:
'password': app.config.get('CACHE_REDIS_PASSWORD'),
```

#### Adım 2.2.6: Flask-Limiter storage URI'sini güncelle

Redis'e şifre eklenince flask-limiter'ın storage_uri'si de güncellenmeli (yoksa limiter Redis'e bağlanamaz ve in-memory fallback yapar):

**Dosya:** `app.py` - limiter konfigürasyonu

```python
# ÖNCE:
storage_uri="redis://localhost:6379/1"

# SONRA:
redis_password = app.config.get('CACHE_REDIS_PASSWORD', '')
if redis_password:
    storage_uri = f"redis://:{redis_password}@localhost:6379/1"
else:
    storage_uri = "redis://localhost:6379/1"
```

> **Not:** Bu adım 2.3'teki rate_limiter.py modülüne taşıma ile birlikte yapılmalı.

#### Adım 2.2.6: Doğrulama

```bash
# Redis şifreli mi?
redis-cli ping
# Beklenen: NOAUTH Authentication required

redis-cli -a xK7mN2pQ9rT4vW6yB8dF3hJ5kL0sA1 ping
# Beklenen: PONG

# API hala çalışıyor mu?
curl http://localhost:8000/api/v1/cache/stats
# Beklenen: 200 OK, cache istatistikleri
```

---

### 2.3 Rate Limiting Düzeltmeleri

**Çözdüğü açıklar:** #8 (Rate limiting devre dışı), #15 (Token brute-force)
**Dosyalar:** `routes/auth.py`, `app.py`

#### Adım 2.3.1: Limiter'ı ayrı modüle taşı (circular import önleme)

`app.py`'den `from app import limiter` yapmak circular import'a neden olur çünkü `app.py` route'ları import eder. Çözüm: limiter'ı ayrı bir modüle taşımak.

**Dosya:** Yeni `rate_limiter.py` oluştur:

```python
"""Global rate limiter instance - circular import önlemek için ayrı modül"""
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["3000 per hour", "200 per minute"],
    storage_uri="memory://",  # app.py'de Redis URI ile override edilecek
)
```

**Dosya:** `app.py` - mevcut limiter tanımını değiştir:

```python
# ÖNCE:
limiter = Limiter(
    key_func=get_rate_limit_key,
    app=app,
    default_limits=["3000 per hour", "200 per minute"],
    ...
)

# SONRA:
from rate_limiter import limiter

# Storage URI'yi Redis'e güncelle (eğer Redis varsa)
if app.config.get('CACHE_TYPE') != 'simple':
    redis_password = app.config.get('CACHE_REDIS_PASSWORD', '')
    redis_host = app.config.get('CACHE_REDIS_HOST', 'localhost')
    redis_port = app.config.get('CACHE_REDIS_PORT', 6379)
    if redis_password:
        storage_uri = f"redis://:{redis_password}@{redis_host}:{redis_port}/1"
    else:
        storage_uri = f"redis://{redis_host}:{redis_port}/1"
    limiter._storage_uri = storage_uri

limiter.init_app(app)
```

#### Adım 2.3.2: Token endpoint'e özel rate limit ekle

**Dosya:** `routes/auth.py`

```python
# ÖNCE (satır ~15):
@auth_bp.route('/auth/token', methods=['POST'])
def generate_token():

# SONRA:
from rate_limiter import limiter  # Circular import yok!

@auth_bp.route('/auth/token', methods=['POST'])
@limiter.limit("10 per minute")   # Dakikada 10 deneme
@limiter.limit("30 per hour")     # Saatte 30 deneme
def generate_token():
```

#### Adım 2.3.3: Admin endpoint'lere rate limit ekle

**Dosya:** `routes/health.py`

> **DECORATOR SIRASI ÖNEMLİ:** Flask'ta decorator sırası aşağıdan yukarıya çalışır. `@limiter.limit` en dışta (en üstte) olmalı ki rate limit önce çalışsın, sonra auth kontrol edilsin.

```python
from rate_limiter import limiter

# DOĞRU SIRA: limiter → auth → route
@health_bp.route('/cache/clear', methods=['POST'])
@limiter.limit("5 per minute")    # 1. Rate limit kontrol
@require_api_key                   # 2. Auth kontrol
def clear_cache():
    ...

@health_bp.route('/sources/force-primary', methods=['POST'])
@limiter.limit("3 per minute")    # Source değiştirme çok sınırlı
@require_api_key
def force_primary_source():
    ...

@health_bp.route('/sources/reset-metrics', methods=['POST'])
@limiter.limit("5 per minute")
@require_api_key
def reset_source_metrics():
    ...

@health_bp.route('/cache/stats/reset', methods=['POST'])
@limiter.limit("5 per minute")
@require_api_key
def reset_cache_stats():
    ...
```

#### Adım 2.3.3: Doğrulama

```bash
# 11. deneme engellenecek
for i in $(seq 1 12); do
  echo "Deneme $i:"
  curl -s -o /dev/null -w "%{http_code}" -X POST \
    http://localhost:8000/api/v1/auth/token \
    -H "Content-Type: application/json" \
    -d '{"api_key": "yanlis_key"}'
  echo
done
# Beklenen: İlk 10 → 403, 11-12 → 429
```

---

### 2.4 HTTP Redirect Güvenliği

**Çözdüğü açıklar:** #9 (HTTP redirect doğrulaması yok)
**Dosya:** `http_client.py` satır 137, 423, 733, 939

#### Adım 2.4.1: Safe redirect wrapper fonksiyonu oluştur

**Dosya:** `http_client.py` - dosya başına (import'lardan sonra) ekle:

```python
from urllib.parse import urlparse
import ipaddress

# İzin verilen hostlar (source_manager'daki kaynaklarla eşleşmeli)
ALLOWED_REDIRECT_HOSTS = {
    'live3.nowgoal26.com',
    'live4.nowgoal26.com',
    'www.nowgoal.com',
    'www.goaloo.com',
    'football.nowgoal26.com',
    'nowgoal26.com',
    'nowgoal.com',
    'goaloo.com',
}

def _is_safe_redirect(url):
    """Redirect hedefinin güvenli olup olmadığını kontrol et"""
    try:
        parsed = urlparse(url)

        # Sadece HTTP/HTTPS
        if parsed.scheme not in ('http', 'https'):
            return False

        hostname = parsed.hostname
        if not hostname:
            return False

        # İç IP'leri engelle
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return False
        except ValueError:
            pass  # hostname, IP değil

        # Bilinen hostlar kontrolü
        for allowed in ALLOWED_REDIRECT_HOSTS:
            if hostname == allowed or hostname.endswith('.' + allowed):
                return True

        return False
    except Exception:
        return False


def safe_get(session, url, **kwargs):
    """Redirect doğrulamalı güvenli GET isteği"""
    kwargs['allow_redirects'] = False
    response = session.get(url, **kwargs)

    redirect_count = 0
    max_redirects = 5

    while response.status_code in (301, 302, 303, 307, 308) and redirect_count < max_redirects:
        redirect_url = response.headers.get('Location')
        if not redirect_url:
            break

        if not _is_safe_redirect(redirect_url):
            logger.warning(f"Güvensiz redirect engellendi: {url} → {redirect_url}")
            break

        response = session.get(redirect_url, allow_redirects=False, **{k:v for k,v in kwargs.items() if k != 'allow_redirects'})
        redirect_count += 1

    return response
```

#### Adım 2.4.2: 4 lokasyonda allow_redirects=True'yu değiştir

**Satır 137** (Cookie warmup):
```python
# ÖNCE:
warmup_response = session.get(url, ..., allow_redirects=True)
# SONRA:
warmup_response = safe_get(session, url, headers=warmup_headers, timeout=(5, 10))
```

**Satır 423** (Primary data fetch):
```python
# ÖNCE:
response = session.get(url, ..., allow_redirects=True)
# SONRA:
response = safe_get(session, url, headers=headers, timeout=(...))
```

**Satır 733** (Date data fetch):
```python
# ÖNCE:
response = session.get(url, ..., allow_redirects=True)
# SONRA:
response = safe_get(session, url, headers=headers, timeout=(...))
```

**Satır 939** (Old format fetch):
```python
# ÖNCE:
response = session.get(url, ..., allow_redirects=True)
# SONRA:
response = safe_get(session, url, headers=headers, timeout=(15, 30))
```

---

### 2.5 Source URL Validasyonu

**Çözdüğü açıklar:** #3 (SSRF), #14 (SSRF via force-primary)
**Dosya:** `routes/health.py` satır ~197-236

#### Adım 2.5.1: URL validasyon fonksiyonu ekle

**Dosya:** `routes/health.py` - import'lardan sonra

```python
from urllib.parse import urlparse

ALLOWED_SOURCE_HOSTS = {
    'live3.nowgoal26.com',
    'live4.nowgoal26.com',
    'www.nowgoal.com',
    'www.goaloo.com',
    'football.nowgoal26.com',
}

def validate_source_url(url):
    """Source URL'i doğrula - sadece bilinen kaynaklar kabul edilir"""
    parsed = urlparse(url)

    if parsed.scheme not in ('http', 'https'):
        return False, "Sadece HTTP/HTTPS desteklenir"

    if parsed.hostname not in ALLOWED_SOURCE_HOSTS:
        return False, f"Bilinmeyen kaynak: {parsed.hostname}. İzin verilen: {', '.join(ALLOWED_SOURCE_HOSTS)}"

    return True, None
```

#### Adım 2.5.2: force-primary endpoint'ine ekle

```python
@health_bp.route('/sources/force-primary', methods=['POST'])
@require_api_key
def force_primary_source():
    data = request.get_json()
    source_url = data.get('source_url')

    if not source_url:
        return jsonify(build_error_response("Missing 'source_url'")), 400

    # URL validasyonu ekle
    is_valid, error_msg = validate_source_url(source_url)
    if not is_valid:
        return jsonify(build_error_response(error_msg)), 400

    # ... mevcut kod devam eder
```

---

### 2.6 Security Headers Tamamlama

**Çözdüğü açıklar:** #16 (Server header), #22 (CSP eksik), #24 (Auth response cache-control)
**Dosyalar:** `security.py`, `app.py`, `routes/auth.py`

#### Adım 2.6.1: Eksik header'ları ekle

**Dosya:** `security.py` - SecurityMiddleware.after_request bölümü (satır ~285-300)

```python
# MEVCUT header'ların yanına ekle:
response.headers['Content-Security-Policy'] = "default-src 'none'; frame-ancestors 'none'"
response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
response.headers['Permissions-Policy'] = 'geolocation=(), camera=(), microphone=()'

# Server header'ı kaldır (varsa)
response.headers.pop('Server', None)
```

#### Adım 2.6.2: Auth endpoint'e Cache-Control ekle

**Dosya:** `routes/auth.py` - generate_token fonksiyonunda response dönmeden önce:

```python
response = jsonify({
    'access_token': token,
    'token_type': 'Bearer',
    'expires_in': 3600
})
response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
response.headers['Pragma'] = 'no-cache'
return response
```

#### Adım 2.6.3: Gunicorn server header'ı gizle

**Dosya:** `gunicorn_config.py` - dosya sonuna ekle:

```python
# Server header'ı gizle
import gunicorn
gunicorn.SERVER = ''
```

---

## Faz 3: Orta Vade (1 Hafta)

### 3.1 JWT Token Güvenliği

**Çözdüğü açıklar:** #16 (Token iptal yok), #18 (Concurrent token), #21 (jti yok)
**Dosyalar:** `security.py`

#### Adım 3.1.1: Token'a jti claim ekle

**Dosya:** `security.py` - generate_api_token fonksiyonu (satır ~220-234)

```python
import uuid

def generate_api_token(user_id='api_user', role='user', expires_in=3600):
    """JWT token oluştur - jti ve role ile"""
    jti = str(uuid.uuid4())

    payload = {
        'user_id': user_id,
        'role': role,
        'jti': jti,
        'exp': time.time() + expires_in,
        'iat': time.time()
    }

    token = jwt.encode(payload, current_app.config['JWT_SECRET_KEY'], algorithm='HS256')

    # Active token olarak kaydet (eski token'ı iptal etmek için)
    try:
        from app_config import current_config
        import redis
        r = redis.Redis(
            host=current_config.CACHE_REDIS_HOST,
            port=current_config.CACHE_REDIS_PORT,
            password=current_config.CACHE_REDIS_PASSWORD
        )
        # Eski token'ı iptal et
        old_jti = r.get(f"active_token:{user_id}")
        if old_jti:
            r.setex(f"revoked:{old_jti.decode()}", expires_in, "1")

        # Yeni token'ı active olarak kaydet
        r.setex(f"active_token:{user_id}", expires_in, jti)
    except Exception:
        pass  # Redis yoksa sessizce devam et

    return token
```

#### Adım 3.1.2: require_auth'a revocation kontrolü ekle

**Dosya:** `security.py` - require_auth decorator'ında (satır ~18-55)

JWT decode'dan sonra, return'den önce:

```python
# JWT doğrulamadan sonra:
payload = jwt.decode(token, ...)
current_user = payload.get('user_id')
jti = payload.get('jti')

# Token revocation kontrolü
if jti:
    try:
        import redis
        from app_config import current_config
        r = redis.Redis(
            host=current_config.CACHE_REDIS_HOST,
            port=current_config.CACHE_REDIS_PORT,
            password=current_config.CACHE_REDIS_PASSWORD
        )
        if r.exists(f"revoked:{jti}"):
            return jsonify({'error': 'Token has been revoked'}), 401
    except Exception:
        pass  # Redis yoksa skip (güvenlik vs erişilebilirlik tradeoff)

g.current_user = current_user
```

---

### 3.2 RBAC Implementasyonu

**Çözdüğü açıklar:** #12 (RBAC yok)
**Dosya:** `security.py`

#### Adım 3.2.1: Role decorator oluştur

**Dosya:** `security.py` - require_api_key'den sonra ekle:

```python
def require_role(required_role):
    """Rol tabanlı yetkilendirme decorator'ı"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # JWT'den role al
            user_role = getattr(g, 'user_role', None)

            # API key ile giriş yaptıysa admin sayılır
            if getattr(g, 'api_authenticated', False):
                user_role = 'admin'

            if not user_role:
                return jsonify({'error': 'Authentication required'}), 401

            if user_role != required_role and user_role != 'admin':
                return jsonify({'error': f'{required_role} privileges required'}), 403

            return f(*args, **kwargs)
        return decorated_function
    return decorator

require_admin = require_role('admin')
```

#### Adım 3.2.2: Admin endpoint'lere role check ekle

İleride `@require_api_key` yerine `@require_auth` + `@require_admin` kombinasyonu kullanılabilir. Şimdilik `@require_api_key` zaten admin erişimi sağlıyor.

---

### 3.3 Audit Logging

**Çözdüğü açıklar:** #17 (Audit log yok)
**Dosya:** Yeni `audit.py`

#### Adım 3.3.1: audit.py oluştur

```python
"""Güvenlik audit logging modülü"""
import logging
import json
from datetime import datetime
from flask import request
from security import get_real_ip

audit_logger = logging.getLogger('audit')
audit_handler = logging.FileHandler('logs/audit.log')
audit_handler.setFormatter(logging.Formatter('%(message)s'))
audit_logger.addHandler(audit_handler)
audit_logger.setLevel(logging.INFO)


def log_admin_action(action, endpoint, details=None):
    """Admin işlemlerini logla"""
    entry = {
        'timestamp': datetime.utcnow().isoformat(),
        'type': 'ADMIN_ACTION',
        'action': action,
        'endpoint': endpoint,
        'ip': get_real_ip(),
        'api_key_prefix': (request.headers.get('X-API-Key', '')[:8] + '...') if request.headers.get('X-API-Key') else 'none',
        'user_agent': request.headers.get('User-Agent', 'unknown'),
        'details': details
    }
    audit_logger.info(json.dumps(entry))


def log_auth_attempt(success, reason=None):
    """Auth denemelerini logla"""
    entry = {
        'timestamp': datetime.utcnow().isoformat(),
        'type': 'AUTH_ATTEMPT',
        'success': success,
        'ip': get_real_ip(),
        'endpoint': request.path,
        'reason': reason
    }
    audit_logger.info(json.dumps(entry))
```

#### Adım 3.3.2: Admin endpoint'lerde kullan

**Dosya:** `routes/health.py` - her admin fonksiyonun başına:

```python
from audit import log_admin_action

@health_bp.route('/cache/clear', methods=['POST'])
@require_api_key
def clear_cache():
    log_admin_action('CACHE_CLEAR', '/api/v1/cache/clear')
    # ... mevcut kod
```

---

### 3.4 IP Spoofing Koruması

**Çözdüğü açıklar:** #11 (IP spoofing)
**Dosya:** `security.py` satır 159-169
**Bağımlılık:** Faz 2.1 (HTTPS/Nginx) tamamlanmış olmalı. Nginx `X-Forwarded-For` header'ını `$remote_addr` ile override ettiği için (Adım 2.1.3'te yapıldı) bu adım Nginx arkasında çalışırken güvenlidir.

#### Adım 3.4.1: get_real_ip'i güncelle

```python
# Güvenilir proxy'ler (Nginx, Load Balancer)
TRUSTED_PROXIES = {'127.0.0.1', '::1'}

def get_real_ip():
    """Gerçek client IP'sini al - sadece güvenilir proxy'lere güven"""
    remote = request.remote_addr

    # Sadece güvenilir proxy'den gelen header'lara güven
    if remote in TRUSTED_PROXIES:
        forwarded = request.headers.get('X-Forwarded-For')
        if forwarded:
            # İlk IP client IP'si
            return forwarded.split(',')[0].strip()

        real_ip = request.headers.get('X-Real-IP')
        if real_ip:
            return real_ip

    return remote
```

---

### 3.5 Veri Endpoint'lerine Global Auth Stratejisi

**Çözdüğü açıklar:** #6 (Tüm veri endpoint'leri auth'suz)
**Dosya:** `security.py` - SecurityMiddleware

#### Karar Noktası

Bu adım iş kararı gerektirir. İki seçenek:

**Seçenek A: SecurityMiddleware ile global API key zorunlu kıl (Önerilen)**

Mevcut `SecurityMiddleware.before_request()` zaten bu yeteneğe sahip ama devre dışı bırakılabilir durumda. Etkinleştirmek için:

**Dosya:** `security.py` - SecurityMiddleware.before_request (satır ~258-274)

```python
def before_request(self):
    """Her istek öncesi çalışan güvenlik kontrolü"""
    # Health endpoint'leri muaf tut
    exempt_paths = ['/health', '/api/v1/health', '/api/v1/health/detailed', '/']
    if any(request.path == p or request.path.startswith(p + '/') for p in exempt_paths):
        return None

    # API key kontrolü
    expected_key = current_app.config.get('API_SECRET_KEY')
    if not expected_key:
        return None  # Key ayarlanmamışsa kontrol yapma (dev mode)

    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return jsonify({'error': 'API key is required', 'success': False}), 401

    if not hmac.compare_digest(api_key, expected_key):
        return jsonify({'error': 'Invalid API key', 'success': False}), 403

    return None
```

**Seçenek B: Endpoint bazlı auth (daha granüler ama daha fazla iş)**

Her route dosyasına tek tek `@require_api_key` eklemek. 32 endpoint için uzun iş ama bazı endpoint'leri public bırakma esnekliği verir.

> **Öneri:** Seçenek A ile başla. İleride belirli endpoint'leri public yapmak gerekirse exempt_paths listesine ekle.

#### Adım 3.5.1: Client uygulamayı uyar

Global auth aktif edilmeden önce client uygulamada (golsinyali.com) tüm API çağrılarına `X-API-Key` header'ı eklenmeli:

```javascript
// Client tarafı (golsinyali.com)
const API_KEY = process.env.GOLSINYALI_API_KEY;

fetch('https://api.golsinyali.com/api/v1/matches/today', {
    headers: {
        'X-API-Key': API_KEY
    }
})
```

#### Adım 3.5.2: Kademeli geçiş

1. Önce client'ı güncelle (key göndermeye başla)
2. 1 hafta bekle, loglardan key göndermeyen istekleri izle
3. Global auth'u aktif et
4. Key göndermeyen eski client'lar 401 alır

---

## Faz 4: Uzun Vade (1 Ay)

### 4.1 Dependency Pinning

**Çözdüğü açıklar:** #13 (Dependency pinning yok)
**Dosya:** `requirements.txt`

```bash
# Mevcut versiyonları kilitle
pip freeze > requirements.txt

# Veya pip-tools kullan (daha iyi)
pip install pip-tools
echo "Flask
beautifulsoup4
lxml
requests
flask-caching
python-dotenv
marshmallow
flask-limiter
flask-cors
PyJWT
bcrypt
redis
flask-caching[redis]
sentry-sdk[flask]
gunicorn
gevent
boto3
flask-compress" > requirements.in

pip-compile requirements.in
# → requirements.txt otomatik oluşur, tüm versiyonlar kilitli
```

---

### 4.2 Upstream Veri Sanitizasyonu

**Çözdüğü açıklar:** #20 (Upstream veri sanitize edilmemiş)
**Dosyalar:** `parsers.py`, `live_parsers.py`, `league_parser.py`

#### Adım 4.2.1: Sanitize helper fonksiyonu

**Dosya:** Yeni `sanitize.py`

```python
"""Upstream veriden gelen metni sanitize et"""
import html
import re

def sanitize_text(text):
    """HTML entity'leri escape et"""
    if not isinstance(text, str):
        return text
    return html.escape(text)

def sanitize_dict(data):
    """Dict içindeki tüm string'leri sanitize et"""
    if isinstance(data, dict):
        return {k: sanitize_dict(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_dict(item) for item in data]
    elif isinstance(data, str):
        return sanitize_text(data)
    return data
```

Parser'ların return ettiği verilerde `sanitize_dict()` çağır.

---

### 4.3 Server Hardening

**Çözdüğü açıklar:** #16 (Server header), #15 (HSTS preload)

#### Adım 4.3.1: HSTS Preload listesine başvur

```
1. https://hstspreload.org/ adresine git
2. api.golsinyali.com domain'ini submit et
3. Gereksinimler:
   - HTTPS zorunlu
   - max-age >= 31536000
   - includeSubDomains gerekli
   - preload directive gerekli
```

---

## Test Planı

### Her faz sonrası çalıştırılacak testler:

```bash
#!/bin/bash
# security_test.sh - Güvenlik testleri

echo "=== 1. Health Check ==="
curl -s http://localhost:8000/api/v1/health | python3 -m json.tool

echo "=== 2. Admin Auth Test (auth olmadan → 401 beklenir) ==="
curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/api/v1/cache/clear
curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/api/v1/sources/force-primary
curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/api/v1/sources/reset-metrics
curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/api/v1/cache/stats/reset

echo "=== 3. CORS Test (kötü origin → header yok beklenir) ==="
curl -s -I -H "Origin: https://evil.com" http://localhost:8000/api/v1/health | grep "Access-Control"

echo "=== 4. CORS Test (iyi origin → header var beklenir) ==="
curl -s -I -H "Origin: https://golsinyali.com" http://localhost:8000/api/v1/health | grep "Access-Control"

echo "=== 5. Security Headers ==="
curl -s -I http://localhost:8000/api/v1/health | grep -iE "x-frame|x-content|strict-transport|content-security|server|referrer-policy"

echo "=== 6. Rate Limit Test ==="
for i in $(seq 1 12); do
  curl -s -o /dev/null -w "%{http_code} " -X POST http://localhost:8000/api/v1/auth/token \
    -H "Content-Type: application/json" -d '{"api_key":"test"}'
done

echo "=== 7. Veri erişimi testi ==="
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/matches/today
```

---

## Monitoring ve Alerting

Her faz sonrası şu metrikleri izle:

### Sentry'de izlenecekler

```
1. Error rate artışı → Kod değişikliği bir şeyi bozmuş olabilir
2. 401/403 artışı → Auth değişikliği client'ları etkilemiş olabilir
3. 429 artışı → Rate limit çok agresif olabilir
```

### Log'larda izlenecekler

```bash
# Başarısız auth denemeleri (brute-force tespiti)
grep "Invalid API key\|API key is required" logs/app.log | wc -l

# Rate limit aşımları
grep "429\|Rate limit" logs/app.log | wc -l

# Admin işlemleri (Faz 3 sonrası)
tail -f logs/audit.log

# Source değişiklikleri
grep "force-primary\|source.*forced" logs/app.log
```

### Alarm kuralları (Sentry veya custom)

| Alarm | Koşul | Aksiyon |
|-------|-------|---------|
| Brute-force şüphesi | Aynı IP'den 50+ başarısız auth/dakika | IP'yi geçici ban |
| DoS saldırısı | Cache clear 5+/dakika | Admin endpoint'leri geçici kapat |
| Source manipulation | force-primary çağrısı | Slack/email bildirim |
| Yüksek hata oranı | 5xx > %5 | Otomatik rollback değerlendir |

---

## Rollback Planı

> **KURAL:** Her faz uygulanmadan önce `git tag pre-faz-X` ile tag oluştur. Sorun olursa tag'e dön.

### Her faz öncesi

```bash
# Tag oluştur
git tag pre-faz-1
git push origin pre-faz-1

# .env yedek
cp .env .env.backup.$(date +%Y%m%d_%H%M)
```

### Faz 1 Rollback

```bash
# Secret'ları geri al
cp .env.backup.YYYYMMDD .env
sudo systemctl restart golsinyali-api

# Kod değişikliğini geri al (admin auth)
git checkout pre-faz-1 -- routes/health.py config.py app.py
sudo systemctl restart golsinyali-api
```

### Faz 2 Rollback

```bash
# Nginx'i devre dışı bırak
sudo systemctl stop nginx
sudo ufw allow 8000/tcp

# Gunicorn'u eski haline getir
git checkout pre-faz-2 -- gunicorn_config.py http_client.py
sudo systemctl restart golsinyali-api

# Redis şifresini kaldır (gerekirse)
sudo sed -i 's/^requirepass.*/#requirepass/' /etc/redis/redis.conf
sudo systemctl restart redis
```

### Faz 3 Rollback

```bash
# JWT ve RBAC değişikliklerini geri al
git checkout pre-faz-3 -- security.py
sudo systemctl restart golsinyali-api

# Redis'teki token blacklist verilerini temizle
redis-cli -a SIFRE KEYS "revoked:*" | xargs redis-cli -a SIFRE DEL
redis-cli -a SIFRE KEYS "active_token:*" | xargs redis-cli -a SIFRE DEL

# Audit log dosyası zararsız, silmeye gerek yok
```

### Faz 4 Rollback

```bash
git checkout pre-faz-4 -- requirements.txt sanitize.py
pip install -r requirements.txt  # Eski versiyonlara dön
sudo systemctl restart golsinyali-api
```

### Acil Durum (Tam Rollback)

```bash
# Tüm değişiklikleri geri al
cd /var/www/golsinyali_api
cp /tmp/golsinyali_backup_YYYYMMDD/.env .env
git checkout pre-faz-1
sudo systemctl restart golsinyali-api
sudo systemctl stop nginx  # Eğer kurulduysa
sudo ufw allow 8000/tcp
```

---

## Adımlar Arası Bağımlılıklar

```
1.1 Secret Rotation ──────────────────────────────── Bağımsız (ilk yapılmalı)
1.2 Admin Auth ────────────────────────────────────── Bağımsız
1.3 CORS ──────────────────────────────────────────── Bağımsız
1.4 .env Güvenliği ────────────────────────────────── 1.1'den sonra

2.1 HTTPS ─────────────────────────────────────────── Bağımsız (domain gerekli)
2.2 Redis Şifre ───────────────── 2.3'ten ÖNCE ────── (limiter storage_uri etkiler)
2.3 Rate Limiting ─────────────── 2.2'den SONRA ───── (Redis şifre gerekir)
2.4 Redirect Güvenliği ────────────────────────────── Bağımsız
2.5 Source URL Validasyonu ── 1.2'den SONRA ────────── (auth eklenmişken)
2.6 Security Headers ──────────────────────────────── Bağımsız

3.1 JWT Güvenliği ──────────── 2.2'den SONRA ────────── (Redis şifre gerekir)
3.2 RBAC ───────────────────── 3.1'den SONRA ────────── (JWT role claim gerekir)
3.3 Audit Logging ──────────── 1.2'den SONRA ────────── (admin auth olmalı)
3.4 IP Spoofing ────────────── 2.1'den SONRA ────────── (Nginx trusted proxy)
3.5 Global Auth ────────────── Client güncellendikten SONRA

4.1 Dependency Pinning ────────────────────────────── Bağımsız
4.2 Upstream Sanitizasyon ─────────────────────────── Bağımsız
4.3 Server Hardening ──────── 2.1'den SONRA ────────── (HTTPS gerekli)
```

---

## Özet Zaman Çizelgesi

```
Gün 1 (Acil):                                     Bağımlılık
  ├── 1.1 Secret rotation (30 dk)                  Yok
  ├── 1.2 Admin auth ekleme (15 dk)                Yok
  ├── 1.3 CORS düzeltme (10 dk)                    Yok
  ├── 1.4 .env güvenliği (20 dk)                   → 1.1
  └── TEST + DOĞRULAMA (15 dk)

Gün 2-3 (Yüksek):
  ├── 2.1 HTTPS etkinleştirme (2 saat)             Domain gerekli
  ├── 2.2 Redis şifreleme (30 dk)                  Yok
  ├── 2.3 Rate limiting (45 dk)                    → 2.2
  │   └── rate_limiter.py modülü oluştur
  ├── 2.4 Redirect güvenliği (1 saat)              Yok
  ├── 2.5 Source URL validasyonu (20 dk)            → 1.2
  ├── 2.6 Security headers (20 dk)                 Yok
  └── TEST + DOĞRULAMA (30 dk)

Hafta 1 (Orta):
  ├── 3.1 JWT token güvenliği (2 saat)             → 2.2
  ├── 3.2 RBAC implementasyonu (1 saat)            → 3.1
  ├── 3.3 Audit logging (1 saat)                   → 1.2
  ├── 3.4 IP spoofing koruması (30 dk)             → 2.1
  ├── 3.5 Global auth stratejisi (kademeli)        → Client güncellemesi
  └── TEST + DOĞRULAMA (30 dk)

Ay 1 (Uzun):
  ├── 4.1 Dependency pinning (30 dk)               Yok
  ├── 4.2 Upstream sanitizasyon (2 saat)           Yok
  ├── 4.3 Server hardening (1 saat)                → 2.1
  └── FINAL TEST + SHANNON RE-RUN (1 saat)
```

---

## Checklist (Her adım sonrası işaretle)

### Faz 1
- [ ] 1.1.1 Yeni secret'lar oluşturuldu
- [ ] 1.1.2 AWS key'leri rotate edildi
- [ ] 1.1.3 Sunucu .env güncellendi
- [ ] 1.1.4 Sentry DSN yenilendi
- [ ] 1.1.5 Doğrulama testleri geçti
- [ ] 1.2.1 4 admin endpoint'e @require_api_key eklendi
- [ ] 1.2.3 Auth olmadan 401, auth ile 200 doğrulandı
- [ ] 1.3.1 CORS wildcard kaldırıldı
- [ ] 1.3.3 Evil origin reddedildi, iyi origin kabul edildi
- [ ] 1.4.2 Git geçmişinden .env temizlendi
- [ ] 1.4.3 Default secret'lar kaldırıldı

### Faz 2
- [ ] 2.1 HTTPS aktif, HTTP→HTTPS redirect çalışıyor
- [ ] 2.1 Port 8000 dışarıdan kapalı
- [ ] 2.1 SSL sertifika auto-renew ayarlandı
- [ ] 2.2 Redis şifreli, API hala çalışıyor
- [ ] 2.3 rate_limiter.py modülü oluşturuldu
- [ ] 2.3 Token endpoint rate limit çalışıyor
- [ ] 2.3 Admin endpoint rate limit çalışıyor
- [ ] 2.4 safe_get fonksiyonu 4 lokasyonda uygulandı
- [ ] 2.5 source_url validasyonu eklendi
- [ ] 2.6 CSP, Referrer-Policy, Permissions-Policy header'ları eklendi
- [ ] 2.6 Server header gizlendi

### Faz 3
- [ ] 3.1 JWT token'larda jti claim var
- [ ] 3.1 Token revocation (blacklist) çalışıyor
- [ ] 3.2 require_role decorator oluşturuldu
- [ ] 3.3 audit.py modülü oluşturuldu, admin işlemler loglanıyor
- [ ] 3.4 get_real_ip sadece trusted proxy'ye güveniyor
- [ ] 3.5 Global auth stratejisi için karar verildi

### Faz 4
- [ ] 4.1 requirements.txt versiyonlar kilitli
- [ ] 4.2 sanitize.py oluşturuldu, parser'larda kullanılıyor
- [ ] 4.3 HSTS preload başvurusu yapıldı

---

*Bu plan 24 güvenlik açığının tamamını kapsar. Her adım bağımsız testlerle doğrulanabilir. Faz 1 en kritiktir ve hemen uygulanmalıdır. Adımlar arası bağımlılıklar yukarıda belirtilmiştir - sırayı takip edin.*
