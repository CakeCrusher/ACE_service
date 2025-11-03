"""Pydantic schemas for API and workflow data structures."""

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


###
# Core models represent the underlying data in DB
###


class BulletMetadata(BaseModel):
    """The metadata for a bullet point and its influence on subsequent runs"""

    helpful_count: int = Field(
        0, description="Count of times this bullet has been tagged as helpful"
    )
    harmful_count: int = Field(
        0, description="Count of times this bullet has been tagged as harmful"
    )
    neutral_count: int = Field(
        0, description="Count of times this bullet has been tagged as neutral"
    )

    class Config:
        extra = "allow"


class Playbook(BaseModel):
    """Represent data in postgres"""

    id: str = Field(description="The unique id of the playbook.")
    created_at: datetime = Field(
        description="The date and time the playbook was created."
    )
    modified_at: datetime = Field(
        description="The date and time the playbook was last modified."
    )
    name: str | None = Field(None, description="The name of the playbook.")
    description: str | None = Field(
        None, description="The description of the playbook."
    )


class Bullet(BaseModel):
    """A bullet point representing the a lesson learned from a run."""

    id: str = Field(description="Unique id of the bullet")
    playbook_id: str = Field(
        description="The id of the playbook the bullet belongs to."
    )
    content: str = Field(
        description="Content containing lesson and guidance earned from prior runs"
    )
    metadata: BulletMetadata = Field(description="Metadata pertaining to the bullet")
    created_at: datetime = Field(
        description="The date and time the bullet was created."
    )
    modified_at: datetime = Field(
        description="The date and time the bullet was last modified."
    )


class LearnJob(BaseModel):
    """A job to track progress of the learn_workflow workflow."""

    id: str = Field(description="The id of the job.")
    playbook_id: str = Field(description="The id of the playbook this job belongs to.")
    status: Literal["pending", "running", "completed", "failed"] = Field(
        description="The status of the job."
    )
    error: str | None = Field(None, description="Error message if the job failed.")
    reflection: "Reflection | None" = Field(
        None, description="Output from the reflector activity."
    )
    curation: "Curation | None" = Field(
        None, description="Output from the curator activity."
    )


###
# Key models for LLM generation
###


class BulletTag(BaseModel):
    """A bullet to be tagged with an adjective corresponding to its influence on the outcome."""

    id: str = Field(description="The bullet id to be tagged")
    tag: Literal["harmful", "helpful", "neutral"] = Field(
        description="How this bullet should be tagged based on its influence on the trajectory"
    )


class Reflection(BaseModel):
    """Reflection on the run based on the provided information comprised of the trajectory, retrieved_playbook, optional evaluation, and optional ground truth."""

    reasoning: str = Field(
        description="Your chain of thought / reasoning / thinking process, detailed analysis and calculations"
    )
    error_identification: str = Field(
        description="What specifically went wrong in the reasoning?"
    )
    root_cause_analysis: str = Field(
        description="Why did this error occur? What concept was misunderstood?"
    )
    correct_approach: str = Field(
        description="What should the model have done instead?"
    )
    key_insight: str = Field(
        description="What strategy, formula, or principle should be remembered to avoid this error?"
    )
    bullet_tags: list[BulletTag] = Field(
        description="List of bullets tagged as helpful, harmful, or neutral."
    )


class Operation(BaseModel):
    type: Literal["ADD", "UPDATE", "TAG", "REMOVE"] = Field(
        description="The type of operation to be performed."
    )


class AddOperation(Operation):
    """Add a new bullet."""

    type: Literal["ADD"] = Field(
        "ADD", description="The type of operation to be performed."
    )
    content: str = Field(description="The content of the bullet to add.")


class UpdateOperation(Operation):
    """Update an existing bullet if the alternative is to add a redundant bullet."""

    type: Literal["UPDATE"] = Field(
        "UPDATE", description="The type of operation to be performed."
    )
    bullet_id: str = Field(description="The id of the bullet to be updated")
    content: str = Field(
        description="The new content to replace the the existing bullet content. This should not be too different from the original."
    )


class TagOperation(Operation):
    """Tag a bullet based on the outcome of the run."""

    type: Literal["TAG"] = Field(
        "TAG", description="The type of operation to be performed."
    )
    bullet_id: str = Field(description="The id of the bullet to tag.")
    tag: Literal["helpful", "harmful", "neutral"] = Field(
        description="The tag to associate with this annotated bullet."
    )


class RemoveOperation(Operation):
    """Remove a bullet."""

    type: Literal["REMOVE"] = Field(
        "REMOVE", description="The type of operation to be performed."
    )
    bullet_id: str = Field(description="The id of the bullet to remove.")


OperationUnion = AddOperation | UpdateOperation | TagOperation | RemoveOperation


