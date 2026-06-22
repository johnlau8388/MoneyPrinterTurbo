import os
from datetime import date
from typing import Optional

from loguru import logger

from app.controllers.manager.base_manager import TaskQueueFullError
from app.models import const
from app.models.schema import TaskVideoRequest
from app.services import llm, state as sm, task as tm
from app.services.pet_auto import repository
from app.services.pet_auto.models import (
    GeneratePetVideoRequest,
    PetContentPlan,
    PetProfile,
    PetProfileCreate,
    PetProfileUpdate,
)
from app.utils import file_security, utils

_DEFAULT_TOPICS = [
    "今天它又用一个小动作骗到了主人",
    "宠物其实听懂了多少人话",
    "猫狗为什么总在你忙的时候来找你",
    "宠物眼里的主人到底是什么样",
    "一个适合宠物新手的日常小知识",
    "宠物装作无辜时通常在想什么",
    "猫狗表达喜欢你的几个细节",
]


def _today() -> str:
    return date.today().isoformat()


def _validate_local_materials(image_files: list[str]) -> None:
    if not image_files:
        raise ValueError("image_files is required; upload pet images with /api/v1/video_materials first")

    local_videos_dir = utils.storage_dir("local_videos", create=True)
    allowed_types = set(const.FILE_TYPE_IMAGES + const.FILE_TYPE_VIDEOS)
    for filename in image_files:
        resolved = file_security.resolve_path_within_directory(local_videos_dir, filename)
        ext = utils.parse_extension(resolved)
        if ext not in allowed_types:
            raise ValueError(f"unsupported pet material file type: {filename}")
        if not os.path.isfile(resolved):
            raise ValueError(f"pet material file does not exist: {filename}")


def create_profile(body: PetProfileCreate) -> PetProfile:
    _validate_local_materials(body.image_files)
    now = repository.now_iso()
    profile = PetProfile(
        **body.model_dump(),
        pet_id=utils.get_uuid(remove_hyphen=True),
        created_at=now,
        updated_at=now,
    )
    return repository.save_profile(profile)


def list_profiles(active_only: bool = False) -> list[PetProfile]:
    return repository.list_profiles(active_only=active_only)


def get_profile(pet_id: str) -> Optional[PetProfile]:
    return repository.get_profile(pet_id)


def update_profile(pet_id: str, body: PetProfileUpdate) -> Optional[PetProfile]:
    profile = repository.get_profile(pet_id)
    if not profile:
        return None

    data = profile.model_dump()
    update_data = body.model_dump(exclude_unset=True)
    if "image_files" in update_data and update_data["image_files"] is not None:
        _validate_local_materials(update_data["image_files"])
    data.update(update_data)
    data["updated_at"] = repository.now_iso()
    updated = PetProfile(**data)
    return repository.save_profile(updated)


def delete_profile(pet_id: str) -> bool:
    return repository.delete_profile(pet_id)


def _choose_topic(profile: PetProfile, request: GeneratePetVideoRequest) -> str:
    if request.topic.strip():
        return request.topic.strip()
    templates = profile.topic_templates or _DEFAULT_TOPICS
    index = date.today().toordinal() % len(templates)
    return templates[index].replace("{name}", profile.name).strip()


def _build_script(profile: PetProfile, topic: str, request: GeneratePetVideoRequest) -> str:
    if request.script.strip():
        return request.script.strip()

    species_name = {"dog": "狗", "cat": "猫", "other": "宠物"}.get(profile.species, "宠物")
    prompt = f"""
Create a short-form video narration for a recurring pet account.

Pet:
- name: {profile.name}
- species: {species_name}
- description: {profile.description or 'not provided'}
- style: {profile.style_prompt or 'warm, funny, concise, daily-life focused'}

Rules:
1. Use the same language as requested by the language field.
2. Keep it suitable for a 30-60 second vertical short video.
3. Write only spoken narration. No title, markdown, shot labels, timestamps, or hashtags.
4. Make the pet feel like the same recurring character, but do not claim impossible real actions unless the uploaded material actually shows them.
5. Prefer safe daily-life, pet-care, humor, or light emotional content.
""".strip()
    script = llm.generate_script(
        video_subject=f"{profile.name}的每日宠物短视频：{topic}",
        language=profile.language,
        paragraph_number=1,
        video_script_prompt=prompt,
    ).strip()

    if not script or script.startswith("Error:"):
        logger.warning(f"pet script generation failed, using fallback script: {script}")
        return f"今天的主角还是{profile.name}。{topic}。有时候宠物的小动作，看起来很简单，其实都是它和主人之间慢慢形成的默契。记住，多观察它的状态，多给它一点耐心，日常里的这些小瞬间，才是养宠物最治愈的地方。"
    return script


