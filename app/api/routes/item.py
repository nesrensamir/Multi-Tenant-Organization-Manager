import uuid
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.dependencies import get_db, get_org_member
from app.models.user import User
from app.models.tenant import Item, AuditLog, Membership, RoleEnum
from app.schemas.tenant import ItemCreate, ItemResponse

router = APIRouter(prefix="/organizations/{id}/item", tags=["Items"])

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_item(
    id: uuid.UUID,
    item_in: ItemCreate,
    current_user: User = Depends(get_org_member),
    db: AsyncSession = Depends(get_db)
):
    """
    Members and Admins can create items[cite: 44].
    """
    # We validate that they match to prevent ID spoofing.
    if str(item_in.org_id) != str(id):
        raise HTTPException(status_code=400, detail="Path ID and body org_id do not match.")

    # Create item and assign it for organization and user who created this item [cite: 44]
    db_item = Item(
        organization_id=id,
        created_by_id=current_user.id,
        details=item_in.item_details
    )
    db.add(db_item)
    await db.flush() # Flush to generate the item ID

    # Create AuditLog entry 
    db_audit = AuditLog(
        organization_id=id,
        user_id=current_user.id,
        action="Created Item",
        description=f"User {current_user.email} created a new item."
    )
    db.add(db_audit)

    await db.commit()

    # Return exactly what the requirements asked for
    return {"item_id": str(db_item.id)} 


@router.get("", response_model=list[ItemResponse])
async def get_items(
    id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_org_member),
    db: AsyncSession = Depends(get_db)
):
    """
    Return details of the items. Data isolation is strictly enforced.
    """
    # 1. Fetch the user's membership to determine their role
    mem_query = select(Membership).where(
        Membership.organization_id == id,
        Membership.user_id == current_user.id
    )
    result = await db.execute(mem_query)
    membership = result.scalar_one()

    # 2. Build the base query for the organization's items
    item_query = select(Item).where(Item.organization_id == id)
    
    # 3. Apply Data Isolation Rules
    if membership.role == RoleEnum.MEMBER:
        # Members can see only items created by them 
        item_query = item_query.where(Item.created_by_id == current_user.id)
    # If they are an Admin, we don't add the filter, so admin can see all items 

    # Apply pagination
    item_query = item_query.limit(limit).offset(offset)
    items_result = await db.execute(item_query)
    items = items_result.scalars().all()

    # 4. Create AuditLog entry for viewing data 
    db_audit = AuditLog(
        organization_id=id,
        user_id=current_user.id,
        action="Viewed Items",
        description=f"User {current_user.email} viewed {len(items)} items as {membership.role.value}."
    )
    db.add(db_audit)
    
    await db.commit()

    return items