import threading
from datetime import datetime

from loguru import logger

from app.config import config
from app.services.pet_auto import repository, service
from app.services.pet_auto.models import GeneratePetVideoRequest, SchedulerStatus


class PetAutoScheduler:
    def __init__(self):
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_run_keys: set[str] = set()

    @property
    def enabled(self) -> bool:
        return bool(config.app.get("pet_auto_enabled", False))

    @property
    def default_daily_time(self) -> str:
        return str(config.app.get("pet_auto_daily_time", "09:00") or "09:00")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def status(self) -> SchedulerStatus:
        return SchedulerStatus(
            enabled=self.enabled,
            running=self.is_running(),
            daily_time=self.default_daily_time,
        )

    def start(self) -> None:
        repository.init_db()
        if not self.enabled:
            logger.info("pet auto scheduler is disabled. Set app.pet_auto_enabled=true to enable it.")
            return
        if self.is_running():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="pet-auto-scheduler", daemon=True)
        self._thread.start()
        logger.info(f"pet auto scheduler started, default daily_time={self.default_daily_time}")

    def stop(self) -> None:
        if not self.is_running():
            return
        self._stop_event.set()
        assert self._thread is not None
        self._thread.join(timeout=5)
        logger.info("pet auto scheduler stopped")

    def run_due_once(self) -> list[dict]:
        now = datetime.now()
        results: list[dict] = []
        for profile in repository.list_profiles(active_only=True):
            target_time = profile.daily_time or self.default_daily_time
            if now.strftime("%H:%M") != target_time:
                continue
            run_key = f"{profile.pet_id}:{now.date().isoformat()}:{target_time}"
            if run_key in self._last_run_keys:
                continue
            self._last_run_keys.add(run_key)
            existing = repository.get_plan_by_pet_date(profile.pet_id, now.date().isoformat())
            if existing:
                results.append({"pet_id": profile.pet_id, "skipped": True, "reason": "plan already exists"})
                continue
            plan = service.generate_for_pet(profile.pet_id, GeneratePetVideoRequest())
            results.append({"pet_id": profile.pet_id, "skipped": False, "plan": plan.model_dump()})
        return results

    def _run_loop(self) -> None:
        while not self._stop_event.wait(30):
            try:
                self.run_due_once()
            except Exception as exc:
                logger.exception(f"pet auto scheduler tick failed: {str(exc)}")


pet_auto_scheduler = PetAutoScheduler()
