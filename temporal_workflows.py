"""Temporal workflows for the ACE service."""
import json
from temporalio import workflow

from temporal_activities import (
    reflector_activity,
    curator_activity,
    apply_curation_activity,
    retrieve_global_playbook_activity,
    update_learn_job_activity,
)
from schemas import LearnWorkflowInput, Reflection, Curation


@workflow.defn
class LearnWorkflow:
    """Workflow that orchestrates the learning process: Reflect -> Curate -> Apply."""
    
    @workflow.run
    async def run(self, input_data: dict) -> dict:
        """Execute the learn workflow."""
        # Extract learn_job_id from input if provided, otherwise generate one
        learn_job_id = input_data.get("learn_job_id", input_data["playbook_id"])
        workflow_input = LearnWorkflowInput(**input_data)
        
        try:
            # Update job status to running
            await workflow.execute_activity(
                update_learn_job_activity,
                {
                    "id": learn_job_id,
                    "status": "running",
                },
                start_to_close_timeout=30,
            )
            
            # Step 1: Run reflector activity
            from schemas import ReflectorInput
            
            reflector_input = ReflectorInput(
                playbook_id=workflow_input.playbook_id,
                retrieved_playbook=workflow_input.retrieved_playbook,
                trajectory=workflow_input.trajectory,
                ground_truth=workflow_input.ground_truth,
                evaluation=workflow_input.evaluation,
                reflector_additional_instructions=workflow_input.reflector_additional_instructions,
            )
            
            reflector_output = await workflow.execute_activity(
                reflector_activity,
                reflector_input,
                start_to_close_timeout=300,  # 5 minutes for LLM call
            )
            
            reflection = reflector_output.reflection
            
            # Update job with reflection
            await workflow.execute_activity(
                update_learn_job_activity,
                {
                    "id": learn_job_id,
                    "reflection": reflection.model_dump(mode="json"),
                },
                start_to_close_timeout=30,
            )
            
            # Step 2: Retrieve global playbook
            global_playbook = await workflow.execute_activity(
                retrieve_global_playbook_activity,
                workflow_input.playbook_id,
                start_to_close_timeout=30,
            )
            
            # Step 3: Run curator activity
            from schemas import CuratorInput
            
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
                start_to_close_timeout=300,  # 5 minutes for LLM call
            )
            
            curation = curator_output.curation
            
            # Update job with curation
            await workflow.execute_activity(
                update_learn_job_activity,
                {
                    "id": learn_job_id,
                    "curation": curation.model_dump(mode="json"),
                },
                start_to_close_timeout=30,
            )
            
            # Step 4: Apply curation
            from schemas import ApplyCurationInput
            
            apply_input = ApplyCurationInput(
                playbook_id=workflow_input.playbook_id,
                curation=curation,
            )
            
            apply_output = await workflow.execute_activity(
                apply_curation_activity,
                apply_input,
                start_to_close_timeout=60,  # 1 minute for DB operations
            )
            
            if apply_output.status == "failure":
                # Update job status to failed
                await workflow.execute_activity(
                    update_learn_job_activity,
                    {
                        "id": learn_job_id,
                        "status": "failed",
                        "error": apply_output.error or "Unknown error applying curation",
                    },
                    start_to_close_timeout=30,
                )
                raise Exception(f"Failed to apply curation: {apply_output.error}")
            
            # Update job status to completed
            await workflow.execute_activity(
                update_learn_job_activity,
                {
                    "id": learn_job_id,
                    "status": "completed",
                },
                start_to_close_timeout=30,
            )
            
            # Return the final job state
            from schemas import LearnJob
            learn_job = LearnJob(
                id=learn_job_id,
                playbook_id=workflow_input.playbook_id,
                status="completed",
                error=None,
                reflection=reflection,
                curation=curation,
            )
            
            return {"learn_job": learn_job.model_dump(mode="json")}
            
        except Exception as e:
            # Update job status to failed
            await workflow.execute_activity(
                update_learn_job_activity,
                {
                    "id": learn_job_id,
                    "status": "failed",
                    "error": str(e),
                },
                start_to_close_timeout=30,
            )
            raise

