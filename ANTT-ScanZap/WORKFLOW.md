# ZAP DAST SCANNER — WORKFLOW DIAGRAM

```
====================================================================
               TỔNG QUAN HỆ THỐNG (SYSTEM OVERVIEW)
====================================================================

  ┌─────────────────────────────────────────────────────────────┐
  │                  INFRA SERVER (DevSecOps)                   │
  │                                                             │
  │   ┌─────────────────────────────────────────────────────┐   │
  │   │              ZAP Service (FastAPI :8080)            │   │
  │   │                                                     │   │
  │   │   /scan   /status   /logs   /report   /jobs        │   │
  │   │                                                     │   │
  │   │   workspace/{job_id}/                               │   │
  │   │     ├── zap-tmp/   (auth token, config...)          │   │
  │   │     └── zap-out/   (report HTML)                    │   │
  │   └───────────────┬─────────────────────────────────────┘   │
  │                   │ docker run                               │
  │   ┌───────────────▼─────────────────────────────────────┐   │
  │   │          ZAP Docker Container                       │   │
  │   │     ghcr.io/zaproxy/zaproxy:stable                  │   │
  │   └─────────────────────────────────────────────────────┘   │
  │                                                             │
  │   zap-scripts/ (zap_pipeline.sh, zap_utils.py, ...)        │
  └─────────────────────────────────────────────────────────────┘
               ▲                       ▲
               │ HTTP /scan            │ HTTP /scan
  ┌────────────┴────────┐   ┌──────────┴────────────────────────┐
  │  ZAP-DAST-Scanner   │   │   Pipeline của Project khác       │
  │  (Jenkins job chính)│   │   @Library + zapScan()            │
  │  Jenkinsfile.scanner│   │   hoặc curl thẳng vào /scan       │
  └────────────┬────────┘   └───────────────────────────────────┘
               │ Shared Library
  ┌────────────▼────────┐
  │  vars/zapScan.groovy│
  │  (Shared Library)   │
  └────────────┬────────┘
               │ Gọi từ Jenkins UI
  ┌────────────▼────────┐
  │     Dev Team        │
  │  Build with Params  │
  └─────────────────────┘


====================================================================
        LUỒNG CHI TIẾT: DEV TEAM → ZAP SERVICE (SEQUENCE)
====================================================================

  Dev Team          Jenkins Job         zapScan.groovy      ZAP Service
     │                   │                   │                   │
     │─── Build ────────►│                   │                   │
     │    (với params)   │                   │                   │
     │                   │                   │                   │
     │              [Validate Input]         │                   │
     │              PROJECT_NAME?            │                   │
     │              BASE_URL?                │                   │
     │              LOGIN_CURL ok?           │                   │
     │                   │                   │                   │
     │                   │──zapScan()───────►│                   │
     │                   │                   │                   │
     │                   │              GET /health              │
     │                   │                   │──────────────────►│
     │                   │                   │◄── {"status":"ok"}│
     │                   │                   │                   │
     │                   │              POST /scan               │
     │                   │                   │──────────────────►│
     │                   │                   │◄─{"job_id":"abc"} │
     │                   │                   │                   │
     │                   │          ┌── Poll every 20s ──┐       │
     │                   │          │  GET /status/abc   │       │
     │                   │          │   ◄── running...   │       │
     │                   │          │   echo [Xs] stage  │       │
     │                   │          └────────────────────┘       │
     │                   │                   │                   │
     │                   │              GET /report/abc          │
     │                   │                   │──────────────────►│
     │                   │                   │◄─── report.html   │
     │                   │                   │                   │
     │                   │            DELETE /jobs/abc           │
     │                   │                   │──────────────────►│
     │                   │                   │◄── {"deleted":ok} │
     │                   │                   │                   │
     │              [PublishHTML]            │                   │
     │              [ArchiveArtifacts]       │                   │
     │                   │                   │                   │
     │◄── Report Tab ────│                   │                   │
     │    (Jenkins UI)   │                   │                   │


====================================================================
          ZAP SERVICE — LUỒNG NỘI BỘ (8 STAGES PIPELINE)
====================================================================

  POST /scan
     │
     ▼
  ┌─────────────────────────────────────────────┐
  │  Tạo workspace/{job_id}/                    │
  │  Ghi status = "pending"                     │
  └──────────────────┬──────────────────────────┘
                     │  Background task (asyncio)
                     ▼
  ┌─────────────────────────────────────────────┐
  │  Stage 1: preflight_debug                   │
  │  (in ra config, môi trường hiện tại)        │
  └──────────────────┬──────────────────────────┘
                     │
  ┌─────────────────────────────────────────────┐
  │  Stage 2: preflight_list_dirs               │
  │  (kiểm tra thư mục workspace, scripts)      │
  └──────────────────┬──────────────────────────┘
                     │
  ┌─────────────────────────────────────────────┐
  │  Stage 3: inspect_collection                │
  │  (đọc Postman collection, trích xuất URLs)  │
  └──────────────────┬──────────────────────────┘
                     │
  ┌─────────────────────────────────────────────┐
  │  Stage 4: prelogin                          │
  │  (chạy LOGIN_CURL_COMMAND nếu bật)          │
  │  → lưu response vào auth_response_raw.json  │
  └──────────────────┬──────────────────────────┘
                     │
  ┌─────────────────────────────────────────────┐
  │  Stage 5: validate_token                    │
  │  (trích xuất token từ response)             │
  │  → lưu vào auth_token.txt                   │
  └──────────────────┬──────────────────────────┘
                     │
  ┌─────────────────────────────────────────────┐
  │  Stage 6: prepare_zap_config                │
  │  (render automation.yaml từ template)       │
  └──────────────────┬──────────────────────────┘
                     │
  ┌─────────────────────────────────────────────┐
  │  Stage 7: run_zap_dast                      │
  │                                             │
  │  docker run zaproxy:stable \                │
  │    -v workspace/{job_id}:/zap/wrk \         │
  │    zap.sh -autorun automation.yaml          │
  │                                             │
  │  ZAP Container:                             │
  │    → Đọc Postman collection                 │
  │    → Inject auth token vào header           │
  │    → Crawl + Active Scan target app         │
  │    → Lưu report HTML vào zap-out/           │
  └──────────────────┬──────────────────────────┘
                     │
  ┌─────────────────────────────────────────────┐
  │  Stage 8: evaluate_result                   │
  │  (đọc kết quả, kiểm tra threshold)          │
  │  → exit 0 (pass) hoặc exit 1 (fail)         │
  └──────────────────┬──────────────────────────┘
                     │
          ┌──────────┴──────────┐
          ▼                     ▼
     status=success        status=failed
     report.html saved     log_tail saved


====================================================================
           VÒNG ĐỜI JOB (JOB LIFECYCLE STATES)
====================================================================

  POST /scan
      │
      ▼
  [PENDING]
      │  Background task khởi động
      ▼
  [RUNNING] ──────────────────────────────────────────────┐
      │                                                    │
      │  stage: preflight_debug                           │
      │  stage: inspect_collection                        │
      │  stage: prelogin                                  │
      │  stage: validate_token                            │
      │  stage: prepare_zap_config                        │
      │  stage: run_zap_dast    ← Docker ZAP              │
      │  stage: evaluate_result                           │
      │                                                    │
      │  Nếu bất kỳ stage nào exit != 0 ─────────────────►│
      │                                               [FAILED]
      ▼                                                    │
  [SUCCESS]                                               │
      │                                                    │
      └───────────────────────────────────────────────────┘
              (Cả 2 trạng thái)
               DELETE /jobs/{id}
              → Dọn workspace, giải phóng tài nguyên


====================================================================
           LUỒNG JENKINS KHÁC GỌI ZAP SERVICE
====================================================================

  Pipeline Project A / B / C
     │
     ├── [Cách A] Dùng Shared Library
     │     @Library('zap-shared-lib') _
     │     ...
     │     zapScan(
     │       serviceUrl: 'http://zap-server:8080',
     │       baseUrl:    params.ENV_URL,
     │       ...
     │     )
     │     → Toàn bộ logic trong zapScan.groovy
     │
     └── [Cách B] Dùng curl trực tiếp (không cần Shared Library)
           curl -X POST http://zap-server:8080/scan \
             -H 'Content-Type: application/json' \
             --data-binary @zap_payload.json
           → job_id = "xyz-456"

           while polling:
             curl http://zap-server:8080/status/xyz-456
             → running...

           curl -o zap-out/report.html \
             http://zap-server:8080/report/xyz-456

           curl -X DELETE \
             http://zap-server:8080/jobs/xyz-456


====================================================================
                  PHÂN CHIA TRÁCH NHIỆM
====================================================================

  DEVSECOPS                              DEV TEAM
  ─────────────────────────────          ──────────────────────────
  ✅ Deploy ZAP Service                  ✅ Vào job ZAP-DAST-Scanner
  ✅ Đăng ký Shared Library              ✅ Điền form tham số
  ✅ Tạo job ZAP-DAST-Scanner            ✅ Bấm Build
  ✅ Cập nhật logic scan                 ✅ Xem kết quả + report
  ✅ Cấu hình ZAP_SERVICE_URL            ✅ (Không cần làm gì khác)
  ✅ Bảo trì Shared Library


  ZAP‑RELATED FILES (DevSecOps quản lý)
  ─────────────────────────────────────────────────────────────────
  security/
  ├── zap/
  │   ├── zap_pipeline.sh       ← 8 stages, core scan logic
  │   ├── zap_utils.py          ← Python utilities (token, eval)
  │   ├── zap_logger.js         ← ZAP HttpSender script
  │   ├── automation.yaml.tpl   ← ZAP config template
  │   └── postman_collection.json
  └── zap-service/
      ├── Dockerfile
      ├── docker-compose.yml
      ├── requirements.txt
      ├── app/
      │   ├── main.py           ← API endpoints
      │   ├── runner.py         ← Chạy pipeline.sh, quản lý job
      │   ├── models.py         ← Pydantic schemas
      │   └── config.py         ← Env vars
      └── jenkins-shared-lib/
          ├── vars/
          │   └── zapScan.groovy    ← Shared Library function
          └── Jenkinsfile.scanner   ← Job template cho dev team


====================================================================
                 API ENDPOINTS THAM CHIẾU NHANH
====================================================================

  METHOD   ENDPOINT               MÔ TẢ                  AI GỌI
  ───────  ─────────────────────  ──────────────────────  ─────────
  GET      /health                Health check            Jenkins, K8s
  POST     /scan                  Kích hoạt scan mới      Jenkins pipeline
  GET      /status/{job_id}       Polling trạng thái      Jenkins (loop)
  GET      /logs/{job_id}         Full log text           Debug thủ công
  GET      /report/{job_id}       Tải report HTML         Jenkins post-scan
  GET      /jobs                  Liệt kê tất cả jobs     Monitoring
  DELETE   /jobs/{job_id}         Dọn workspace           Jenkins post-always

  Swagger UI: http://<zap-host>:8080/docs

====================================================================
```
