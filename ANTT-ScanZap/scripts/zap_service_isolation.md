# ZAP Service — Cô Lập Hoàn Toàn Với Jenkins

## Kiến Trúc Tổng Thể

```
┌──────────────────────────────────────────────────────────────────────┐
│                        INFRA / DevSecOps Team                        │
│                                                                      │
│  ┌─────────────────────────────────────────┐                         │
│  │         ZAP Service Repository          │  → deploy 1 lần        │
│  │  zap-service/                           │    chạy mãi mãi        │
│  │    Dockerfile                           │                         │
│  │    docker-compose.yml                   │                         │
│  │    app/ (FastAPI)                       │                         │
│  │    zap-scripts/ (pipeline.sh, utils.py) │                         │
│  └───────────────┬─────────────────────────┘                         │
│                  │ docker-compose up -d                               │
│                  ▼                                                    │
│         [ZAP Service :8080] ◄── http://zap-server:8080               │
└──────────────────────────────────────────────────────────────────────┘
           ▲              ▲              ▲
           │              │              │
   Project A Jenkins   Project B Jenkins   Project C Jenkins
   @Library('zap')     @Library('zap')     @Library('zap')
   zapScan(...)        zapScan(...)        zapScan(...)
```

---

## 3 Thành Phần Cần Tách Ra

### 1. ZAP Service Repository (DevSecOps quản lý)

Repo riêng — không thuộc bất kỳ project app nào:

```
zap-dast-service/               ← Git repo riêng
├── app/
│   ├── main.py
│   ├── runner.py
│   ├── models.py
│   └── config.py
├── zap-scripts/                ← Copy từ zap/ hiện tại
│   ├── zap_pipeline.sh
│   ├── zap_utils.py
│   ├── zap_logger.js
│   └── automation.yaml.tpl
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

### 2. Jenkins Shared Library (DevSecOps quản lý)

Repo riêng cho Shared Library — đăng ký 1 lần trong Jenkins:

```
zap-jenkins-shared-lib/        ← Git repo riêng
└── vars/
    └── zapScan.groovy          ← Function tái sử dụng
```

**Cách đăng ký trong Jenkins:**
> `Manage Jenkins` → `Configure System` → `Global Pipeline Libraries`
> - Name: `zap-shared-lib`
> - Default version: `main`
> - Source: Git URL của repo shared lib

### 3. Project Jenkinsfile (mỗi team dev quản lý)

Mỗi project chỉ cần **3 dòng** để tích hợp ZAP:

```groovy
@Library('zap-shared-lib') _

// Trong stage DAST:
zapScan(
    serviceUrl:       'http://zap-server:8080',
    baseUrl:          'https://dev.myapp.com',
    enablePrelogin:   true,
    loginCurlCommand: 'curl -sS -X POST ...'
)
```

> [!IMPORTANT]
> Project dev **không cần** checkout ZAP repo, không cần biết `zap_pipeline.sh` hoạt động như thế nào.

---

## So Sánh Trước / Sau

| | Trước (embedded) | Sau (service) |
|--|--|--|
| ZAP scripts | Nằm trong repo app | Repo riêng, deploy độc lập |
| Jenkinsfile | Phức tạp, 200 dòng | 3 dòng `zapScan(...)` |
| Cập nhật ZAP | Phải sửa từng repo | Cập nhật service, tất cả project được hưởng |
| Chạy parallel | Không (1 agent) | Có (nhiều job cùng lúc) |
| Phụ thuộc agent | Cần Docker + bash | Chỉ cần `curl` |

---

## Cách Deploy Thực Tế

### Bước 1: Deploy ZAP Service lên server (1 lần)

```bash
# Trên server infra (VD: 192.168.1.100)
git clone https://git.company.com/devsecops/zap-dast-service.git
cd zap-dast-service
docker-compose up -d

# Verify
curl http://192.168.1.100:8080/health
# → {"status":"ok","service":"zap-dast-service"}
```

### Bước 2: Đăng ký Shared Library trong Jenkins (1 lần)

```
Manage Jenkins
  → Configure System
    → Global Pipeline Libraries
      → Add:
          Name: zap-shared-lib
          Default version: main
          Retrieval method: Modern SCM
          Source: https://git.company.com/devsecops/zap-jenkins-shared-lib.git
```

### Bước 3: Mỗi project tự thêm vào Jenkinsfile

```groovy
@Library('zap-shared-lib') _

pipeline {
    ...
    stages {
        stage('DAST Scan') {
            steps {
                script {
                    zapScan(
                        serviceUrl:       'http://192.168.1.100:8080',
                        baseUrl:          'https://dev.myapp.com',
                        enablePrelogin:   true,
                        loginCurlCommand: params.LOGIN_CURL
                    )
                }
            }
        }
    }
}
```

---

## Cập Nhật ZAP Không Ảnh Hưởng Projects

Khi cần cập nhật logic scan (sửa `zap_pipeline.sh`, `zap_utils.py`...):

```bash
# Chỉ cần làm trên ZAP Service server
cd zap-dast-service
git pull
docker-compose up -d --build

# Tất cả project sẽ dùng logic mới ngay lập tức
# Không cần thay đổi bất kỳ Jenkinsfile nào
```

---

> [!TIP]
> Để bảo mật, có thể thêm API key vào service:
> ```python
> # app/main.py — thêm dependency
> from fastapi.security.api_key import APIKeyHeader
> api_key_header = APIKeyHeader(name="X-ZAP-API-Key")
> ```
> Jenkins truyền key qua Jenkins Credentials:
> ```groovy
> withCredentials([string(credentialsId: 'zap-api-key', variable: 'ZAP_KEY')]) {
>     zapScan(serviceUrl: '...', apiKey: env.ZAP_KEY)
> }
> ```
