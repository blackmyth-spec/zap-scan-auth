/**
 * zapScan.groovy — Jenkins Shared Library (Tích hợp Mô hình 1: Qua Osmedeus)
 *
 * Hàm này được gọi từ Jenkinsfile của "ZAP DAST Scanner" job.
 * Thay vì gọi thẳng FastAPI, Jenkins sẽ kích hoạt Osmedeus CLI.
 */
def call(Map cfg = [:]) {

    // ── Đọc từ params Jenkins UI nếu không truyền cfg ────────────────────────
    def baseUrl          = cfg.baseUrl          ?: params.BASE_URL        ?: ''
    def loginCurlCommand = cfg.loginCurlCommand ?: params.LOGIN_CURL_COMMAND ?: ''
    def scanExcludeApis  = cfg.scanExcludeApis  ?: params.SCAN_EXCLUDE_APIS ?: ''
    
    // Tên module đã tạo và nạp vào Osmedeus
    def osmedeusModule   = "osmedeus-fastapi-zap-module"

    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "[ZAP] Kích hoạt ZAP Scan thông qua công cụ Osmedeus"
    echo "[ZAP] Target URL  : ${baseUrl}"
    echo "[ZAP] Exclude APIs: ${scanExcludeApis ?: '(none)'}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    // ── Kích hoạt Osmedeus CLI ──────────────────────────────────────────────
    // Lệnh này giả định rằng jenkins agent đã có sẵn CLI của Osmedeus,
    // hoặc bạn có thể gọi qua SSH tuỳ vào hạ tầng của bạn.
    
    def cmdArgs = "-m ${osmedeusModule} -t \"${baseUrl}\""
    
    if (loginCurlCommand.trim() != '') {
        // Escape nháy kép an toàn để truyền param vào lệnh shell
        def safeCurl = loginCurlCommand.replace('"', '\\"')
        cmdArgs += " -p \"loginCurl=${safeCurl}\""
    }
    
    if (scanExcludeApis.trim() != '') {
        cmdArgs += " -p \"excludeApis=${scanExcludeApis}\""
    }

    // Lệnh thực thi hoàn chỉnh
    def cmd = "osmedeus scan ${cmdArgs}"
    
    echo "[ZAP] Lệnh thực thi: ${cmd}"

    // Thực thi lệnh và chờ kết quả
    def exitCode = sh(script: cmd, returnStatus: true)

    if (exitCode != 0) {
        error "[ZAP] ❌ Quá trình scan bị lỗi hoặc thất bại. Exit code: ${exitCode}"
    }

    echo "[ZAP] ✅ Quá trình scan hoàn tất! Báo cáo đã được lưu trữ và hiển thị trên Osmedeus UI."
    return true
}
