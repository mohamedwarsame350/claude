from typing import Any, Dict, Optional
from pydantic import BaseModel


class ProvisionRequest(BaseModel):
    service_id: str
    plan_id: str
    context: Optional[Dict[str, Any]] = None
    parameters: Optional[Dict[str, Any]] = None
    organization_guid: Optional[str] = None
    space_guid: Optional[str] = None
