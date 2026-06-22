from typing import Optional

from fastapi import Path, Query

from app.controllers.v1.base import new_router
from app.models.exception import HttpException
from app.services.pet_auto import service
from app.services.pet_auto.models import GeneratePetVideoRequest, PetProfileCreate, PetProfileUpdate
from app.services.pet_auto.scheduler import pet_auto_scheduler
from app.utils import utils

router = new_router()


def _response(data=None):
    return utils.get_response(200, data)


@router.post("/pet/profiles", summary="Create a pet profile")
def create_pet_profile(body: PetProfileCreate):
    try:
        profile = service.create_profile(body)
        return _response(profile.model_dump())
    except ValueError as exc:
        raise HttpException("", status_code=400, message=str(exc))


@router.get("/pet/profiles", summary="List pet profiles")
def list_pet_profiles(active_only: bool = Query(False)):
    return _response([profile.model_dump() for profile in service.list_profiles(active_only=active_only)])


@router.get("/pet/profiles/{pet_id}", summary="Get a pet profile")
def get_pet_profile(pet_id: str = Path(...)):
    profile = service.get_profile(pet_id)
    if not profile:
        raise HttpException("", status_code=404, message="pet profile not found")
    return _response(profile.model_dump())


@router.put("/pet/profiles/{pet_id}", summary="Update a pet profile")
def update_pet_profile(body: PetProfileUpdate, pet_id: str = Path(...)):
    try:
        profile = service.update_profile(pet_id, body)
    except ValueError as exc:
        raise HttpException("", status_code=400, message=str(exc))
    if not profile:
        raise HttpException("", status_code=404, message="pet profile not found")
    return _response(profile.model_dump())


@router.delete("/pet/profiles/{pet_id}", summary="Delete a pet profile")
def delete_pet_profile(pet_id: str = Path(...)):
    deleted = service.delete_profile(pet_id)
    if not deleted:
        raise HttpException("", status_code=404, message="pet profile not found")
    return _response({"deleted": True})


@router.post("/pet/profiles/{pet_id}/generate", summary="Generate a pet short video")
def generate_pet_video(body: GeneratePetVideoRequest, pet_id: str = Path(...)):
    try:
        plan = service.generate_for_pet(pet_id, body)
        return _response(plan.model_dump())
    except ValueError as exc:
        raise HttpException("", status_code=400, message=str(exc))


@router.get("/pet/plans", summary="List pet content plans")
def list_pet_plans(pet_id: Optional[str] = Query(None), limit: int = Query(50, ge=1, le=500)):
    return _response([plan.model_dump() for plan in service.list_plans(pet_id=pet_id, limit=limit)])


@router.get("/pet/plans/{plan_id}", summary="Get a pet content plan")
def get_pet_plan(plan_id: str = Path(...)):
    plan = service.get_plan(plan_id)
    if not plan:
        raise HttpException("", status_code=404, message="pet content plan not found")
    return _response(plan.model_dump())


@router.post("/pet/plans/{plan_id}/sync", summary="Sync a pet content plan with the underlying video task")
def sync_pet_plan(plan_id: str = Path(...)):
    plan = service.get_plan(plan_id)
    if not plan:
        raise HttpException("", status_code=404, message="pet content plan not found")
    return _response(plan.model_dump())


@router.get("/pet/scheduler", summary="Get pet scheduler status")
def get_scheduler_status():
    return _response(pet_auto_scheduler.status().model_dump())


@router.post("/pet/scheduler/run_today", summary="Generate today's videos for all active pet profiles")
def run_today(force: bool = Query(False)):
    plans = service.generate_today_for_active_profiles(force=force)
    return _response([plan.model_dump() for plan in plans])


@router.post("/pet/scheduler/run_due_once", summary="Run one scheduler tick for due profiles")
def run_due_once():
    return _response(pet_auto_scheduler.run_due_once())
