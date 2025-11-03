"""Temporal worker for running workflows and activities."""

import asyncio
import os
from dotenv import load_dotenv
from temporalio.client import Client
from temporalio.worker import Worker

from app.temporal.workflows import LearnWorkflow
from app.temporal.activities import (
    reflector_activity,
    curator_activity,
    apply_curation_activity,
    retrieve_global_playbook_activity,
    update_learn_job_activity,
)

# Load environment variables
load_dotenv()


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
    try:
        await worker.run()
    except (KeyboardInterrupt, asyncio.CancelledError):
        # Expected during graceful shutdown (e.g., when watchdog restarts)
        print("Worker shutting down gracefully...")
        raise
    except Exception as e:
        print(f"Worker error: {e}")
        raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        # Suppress expected cancellation errors during restart
        pass
