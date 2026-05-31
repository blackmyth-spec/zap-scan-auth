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
    
    if (!baseUrl.trim()) {
        error "[ZAP] ❌ Lỗi: BASE_URL đang bị rỗng! Osmedeus bắt buộc phải có target (tham số -t)."
    }
    
    def safeBaseUrl = baseUrl.replace("'", "'\\''")
    // Đảo thứ tự -t lên trước -m cho đúng chuẩn CLI thông thường của Osmedeus
    def cmdArgs = "-t '${safeBaseUrl}' -m ${osmedeusModule}"
    
    if (loginCurlCommand.trim() != '') {
        // 1. Escape dấu \ và nháy kép để file JSON của Osmedeus module không bị hỏng
        def jsonSafeCurl = loginCurlCommand.replace('\\', '\\\\').replace('"', '\\"')
        // 2. Escape nháy đơn để an toàn khi chạy trên Bash
        def bashSafeCurl = jsonSafeCurl.replace("'", "'\\''")
        cmdArgs += " -p 'loginCurl=${bashSafeCurl}'"
    }
    
    if (scanExcludeApis.trim() != '') {
        def safeExclude = scanExcludeApis.replace("'", "'\\''")
        cmdArgs += " -p 'excludeApis=${safeExclude}'"
    }

    // ── Cấu hình kết nối tới server Osmedeus ────────────────────────────────
    def osmedeusIp = "192.168.119.156"
    def osmedeusUser = "root" // Sửa thành 'ubuntu' nếu cài đặt Osmedeus trên user đó

    // Lệnh thực thi hoàn chỉnh (Gọi qua SSH sang server Osmedeus)
    // Để tránh lỗi Syntax Error do các ký tự đặc biệt như (, ), $, ', " khi gọi SSH trực tiếp, 
    // chúng ta ghi lệnh ra script và đẩy qua stdin.
    def scriptContent = """#!/bin/bash
# Nạp biến môi trường vì SSH non-interactive sẽ không tự chạy ~/.bashrc
source ~/.bashrc 2>/dev/null
source ~/.profile 2>/dev/null
export PATH=\$PATH:/root/osmedeus-base:/root/.osmedeus:/usr/local/bin:/usr/bin

# Chạy osmedeus (nếu vẫn lỗi not found, có thể thay bằng đường dẫn tuyệt đối, vd: /root/osmedeus-base/osmedeus)
osmedeus scan ${cmdArgs}
"""
    writeFile(file: 'zap-scan-trigger.sh', text: scriptContent)
    
    def cmd = "ssh -o StrictHostKeyChecking=no ${osmedeusUser}@${osmedeusIp} 'bash -s' < zap-scan-trigger.sh"
    
    echo "[ZAP] Lệnh thực thi: osmedeus scan ${cmdArgs}"

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