class Curation(BaseModel):
    """Curation of the playbook through a batch update as needed."""

    reasoning: str = Field(
        description="Your chain of thought / reasoning / thinking process, detailed analysis of changes and additions to be made and why."
    )
    operations: list[OperationUnion] = Field(
        description="List of operations to be performed, should only perform meaningful needed operations no more no less."
    )


###
# Temporal data structures (inputs and outputs)
###


class LearnWorkflowInput(BaseModel):
    """Input for learn_workflow workflow."""

    playbook_id: str = Field(..., description="The id of the playbook to be used.")
    learn_job_id: str | None = Field(
        None,
        description="The id of the learn job (optional, will use playbook_id if not provided).",
    )
    user_message: str = Field(
        ..., description="Complete initial message passed to the agent."
    )
    trajectory: str = Field(
        ...,
        description="The complete trajectory of the agent's run. Should contain embedded prompt with PLAYBOOK_BEGIN/PLAYBOOK_END markers if retrieved_playbook is not provided.",
    )
    ground_truth: str | None = Field(
        None, description="Ground truth expectation of the run."
    )
    evaluation: str | None = Field(
        None,
        description="Evaluation of the run may include any of execution feedback, custom evaluations, unit tests and more.",
    )
    reflector_additional_instructions: str | None = Field(
        None, description="Instructions to add to the reflector."
    )
    curator_additional_instructions: str | None = Field(
        None, description="Instructions to add to the curator."
    )


class LearnWorkflowOutput(BaseModel):
    """Output for learn_workflow workflow."""

    learn_job: LearnJob = Field(
        ..., description="The job tracking the progress of the workflow."
    )


class ReflectorInput(BaseModel):
    """Inputs to reflector activity"""

    playbook_id: str = Field(..., description="The id of the playbook to be used.")
    retrieved_playbook: str = Field(
        ...,
        description="Playbook retrieved to supplement the initial prompt with context.",
    )
    trajectory: str = Field(..., description="Complete trajectory of the run.")
    ground_truth: str | None = Field(
        None, description="Ground truth expectation of the run."
    )
    evaluation: str | None = Field(
        None,
        description="Evaluation of the run may include any of execution feedback, custom evaluations, unit tests and more.",
    )
    reflector_additional_instructions: str | None = Field(
        None, description="Instructions to add to the reflector."
    )


class ReflectorOutput(BaseModel):
    """Output from the reflector activity."""

    reflection: Reflection = Field(..., description="The production of the reflector.")


class CuratorInput(BaseModel):
    """Input into the curator activity"""

    playbook_id: str = Field(..., description="The id of the playbook to be used.")
    user_message: str = Field(
        ..., description="Complete initial message passed to the agent."
    )
    global_playbook: str = Field(
        ..., description="Complete playbook for the target prompt."
    )
    trajectory: str = Field(
        ..., description="The complete trajectory of the agent's run."
    )
    reflection: Reflection = Field(..., description="The production of the reflector.")
    curator_additional_instructions: str | None = Field(
        None, description="Instructions to add to the curator."
    )


class CuratorOutput(BaseModel):
    """Output from the curator activity."""

    curation: Curation = Field(..., description="The production of the curator.")


class ApplyCurationInput(BaseModel):
    """Input into the apply_curation activity"""

    playbook_id: str = Field(..., description="The id of the playbook to be used.")
    curation: Curation = Field(..., description="Curation to apply.")


class ApplyCurationOutput(BaseModel):
    """Output from the apply_curation activity."""

    status: Literal["success", "failure"] = Field(
        ..., description="Status of Operations"
    )
    error: str | None = Field(
        None, description="Error message if the operation failed."
    )


class UpdateLearnJobInput(BaseModel):
    """Input for update_learn_job_activity."""

    id: str = Field(..., description="The learn job ID to update.")
    status: str | None = Field(
        None,
        description="New status for the job (pending, running, completed, failed).",
    )
    error: str | None = Field(None, description="Error message if the job failed.")
    reflection: Reflection | None = Field(
        None, description="Reflection data to store (will be JSON serialized)."
    )
    curation: Curation | None = Field(
        None, description="Curation data to store (will be JSON serialized)."
    )


###
# API Request/Response models
###


class EmbeddedPromptInput(BaseModel):
    """Request model for POST /playbooks/{playbook_id}/embed_prompt."""

    prompt: str = Field(..., description="The prompt to be embedded.")
    k: int = Field(
        20, description="Number of top bullets to retrieve and embed from the playbook."
    )


class EmbeddedPromptOutput(BaseModel):
    """Response model for POST /embed_prompt."""

    prompt: str = Field(..., description="The embedded prompt.")


