# ACE Service
An implementation of the ACE framework as a separate serice. This service is composed of an exposed API managing the logic of the ACE framework including the retrieval of bullets from the global playbook, the reflection and curator workflows. Additionally, a client is provided to visualize the database as an internal utility GUI.

## Architecure
The high level system architecture will be comprised of 3 services inside of the of a docker compose network.

- Postgres: A postgres image will made available to the network this will contain and persist the data stores.

- Temporal: A temporal service that will be leveraged to host workflows and activities of the ACE system.

- API: A FastAPI service will be tapping into the aformentioned services to serve as the interface for clients. The environment will use UV and the server will leverage SQLAlchemy to interact with the postgres database and Temporal to host the workflows and activities.a

And externally a react frontend will be used to visualize the data.

## Data structures

```python
from pydantic import BaseModel, Field
from typing import Literal

###
# Core models represent the underlying data in DB
###

class Playbook(BaseModel): # represent data in postgres
    id: str = Field(description="The unique id of the playbook.")
    created_at: datetime = Field(description="The date and time the playbook was created.")
    modified_at: datetime = Field(description="The date and time the playbook was last modified.")
    name: str | None = Field(None, description="The name of the playbook.")
    description: str | None = Field(None, description="The description of the playbook.")

class BulletMetadata(BaseModel):
    """The metadata for a bullet point and its influence on subsequent runs"""
    helpful_count: int = Field(0, description="Count of times this bullet has been tagged as helpful")
    harmful_count: int = Field(0, description="Count of times this bullet has been tagged as narmful")
    neutral_count: int = Field(0, description="Count of times this bullet has been tagged as neutral")
    class Config:
        extra = "allow"

class Bullet(BaseModel): # represent data in postgres
    """A bullet point representing the a lesson learned from a run."""
    id: str = Field(description="Unique id of the bullet")
    playbook_id: str = Field(description="The id of the playbook the bullet belongs to.") # Foreign key to playbook
    content: str = Field(description="Content containing lesson ang guidance earned from prior runs")
    metadata: BulletMetadata = Field(description="Metadata pertaining to the bullet") # will be serialized into as a json string for storage in postgres and deserialized for fastapi logic
    created_at: datetime = Field(description="The date and time the bullet was created.")
    modified_at: datetime = Field(description="The date and time the bullet was last modified.")
    # Should the created and modified at fields be inside metadata

class LearnJob(BaseModel):
    """A job to track progress of the learn_workflow workflow."""
    id: str = Field(description="The id of the job.")
    status: Literal["pending","running","completed","failed"] = Field(description="The status of the job.")
    error: str | None = Field(None, description="Error message if the job failed.")
    reflection: Reflection | None = Field(None, description="Output from the reflector activity.") # Will be applied once Reflector activity is completed
    curation: Curation | None = Field(None, description="Output from the curator activity.") # Will be applied once Curator activity is completed


###
# Key models for LLM generation
###

class BulletTag(BaseModel):
    """A bullet to be tagged with an adjective corresponding to its influence on the outcome."""
    id: str = Field(description="The bullet id to be tagged")
    tag: Literal['harmful','helpful','neutral'] = Field(description="How this bullet should be tagged based on its influence on the trajectory")

class Reflection(BaseModel): # used to guide the reflection llm structured output
    """Reflection on the run based on the provided information comprised of the trajectory, retrieved_playbook, optional evaluation, and optional ground truth."""
    reasoning: str = Field(description="Your chain of thought / reasoning / thinking process, detailed analysis and calculations")
    error_identification: str = Field(description="What specifically went wrong in the reasoning?")
    root_cause_analysis: str = Field(description="Why did this error occur? What concept was misunderstood?")
    correct_approach: str = Field(description="Why did this error occur? What concept was misunderstood?")
    key_insight: str = Field(description="What strategy, formula, or principle should be remembered to avoid this error?]")
    bullet_tags: list[BulletTag] = Field(description="List of bullets tagged as helpful, harmful, or neutral.")


class Operation(BaseModel):
    type: Literal["ADD","UPDATE","TAG","REMOVE"] = Field(description="The type of operation to be performed.")

class AddOperation(Operation):
    """Add a new bullet."""
    type: Literal["ADD"] = Field("ADD",description="The type of operation to be performed.")
    content: str = Field(description="The content of the bullet to add.")

class UpdateOperation(Operation): # modified_at and content will be updated
    """Update an existing bullet if the alternative is to add a redundant bullet. The update should be small but carryimportant new information but not too much othewise a new bullet should be made."""
    type: Literal["UPDATE"] = Field("ADD",description="The type of operation to be performed.")
    bullet_id: str = Field(description="The id of the bullet to be updated")
    content: str = Field(description="The new content to replace the the existing bullet content. This should not be too different from the original.")

class TagOperation(Operation):
    """Tag a bullet based on the outcome of the run."""
    type: Literal["TAG"] = Field("TAG",description="The type of operation to be performed.")
    bullet_id: str = Field(description="The id of the bullet to tag.")
    tag: Literal["helpful","harmful","neutral"] = Field(description="The tag to associate with this annotated bullet.")

class RemoveOperation(Operation):
    """Remove a bullet."""
    type: Literal["REMOVE"] = Field("REMOVE",description="The type of operation to be performed.")
    bullet_id: str = Field(description="The id of the bullet to remove.")

OperationUnion = AddOperation | UpdateOperation | TagOperation | RemoveOperation

class Curation(BaseModel): # used to guide the curator llm structured output
    """Curation of the playbook through a batch update as needed."""
    reasoning: str = Field(description="Your chain of thought / reasoning / thinking process, detailed analysis of changes and additions to be made and why.")
    operations: list[OperationUnion] = Field(description="List of operations to be performed, should only perform meaningful needed operations no more no less.")


###
# Temporal data structures (inputs and outputs)
###

# learn_workflow
class LearnWorkflowInput(BaseModel):
    """Input for learn_workflow workflow."""
    playbook_id: str = Field(..., description="The id of the playbook to be used.")
    user_message: str = Field(..., description="Complete initial message passed to the agent.")
    retrieved_playbook: str = Field(..., description="Playbook retrieved to supplement the initial prompt with context.")
    trajectory: str = Field(..., description="The complete trajectory of the agent's run.")
    ground_truth: str | None = Field(None, description="Ground truth expectation of the run.")
    evaluation: str | None = Field(None, description="Evaluation of the run may include any of execution feedback, custom evaluations, unit tests and more.")
    reflector_additional_instructions: str | None = Field(None, description="Instructions to add to the curator.")
    curator_additional_instructions: str | None = Field(None, description="Instructions to add to the curator.")
    # global_playbook will be retrieved within workflow (inside the curator specifically)
    # when curation is applied it will leverage a batch update to the playbook in db

class LearnWorkflowOutput(BaseModel):
    """Output for learn_workflow workflow."""
    learn_job: LearnJob = Field(..., description="The job tracking the progress of the workflow.") # will be completed by the time the workflow is completed

# reflector activity
class ReflectorInput(BaseModel):
    """Inputs to reflector activity"""
    playbook_id: str = Field(..., description="The id of the playbook to be used.")
    trajectory: str = Field(..., description="Complete trajectory of the run.")
    ground_truth: str | None = Field(None, description="Ground truth expectation of the run.")
    evaluation: str | None = Field(None, description="Evaluation of the run may include any of execution feedback, custom evaluations, unit tests and more.")
    reflector_additional_instructions: str | None = Field(None, description="Instructions to add to the reflector.")

class ReflectorOutput(BaseModel):
    """Output from the reflector activity."""
    reflection: Reflection = Field(..., description="The production of the reflector.")

# curator activity
class CuratorInput(BaseModel):
    """Input into the curator activity"""
    user_message: str = Field(..., description="Complete initial message passed to the agent.")
    global_playbook: str = Field(..., description="Complete playbook for the target prompt.")
    trajectory: str = Field(..., description="The complete trajectory of the agent's run.")
    reflection: Reflection = Field(..., description="The production of the reflector.")
    curator_additional_instructions: str | None = Field(None, description="Instructions to add to the curator.")

class CuratorOutput(BaseModel):
    """Output from the curator activity."""
    curation: Curation = Field(..., description="The production of the curator.")


# apply_curation activity
class ApplyCurationInput(BaseModel):
    """Input into the apply_curation activity"""
    curation: Curation = Field(..., description="Curation to apply.")

class ApplyCurationOutput(BaseModel):
    """Output from the apply_curation activity."""
    status: Literal["success","failure"] = Field(..., description="Status of Operations")
    error: str | None = Field(None, description="Error message if the operation failed.")


###
# API
###
# Conventions:
# - All endpoints are versionless here for clarity, but you'd likely mount under /v1.
# - {playbook_id} always refers to a valid Playbook row.
# - These models shape FastAPI request/response bodies.
# - Comments note main consumer:
#     - "internal"  = our GUI / operator console
#     - "client"    = the user's agent runtime
#     - "both"      = both sides will realistically call this
#
# NOTE ON PATCH LOGIC:
#   You asked to expose PATCH-like behaviors as separate endpoints:
#       /content
#       /increment_helpful
#       /increment_harmful
#       /increment_neutral
#   We reflect that in the API models below.

# 0. Embedded prompt

class EmbeddedPromptInput(BaseModel):
    """Request model for GET /embed_prompt.
    Used by: client (agent runtime) BEFORE it calls its LLM.
    Embeds user prompt into generator template."""
    prompt: str = Field(..., description="The prompt to be embedded.")

class EmbeddedPromptOutput(BaseModel):
    """Response model for GET /embed_prompt.
    Returns the embedded prompt."""
    prompt: str = Field(..., description="The embedded prompt.")

# 1. Playbook Management / Introspection

class ListPlaybooksResponse(BaseModel):
    """Response model for GET /playbooks.
    Used by: internal (browse all playbooks) and client (if multiple prompts/agents exist)."""
    playbooks: list[Playbook] = Field(
        ..., description="All registered playbooks visible to this caller."
    )


class CreatePlaybookRequest(BaseModel):
    """Request model for POST /playbooks.
    Used by: internal (bootstrapping a new agent domain)."""
    name: str = Field(..., description="Human-readable name of the playbook.")
    description: str | None = Field(
        None,
        description="Optional description of this playbook's purpose/scope."
    )

class CreatePlaybookResponse(BaseModel):
    """Response model for POST /playbooks."""
    playbook: Playbook = Field(
        ..., description="The created playbook record."
    )


class GetPlaybookResponse(BaseModel):
    """Response model for GET /playbooks/{playbook_id}.
    Used by: both (metadata panels, sanity checks)."""
    playbook: Playbook = Field(
        ..., description="The requested playbook, including timestamps and metadata."
    )


# 2. Bullet Management / Introspection / Manual Edits

class ListBulletsResponse(BaseModel):
    """Response model for GET /playbooks/{playbook_id}/bullets.
    Used by: internal (visualize full evolving playbook), sometimes client (debug)."""
    bullets: list[Bullet] = Field(
        ..., description="All bullets under this playbook."
    )


class CreateBulletRequest(BaseModel):
    """Request model for POST /playbooks/{playbook_id}/bullets.
    Used by: internal (manual seeding / human expert input).
    NOTE: metadata counts always start at 0; user can't set them here."""
    content: str = Field(
        ..., description="The text content of the new bullet (guidance, heuristic, principle, rule, etc.)."
    )

class CreateBulletResponse(BaseModel):
    """Response model for POST /playbooks/{playbook_id}/bullets."""
    bullet: Bullet = Field(
        ..., description="The newly created bullet with assigned id and zeroed counts."
    )


# PATCH /playbooks/{playbook_id}/bullets/{bullet_id}/content
class UpdateBulletContentRequest(BaseModel):
    """Request to update ONLY the bullet content.
    Used by: internal (surgical fix to wording).
    This should remain semantically close to the original, not a totally new rule."""
    content: str = Field(
        ..., description="Replacement content for the bullet."
    )

class UpdateBulletContentResponse(BaseModel):
    """Response after updating bullet content."""
    bullet: Bullet = Field(
        ..., description="Bullet after content update, with modified_at bumped."
    )


# POST /playbooks/{playbook_id}/bullets/{bullet_id}/increment_helpful
class IncrementHelpfulResponse(BaseModel):
    """Response after incrementing helpful_count.
    Used by: internal (operator dashboards), and by learn_workflow when applying TAG 'helpful'."""
    bullet: Bullet = Field(
        ..., description="Bullet after helpful_count increment."
    )

# POST /playbooks/{playbook_id}/bullets/{bullet_id}/increment_harmful
class IncrementHarmfulResponse(BaseModel):
    """Response after incrementing harmful_count.
    Used by: internal and learn_workflow when applying TAG 'harmful'."""
    bullet: Bullet = Field(
        ..., description="Bullet after harmful_count increment."
    )

# POST /playbooks/{playbook_id}/bullets/{bullet_id}/increment_neutral
class IncrementNeutralResponse(BaseModel):
    """Response after incrementing neutral_count.
    Used by: internal and learn_workflow when applying TAG 'neutral'."""
    bullet: Bullet = Field(
        ..., description="Bullet after neutral_count increment."
    )


# 3. Retrieval for Generation (pre-run, used by the agent runtime)

class RetrieveBulletsRequest(BaseModel):
    """Request model for POST /playbooks/{playbook_id}/retrieve.
    Used by: client (agent runtime) BEFORE it calls its LLM.
    We use this to build the 'retrieved_playbook' subset for prompting."""
    user_message: str = Field(
        ..., description="The task or question the agent is about to solve."
    )
    k: int = Field(
        20,
        description="Max number of bullets to retrieve for this task. The server will rank/filter from this playbook."
    )

class RetrieveBulletsResponse(BaseModel):
    """Response model for POST /playbooks/{playbook_id}/retrieve.
    Used by: client. This is what gets injected into the agent's prompt as guidance."""
    retrieved_bullets: list[Bullet] = Field(
        ..., description="Subset of bullets (active context) ranked as most relevant to this user_message."
    )


# 4. Learning Workflow (Reflector -> Curator -> ApplyCuration) via Temporal
#
# We support:
#   POST /playbooks/{playbook_id}/episodes/learn       (start job, returns learn_job_id)
#   GET  /playbooks/{playbook_id}/episodes/learn/{job} (poll job, returns LearnJob)
#
# The workflow will:
# - run the reflector,
# - run the curator,
# - optionally apply curation if `apply_curation=True`,
# - and store status + reflection + curation in a LearnJob row/state
#   that we can return.


class StartLearnRequest(BaseModel):
    """Request model for POST /playbooks/{playbook_id}/episodes/learn.
    Used by: client (agent runtime) AFTER it finishes a run.
    This launches learn_workflow asynchronously in Temporal."""
    user_message: str = Field(
        ..., description="Original user instruction that kicked off this agent run."
    )
    retrieved_playbook: str = Field(
        ..., description="The exact playbook context (bullets) you gave the agent at generation time, serialized as text or JSON. \
                          Stored so reflector can attribute helpful/harmful. This must match what conditioned the model."
    )
    trajectory: str = Field(
        ..., description="Full reasoning trace / tool calls / code / outputs from the run."
    )
    ground_truth: str | None = Field(
        None,
        description="If you know the correct final answer / canonical solution for this run, include it. Otherwise leave null."
    )
    evaluation: str | None = Field(
        None,
        description="Execution feedback such as unit test results, runtime errors, grader output, etc."
    )
    reflector_additional_instructions: str | None = Field(
        None,
        description="Optional tweaks or domain-specific guidance to inject into reflector prompt for this episode only."
    )
    curator_additional_instructions: str | None = Field(
        None,
        description="Optional tweaks or domain-specific guidance to inject into curator prompt for this episode only."
    )

class StartLearnResponse(BaseModel):
    """Response model for POST /playbooks/{playbook_id}/episodes/learn.
    Used by: client.
    We immediately return a learn_job_id (Temporal workflow id / tracking id)."""
    learn_job_id: str = Field(
        ..., description="Identifier of the launched learn_workflow job. \
                          Poll this via GET /playbooks/{playbook_id}/episodes/learn/{learn_job_id}."
    )


class GetLearnJobResponse(BaseModel):
    """Response model for GET /playbooks/{playbook_id}/episodes/learn/{learn_job_id}.
    Used by: client (polling) and internal (debugging).
    Represents the current state of the learn_workflow."""
    learn_job: LearnJob = Field(
        ...,
        description="Learn job status including reflection/curation if available, \
                     and any error if the workflow failed."
    )
```


