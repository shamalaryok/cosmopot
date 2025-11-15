# Removed Tests

## test_pipeline_integration.py
**Removed**: 2025-11-03  
**Reason**: Legacy code `backend/app/celery_app` no longer exists in project.

**Details**:
- Test imported from `backend.app.celery_app` which was removed/refactored
- Legacy worker structure `backend/app/worker/` replaced with new structure
- If worker functionality is still needed, new tests should be written for the new implementation
