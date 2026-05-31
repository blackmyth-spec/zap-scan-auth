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

    // ── Cấu hình kết nối tới server Osmedeus ────────────────────────────────
    def osmedeusIp = "192.168.119.152"
    def osmedeusUser = "root" // Sửa thành 'ubuntu' nếu cài đặt Osmedeus trên user đó

    // Lệnh thực thi hoàn chỉnh (Gọi qua SSH sang server Osmedeus)
    def cmd = "ssh -o StrictHostKeyChecking=no ${osmedeusUser}@${osmedeusIp} 'osmedeus scan ${cmdArgs}'"
    
    echo "[ZAP] Lệnh thực thi: ${cmd}"

    // Thực thi lệnh và chờ kết quả
    def exitCode = sh(script: cmd, returnStatus: true)

    if (exitCode != 0) {
        error "[ZAP] ❌ Quá trình scan bị lỗi hoặc thất bại. Exit code: ${exitCode}"
    }

    def cleanTarget = baseUrl.replaceAll('^https?://', '')
    def osmedeusUiUrl = "http://${osmedeusIp}:8002"

    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "[ZAP] ✅ QUÁ TRÌNH SCAN HOÀN TẤT!"
    echo "[ZAP] 🔍 Vui lòng kiểm tra báo cáo ZAP HTML trên Dashboard của Osmedeus:"
    echo "[ZAP] 🔗 Link: ${osmedeusUiUrl}/ (Tìm workspace của: ${cleanTarget})"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    // BƯỚC MỚI: Kéo file báo cáo từ Osmedeus về Jenkins Workspace để hiển thị UI
    echo "[ZAP] Đang kéo báo cáo về Jenkins để hiển thị lên UI cho Dev..."
    def osmedeusWorkspace = "~/.osmedeus/workspaces/${cleanTarget}"
    def reportPath = "${osmedeusWorkspace}/zap/zap-report.html"
    
    // Copy file từ server Osmedeus về thư mục hiện tại của Jenkins qua SCP
    sh "scp -o StrictHostKeyChecking=no ${osmedeusUser}@${osmedeusIp}:${reportPath} zap-report.html || echo '[ZAP] ⚠️ Không tìm thấy file báo cáo tại ${reportPath}'"

    // 1. Publish dưới dạng Tab HTML (Nếu có cài plugin HTML Publisher)
    try {
        publishHTML(target: [
            allowMissing: true,
            alwaysLinkToLastBuild: true,
            keepAll: true,
            reportDir: '.',
            reportFiles: 'zap-report.html',
            reportName: 'ZAP Security Report',
            reportTitles: 'ZAP DAST Scan Result'
        ])
        echo "[ZAP] Đã publish HTML Report lên Jenkins UI!"
    } catch (Throwable t) {
        echo "[ZAP] ⚠️ Bạn chưa cài 'HTML Publisher Plugin', Jenkins sẽ bỏ qua bước tạo Tab HTML."
    }

    // 2. Lưu trữ file tĩnh (Artifact) để tải về (Built-in của Jenkins, luôn chạy được)
    archiveArtifacts artifacts: 'zap-report.html', allowEmptyArchive: true
    echo "[ZAP] Đã lưu file báo cáo dưới dạng Artifact (Có thể tải về từ Jenkins Build Page)."

    return true
}
