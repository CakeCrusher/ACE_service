"""Temporal workflows for the ACE service."""

from datetime import timedelta
from temporalio import workflow

# Import activities inside unsafe context to bypass workflow sandbox restrictions
# This is needed because activities import OpenAI client which has restricted dependencies
with workflow.unsafe.imports_passed_through():
    from app.temporal.activities import (
        reflector_activity,
        curator_activity,
        apply_curation_activity,
        retrieve_global_playbook_activity,
        update_learn_job_activity,
    )

from app.schemas import (
    LearnWorkflowInput,
    LearnWorkflowOutput,
    Reflection,
    UpdateLearnJobInput,
    Curation,
)


def reconstruct_pydantic_model(model_class: type, value: any):
    """
    Reconstruct a Pydantic model after Temporal serialization.

    Temporal deserializes Pydantic models in a way that can cause validation
    issues when used in other Pydantic models. This ensures we get a fresh,
    properly validated instance.
    """
    if isinstance(value, dict):
        return model_class.model_validate(value)
    elif hasattr(value, "model_dump"):
        return model_class.model_validate(value.model_dump(mode="python"))
    else:
        # Already the right type, but reconstruct anyway to ensure validation
        return model_class.model_validate(
            value.model_dump(mode="python") if hasattr(value, "model_dump") else value
        )


def extract_playbook_from_trajectory(trajectory: str) -> str:
    """
    Extract playbook content from trajectory between PLAYBOOK_BEGIN and PLAYBOOK_END markers.

    The markers are in the format: **PLAYBOOK_BEGIN** ... **PLAYBOOK_END**
    Returns the content between the markers, or "(None)" if not found.
    """
    begin_marker = "**PLAYBOOK_BEGIN**"
    end_marker = "**PLAYBOOK_END**"

    begin_idx = trajectory.find(begin_marker)
    if begin_idx == -1:
        return "(None)"

    # Move past the marker
    begin_idx += len(begin_marker)

    end_idx = trajectory.find(end_marker, begin_idx)
    if end_idx == -1:
        return "(None)"

    # Extract content and strip whitespace
    playbook_content = trajectory[begin_idx:end_idx].strip()
    return playbook_content if playbook_content else "(None)"


@workflow.defn
class LearnWorkflow:
    """Workflow that orchestrates the learning process: Reflect -> Curate -> Apply."""

    @workflow.run
    async def run(self, input_data: LearnWorkflowInput) -> LearnWorkflowOutput:
        """Execute the learn workflow."""
        # Extract learn_job_id from input if provided, otherwise use playbook_id
        learn_job_id = input_data.learn_job_id or input_data.playbook_id
        workflow_input = input_data

        # Extract retrieved_playbook from trajectory (always extracted, never provided by user)
        retrieved_playbook = extract_playbook_from_trajectory(workflow_input.trajectory)

        try:
            # Update job status to running
            await workflow.execute_activity(
                update_learn_job_activity,
                UpdateLearnJobInput(
                    id=learn_job_id,
                    status="running",
                ),
                start_to_close_timeout=timedelta(seconds=30),
            )

            # Step 1: Run reflector activity
            from app.schemas import ReflectorInput

            reflector_input = ReflectorInput(
                playbook_id=workflow_input.playbook_id,
                retrieved_playbook=retrieved_playbook,
                trajectory=workflow_input.trajectory,
                ground_truth=workflow_input.ground_truth,
                evaluation=workflow_input.evaluation,
                reflector_additional_instructions=workflow_input.reflector_additional_instructions,
            )

            reflector_output = await workflow.execute_activity(
                reflector_activity,
                reflector_input,
                start_to_close_timeout=timedelta(seconds=300),  # 5 minutes for LLM call
            )

            # Reconstruct Reflection after Temporal serialization
            reflection = reconstruct_pydantic_model(
                Reflection, reflector_output.reflection
            )

            # Update job with reflection
            await workflow.execute_activity(
                update_learn_job_activity,
                UpdateLearnJobInput(
                    id=learn_job_id,
                    reflection=reflection,
                ),
                start_to_close_timeout=timedelta(seconds=30),
            )

            # Step 2: Retrieve global playbook
            global_playbook = await workflow.execute_activity(
                retrieve_global_playbook_activity,
                workflow_input.playbook_id,
                start_to_close_timeout=timedelta(seconds=30),
            )

            # Step 3: Run curator activity
            from app.schemas import CuratorInput

            curator_input = CuratorInput(
                playbook_id=workflow_input.playbook_id,
                user_message=workflow_input.user_message,
                global_playbook=global_playbook,
                trajectory=workflow_input.trajectory,
                reflection=reflection,
                curator_additional_instructions=workflow_input.curator_additional_instructions,
            )

            curator_output = await workflow.execute_activity(
                curator_activity,
                curator_input,
                start_to_close_timeout=timedelta(seconds=300),  # 5 minutes for LLM call
            )

            # Reconstruct Curation after Temporal serialization
            curation = reconstruct_pydantic_model(Curation, curator_output.curation)

            # Update job with curation
            await workflow.execute_activity(
                update_learn_job_activity,
                UpdateLearnJobInput(
                    id=learn_job_id,
                    curation=curation,
                ),
                start_to_close_timeout=timedelta(seconds=30),
            )

            # Step 4: Apply curation
            from app.schemas import ApplyCurationInput

            apply_input = ApplyCurationInput(
                playbook_id=workflow_input.playbook_id,
                curation=curation,
            )

            apply_output = await workflow.execute_activity(
                apply_curation_activity,
                apply_input,
                start_to_close_timeout=timedelta(
                    seconds=60
                ),  # 1 minute for DB operations
            )

            if apply_output.status == "failure":
                # Update job status to failed
                await workflow.execute_activity(
                    update_learn_job_activity,
                    UpdateLearnJobInput(
                        id=learn_job_id,
                        status="failed",
                        error=apply_output.error or "Unknown error applying curation",
                    ),
                    start_to_close_timeout=timedelta(seconds=30),
                )
                raise Exception(f"Failed to apply curation: {apply_output.error}")

            # Update job status to completed
            await workflow.execute_activity(
                update_learn_job_activity,
                UpdateLearnJobInput(
                    id=learn_job_id,
                    status="completed",
                ),
                start_to_close_timeout=timedelta(seconds=30),
            )

            # Return the final job state
            from app.schemas import LearnJob

            learn_job = LearnJob(
                id=learn_job_id,
                playbook_id=workflow_input.playbook_id,
                status="completed",
                error=None,
                reflection=reflection,
                curation=curation,
            )

            return LearnWorkflowOutput(learn_job=learn_job)

        except Exception as e:
            # Update job status to failed
            await workflow.execute_activity(
                update_learn_job_activity,
                UpdateLearnJobInput(
                    id=learn_job_id,
                    status="failed",
                    error=str(e),
                ),
                start_to_close_timeout=timedelta(seconds=30),
            )
            raise
