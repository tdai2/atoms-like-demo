import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.usage_quotas import Usage_quotasService
from dependencies.auth import get_current_user
from schemas.auth import UserResponse

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/usage_quotas", tags=["usage_quotas"])


# ---------- Pydantic Schemas ----------
class Usage_quotasData(BaseModel):
    """Entity data schema (for create/update)"""
    period: str
    plan: str = None
    used: int = None
    quota_limit: int = None


class Usage_quotasUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    period: Optional[str] = None
    plan: Optional[str] = None
    used: Optional[int] = None
    quota_limit: Optional[int] = None


class Usage_quotasResponse(BaseModel):
    """Entity response schema"""
    id: int
    user_id: str
    period: str
    plan: Optional[str] = None
    used: Optional[int] = None
    quota_limit: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Usage_quotasListResponse(BaseModel):
    """List response schema"""
    items: List[Usage_quotasResponse]
    total: int
    skip: int
    limit: int


class Usage_quotasBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[Usage_quotasData]


class Usage_quotasBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: Usage_quotasUpdateData


class Usage_quotasBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[Usage_quotasBatchUpdateItem]


class Usage_quotasBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=Usage_quotasListResponse)
async def query_usage_quotass(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Query usage_quotass with filtering, sorting, and pagination (user can only see their own records)"""
    logger.debug(f"Querying usage_quotass: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = Usage_quotasService(db)
    try:
        # Parse query JSON if provided
        query_dict = None
        if query:
            try:
                query_dict = json.loads(query)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid query JSON format")
        
        result = await service.get_list(
            skip=skip, 
            limit=limit,
            query_dict=query_dict,
            sort=sort,
            user_id=str(current_user.id),
        )
        logger.debug(f"Found {result['total']} usage_quotass")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid usage_quotas query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying usage_quotass: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=Usage_quotasListResponse)
async def query_usage_quotass_all(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    # Query usage_quotass with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying usage_quotass: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = Usage_quotasService(db)
    try:
        # Parse query JSON if provided
        query_dict = None
        if query:
            try:
                query_dict = json.loads(query)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid query JSON format")

        result = await service.get_list(
            skip=skip,
            limit=limit,
            query_dict=query_dict,
            sort=sort
        )
        logger.debug(f"Found {result['total']} usage_quotass")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid usage_quotas query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying usage_quotass: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=Usage_quotasResponse)
async def get_usage_quotas(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single usage_quotas by ID (user can only see their own records)"""
    logger.debug(f"Fetching usage_quotas with id: {id}, fields={fields}")
    
    service = Usage_quotasService(db)
    try:
        result = await service.get_by_id(id, user_id=str(current_user.id))
        if not result:
            logger.warning(f"Usage_quotas with id {id} not found")
            raise HTTPException(status_code=404, detail="Usage_quotas not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching usage_quotas {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=Usage_quotasResponse, status_code=201)
async def create_usage_quotas(
    data: Usage_quotasData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new usage_quotas"""
    logger.debug(f"Creating new usage_quotas with data: {data}")
    
    service = Usage_quotasService(db)
    try:
        result = await service.create(data.model_dump(), user_id=str(current_user.id))
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create usage_quotas")
        
        logger.info(f"Usage_quotas created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating usage_quotas: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating usage_quotas: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[Usage_quotasResponse], status_code=201)
async def create_usage_quotass_batch(
    request: Usage_quotasBatchCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create multiple usage_quotass in a single request"""
    logger.debug(f"Batch creating {len(request.items)} usage_quotass")
    
    service = Usage_quotasService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump(), user_id=str(current_user.id))
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} usage_quotass successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[Usage_quotasResponse])
async def update_usage_quotass_batch(
    request: Usage_quotasBatchUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update multiple usage_quotass in a single request (requires ownership)"""
    logger.debug(f"Batch updating {len(request.items)} usage_quotass")
    
    service = Usage_quotasService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict, user_id=str(current_user.id))
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} usage_quotass successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=Usage_quotasResponse)
async def update_usage_quotas(
    id: int,
    data: Usage_quotasUpdateData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing usage_quotas (requires ownership)"""
    logger.debug(f"Updating usage_quotas {id} with data: {data}")

    service = Usage_quotasService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict, user_id=str(current_user.id))
        if not result:
            logger.warning(f"Usage_quotas with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Usage_quotas not found")
        
        logger.info(f"Usage_quotas {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating usage_quotas {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating usage_quotas {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_usage_quotass_batch(
    request: Usage_quotasBatchDeleteRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple usage_quotass by their IDs (requires ownership)"""
    logger.debug(f"Batch deleting {len(request.ids)} usage_quotass")
    
    service = Usage_quotasService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id, user_id=str(current_user.id))
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} usage_quotass successfully")
        return {"message": f"Successfully deleted {deleted_count} usage_quotass", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_usage_quotas(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single usage_quotas by ID (requires ownership)"""
    logger.debug(f"Deleting usage_quotas with id: {id}")
    
    service = Usage_quotasService(db)
    try:
        success = await service.delete(id, user_id=str(current_user.id))
        if not success:
            logger.warning(f"Usage_quotas with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Usage_quotas not found")
        
        logger.info(f"Usage_quotas {id} deleted successfully")
        return {"message": "Usage_quotas deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting usage_quotas {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")