class ListPlaybooksResponse(BaseModel):
    """Response model for GET /playbooks."""

    playbooks: list[Playbook] = Field(
        ..., description="All registered playbooks visible to this caller."
    )


class CreatePlaybookRequest(BaseModel):
    """Request model for POST /playbooks."""

    name: str = Field(..., description="Human-readable name of the playbook.")
    description: str | None = Field(
        None, description="Optional description of this playbook's purpose/scope."
    )


class CreatePlaybookResponse(BaseModel):
    """Response model for POST /playbooks."""

    playbook: Playbook = Field(..., description="The created playbook record.")


class GetPlaybookResponse(BaseModel):
    """Response model for GET /playbooks/{playbook_id}."""

    playbook: Playbook = Field(
        ..., description="The requested playbook, including timestamps and metadata."
    )


class UpdatePlaybookRequest(BaseModel):
    """Request model for PATCH /playbooks/{playbook_id}."""

    name: str | None = Field(None, description="New name for the playbook.")
    description: str | None = Field(
        None, description="New description for the playbook."
    )


class UpdatePlaybookResponse(BaseModel):
    """Response model for PATCH /playbooks/{playbook_id}."""

    playbook: Playbook = Field(..., description="The updated playbook record.")


class ListBulletsResponse(BaseModel):
    """Response model for GET /playbooks/{playbook_id}/bullets."""

    bullets: list[Bullet] = Field(..., description="All bullets under this playbook.")


class CreateBulletRequest(BaseModel):
    """Request model for POST /playbooks/{playbook_id}/bullets."""

    content: str = Field(
        ...,
        description="The text content of the new bullet (guidance, heuristic, principle, rule, etc.).",
    )


class CreateBulletResponse(BaseModel):
    """Response model for POST /playbooks/{playbook_id}/bullets."""

    bullet: Bullet = Field(
        ..., description="The newly created bullet with assigned id and zeroed counts."
    )


class UpdateBulletContentRequest(BaseModel):
    """Request to update ONLY the bullet content."""

    content: str = Field(..., description="Replacement content for the bullet.")


class UpdateBulletContentResponse(BaseModel):
    """Response after updating bullet content."""

    bullet: Bullet = Field(
        ..., description="Bullet after content update, with modified_at bumped."
    )


class IncrementHelpfulResponse(BaseModel):
    """Response after incrementing helpful_count."""

    bullet: Bullet = Field(..., description="Bullet after helpful_count increment.")


class IncrementHarmfulResponse(BaseModel):
    """Response after incrementing harmful_count."""

    bullet: Bullet = Field(..., description="Bullet after harmful_count increment.")


class IncrementNeutralResponse(BaseModel):
    """Response after incrementing neutral_count."""

    bullet: Bullet = Field(..., description="Bullet after neutral_count increment.")


class RetrieveBulletsRequest(BaseModel):
    """Request model for POST /playbooks/{playbook_id}/retrieve."""

    user_message: str = Field(
        ..., description="The task or question the agent is about to solve."
    )
    k: int = Field(20, description="Max number of bullets to retrieve for this task.")


class RetrieveBulletsResponse(BaseModel):
    """Response model for POST /playbooks/{playbook_id}/retrieve."""

    retrieved_bullets: list[Bullet] = Field(
        ...,
        description="Subset of bullets ranked as most relevant to this user_message.",
    )


class StartLearnRequest(BaseModel):
    """Request model for POST /playbooks/{playbook_id}/episodes/learn."""

    user_message: str = Field(
        ..., description="Original user instruction that kicked off this agent run."
    )
    trajectory: str = Field(
        ...,
        description="Full reasoning trace / tool calls / code / outputs from the run. Should contain embedded prompt with PLAYBOOK_BEGIN/PLAYBOOK_END markers if retrieved_playbook is not provided.",
    )
    ground_truth: str | None = Field(
        None,
        description="If you know the correct final answer / canonical solution for this run, include it.",
    )
    evaluation: str | None = Field(
        None,
        description="Execution feedback such as unit test results, runtime errors, grader output, etc.",
    )
    reflector_additional_instructions: str | None = Field(
        None,
        description="Optional tweaks or domain-specific guidance to inject into reflector prompt.",
    )
    curator_additional_instructions: str | None = Field(
        None,
        description="Optional tweaks or domain-specific guidance to inject into curator prompt.",
    )


class StartLearnResponse(BaseModel):
    """Response model for POST /playbooks/{playbook_id}/episodes/learn."""

    learn_job_id: str = Field(
        ..., description="Identifier of the launched learn_workflow job."
    )


class GetLearnJobResponse(BaseModel):
    """Response model for GET /playbooks/{playbook_id}/episodes/learn/{learn_job_id}."""

    learn_job: LearnJob = Field(
        ..., description="Learn job status including reflection/curation if available."
    )
