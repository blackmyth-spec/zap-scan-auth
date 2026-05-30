env:
  contexts:
    - name: "App-API-Context"
      urls:
{{ZAP_CONTEXT_URLS}}
      excludePaths:
        - ".*/public/api/encode-base64.*"
        - ".*/api/authenticate-hash-2.*"
        - ".*\\.js"
        - ".*\\.css"
        - ".*\\.png"
        - ".*\\.jpg"
        - ".*\\.svg"
        - ".*\\.woff2?"
        - ".*/health.*"
        - ".*/actuator.*"
{{ZAP_SCAN_EXCLUDE_PATHS_YAML}}
  parameters:
    failOnError: true
    failOnWarning: false
    progressToStdout: true

jobs:
  - type: replacer
    name: "replacer"
    rules:
      - description: "Inject Dynamic TransID"
        matchType: "req_body_str"
        matchString: "ZAP-123456789"
        replacementString: "{{TRANS_ID}}"

  - type: postman
    parameters:
      collectionFile: "/zap/wrk/config/postman_collection.json"
    name: "import-postman"
  
  - type: script
    parameters:
      action: "add"
      type: "httpsender"
      engine: "Graal.js"
      name: "zap_logger.js"
      file: "/zap/wrk/scripts/zap_logger.js"
    name: "add-logger-script"

  - type: script
    parameters:
      action: "enable"
      name: "zap_logger.js"
    name: "enable-logger-script"

  - type: activeScan
    parameters:
      context: "App-API-Context"
      policy: "API-Minimal"
      maxRuleDurationInMins: 5
      maxScanDurationInMins: 60
      addQueryParam: false
      delayInMs: 0
      handleAntiCSRFTokens: false
      injectPluginIdInHeader: false
      scanHeadersAllRequests: false
      threadPerHost: 5
    name: "activeScan"

  - type: report
    parameters:
      template: "traditional-json"
      reportDir: "/zap/wrk/reports"
      reportFile: "{{REPORT_BASENAME}}"
      displayReport: false
    name: "report-json"

  - type: report
    parameters:
      template: "traditional-html"
      reportDir: "/zap/wrk/reports"
      reportFile: "{{REPORT_BASENAME}}"
      reportTitle: "ZAP Security Report"
      reportDescription: "DAST scan APIs từ Postman Collection với auth tùy điều kiện endpoint."
      displayReport: false
    name: "report-html"