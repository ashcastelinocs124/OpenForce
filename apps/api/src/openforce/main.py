import os

from fastapi import FastAPI

from openforce.api.health import router as health_router
from openforce.api.integrations import router as integrations_router
from openforce.api.proposals import router as proposals_router
from openforce.workers.scheduler import scheduler_lifespan

# Skip the scheduler under pytest so background loops don't leak across tests.
_lifespan = None if os.environ.get("PYTEST_CURRENT_TEST") else scheduler_lifespan

app = FastAPI(title="Openforce", version="0.1.0", lifespan=_lifespan)
app.include_router(health_router)
app.include_router(integrations_router)
app.include_router(proposals_router)
