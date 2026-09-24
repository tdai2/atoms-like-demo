import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.bugs import BugsService
from dependencies.auth import get_current_user
from schemas.auth import UserResponse

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/bugs", tags=["bugs"])


# ---------- Pydantic Schemas ----------
class BugsData(BaseModel):
    """Entity data schema (for create/update)"""
    project_id: int
    title: str
    description: str = None
    severity: str = None
    reproduction: str = None
    related_case_id: int = None
    status: str = None
    fix_attempts: int = None
    latest_fix_id: int = None
    resolution: str = None
    target_version: int = None


class BugsUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    project_id: Optional[int] = None
    title: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[str] = None
    reproduction: Optional[str] = None
    related_case_id: Optional[int] = None
    status: Optional[str] = None
    fix_attempts: Optional[int] = None
    latest_fix_id: Optional[int] = None
    resolution: Optional[str] = None
    target_version: Optional[int] = None


class BugsResponse(BaseModel):
    """Entity response schema"""
    id: int
    user_id: str
    project_id: int
    title: str
    description: Optional[str] = None
    severity: Optional[str] = None
    reproduction: Optional[str] = None
    related_case_id: Optional[int] = None
    status: Optional[str] = None
    fix_attempts: Optional[int] = None
    latest_fix_id: Optional[int] = None
    resolution: Optional[str] = None
    target_version: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class BugsListResponse(BaseModel):
    """List response schema"""
    items: List[BugsResponse]
    total: int
    skip: int
    limit: int


class BugsBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[BugsData]


class BugsBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: BugsUpdateData


class BugsBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[BugsBatchUpdateItem]


class BugsBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=BugsListResponse)
async def query_bugss(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Query bugss with filtering, sorting, and pagination (user can only see their own records)"""
    logger.debug(f"Querying bugss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = BugsService(db)
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
        logger.debug(f"Found {result['total']} bugss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid bugs query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying bugss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=BugsListResponse)
async def query_bugss_all(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    # Query bugss with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying bugss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = BugsService(db)
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
        logger.debug(f"Found {result['total']} bugss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid bugs query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying bugss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=BugsResponse)
async def get_bugs(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single bugs by ID (user can only see their own records)"""
    logger.debug(f"Fetching bugs with id: {id}, fields={fields}")
    
    service = BugsService(db)
    try:
        result = await service.get_by_id(id, user_id=str(current_user.id))
        if not result:
            logger.warning(f"Bugs with id {id} not found")
            raise HTTPException(status_code=404, detail="Bugs not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching bugs {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=BugsResponse, status_code=201)
async def create_bugs(
    data: BugsData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new bugs"""
    logger.debug(f"Creating new bugs with data: {data}")
    
    service = BugsService(db)
    try:
        result = await service.create(data.model_dump(), user_id=str(current_user.id))
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create bugs")
        
        logger.info(f"Bugs created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating bugs: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating bugs: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[BugsResponse], status_code=201)
async def create_bugss_batch(
    request: BugsBatchCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create multiple bugss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} bugss")
    
    service = BugsService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump(), user_id=str(current_user.id))
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} bugss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[BugsResponse])
async def update_bugss_batch(
    request: BugsBatchUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update multiple bugss in a single request (requires ownership)"""
    logger.debug(f"Batch updating {len(request.items)} bugss")
    
    service = BugsService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict, user_id=str(current_user.id))
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} bugss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=BugsResponse)
async def update_bugs(
    id: int,
    data: BugsUpdateData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing bugs (requires ownership)"""
    logger.debug(f"Updating bugs {id} with data: {data}")

    service = BugsService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict, user_id=str(current_user.id))
        if not result:
            logger.warning(f"Bugs with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Bugs not found")
        
        logger.info(f"Bugs {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating bugs {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating bugs {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_bugss_batch(
    request: BugsBatchDeleteRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple bugss by their IDs (requires ownership)"""
    logger.debug(f"Batch deleting {len(request.ids)} bugss")
    
    service = BugsService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id, user_id=str(current_user.id))
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} bugss successfully")
        return {"message": f"Successfully deleted {deleted_count} bugss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_bugs(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single bugs by ID (requires ownership)"""
    logger.debug(f"Deleting bugs with id: {id}")
    
    service = BugsService(db)
    try:
        success = await service.delete(id, user_id=str(current_user.id))
        if not success:
            logger.warning(f"Bugs with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Bugs not found")
        
        logger.info(f"Bugs {id} deleted successfully")
        return {"message": "Bugs deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting bugs {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")