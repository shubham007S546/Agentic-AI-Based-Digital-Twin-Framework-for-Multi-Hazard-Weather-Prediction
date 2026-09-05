"""
app/api/v1/routers/user_router.py
─────────────────────────────────
User management routing definitions.

Design decisions:
  • All endpoints use the standard ApiResponse/ApiListResponse envelope.
  • Admin endpoints are protected by `require_role(["ADMIN"])`.
  • The `me` endpoints allow authenticated users to fetch/update their own profile.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.v1.controllers.user_controller import UserController
from app.core.enums import UserRole
from app.dependencies.auth import CurrentUserToken, require_role
from app.exceptions.domain import AuthorizationError
from app.schemas.common import ApiListResponse, ApiResponse, EmptyResponse, PaginationMeta, PaginationParams
from app.schemas.user import UserCreate, UserResponse, UserUpdate

router = APIRouter()


@router.get(
    "/me",
    response_model=ApiResponse[UserResponse],
    summary="Get current user profile",
)
async def get_current_user_profile(
    token_data: CurrentUserToken,
    controller: Annotated[UserController, Depends()],
) -> ApiResponse[UserResponse]:
    """Retrieve the profile of the currently authenticated user."""
    user = await controller.get_user_by_id(uuid.UUID(token_data.user_id))
    return ApiResponse(data=user, message="Profile retrieved successfully.")


@router.get(
    "",
    response_model=ApiListResponse[UserResponse],
    summary="List users (Admin only)",
    dependencies=[Depends(require_role([UserRole.ADMIN, UserRole.SUPER_ADMIN]))],
)
async def list_users(
    pagination: Annotated[PaginationParams, Depends()],
    controller: Annotated[UserController, Depends()],
) -> ApiListResponse[UserResponse]:
    """Retrieve a paginated list of all users."""
    users, total = await controller.get_all_users(skip=pagination.offset, limit=pagination.limit)
    
    meta = PaginationMeta.create(
        page=pagination.page, 
        page_size=pagination.page_size, 
        total_items=total
    )
    
    return ApiListResponse(data=users, pagination=meta)


@router.post(
    "",
    response_model=ApiResponse[UserResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create user (Admin only)",
    dependencies=[Depends(require_role([UserRole.ADMIN, UserRole.SUPER_ADMIN]))],
)
async def create_user(
    payload: UserCreate,
    controller: Annotated[UserController, Depends()],
) -> ApiResponse[UserResponse]:
    """Create a new user manually."""
    user = await controller.create_user(payload)
    return ApiResponse(data=user, message="User created successfully.")


@router.get(
    "/{user_id}",
    response_model=ApiResponse[UserResponse],
    summary="Get user by ID (Admin only)",
    dependencies=[Depends(require_role([UserRole.ADMIN, UserRole.SUPER_ADMIN]))],
)
async def get_user(
    user_id: uuid.UUID,
    controller: Annotated[UserController, Depends()],
) -> ApiResponse[UserResponse]:
    """Fetch a specific user profile by UUID."""
    user = await controller.get_user_by_id(user_id)
    return ApiResponse(data=user)


@router.patch(
    "/{user_id}",
    response_model=ApiResponse[UserResponse],
    summary="Update user (Admin only)",
    dependencies=[Depends(require_role([UserRole.ADMIN, UserRole.SUPER_ADMIN]))],
)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    token_data: CurrentUserToken,
    controller: Annotated[UserController, Depends()],
) -> ApiResponse[UserResponse]:
    """Update a specific user profile."""
    if payload.role is not None:
        if token_data.role != UserRole.SUPER_ADMIN.value:
            raise AuthorizationError("Only a super administrator can change roles.")
        if user_id == uuid.UUID(token_data.user_id):
            raise AuthorizationError("You cannot change your own role.")
    user = await controller.update_user(user_id, payload)
    return ApiResponse(data=user, message="User updated successfully.")


@router.delete(
    "/{user_id}",
    response_model=EmptyResponse,
    summary="Delete user (Admin only)",
    dependencies=[Depends(require_role([UserRole.ADMIN, UserRole.SUPER_ADMIN]))],
)
async def delete_user(
    user_id: uuid.UUID,
    controller: Annotated[UserController, Depends()],
) -> EmptyResponse:
    """Soft-delete a user."""
    await controller.delete_user(user_id)
    return EmptyResponse(message="User deleted successfully.")
