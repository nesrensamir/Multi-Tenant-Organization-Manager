import uuid
from typing import AsyncGenerator
from fastapi import Depends, HTTPException, status, Path
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import jwt
from pydantic import ValidationError

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.user import User
from app.models.tenant import Membership, RoleEnum
from app.schemas.token import TokenPayload

security = HTTPBearer()

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to provide a transactional database session."""
    async with AsyncSessionLocal() as session:
        yield session

async def get_current_user(
    db: AsyncSession = Depends(get_db),
    token: HTTPAuthorizationCredentials = Depends(security)
) -> User:
    """Validates JWT, extracts user_id (sub), and retrieves the user from DB."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token.credentials, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
        if token_data.sub is None:
            raise credentials_exception
    except (jwt.PyJWTError, ValidationError):
        raise credentials_exception

    query = select(User).where(User.id == uuid.UUID(token_data.sub))
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    
    if not user:
        raise credentials_exception
        
    return user

async def get_org_admin(
    id: uuid.UUID = Path(..., description="The ID of the organization"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> User:
    """RBAC Dependency: Verifies the current user is an ADMIN of the specified organization."""
    query = select(Membership).where(
        Membership.organization_id == id,
        Membership.user_id == current_user.id,
        Membership.role == RoleEnum.ADMIN
    )
    result = await db.execute(query)
    membership = result.scalar_one_or_none()
    
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have admin permissions for this organization."
        )
    return current_user

async def get_org_member(
    id: uuid.UUID = Path(..., description="The ID of the organization"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> User:
    """RBAC Dependency: Verifies the current user is at least a MEMBER of the specified organization."""
    query = select(Membership).where(
        Membership.organization_id == id,
        Membership.user_id == current_user.id
    )
    result = await db.execute(query)
    membership = result.scalar_one_or_none()
    
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this organization."
        )
    return current_user