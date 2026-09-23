import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.build_tasks import Build_tasksService
from dependencies.auth import get_current_user
from schemas.auth import UserResponse

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/build_tasks", tags=["build_tasks"])


# ---------- Pydantic Schemas ----------
class Build_tasksData(BaseModel):
    """Entity data schema (for create/update)"""
    project_id: int
    run_no: int = None
    stage: str
    stage_name: str = None
    stage_order: int = None
    stage_state: str
    stage_log: str = None
    error_message: str = None
    output_summary: str = None


class Build_tasksUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    project_id: Optional[int] = None
    run_no: Optional[int] = None
    stage: Optional[str] = None
    stage_name: Optional[str] = None
    stage_order: Optional[int] = None
    stage_state: Optional[str] = None
    stage_log: Optional[str] = None
    error_message: Optional[str] = None
    output_summary: Optional[str] = None


class Build_tasksResponse(BaseModel):
    """Entity response schema"""
    id: int
    user_id: str
    project_id: int
    run_no: Optional[int] = None
    stage: str
    stage_name: Optional[str] = None
    stage_order: Optional[int] = None
    stage_state: str
    stage_log: Optional[str] = None
    error_message: Optional[str] = None
    output_summary: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Build_tasksListResponse(BaseModel):
    """List response schema"""
    items: List[Build_tasksResponse]
    total: int
    skip: int
    limit: int


class Build_tasksBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[Build_tasksData]


class Build_tasksBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: Build_tasksUpdateData


class Build_tasksBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[Build_tasksBatchUpdateItem]


class Build_tasksBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=Build_tasksListResponse)
async def query_build_taskss(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Query build_taskss with filtering, sorting, and pagination (user can only see their own records)"""
    logger.debug(f"Querying build_taskss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = Build_tasksService(db)
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
        logger.debug(f"Found {result['total']} build_taskss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid build_tasks query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying build_taskss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=Build_tasksListResponse)
async def query_build_taskss_all(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    # Query build_taskss with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying build_taskss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = Build_tasksService(db)
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
        logger.debug(f"Found {result['total']} build_taskss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid build_tasks query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying build_taskss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=Build_tasksResponse)
async def get_build_tasks(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single build_tasks by ID (user can only see their own records)"""
    logger.debug(f"Fetching build_tasks with id: {id}, fields={fields}")
    
    service = Build_tasksService(db)
    try:
        result = await service.get_by_id(id, user_id=str(current_user.id))
        if not result:
            logger.warning(f"Build_tasks with id {id} not found")
            raise HTTPException(status_code=404, detail="Build_tasks not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching build_tasks {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=Build_tasksResponse, status_code=201)
async def create_build_tasks(
    data: Build_tasksData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new build_tasks"""
    logger.debug(f"Creating new build_tasks with data: {data}")
    
    service = Build_tasksService(db)
    try:
        result = await service.create(data.model_dump(), user_id=str(current_user.id))
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create build_tasks")
        
        logger.info(f"Build_tasks created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating build_tasks: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating build_tasks: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[Build_tasksResponse], status_code=201)
async def create_build_taskss_batch(
    request: Build_tasksBatchCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create multiple build_taskss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} build_taskss")
    
    service = Build_tasksService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump(), user_id=str(current_user.id))
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} build_taskss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[Build_tasksResponse])
async def update_build_taskss_batch(
    request: Build_tasksBatchUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update multiple build_taskss in a single request (requires ownership)"""
    logger.debug(f"Batch updating {len(request.items)} build_taskss")
    
    service = Build_tasksService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict, user_id=str(current_user.id))
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} build_taskss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=Build_tasksResponse)
async def update_build_tasks(
    id: int,
    data: Build_tasksUpdateData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing build_tasks (requires ownership)"""
    logger.debug(f"Updating build_tasks {id} with data: {data}")

    service = Build_tasksService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict, user_id=str(current_user.id))
        if not result:
            logger.warning(f"Build_tasks with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Build_tasks not found")
        
        logger.info(f"Build_tasks {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating build_tasks {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating build_tasks {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_build_taskss_batch(
    request: Build_tasksBatchDeleteRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple build_taskss by their IDs (requires ownership)"""
    logger.debug(f"Batch deleting {len(request.ids)} build_taskss")
    
    service = Build_tasksService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id, user_id=str(current_user.id))
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} build_taskss successfully")
        return {"message": f"Successfully deleted {deleted_count} build_taskss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_build_tasks(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single build_tasks by ID (requires ownership)"""
    logger.debug(f"Deleting build_tasks with id: {id}")
    
    service = Build_tasksService(db)
    try:
        success = await service.delete(id, user_id=str(current_user.id))
        if not success:
            logger.warning(f"Build_tasks with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Build_tasks not found")
        
        logger.info(f"Build_tasks {id} deleted successfully")
        return {"message": "Build_tasks deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting build_tasks {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")