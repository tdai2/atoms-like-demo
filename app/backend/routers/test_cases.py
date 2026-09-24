import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.test_cases import Test_casesService
from dependencies.auth import get_current_user
from schemas.auth import UserResponse

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/test_cases", tags=["test_cases"])


# ---------- Pydantic Schemas ----------
class Test_casesData(BaseModel):
    """Entity data schema (for create/update)"""
    project_id: int
    title: str
    case_type: str = None
    preconditions: str = None
    steps: str = None
    expected: str = None
    assertion: str = None
    source: str = None
    case_state: str = None


class Test_casesUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    project_id: Optional[int] = None
    title: Optional[str] = None
    case_type: Optional[str] = None
    preconditions: Optional[str] = None
    steps: Optional[str] = None
    expected: Optional[str] = None
    assertion: Optional[str] = None
    source: Optional[str] = None
    case_state: Optional[str] = None


class Test_casesResponse(BaseModel):
    """Entity response schema"""
    id: int
    user_id: str
    project_id: int
    title: str
    case_type: Optional[str] = None
    preconditions: Optional[str] = None
    steps: Optional[str] = None
    expected: Optional[str] = None
    assertion: Optional[str] = None
    source: Optional[str] = None
    case_state: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Test_casesListResponse(BaseModel):
    """List response schema"""
    items: List[Test_casesResponse]
    total: int
    skip: int
    limit: int


class Test_casesBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[Test_casesData]


class Test_casesBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: Test_casesUpdateData


class Test_casesBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[Test_casesBatchUpdateItem]


class Test_casesBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=Test_casesListResponse)
async def query_test_casess(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Query test_casess with filtering, sorting, and pagination (user can only see their own records)"""
    logger.debug(f"Querying test_casess: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = Test_casesService(db)
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
        logger.debug(f"Found {result['total']} test_casess")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid test_cases query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying test_casess: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=Test_casesListResponse)
async def query_test_casess_all(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    # Query test_casess with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying test_casess: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = Test_casesService(db)
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
        logger.debug(f"Found {result['total']} test_casess")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid test_cases query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying test_casess: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=Test_casesResponse)
async def get_test_cases(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single test_cases by ID (user can only see their own records)"""
    logger.debug(f"Fetching test_cases with id: {id}, fields={fields}")
    
    service = Test_casesService(db)
    try:
        result = await service.get_by_id(id, user_id=str(current_user.id))
        if not result:
            logger.warning(f"Test_cases with id {id} not found")
            raise HTTPException(status_code=404, detail="Test_cases not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching test_cases {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=Test_casesResponse, status_code=201)
async def create_test_cases(
    data: Test_casesData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new test_cases"""
    logger.debug(f"Creating new test_cases with data: {data}")
    
    service = Test_casesService(db)
    try:
        result = await service.create(data.model_dump(), user_id=str(current_user.id))
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create test_cases")
        
        logger.info(f"Test_cases created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating test_cases: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating test_cases: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[Test_casesResponse], status_code=201)
async def create_test_casess_batch(
    request: Test_casesBatchCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create multiple test_casess in a single request"""
    logger.debug(f"Batch creating {len(request.items)} test_casess")
    
    service = Test_casesService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump(), user_id=str(current_user.id))
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} test_casess successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[Test_casesResponse])
async def update_test_casess_batch(
    request: Test_casesBatchUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update multiple test_casess in a single request (requires ownership)"""
    logger.debug(f"Batch updating {len(request.items)} test_casess")
    
    service = Test_casesService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict, user_id=str(current_user.id))
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} test_casess successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=Test_casesResponse)
async def update_test_cases(
    id: int,
    data: Test_casesUpdateData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing test_cases (requires ownership)"""
    logger.debug(f"Updating test_cases {id} with data: {data}")

    service = Test_casesService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict, user_id=str(current_user.id))
        if not result:
            logger.warning(f"Test_cases with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Test_cases not found")
        
        logger.info(f"Test_cases {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating test_cases {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating test_cases {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_test_casess_batch(
    request: Test_casesBatchDeleteRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple test_casess by their IDs (requires ownership)"""
    logger.debug(f"Batch deleting {len(request.ids)} test_casess")
    
    service = Test_casesService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id, user_id=str(current_user.id))
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} test_casess successfully")
        return {"message": f"Successfully deleted {deleted_count} test_casess", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_test_cases(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single test_cases by ID (requires ownership)"""
    logger.debug(f"Deleting test_cases with id: {id}")
    
    service = Test_casesService(db)
    try:
        success = await service.delete(id, user_id=str(current_user.id))
        if not success:
            logger.warning(f"Test_cases with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Test_cases not found")
        
        logger.info(f"Test_cases {id} deleted successfully")
        return {"message": "Test_cases deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting test_cases {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")