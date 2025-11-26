# E081: FastAPI Backend for PlanAlign Studio

**Status**: ✅ COMPLETED
**Branch**: `feature/E081-fastapi-backend`
**Completed**: 2025-11-24

## Overview

This epic delivers a FastAPI backend to serve the PlanAlign Studio React frontend, replacing mock data with real API calls to the simulation engine.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     PlanAlign Studio (React)                     │
│                    planalign_studio/                             │
├─────────────────────────────────────────────────────────────────┤
│  services/api.ts          │  services/websocket.ts              │
│  - REST API client        │  - useSimulationSocket()            │
│  - Type definitions       │  - useBatchSocket()                 │
└────────────────┬──────────┴──────────────┬──────────────────────┘
                 │ HTTP/REST               │ WebSocket
                 ▼                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                     PlanAlign API (FastAPI)                      │
│                    planalign_api/                                │
├─────────────────────────────────────────────────────────────────┤
│  Routers:                 │  Services:                          │
│  - /api/workspaces        │  - SimulationService                │
│  - /api/scenarios         │  - ComparisonService                │
│  - /api/simulations       │  - TelemetryService                 │
│  - /api/batches           │                                     │
│  - /api/comparison        │  WebSocket:                         │
│  - /api/health            │  - /ws/simulation/{run_id}          │
│  - /api/system/status     │  - /ws/batch/{batch_id}             │
├─────────────────────────────────────────────────────────────────┤
│  Storage:                                                        │
│  - WorkspaceStorage (filesystem at ~/.planalign/workspaces/)    │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│              PlanAlign Orchestrator (Existing)                   │
│             planalign_orchestrator/                              │
│  - PipelineOrchestrator                                         │
│  - DuckDB database                                              │
│  - dbt transformations                                          │
└─────────────────────────────────────────────────────────────────┘
```

## Package Structure

```
planalign_api/
├── __init__.py                 # Package init (v0.1.0)
├── config.py                   # APISettings (Pydantic)
├── main.py                     # FastAPI app entry point
├── models/                     # Pydantic request/response models
│   ├── __init__.py
│   ├── system.py              # HealthResponse, SystemStatus
│   ├── workspace.py           # Workspace, WorkspaceCreate, WorkspaceUpdate
│   ├── scenario.py            # Scenario, ScenarioCreate, ScenarioUpdate
│   ├── simulation.py          # SimulationRun, SimulationTelemetry, SimulationResults
│   ├── comparison.py          # ComparisonResponse, DeltaValue, WorkforceMetrics
│   └── batch.py               # BatchJob, BatchScenario, BatchCreate
├── routers/                    # API endpoint handlers
│   ├── __init__.py
│   ├── system.py              # GET /api/health, /api/system/status, /api/config/defaults
│   ├── workspaces.py          # CRUD /api/workspaces
│   ├── scenarios.py           # CRUD /api/workspaces/{id}/scenarios
│   ├── simulations.py         # POST /api/scenarios/{id}/run, GET status, results
│   ├── batch.py               # POST /api/workspaces/{id}/run-all
│   └── comparison.py          # GET /api/workspaces/{id}/comparison
├── services/                   # Business logic
│   ├── __init__.py
│   ├── simulation_service.py  # Wraps PipelineOrchestrator
│   ├── comparison_service.py  # Delta calculations from DuckDB
│   ├── telemetry_service.py   # Real-time broadcast
│   ├── workspace_service.py   # Thin wrapper
│   └── scenario_service.py    # Thin wrapper
├── storage/
│   ├── __init__.py
│   └── workspace_storage.py   # Filesystem operations
└── websocket/
    ├── __init__.py
    ├── manager.py             # ConnectionManager
    └── handlers.py            # WebSocket endpoint handlers
```

## API Endpoints

### System
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check with issues/warnings |
| GET | `/api/system/status` | Detailed system status |
| GET | `/api/config/defaults` | Default simulation configuration |

### Workspaces
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/workspaces` | List all workspaces |
| POST | `/api/workspaces` | Create workspace |
| GET | `/api/workspaces/{id}` | Get workspace by ID |
| PUT | `/api/workspaces/{id}` | Update workspace |
| DELETE | `/api/workspaces/{id}` | Delete workspace |

