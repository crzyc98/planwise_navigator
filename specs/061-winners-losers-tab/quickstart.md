# Quickstart: Winners & Losers Tab

## Prerequisites

- Two completed simulation scenarios in the same workspace
- Both scenarios share the same census (matching employee_ids)

## Development Setup

```bash
source .venv/bin/activate

# Backend
cd /workspace
uvicorn planalign_api.main:app --reload --port 8000

# Frontend (separate terminal)
cd /workspace/planalign_studio
npm run dev
```

## Test the Feature

1. Open PlanAlign Studio at `http://localhost:5173`
2. Navigate to "Winners & Losers" in the sidebar
3. Select workspace, then Plan A and Plan B scenarios
4. View age band chart, tenure band chart, and heatmap

## Key Files

| File | Purpose |
|------|---------|
| `planalign_api/routers/analytics.py` | API endpoint |
| `planalign_api/services/winners_losers_service.py` | Comparison logic |
| `planalign_api/models/winners_losers.py` | Pydantic response models |
| `planalign_studio/components/WinnersLosersTab.tsx` | React component |
| `planalign_studio/services/api.ts` | Frontend API client |
| `planalign_studio/App.tsx` | Route registration |
| `planalign_studio/components/Layout.tsx` | Navigation entry |

## Running Tests

```bash
pytest tests/test_winners_losers.py -v
```