## Principles
-
- The FastAPI server must be strongly documented to enable agent assisted integration of the service.
- A claude plugin will be provided to educate the agent copilot on ACE and how it should be integrated into the user's codebase.
    - This plugin will consist of a SKILL that will retrieve the openapi specification of the ACE service and use it to generate code for the user's codebase.



## Side Notes
### Commentary and Interpretation on the ACE Framework (strongly influenced implementation)
    - Exploring https://github.com/kayba-ai/agentic-context-engine
        - Provided prompts are not used
        - Designed for offline
        - Using pip instead of uv
        - Intermediate validation step in between generator and reflector?
    - What are the limitations on LLM execution aka the generator, is it opinionated or does it just need to collect the execution?
    - Is the Generator appears to be dependent on ground truth?
        - The prompt is
        - But supposedly can still improve without ground truth
    - Requires feedback from the environment to improve
    - Had to significantly touch up the prompt to generalize it to other domains
    - Decided to replace `playbook` in reflector to clarify the "playbook" being passed
    - So inconsistent between its pillars of Generator, Reflector, and Curator (cry emoji)
    - not sure if the provided playbook to the generator is the full playbook or just a subset of it
    - removed few shot examples from the prompt as I dont trust them
    - section from curator ADD operation is removed as it will be added programmatically

## Future Work
- [ ] Build an SDK to abstract the interactions with the ACE service at the client side
