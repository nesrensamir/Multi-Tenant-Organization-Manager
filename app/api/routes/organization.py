import uuid
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.api.dependencies import get_db, get_current_user, get_org_admin
from app.models.user import User
from app.models.tenant import Organization, Membership, RoleEnum, AuditLog
from app.schemas.tenant import OrganizationCreate, MembershipCreate, OrganizationResponse
from app.schemas.user import UserResponse

router = APIRouter(prefix="/organizations", tags=["Organizations"])

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_organization(
    org_in: OrganizationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create organization, assign Admin role, and log action."""
    # 1. Create Organization
    db_org = Organization(name=org_in.name)
    db.add(db_org)
    await db.flush()  # Flush to get the generated org ID

    # 2. Create Admin Membership
    db_membership = Membership(
        user_id=current_user.id,
        organization_id=db_org.id,
        role=RoleEnum.ADMIN
    )
    db.add(db_membership)

    # 3. Create Audit Log
    db_audit = AuditLog(
        organization_id=db_org.id,
        user_id=current_user.id,
        action="Created Organization",
        description=f"Organization '{db_org.name}' created by {current_user.email}."
    )
    db.add(db_audit)

    await db.commit()
    
    # Required response format from task instructions
    return {"org_id": str(db_org.id)}


@router.get("", response_model=list[OrganizationResponse])
async def get_my_organizations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all organizations the current authenticated user belongs to."""
    query = select(Organization).join(Membership).where(
        Membership.user_id == current_user.id
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/{id}/user", status_code=status.HTTP_201_CREATED)
async def invite_user(
    id: uuid.UUID,
    member_in: MembershipCreate,
    current_admin: User = Depends(get_org_admin),
    db: AsyncSession = Depends(get_db)
):
    """Admins only. Create membership and assign user to this organization."""
    # Find user by email
    query = select(User).where(User.email == member_in.email)
    result = await db.execute(query)
    target_user = result.scalar_one_or_none()
    
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found.")

    # Check if membership already exists
    mem_query = select(Membership).where(
        Membership.organization_id == id,
        Membership.user_id == target_user.id
    )
    if (await db.execute(mem_query)).scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User is already a member of this organization.")

    # Create membership
    db_membership = Membership(
        user_id=target_user.id,
        organization_id=id,
        role=member_in.role
    )
    db.add(db_membership)

    # Log action
    db_audit = AuditLog(
        organization_id=id,
        user_id=current_admin.id,
        action="Invited User",
        description=f"Admin invited {target_user.email} as {member_in.role.value}."
    )
    db.add(db_audit)

    await db.commit()
    return {"message": "User invited successfully."}


@router.get("/{id}/users", response_model=list[UserResponse])
async def get_organization_users(
    id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_admin: User = Depends(get_org_admin),
    db: AsyncSession = Depends(get_db)
):
    """Admin only. Get all users assigned to this organization with pagination."""
    query = select(User).join(Membership).where(
        Membership.organization_id == id
    ).limit(limit).offset(offset)
    
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{id}/users/search", response_model=list[UserResponse])
async def search_organization_users(
    id: uuid.UUID,
    q: str = Query(..., description="Keyword to search for"),
    current_admin: User = Depends(get_org_admin),
    db: AsyncSession = Depends(get_db)
):
    """Admin only. Full-Text Search via PostgreSQL tsvector."""
    # We use PostgreSQL's '@@' operator to match the tsvector column against a tsquery
    query = select(User).join(Membership).where(
        Membership.organization_id == id,
        User.search_vector.op("@@")(func.plainto_tsquery('english', q))
    )
    
    result = await db.execute(query)
    return result.scalars().all()