# Setup Guide: ZAP DAST Scanner (Dev Team Chỉ Điền Form)

## Mô Hình Hoàn Chỉnh

```
DevSecOps làm 1 lần:                      Dev Team mỗi lần muốn scan:
─────────────────────────────────          ────────────────────────────────
1. Deploy ZAP Service                      1. Vào job "ZAP-DAST-Scanner"
2. Đăng ký Shared Library                 2. Bấm "Build with Parameters"
3. Tạo Jenkins job Scanner                 3. Điền form → Bấm Build
                                           4. Xem kết quả
```

---

## Cấu Trúc Repo Shared Lib (đẩy lên Git riêng)

```
zap-jenkins-shared-lib/              ← Git repo riêng (hoặc subfolder)
├── vars/
│   └── zapScan.groovy               ← Logic hoàn chỉnh, tự đọc params.*
└── Jenkinsfile.scanner              ← Pipeline cho job Scanner
```

---

## Bước 1: Đăng Ký Shared Library Trong Jenkins

> **Thực hiện 1 lần duy nhất** bởi DevSecOps / Jenkins Admin

```
Manage Jenkins
  → Configure System
    → Global Pipeline Libraries
      → Add:
          Name:            zap-shared-lib
          Default version: main
          Retrieval:       Modern SCM → Git
          URL:             https://git.company.com/devsecops/zap-jenkins-shared-lib.git
```

---

## Bước 2: Tạo Jenkins Job "ZAP-DAST-Scanner"

> **Thực hiện 1 lần duy nhất** bởi DevSecOps / Jenkins Admin

```
Jenkins → New Item
  → Tên: ZAP-DAST-Scanner
  → Loại: Pipeline
  → OK

Cấu hình:
  Pipeline → Definition: Pipeline script from SCM
    SCM: Git
    URL: https://git.company.com/devsecops/zap-jenkins-shared-lib.git
    Script Path: Jenkinsfile.scanner
```

> [!IMPORTANT]
> **Chỉ làm đúng 2 bước trên.** Sau đó dev team tự dùng, không cần đụng vào cấu hình nữa.

---

## Trải Nghiệm Dev Team (Không Cần Viết Code)

Dev team vào job `ZAP-DAST-Scanner` → `Build with Parameters`, thấy form:

```
┌──────────────────────────────────────────────────────┐
│  ZAP DAST Scanner — Build with Parameters            │
├──────────────────────────────────────────────────────┤
│  PROJECT_NAME    [nextgen-ebanking            ]      │
│  ENVIRONMENT     [DEV                         ]      │
│                                                      │
│  BASE_URL        [https://dev.myapp.com       ]      │
│                                                      │
│  ENABLE_PRELOGIN [✓]                                 │
│                                                      │
│  LOGIN_CURL_COMMAND                                  │
│  ┌────────────────────────────────────────────────┐  │
│  │ curl -sS -X POST                               │  │
│  │   -H "Content-Type: application/json"          │  │
│  │   --data-binary '{"username":"u","password":"p"}│  │
│  │   https://dev.myapp.com/api/login               │  │
│  │   > zap-tmp/auth_response_raw.json              │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  SCAN_EXCLUDE_APIS [/api/logout,/api/health   ]      │
│  API_PATH          [/api/                     ]      │
│                                                      │
│  ▼ Advanced                                          │
│  DOCKER_IMAGE      [ghcr.io/zaproxy/zaproxy:stable]  │
│  POLL_TIMEOUT_SEC  [1800                      ]      │
│                                                      │
│                              [  BUILD  ]             │
└──────────────────────────────────────────────────────┘
```

---

## Luồng Khi Dev Team Bấm Build

```
Jenkins Job
  │
  ▼
Stage: Validate Input
  │  Kiểm tra PROJECT_NAME, BASE_URL, LOGIN_CURL_COMMAND
  │  Nếu thiếu → fail sớm với thông báo rõ ràng
  ▼
Stage: Run ZAP DAST Scan
  │  zapScan() tự đọc params.* từ Jenkins UI
  │  → POST http://zap-server:8080/scan
  │  → Polling mỗi 20s
  │  → In log realtime
  ▼
Post: Publish Report
  │  publishHTML → Tab "ZAP Report" xuất hiện trên job
  │  archiveArtifacts → zap-out/*.html
  ▼
Kết quả:
  ✅ SUCCESS → Xem report
  ❌ FAILURE → Xem log lỗi + link full log trên ZAP Service
```

---

## Cấu Hình Validation Tự Động

Job sẽ tự kiểm tra và báo lỗi rõ ràng nếu dev team điền sai:

| Lỗi | Thông báo |
|-----|-----------|
| `PROJECT_NAME` trống | `❌ PROJECT_NAME không được để trống!` |
| `BASE_URL` trống | `❌ BASE_URL không được để trống!` |
| Bật prelogin nhưng không có curl command | `❌ LOGIN_CURL_COMMAND bắt buộc khi ENABLE_PRELOGIN = true!` |
| Curl command thiếu redirect | `❌ LOGIN_CURL_COMMAND phải có '> zap-tmp/auth_response_raw.json' ở cuối!` |

---

## Thêm Notification (Tuỳ Chọn)

Có thể thêm Slack/Email vào `post` trong `Jenkinsfile.scanner`:

```groovy
post {
    success {
        slackSend(
            color: 'good',
            message: "✅ ZAP Scan PASSED: *${params.PROJECT_NAME}* [${params.ENVIRONMENT}]\n${env.BUILD_URL}"
        )
    }
    failure {
        slackSend(
            color: 'danger',
            message: "❌ ZAP Scan FAILED: *${params.PROJECT_NAME}* [${params.ENVIRONMENT}]\n${env.BUILD_URL}"
        )
    }
}
```
