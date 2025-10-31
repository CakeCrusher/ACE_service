"""Temporal activities for the ACE service."""
import os
import json
from dotenv import load_dotenv

from jinja2 import Environment, FileSystemLoader
from openai import OpenAI
from temporalio import activity

# Load environment variables
load_dotenv()

from schemas import (
    ReflectorInput,
    ReflectorOutput,
    CuratorInput,
    CuratorOutput,
    ApplyCurationInput,
    ApplyCurationOutput,
    Reflection,
    Curation,
    AddOperation,
    UpdateOperation,
    TagOperation,
    RemoveOperation,
)
from database import SessionLocal, get_db
from models import BulletModel, LearnJobModel
from schemas import BulletMetadata


# OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Jinja2 environment
env = Environment(loader=FileSystemLoader("prompts"))


@activity.defn
async def reflector_activity(reflector_input: ReflectorInput) -> ReflectorOutput:
    """Reflector activity that analyzes a run and produces a reflection."""
    
    # Load the reflector template
    template = env.get_template("reflector.j2")
    
    # Format retrieved_playbook if it's not already formatted
    # It should be a string, either formatted bullets or JSON
    retrieved_playbook_text = reflector_input.retrieved_playbook
    
    # Prepare template context
    template_context = {
        "ground_truth": reflector_input.ground_truth or "",
        "evaluation": reflector_input.evaluation or "",
        "retrieved_playbook": retrieved_playbook_text,
        "trajectory": reflector_input.trajectory,
        "reflector_additional_instructions": reflector_input.reflector_additional_instructions or "",
    }
    
    # Render the prompt
    prompt = template.render(**template_context)
    
    # Call OpenAI with structured output
    completion = client.chat.completions.create(
        model="gpt-4o-2024-08-06",
        messages=[
            {"role": "user", "content": prompt},
        ],
        response_format=Reflection,
        temperature=0.7,
    )
    
    message = completion.choices[0].message
    
    if message.refusal:
        raise ValueError(f"Model refused to respond: {message.refusal}")
    
    reflection = message.parsed
    
    return ReflectorOutput(reflection=reflection)


@activity.defn
async def curator_activity(curator_input: CuratorInput) -> CuratorOutput:
    """Curator activity that determines what changes to make to the playbook."""
    reflection = curator_input.reflection
    
    # Load the curator template
    template = env.get_template("curator.j2")
    
    # Serialize reflection for template - format as readable text
    reflection_dict = reflection.model_dump()
    reflection_text = f"""
Reasoning: {reflection_dict.get('reasoning', '')}
Error Identification: {reflection_dict.get('error_identification', '')}
Root Cause Analysis: {reflection_dict.get('root_cause_analysis', '')}
Correct Approach: {reflection_dict.get('correct_approach', '')}
Key Insight: {reflection_dict.get('key_insight', '')}
Bullet Tags: {json.dumps(reflection_dict.get('bullet_tags', []), indent=2)}
"""
    
    # Prepare template context
    template_context = {
        "user_message": curator_input.user_message,
        "global_playbook": curator_input.global_playbook,
        "trajectory": curator_input.trajectory,
        "reflection": reflection_text,
        "curator_additional_instructions": curator_input.curator_additional_instructions or "",
    }
    
    # Render the prompt
    prompt = template.render(**template_context)
    
    # Call OpenAI with structured output
    completion = client.chat.completions.create(
        model="gpt-4o-2024-08-06",
        messages=[
            {"role": "user", "content": prompt},
        ],
        response_format=Curation,
        temperature=0.7,
    )
    
    message = completion.choices[0].message
    
    if message.refusal:
        raise ValueError(f"Model refused to respond: {message.refusal}")
    
    curation = message.parsed
    
    return CuratorOutput(curation=curation)


@activity.defn
async def apply_curation_activity(apply_input: ApplyCurationInput) -> ApplyCurationOutput:
    """Apply curation activity that executes operations on the playbook."""
    curation = apply_input.curation
    playbook_id = apply_input.playbook_id
    
    db = SessionLocal()
    
    try:
        for operation in curation.operations:
            if isinstance(operation, AddOperation):
                # Add new bullet
                new_bullet = BulletModel(
                    playbook_id=playbook_id,
                    content=operation.content,
                    metadata=json.dumps({"helpful_count": 0, "harmful_count": 0, "neutral_count": 0}),
                )
                db.add(new_bullet)
                
            elif isinstance(operation, UpdateOperation):
                # Update existing bullet
                bullet = db.query(BulletModel).filter(BulletModel.id == operation.bullet_id).first()
                if not bullet:
                    raise ValueError(f"Bullet {operation.bullet_id} not found")
                bullet.content = operation.content
                
            elif isinstance(operation, TagOperation):
                # Tag a bullet (increment metadata counters)
                bullet = db.query(BulletModel).filter(BulletModel.id == operation.bullet_id).first()
                if not bullet:
                    raise ValueError(f"Bullet {operation.bullet_id} not found")
                
                # Parse existing metadata
                metadata_dict = json.loads(bullet.metadata) if isinstance(bullet.metadata, str) else bullet.metadata
                metadata = BulletMetadata(**metadata_dict)
                
                # Increment appropriate counter
                if operation.tag == "helpful":
                    metadata.helpful_count += 1
                elif operation.tag == "harmful":
                    metadata.harmful_count += 1
                elif operation.tag == "neutral":
                    metadata.neutral_count += 1
                
                # Update metadata
                bullet.metadata = json.dumps(metadata.model_dump())
                
            elif isinstance(operation, RemoveOperation):
                # Remove bullet
                bullet = db.query(BulletModel).filter(BulletModel.id == operation.bullet_id).first()
                if not bullet:
                    raise ValueError(f"Bullet {operation.bullet_id} not found")
                db.delete(bullet)
        
        db.commit()
        
        return ApplyCurationOutput(status="success")
        
    except Exception as e:
        db.rollback()
        return ApplyCurationOutput(status="failure", error=str(e))
    finally:
        db.close()


@activity.defn
async def retrieve_global_playbook_activity(playbook_id: str) -> str:
    """Retrieve all bullets from a playbook and serialize them."""
    db = SessionLocal()
    try:
        bullets = db.query(BulletModel).filter(BulletModel.playbook_id == playbook_id).all()
        
        # Format bullets for playbook context
        bullet_texts = []
        for bullet in bullets:
            metadata = json.loads(bullet.metadata) if isinstance(bullet.metadata, str) else bullet.metadata
            bullet_texts.append(f"[{bullet.id}] helpful={metadata.get('helpful_count', 0)} harmful={metadata.get('harmful_count', 0)} :: {bullet.content}")
        
        return "\n".join(bullet_texts)
    finally:
        db.close()


@activity.defn
async def update_learn_job_activity(job_data: dict[str, Any]) -> None:
    """Update a learn job in the database."""
    db = SessionLocal()
    try:
        job_id = job_data["id"]
        job = db.query(LearnJobModel).filter(LearnJobModel.id == job_id).first()
        
        if job:
            if "status" in job_data:
                job.status = job_data["status"]
            if "error" in job_data:
                job.error = job_data.get("error")
            if "reflection" in job_data:
                job.reflection = json.dumps(job_data["reflection"]) if job_data["reflection"] else None
            if "curation" in job_data:
                job.curation = json.dumps(job_data["curation"]) if job_data["curation"] else None
            
            db.commit()
    finally:
        db.close()

