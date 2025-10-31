"""Temporal worker for running workflows and activities."""
import asyncio
import os
from dotenv import load_dotenv
from temporalio.client import Client
from temporalio.worker import Worker

# Load environment variables
load_dotenv()

from temporal_workflows import LearnWorkflow
from temporal_activities import (
    reflector_activity,
    curator_activity,
    apply_curation_activity,
    retrieve_global_playbook_activity,
    update_learn_job_activity,
)


async def main():
    """Run the Temporal worker."""
    # Connect to Temporal server
    client = await Client.connect(
        os.getenv("TEMPORAL_ADDRESS", "localhost:7233"),
        namespace=os.getenv("TEMPORAL_NAMESPACE", "default"),
    )
    
    # Create and run worker
    worker = Worker(
        client,
        task_queue="ace-task-queue",
        workflows=[LearnWorkflow],
        activities=[
            reflector_activity,
            curator_activity,
            apply_curation_activity,
            retrieve_global_playbook_activity,
            update_learn_job_activity,
        ],
    )
    
    print("Temporal worker started. Waiting for workflows...")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())

