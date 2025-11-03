"""FastAPI application with all endpoints."""

import json
import uuid
from pathlib import Path
from typing import Annotated
from dotenv import load_dotenv

from fastapi import FastAPI, Depends, HTTPException, status, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from jinja2 import Environment, FileSystemLoader

from app.database.database import get_db, init_db
from app.database.models import PlaybookModel, BulletModel, LearnJobModel
from app.schemas import (
    # Core models
    Playbook,
    Bullet,
    BulletMetadata,
    LearnJob,
    Reflection,
    Curation,
    # API request/response models
    EmbeddedPromptInput,
    EmbeddedPromptOutput,
    ListPlaybooksResponse,
    CreatePlaybookRequest,
    CreatePlaybookResponse,
    GetPlaybookResponse,
    UpdatePlaybookRequest,
    UpdatePlaybookResponse,
    ListBulletsResponse,
    CreateBulletRequest,
    CreateBulletResponse,
    UpdateBulletContentRequest,
    UpdateBulletContentResponse,
    IncrementHelpfulResponse,
    IncrementHarmfulResponse,
    IncrementNeutralResponse,
    RetrieveBulletsRequest,
    RetrieveBulletsResponse,
    StartLearnRequest,
    StartLearnResponse,
    GetLearnJobResponse,
    # Workflow models
    LearnWorkflowInput,
)
from temporalio.client import Client
from app.temporal.workflows import LearnWorkflow

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI(
    title="ACE Service API",
    description="An implementation of the ACE framework as a separate service.",
    version="0.1.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Jinja2 environment for prompt templates
# Get prompts directory (now in app/prompts)
prompts_dir = Path(__file__).parent / "prompts"
env = Environment(loader=FileSystemLoader(str(prompts_dir)))

# Create API routers for better organization
prompts_router = APIRouter(prefix="/playbooks/{playbook_id}", tags=["Prompts"])
playbooks_router = APIRouter(prefix="/playbooks", tags=["Playbooks"])
bullets_router = APIRouter(prefix="/playbooks/{playbook_id}/bullets", tags=["Bullets"])
learning_router = APIRouter(
    prefix="/playbooks/{playbook_id}/episodes/learn", tags=["Learning"]
)


# Dependency functions
def get_or_create_playbook(
    playbook_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> PlaybookModel:
    """
    Dependency that gets a playbook if it exists, or creates it if it doesn't.
    Returns the PlaybookModel instance.
    """
    playbook = db.query(PlaybookModel).filter(PlaybookModel.id == playbook_id).first()
    if not playbook:
        # Create a new playbook with default values
        playbook = PlaybookModel(
            id=playbook_id,
            name=f"Playbook {playbook_id[:8]}",  # Use first 8 chars of ID as default name
            description=None,
        )
        db.add(playbook)
        db.commit()
        db.refresh(playbook)
    return playbook


# Helper functions
def model_to_playbook_schema(playbook_model: PlaybookModel) -> Playbook:
    """Convert PlaybookModel to Playbook schema."""
    return Playbook(
        id=playbook_model.id,
        created_at=playbook_model.created_at,
        modified_at=playbook_model.modified_at,
        name=playbook_model.name,
        description=playbook_model.description,
    )


def model_to_bullet_schema(bullet_model: BulletModel) -> Bullet:
    """Convert BulletModel to Bullet schema."""
    metadata_dict = (
        json.loads(bullet_model.bullet_metadata)
        if isinstance(bullet_model.bullet_metadata, str)
        else bullet_model.bullet_metadata
    )
    metadata = BulletMetadata(**metadata_dict)

    return Bullet(
        id=bullet_model.id,
        playbook_id=bullet_model.playbook_id,
        content=bullet_model.content,
        metadata=metadata,
        created_at=bullet_model.created_at,
        modified_at=bullet_model.modified_at,
    )


def model_to_learn_job_schema(job_model: LearnJobModel) -> LearnJob:
    """Convert LearnJobModel to LearnJob schema."""
    reflection = None
    if job_model.reflection:
        reflection_dict = (
            json.loads(job_model.reflection)
            if isinstance(job_model.reflection, str)
            else job_model.reflection
        )
        reflection = Reflection(**reflection_dict)

    curation = None
    if job_model.curation:
        curation_dict = (
            json.loads(job_model.curation)
            if isinstance(job_model.curation, str)
            else job_model.curation
        )
        curation = Curation(**curation_dict)

    return LearnJob(
        id=job_model.id,
        playbook_id=job_model.playbook_id,
        status=job_model.status,
        error=job_model.error,
        reflection=reflection,
        curation=curation,
    )


# ============================================================================
# Prompt Generation Endpoints
# ============================================================================


@prompts_router.post("/embed_prompt", response_model=EmbeddedPromptOutput)
async def embed_prompt(
    request: EmbeddedPromptInput,
    playbook: Annotated[PlaybookModel, Depends(get_or_create_playbook)],
    db: Annotated[Session, Depends(get_db)],
) -> EmbeddedPromptOutput:
    """
    Embed user prompt into generator template with top k bullets from the playbook.

    Used by: client (agent runtime) BEFORE it calls its LLM.
    Retrieves top k bullets from the playbook and embeds them into the generator template.
    """
    # Retrieve top k bullets from the playbook
    bullets = (
        db.query(BulletModel)
        .filter(BulletModel.playbook_id == playbook.id)
        .limit(request.k)
        .all()
    )

    if not bullets:
        return EmbeddedPromptOutput(prompt=request.prompt)

    # Format bullets for playbook context
    # Format: "[bullet_id] helpful=X harmful=Y :: content" for each bullet
    bullet_texts = []
    for bullet in bullets:
        metadata_dict = (
            json.loads(bullet.bullet_metadata)
            if isinstance(bullet.bullet_metadata, str)
            else bullet.bullet_metadata
        )
        bullet_texts.append(
            f"[{bullet.id}] helpful={metadata_dict.get('helpful_count', 0)} harmful={metadata_dict.get('harmful_count', 0)} :: {bullet.content}"
        )

    formatted_playbook = "- " + "\n- ".join(bullet_texts)

    # Render template with prompt and formatted playbook
    template = env.get_template("generator.j2")

    embedded_prompt = template.render(
        prompt=request.prompt,
        playbook=formatted_playbook,
    )

    return EmbeddedPromptOutput(prompt=embedded_prompt)


# ============================================================================
# Playbook Management Endpoints
# ============================================================================


@playbooks_router.get("", response_model=ListPlaybooksResponse)
async def list_playbooks(
    db: Annotated[Session, Depends(get_db)],
) -> ListPlaybooksResponse:
    """
    List all playbooks.

    Used by: internal (browse all playbooks) and client (if multiple prompts/agents exist).
    """
    playbooks = db.query(PlaybookModel).all()
    return ListPlaybooksResponse(
        playbooks=[model_to_playbook_schema(pb) for pb in playbooks]
    )


@playbooks_router.post(
    "", response_model=CreatePlaybookResponse, status_code=status.HTTP_201_CREATED
)
async def create_playbook(
    request: CreatePlaybookRequest,
    db: Annotated[Session, Depends(get_db)],
) -> CreatePlaybookResponse:
    """
    Create a new playbook.

    Used by: internal (bootstrapping a new agent domain).
    """
    playbook = PlaybookModel(
        id=str(uuid.uuid4()),
        name=request.name,
        description=request.description,
    )
    db.add(playbook)
    db.commit()
    db.refresh(playbook)

    return CreatePlaybookResponse(playbook=model_to_playbook_schema(playbook))


@playbooks_router.get("/{playbook_id}", response_model=GetPlaybookResponse)
async def get_playbook(
    playbook: Annotated[PlaybookModel, Depends(get_or_create_playbook)],
) -> GetPlaybookResponse:
    """
    Get a specific playbook by ID.

    Used by: both (metadata panels, sanity checks).
    """
    return GetPlaybookResponse(playbook=model_to_playbook_schema(playbook))


@playbooks_router.patch("/{playbook_id}", response_model=UpdatePlaybookResponse)
async def update_playbook(
    playbook: Annotated[PlaybookModel, Depends(get_or_create_playbook)],
    request: UpdatePlaybookRequest,
    db: Annotated[Session, Depends(get_db)],
) -> UpdatePlaybookResponse:
    """
    Update a playbook's name and/or description.

    Used by: internal (updating playbook metadata).
    """
    # Update fields if provided
    if request.name is not None:
        playbook.name = request.name
    if request.description is not None:
        playbook.description = request.description

    db.commit()
    db.refresh(playbook)

    return UpdatePlaybookResponse(playbook=model_to_playbook_schema(playbook))


# ============================================================================
# Bullet Management Endpoints
# ============================================================================


@bullets_router.get("", response_model=ListBulletsResponse)
async def list_bullets(
    playbook: Annotated[PlaybookModel, Depends(get_or_create_playbook)],
    db: Annotated[Session, Depends(get_db)],
) -> ListBulletsResponse:
    """
    List all bullets for a playbook.

    Used by: internal (visualize full evolving playbook), sometimes client (debug).
    """
    bullets = db.query(BulletModel).filter(BulletModel.playbook_id == playbook.id).all()
    return ListBulletsResponse(bullets=[model_to_bullet_schema(b) for b in bullets])


@bullets_router.post(
    "", response_model=CreateBulletResponse, status_code=status.HTTP_201_CREATED
)
async def create_bullet(
    playbook: Annotated[PlaybookModel, Depends(get_or_create_playbook)],
    request: CreateBulletRequest,
    db: Annotated[Session, Depends(get_db)],
) -> CreateBulletResponse:
    """
    Create a new bullet for a playbook.

    Used by: internal (manual seeding / human expert input).
    """
    bullet = BulletModel(
        id=str(uuid.uuid4()),
        playbook_id=playbook.id,
        content=request.content,
        bullet_metadata=json.dumps(
            {"helpful_count": 0, "harmful_count": 0, "neutral_count": 0}
        ),
    )
    db.add(bullet)
    db.commit()
    db.refresh(bullet)

    return CreateBulletResponse(bullet=model_to_bullet_schema(bullet))


@bullets_router.patch(
    "/{bullet_id}/content", response_model=UpdateBulletContentResponse
)
async def update_bullet_content(
    playbook: Annotated[PlaybookModel, Depends(get_or_create_playbook)],
    bullet_id: str,
    request: UpdateBulletContentRequest,
    db: Annotated[Session, Depends(get_db)],
) -> UpdateBulletContentResponse:
    """
    Update the content of a bullet.

    Used by: internal (surgical fix to wording).
    """
    bullet = (
        db.query(BulletModel)
        .filter(
            BulletModel.id == bullet_id,
            BulletModel.playbook_id == playbook.id,
        )
        .first()
    )

    if not bullet:
        raise HTTPException(status_code=404, detail="Bullet not found")

    bullet.content = request.content
    db.commit()
    db.refresh(bullet)

    return UpdateBulletContentResponse(bullet=model_to_bullet_schema(bullet))


@bullets_router.post(
    "/{bullet_id}/increment_helpful", response_model=IncrementHelpfulResponse
)
async def increment_helpful(
    playbook: Annotated[PlaybookModel, Depends(get_or_create_playbook)],
    bullet_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> IncrementHelpfulResponse:
    """
    Increment the helpful_count for a bullet.

    Used by: internal (operator dashboards), and by learn_workflow when applying TAG 'helpful'.
    """
    bullet = (
        db.query(BulletModel)
        .filter(
            BulletModel.id == bullet_id,
            BulletModel.playbook_id == playbook.id,
        )
        .first()
    )

    if not bullet:
        raise HTTPException(status_code=404, detail="Bullet not found")

    metadata_dict = (
        json.loads(bullet.bullet_metadata)
        if isinstance(bullet.bullet_metadata, str)
        else bullet.bullet_metadata
    )
    metadata_dict["helpful_count"] = metadata_dict.get("helpful_count", 0) + 1
    bullet.bullet_metadata = json.dumps(metadata_dict)
    db.commit()
    db.refresh(bullet)

    return IncrementHelpfulResponse(bullet=model_to_bullet_schema(bullet))


@bullets_router.post(
    "/{bullet_id}/increment_harmful", response_model=IncrementHarmfulResponse
)
async def increment_harmful(
    playbook: Annotated[PlaybookModel, Depends(get_or_create_playbook)],
    bullet_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> IncrementHarmfulResponse:
    """
    Increment the harmful_count for a bullet.

    Used by: internal and learn_workflow when applying TAG 'harmful'.
    """
    bullet = (
        db.query(BulletModel)
        .filter(
            BulletModel.id == bullet_id,
            BulletModel.playbook_id == playbook.id,
        )
        .first()
    )

    if not bullet:
        raise HTTPException(status_code=404, detail="Bullet not found")

    metadata_dict = (
        json.loads(bullet.bullet_metadata)
        if isinstance(bullet.bullet_metadata, str)
        else bullet.bullet_metadata
    )
    metadata_dict["harmful_count"] = metadata_dict.get("harmful_count", 0) + 1
    bullet.bullet_metadata = json.dumps(metadata_dict)
    db.commit()
    db.refresh(bullet)

    return IncrementHarmfulResponse(bullet=model_to_bullet_schema(bullet))


@bullets_router.post(
    "/{bullet_id}/increment_neutral", response_model=IncrementNeutralResponse
)
async def increment_neutral(
    playbook: Annotated[PlaybookModel, Depends(get_or_create_playbook)],
    bullet_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> IncrementNeutralResponse:
    """
    Increment the neutral_count for a bullet.

    Used by: internal and learn_workflow when applying TAG 'neutral'.
    """
    bullet = (
        db.query(BulletModel)
        .filter(
            BulletModel.id == bullet_id,
            BulletModel.playbook_id == playbook.id,
        )
        .first()
    )

    if not bullet:
        raise HTTPException(status_code=404, detail="Bullet not found")

    metadata_dict = (
        json.loads(bullet.bullet_metadata)
        if isinstance(bullet.bullet_metadata, str)
        else bullet.bullet_metadata
    )
    metadata_dict["neutral_count"] = metadata_dict.get("neutral_count", 0) + 1
    bullet.bullet_metadata = json.dumps(metadata_dict)
    db.commit()
    db.refresh(bullet)

    return IncrementNeutralResponse(bullet=model_to_bullet_schema(bullet))


@bullets_router.post("/retrieve", response_model=RetrieveBulletsResponse)
async def retrieve_bullets(
    playbook: Annotated[PlaybookModel, Depends(get_or_create_playbook)],
    request: RetrieveBulletsRequest,
    db: Annotated[Session, Depends(get_db)],
) -> RetrieveBulletsResponse:
    """
    Retrieve relevant bullets for a user message.

    Used by: client (agent runtime) BEFORE it calls its LLM.
    We use this to build the 'retrieved_playbook' subset for prompting.

    NOTE: This is a simple implementation that returns all bullets up to k.
    In production, you would implement semantic search/ranking here.

    The client should format the returned bullets into a string for use in
    the retrieved_playbook field when calling the learn endpoint.
    Format: "[bullet_id] helpful=X harmful=Y :: content" for each bullet.
    """
    # Simple implementation: return first k bullets
    # In production, implement semantic search/ranking based on user_message
    bullets = (
        db.query(BulletModel)
        .filter(BulletModel.playbook_id == playbook.id)
        .limit(request.k)
        .all()
    )

    return RetrieveBulletsResponse(
        retrieved_bullets=[model_to_bullet_schema(b) for b in bullets]
    )


# ============================================================================
# Learning Workflow Endpoints
# ============================================================================


@learning_router.post("", response_model=StartLearnResponse)
async def start_learn(
    playbook: Annotated[PlaybookModel, Depends(get_or_create_playbook)],
    request: StartLearnRequest,
    db: Annotated[Session, Depends(get_db)],
) -> StartLearnResponse:
    """
    Start a learn workflow for an episode.

    Used by: client (agent runtime) AFTER it finishes a run.
    This launches learn_workflow asynchronously in Temporal.
    """
    # Create learn job record
    learn_job_id = str(uuid.uuid4())
    learn_job = LearnJobModel(
        id=learn_job_id,
        playbook_id=playbook.id,
        status="pending",
    )
    db.add(learn_job)
    db.commit()

    # Connect to Temporal and start workflow
    import os

    temporal_address = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
    temporal_namespace = os.getenv("TEMPORAL_NAMESPACE", "default")
    temporal_client = await Client.connect(
        temporal_address, namespace=temporal_namespace
    )

    workflow_input = LearnWorkflowInput(
        playbook_id=playbook.id,
        learn_job_id=learn_job_id,
        user_message=request.user_message,
        trajectory=request.trajectory,
        ground_truth=request.ground_truth,
        evaluation=request.evaluation,
        reflector_additional_instructions=request.reflector_additional_instructions,
        curator_additional_instructions=request.curator_additional_instructions,
    )

    # Start workflow
    await temporal_client.start_workflow(
        LearnWorkflow.run,
        workflow_input,
        id=learn_job_id,
        task_queue="ace-task-queue",
    )

    return StartLearnResponse(learn_job_id=learn_job_id)


@learning_router.get("/{learn_job_id}", response_model=GetLearnJobResponse)
async def get_learn_job(
    playbook: Annotated[PlaybookModel, Depends(get_or_create_playbook)],
    learn_job_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> GetLearnJobResponse:
    """
    Get the status of a learn job.

    Used by: client (polling) and internal (debugging).
    Represents the current state of the learn_workflow.
    """
    learn_job = (
        db.query(LearnJobModel)
        .filter(
            LearnJobModel.id == learn_job_id,
            LearnJobModel.playbook_id == playbook.id,
        )
        .first()
    )

    if not learn_job:
        raise HTTPException(status_code=404, detail="Learn job not found")

    return GetLearnJobResponse(learn_job=model_to_learn_job_schema(learn_job))


# Register routers with the app
app.include_router(prompts_router)
app.include_router(playbooks_router)
app.include_router(bullets_router)
app.include_router(learning_router)


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    init_db()
