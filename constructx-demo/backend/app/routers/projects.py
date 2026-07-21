"""Projects API — the jobs that subcontractors are assigned to."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Project

router = APIRouter(prefix="/api/projects", tags=["Projects"])


@router.get("")
def list_projects(db: Session = Depends(get_db)):
    return [{
        "project_id": p.project_id, "name": p.name, "client": p.client,
        "start_date": p.start_date.isoformat() if p.start_date else None,
        "planned_end_date": p.planned_end_date.isoformat()
        if p.planned_end_date else None,
        "status": p.status,
    } for p in db.query(Project).all()]