### Scenarios
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/workspaces/{id}/scenarios` | List scenarios |
| POST | `/api/workspaces/{id}/scenarios` | Create scenario |
| GET | `/api/workspaces/{id}/scenarios/{sid}` | Get scenario |
| PUT | `/api/workspaces/{id}/scenarios/{sid}` | Update scenario |
| DELETE | `/api/workspaces/{id}/scenarios/{sid}` | Delete scenario |
| GET | `/api/workspaces/{id}/scenarios/{sid}/config` | Get merged config |

### Simulations
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/scenarios/{id}/run` | Start simulation |
| GET | `/api/scenarios/{id}/run/status` | Get run status |
| POST | `/api/scenarios/{id}/run/cancel` | Cancel simulation |
| GET | `/api/scenarios/{id}/results` | Get results |
| GET | `/api/scenarios/{id}/results/export` | Export to Excel/CSV |

### Batch Processing
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/workspaces/{id}/run-all` | Run all scenarios |
| GET | `/api/batches/{id}/status` | Get batch status |
| GET | `/api/workspaces/{id}/batches` | List batch jobs |

### Comparison
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/workspaces/{id}/comparison` | Compare scenarios |

### WebSocket
| Endpoint | Description |
|----------|-------------|
| `WS /ws/simulation/{run_id}` | Real-time simulation telemetry |
| `WS /ws/batch/{batch_id}` | Batch progress updates |

## Frontend Integration

### Files Created in `planalign_studio/services/`

1. **`api.ts`** - Full REST API client with TypeScript types
2. **`websocket.ts`** - WebSocket hooks for real-time updates
3. **`index.ts`** - Barrel exports

### Files Updated

1. **`components/Layout.tsx`** - Loads workspaces from API
2. **`components/Dashboard.tsx`** - Uses real system status and scenarios
3. **`components/SimulationControl.tsx`** - Real simulation control with WebSocket telemetry
4. **`.env.local`** - Added `VITE_API_URL` and `VITE_WS_URL`

## Running the Stack

### Terminal 1 - API Server
```bash
cd /Users/nicholasamaral/planwise_navigator
source .venv/bin/activate
uvicorn planalign_api.main:app --reload --port 8000
```

### Terminal 2 - Frontend Dev Server
```bash
cd /Users/nicholasamaral/planwise_navigator/planalign_studio
npm install
npm run dev
```

### API Documentation
- Swagger UI: http://localhost:8000/api/docs
- ReDoc: http://localhost:8000/api/redoc
- OpenAPI JSON: http://localhost:8000/api/openapi.json

## Configuration

### Environment Variables

**API (`planalign_api/config.py`)**:
| Variable | Default | Description |
|----------|---------|-------------|
| `PLANALIGN_HOST` | `0.0.0.0` | API host |
| `PLANALIGN_PORT` | `8000` | API port |
| `PLANALIGN_WORKSPACES_ROOT` | `~/.planalign/workspaces` | Storage path |
| `PLANALIGN_CORS_ORIGINS` | `localhost:3000,5173` | Allowed origins |

**Frontend (`.env.local`)**:
```env
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000
```

## Storage Format

Workspaces are stored on the filesystem:
```
~/.planalign/workspaces/
├── {workspace-uuid}/
│   ├── workspace.json          # Workspace metadata
│   ├── base_config.yaml        # Base simulation config
│   └── scenarios/
│       ├── {scenario-uuid}/
│       │   ├── scenario.json   # Scenario metadata
│       │   ├── config.yaml     # Config overrides
│       │   ├── simulation.duckdb  # Results database
│       │   └── results/
│       │       ├── results.xlsx
│       │       └── results.csv
│       └── ...
└── ...
```

## Dependencies Added

```
fastapi==0.122.0
uvicorn==0.38.0
websockets==15.0.1
pydantic-settings==2.12.0
python-multipart==0.0.20
```

## Testing

```bash
# Health check
curl http://localhost:8000/api/health

# System status
curl http://localhost:8000/api/system/status

# List workspaces
curl http://localhost:8000/api/workspaces

# Create workspace
curl -X POST http://localhost:8000/api/workspaces \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Workspace", "description": "Testing"}'
```

## Future Enhancements

1. **Authentication** - Add JWT/OAuth for multi-user support
2. **Redis** - Replace in-memory stores with Redis for persistence
3. **Background Workers** - Use Celery for long-running simulations
4. **Database** - Add PostgreSQL for workspace metadata (vs filesystem)
5. **Rate Limiting** - Add API rate limiting for production
