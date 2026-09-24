import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.bug_fix_logs import Bug_fix_logsService
from dependencies.auth import get_current_user
from schemas.auth import UserResponse

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/bug_fix_logs", tags=["bug_fix_logs"])


# ---------- Pydantic Schemas ----------
class Bug_fix_logsData(BaseModel):
    """Entity data schema (for create/update)"""
    project_id: int
    bug_id: int
    status: str = None
    attempt_no: int = None
    model: str = None
    source_version: int = None
    target_version: int = None
    artifact_key: str = None
    changes_json: str = None
    diff_summary: str = None
    retest_json: str = None
    error_message: str = None
    duration_ms: int = None


class Bug_fix_logsUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    project_id: Optional[int] = None
    bug_id: Optional[int] = None
    status: Optional[str] = None
    attempt_no: Optional[int] = None
    model: Optional[str] = None
    source_version: Optional[int] = None
    target_version: Optional[int] = None
    artifact_key: Optional[str] = None
    changes_json: Optional[str] = None
    diff_summary: Optional[str] = None
    retest_json: Optional[str] = None
    error_message: Optional[str] = None
    duration_ms: Optional[int] = None


class Bug_fix_logsResponse(BaseModel):
    """Entity response schema"""
    id: int
    user_id: str
    project_id: int
    bug_id: int
    status: Optional[str] = None
    attempt_no: Optional[int] = None
    model: Optional[str] = None
    source_version: Optional[int] = None
    target_version: Optional[int] = None
    artifact_key: Optional[str] = None
    changes_json: Optional[str] = None
    diff_summary: Optional[str] = None
    retest_json: Optional[str] = None
    error_message: Optional[str] = None
    duration_ms: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Bug_fix_logsListResponse(BaseModel):
    """List response schema"""
    items: List[Bug_fix_logsResponse]
    total: int
    skip: int
    limit: int


class Bug_fix_logsBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[Bug_fix_logsData]


class Bug_fix_logsBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: Bug_fix_logsUpdateData


class Bug_fix_logsBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[Bug_fix_logsBatchUpdateItem]


class Bug_fix_logsBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=Bug_fix_logsListResponse)
async def query_bug_fix_logss(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Query bug_fix_logss with filtering, sorting, and pagination (user can only see their own records)"""
    logger.debug(f"Querying bug_fix_logss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = Bug_fix_logsService(db)
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
        logger.debug(f"Found {result['total']} bug_fix_logss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid bug_fix_logs query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying bug_fix_logss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=Bug_fix_logsListResponse)
async def query_bug_fix_logss_all(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    # Query bug_fix_logss with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying bug_fix_logss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = Bug_fix_logsService(db)
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
        logger.debug(f"Found {result['total']} bug_fix_logss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid bug_fix_logs query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying bug_fix_logss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=Bug_fix_logsResponse)
async def get_bug_fix_logs(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single bug_fix_logs by ID (user can only see their own records)"""
    logger.debug(f"Fetching bug_fix_logs with id: {id}, fields={fields}")
    
    service = Bug_fix_logsService(db)
    try:
        result = await service.get_by_id(id, user_id=str(current_user.id))
        if not result:
            logger.warning(f"Bug_fix_logs with id {id} not found")
            raise HTTPException(status_code=404, detail="Bug_fix_logs not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching bug_fix_logs {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=Bug_fix_logsResponse, status_code=201)
async def create_bug_fix_logs(
    data: Bug_fix_logsData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new bug_fix_logs"""
    logger.debug(f"Creating new bug_fix_logs with data: {data}")
    
    service = Bug_fix_logsService(db)
    try:
        result = await service.create(data.model_dump(), user_id=str(current_user.id))
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create bug_fix_logs")
        
        logger.info(f"Bug_fix_logs created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating bug_fix_logs: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating bug_fix_logs: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[Bug_fix_logsResponse], status_code=201)
async def create_bug_fix_logss_batch(
    request: Bug_fix_logsBatchCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create multiple bug_fix_logss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} bug_fix_logss")
    
    service = Bug_fix_logsService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump(), user_id=str(current_user.id))
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} bug_fix_logss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[Bug_fix_logsResponse])
async def update_bug_fix_logss_batch(
    request: Bug_fix_logsBatchUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update multiple bug_fix_logss in a single request (requires ownership)"""
    logger.debug(f"Batch updating {len(request.items)} bug_fix_logss")
    
    service = Bug_fix_logsService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict, user_id=str(current_user.id))
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} bug_fix_logss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=Bug_fix_logsResponse)
async def update_bug_fix_logs(
    id: int,
    data: Bug_fix_logsUpdateData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing bug_fix_logs (requires ownership)"""
    logger.debug(f"Updating bug_fix_logs {id} with data: {data}")

    service = Bug_fix_logsService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict, user_id=str(current_user.id))
        if not result:
            logger.warning(f"Bug_fix_logs with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Bug_fix_logs not found")
        
        logger.info(f"Bug_fix_logs {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating bug_fix_logs {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating bug_fix_logs {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_bug_fix_logss_batch(
    request: Bug_fix_logsBatchDeleteRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple bug_fix_logss by their IDs (requires ownership)"""
    logger.debug(f"Batch deleting {len(request.ids)} bug_fix_logss")
    
    service = Bug_fix_logsService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id, user_id=str(current_user.id))
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} bug_fix_logss successfully")
        return {"message": f"Successfully deleted {deleted_count} bug_fix_logss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_bug_fix_logs(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single bug_fix_logs by ID (requires ownership)"""
    logger.debug(f"Deleting bug_fix_logs with id: {id}")
    
    service = Bug_fix_logsService(db)
    try:
        success = await service.delete(id, user_id=str(current_user.id))
        if not success:
            logger.warning(f"Bug_fix_logs with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Bug_fix_logs not found")
        
        logger.info(f"Bug_fix_logs {id} deleted successfully")
        return {"message": "Bug_fix_logs deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting bug_fix_logs {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")