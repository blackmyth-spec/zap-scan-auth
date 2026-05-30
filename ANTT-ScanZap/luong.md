Dev Team        Jenkins        Osmedeus CLI      FastAPI       ZAP
   |               |               |               |             |
   |---Build------>|               |               |             |
   |   (params)    |               |               |             |
   |               |--osmedeus cmd>|               |             |
   |               |               |---POST /scan->|             |
   |               |               |               |---Scan----->|
   |               |               |               |<--Report----|
   |               |               |<---Download---|             |
   |               |<--Exit Code---| (Saves to UI) |             |
   |<---Build Result---------------|               |             |


   Dev Team        Jenkins Job        Osmedeus CLI/UI        FastAPI Scan Service
   |                 |                     |                      |
   |---Build-------> |                     |                      |
   |   (params)      |                     |                      |
   |                 |--osmedeus scan -m ->|                      |
   |                 |                     |                      |
   |                 |                     |---POST /scan-------->|
   |                 |                     |<---Polling Status----|
   |                 |                     |<---Download Report---|
   |                 |                     |[Report shows on UI]  |
   |                 |<---Exit Code 0/1----|                      |
   |<----Build Result|                     |                      |



┌──────────┐
│ Dev Team │
└────┬─────┘
     │ Build + Params
     ▼
┌──────────────┐
│ Jenkins Job  │
└────┬─────────┘
     │ OS Command (sh)
     ▼
┌─────────────────────────────────┐
│       Osmedeus CLI / UI         │
│                                 │
│  - Executes YAML module         │
│  - Calls FastAPI                │
│  - Saves Report to Workspace    │
│  - Displays on Dashboard        │
└──────────────┬──────────────────┘
               │ REST API
               ▼
┌─────────────────────────────────┐
│     FastAPI Scan Service        │
│                                 │
│  - Auth / Login                 │
│  - OWASP ZAP Execution          │
│  - Generate HTML Report         │
└─────────────────────────────────┘