def _build_video_params(
    profile: PetProfile,
    topic: str,
    script: str,
    request: GeneratePetVideoRequest,
) -> TaskVideoRequest:
    clip_duration = int(
        request.video_params.get(
            "video_clip_duration",
            profile.video_params.get("video_clip_duration", 5),
        )
    )
    payload = {
        "video_subject": topic,
        "video_script": script,
        "video_language": profile.language,
        "video_aspect": "9:16",
        "video_concat_mode": "sequential",
        "video_clip_duration": clip_duration,
        "match_materials_to_script": False,
        "video_count": 1,
        "video_source": "local",
        "video_materials": [
            {"provider": "local", "url": file_name, "duration": clip_duration}
            for file_name in profile.image_files
        ],
        "voice_name": "zh-CN-XiaoxiaoNeural-Female",
        "voice_rate": 1.0,
        "bgm_type": "random",
        "bgm_volume": 0.2,
        "subtitle_enabled": True,
        "font_size": 60,
    }
    payload.update(profile.video_params or {})
    payload.update(request.video_params or {})
    payload["video_source"] = "local"
    payload["video_materials"] = [
        {"provider": "local", "url": file_name, "duration": clip_duration}
        for file_name in profile.image_files
    ]
    return TaskVideoRequest(**payload)


def _submit_video_task(params: TaskVideoRequest) -> str:
    from app.controllers.v1 import video as video_controller

    task_id = utils.get_uuid()
    sm.state.update_task(task_id)
    video_controller.task_manager.add_task(tm.start, task_id=task_id, params=params, stop_at="video")
    return task_id


def _task_video_urls(task_id: str, task: dict) -> list[str]:
    task_dir = utils.task_dir()
    urls: list[str] = []
    for file_path in task.get("videos") or []:
        if not isinstance(file_path, str):
            continue
        if file_path.startswith(("http://", "https://", "/tasks/")):
            urls.append(file_path)
            continue
        try:
            resolved = file_security.resolve_path_within_directory(task_dir, file_path)
            relative = os.path.relpath(resolved, task_dir).replace("\\", "/")
            urls.append(f"/tasks/{relative}")
        except ValueError:
            logger.warning(f"skip unsafe pet task video path: {file_path}")
    return urls


def sync_plan_result(plan_id: str) -> Optional[PetContentPlan]:
    plan = repository.get_plan(plan_id)
    if not plan or not plan.task_id:
        return plan

    task = sm.state.get_task(plan.task_id)
    if not task:
        return plan

    state = task.get("state")
    data = plan.model_dump()
    if state == const.TASK_STATE_COMPLETE:
        data.update({"status": "generated", "videos": _task_video_urls(plan.task_id, task), "error_message": ""})
    elif state == const.TASK_STATE_FAILED:
        data.update({"status": "failed", "error_message": "MoneyPrinterTurbo video task failed"})
    else:
        data.update({"status": "generating"})
    data["updated_at"] = repository.now_iso()
    return repository.save_plan(PetContentPlan(**data))


def generate_for_pet(pet_id: str, request: GeneratePetVideoRequest) -> PetContentPlan:
    profile = repository.get_profile(pet_id)
    if not profile:
        raise ValueError("pet profile not found")
    _validate_local_materials(profile.image_files)

    plan_date = request.plan_date or _today()
    existing = repository.get_plan_by_pet_date(pet_id, plan_date)
    if existing and not request.force:
        return sync_plan_result(existing.plan_id) or existing

    topic = _choose_topic(profile, request)
    script = _build_script(profile, topic, request)
    now = repository.now_iso()
    plan = PetContentPlan(
        plan_id=utils.get_uuid(remove_hyphen=True),
        pet_id=pet_id,
        plan_date=plan_date,
        topic=topic,
        script=script,
        status="planned",
        created_at=now,
        updated_at=now,
    )
    repository.save_plan(plan)

    try:
        params = _build_video_params(profile, topic, script, request)
        task_id = _submit_video_task(params)
        updated = plan.model_dump()
        updated.update({"status": "generating", "task_id": task_id, "updated_at": repository.now_iso()})
        return repository.save_plan(PetContentPlan(**updated))
    except TaskQueueFullError as exc:
        updated = plan.model_dump()
        updated.update({"status": "failed", "error_message": str(exc), "updated_at": repository.now_iso()})
        return repository.save_plan(PetContentPlan(**updated))
    except Exception as exc:
        logger.exception(f"failed to create pet video task for pet_id={pet_id}")
        updated = plan.model_dump()
        updated.update({"status": "failed", "error_message": str(exc), "updated_at": repository.now_iso()})
        return repository.save_plan(PetContentPlan(**updated))


def generate_today_for_active_profiles(force: bool = False) -> list[PetContentPlan]:
    plans: list[PetContentPlan] = []
    for profile in repository.list_profiles(active_only=True):
        try:
            plans.append(generate_for_pet(profile.pet_id, GeneratePetVideoRequest(force=force)))
        except Exception as exc:
            logger.exception(f"failed to generate pet daily video for {profile.pet_id}: {str(exc)}")
    return plans


def list_plans(pet_id: Optional[str] = None, limit: int = 50) -> list[PetContentPlan]:
    plans = repository.list_plans(pet_id=pet_id, limit=limit)
    return [sync_plan_result(plan.plan_id) or plan for plan in plans]


def get_plan(plan_id: str) -> Optional[PetContentPlan]:
    return sync_plan_result(plan_id)
