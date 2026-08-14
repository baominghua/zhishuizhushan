from fastapi import APIRouter

from .entities import router as entities_router
from .resources import router as resources_router
from .imports import router as imports_router
from .patrol import router as patrol_router
from .harvest import router as harvest_router
from .labor import router as labor_router
from .safety import router as safety_router
from .iot import router as iot_router
from .drone import router as drone_router
from .ai import router as ai_router
from .ai_models import router as ai_models_router
from .ai_inference import router as ai_inference_router
from .mobile import router as mobile_router
from .system import router as system_router
from .workspace import router as workspace_router
from .attachments import router as attachments_router
from .operations_center import router as operations_center_router
from .carbon import router as carbon_router
from .cockpit import router as cockpit_router


router = APIRouter(prefix="/api/v2")
router.include_router(system_router)
router.include_router(workspace_router)
router.include_router(entities_router)
router.include_router(resources_router)
router.include_router(attachments_router)
router.include_router(imports_router)
router.include_router(patrol_router)
router.include_router(harvest_router)
router.include_router(labor_router)
router.include_router(safety_router)
router.include_router(iot_router)
router.include_router(drone_router)
router.include_router(ai_router)
router.include_router(ai_models_router)
router.include_router(ai_inference_router)
router.include_router(mobile_router)
router.include_router(operations_center_router)
router.include_router(carbon_router)
router.include_router(cockpit_router)
