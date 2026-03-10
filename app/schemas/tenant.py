from pydantic import BaseModel, ConfigDict, Field, EmailStr
import uuid
from datetime import datetime
from app.models.tenant import RoleEnum

# --- Organization Schemas ---
class OrganizationCreate(BaseModel):
    name: str = Field(alias="org_name")

class OrganizationResponse(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

# --- Membership Schemas ---
class MembershipCreate(BaseModel):
    email: EmailStr
    role: RoleEnum = RoleEnum.MEMBER

class MembershipResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    organization_id: uuid.UUID
    role: RoleEnum
    
    model_config = ConfigDict(from_attributes=True)

# --- Item Schemas ---
class ItemCreate(BaseModel):
    org_id: uuid.UUID
    item_details: dict

class ItemResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    created_by_id: uuid.UUID | None
    details: dict
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

# --- Audit Log Schemas ---
class AuditLogResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID | None
    action: str
    description: str | None
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class AskRequest(BaseModel):
    question: str
    stream: bool = True