
# ACE Service Integration Skill

## Overview

The ACE (Adaptive Context Enhancement) service enables agents to learn from each execution and continuously improve by maintaining a playbook of proven strategies, common mistakes, and effective solutions. This skill guides implementation of ACE into your existing agent infrastructure.

**Goal**: Implement the simplest possible integration into this repository that enables continuous learning.

- The changes should be simple edits into the existing codebase, try not to add new files or modules just keep the edits minimal and inline with the existing codebase.
- There is no ACE api key and the default endpoint will be http://0.0.0.0:8000/ .
- Dont add additional conditions or constants or environment variables to the code literally only apply the two endpoints where they correspond assume that the developer just wants ace integrated in the minimal amount of code possible.
- Add the embed prompt not to the user message but to the system message or instruction for the agent or llm call.

## Essential Workflow

ACE operates in two phases:

1. **Before Inference**: Enrich the prompt with learned context from previous runs
2. **After Execution**: Submit the run trajectory for analysis (runs asynchronously in background)

## Essential Endpoints

### 1. Embed Prompt (Before Inference) - REQUIRED

**Endpoint**: `POST /playbooks/{playbook_id}/embed_prompt`

**When**: Immediately before sending the prompt to your LLM provider

**Request**:
```json
{
  "prompt": "Your final user prompt",
  "k": 20
}
```

**Response**:
```json
{
  "prompt": "Your prompt with embedded playbook context"
}
```

**Implementation**:
- Call this endpoint as the final step before sending to inference
- The enriched prompt includes bullets wrapped in `**PLAYBOOK_BEGIN**` and `**PLAYBOOK_END**` markers
- **Use the same `playbook_id` for both `embed_prompt` and `start_learn`** so the learn workflow can extract the context that was used

**Note**: The playbook is created automatically if it doesn't exist. You don't need to create or manage playbooks - just use a consistent `playbook_id`.

### 2. Start Learn (After Execution) - REQUIRED

**Endpoint**: `POST /playbooks/{playbook_id}/episodes/learn`

**When**: After the agent run completes (successful or failed)

**Purpose**: Submit the complete trajectory for analysis. This runs asynchronously in the background and will eventually improve subsequent prompts.

**Request**:
```json
{
  "user_message": "The enriched prompt that was sent to the LLM",
  "trajectory": "Complete execution trace from start to finish"
}
```

**Minimal Required Fields**:
- `user_message` (required): The enriched prompt that was sent to inference
- `trajectory` (required): Complete execution trace including the original input (with PLAYBOOK_BEGIN/PLAYBOOK_END markers), all reasoning, tool calls, code execution, outputs, errors, and final result

**Response**:
```json
{
  "learn_job_id": "uuid-of-the-background-job"
}
```

**Implementation**:
- Collect `user_message` and `trajectory` during agent execution
- Call `start_learn` after the run completes
- **You do NOT need to poll for job status** - it runs in background and will automatically improve future prompts when ready
- The next run may not immediately benefit if the analysis is still running, but subsequent runs will benefit once analysis completes

## StartLearnRequest: Essential vs Optional

### Essential Fields (Must Provide)

#### `user_message` (required)

**What**: The enriched prompt that was sent to your LLM provider

**Content**: This is the output from `embed_prompt` - the prompt with embedded playbook context that was actually sent for inference.

**Why essential**: This is the exact prompt the agent received, which is needed for accurate reflection analysis.

#### `trajectory` (required)

**What**: Complete execution trace from start to finish

**Content**: Include everything that occurred during the run:
- The original input (preserve the `**PLAYBOOK_BEGIN**` and `**PLAYBOOK_END**` markers so ACE can extract what context was used)
- All reasoning traces and internal thought processes
- Tool calls, function invocations, API calls
- Code that was executed (if applicable)
- Intermediate outputs and results
- Exceptions, error messages, and stack traces (if any occurred)
- The final output or conclusion

**Format**: There is no necessary format for the trajectory - it can be any string that is useful for the reflector and curator to analyze the run. However, preserving the PLAYBOOK_BEGIN/PLAYBOOK_END markers from the initial input is helpful.

**Why essential**: This is the complete execution record needed for learning.

### Optional Fields (Only Provide If Available)

**Important**: Do NOT try to generate or create these fields. Only include them if:
1. Your codebase already produces them, OR
2. The user explicitly states they have access to them

If these are not readily available, **simply omit them**. ACE works effectively with just `user_message` and `trajectory`.

#### `ground_truth` (optional)

**When to include**: Only if your system has a known correct answer or reference implementation for this specific run

**What it is**: The canonical or correct solution - what the trajectory should have been

**Examples of when you might have it**:
- You have unit tests with expected outputs
- You have reference implementations
- You have a human-provided correct answer
- You have validation datasets with ground truth labels

**Do NOT include if**:
- You would need to generate it manually
- You would need to create test cases
- It's not readily available in your existing workflow

#### `evaluation` (optional)

**When to include**: Only if your system automatically produces execution feedback

**What it is**: Any evaluation mechanism that provides feedback about run effectiveness

**Examples of when you might have it**:
- Unit tests automatically run and produce pass/fail results
- Your system has built-in judge/evaluator outputs
- You have automated performance metrics
- Error logs or validation results are automatically generated

**Do NOT include if**:
- You would need to manually evaluate
- You would need to write new evaluation code
- It's not part of your existing execution pipeline

#### `reflector_additional_instructions` (optional)

**When to include**: Only if the user explicitly requests custom reflector guidance or you have domain-specific requirements that must override default behavior

**What it is**: Custom instructions that supplement the reflector prompt

**Do NOT include if**: You don't have specific requirements - the default reflector is sufficient

#### `curator_additional_instructions` (optional)

**When to include**: Only if the user explicitly requests custom curator guidance or you have specific playbook formatting/styling requirements

**What it is**: Custom instructions that supplement the curator prompt

**Do NOT include if**: You don't have specific requirements - the default curator is sufficient

## Minimal Implementation Checklist

**Essential Steps Only**:

1. **Before each inference**:
   - Build your final prompt
   - Call `POST /playbooks/{playbook_id}/embed_prompt` with `k` bullets
   - Use the enriched prompt that is returned for inference

2. **During agent execution**:
   - Store the enriched prompt as `user_message`
   - Collect complete execution trace as `trajectory` (preserve PLAYBOOK_BEGIN/PLAYBOOK_END markers)

3. **After execution completes**:
   - Call `POST /playbooks/{playbook_id}/episodes/learn` with:
     - `user_message`: The enriched prompt that was sent
     - `trajectory`: Complete execution trace
     - Any optional fields ONLY if they already exist in your system

**That's it.** The learning happens automatically in the background.

## Workflow Diagram

```
User Prompt
    ↓
[Your Agent Logic]
    ↓
Call embed_prompt(playbook_id, prompt, k)
    ↓
Enriched Prompt (with playbook context)
    ↓
[Send to LLM Provider / Execute]
    ↓
[Collect: user_message, trajectory]
    ↓
Call start_learn(playbook_id, {user_message, trajectory})
    ↓
[ACE analyzes in background - may still be running]
    ↓
[Next run uses same playbook_id]
    ↓
[Eventually benefits from new playbook knowledge once analysis completes]
```

## Key Principles

1. **Keep it simple**: Only implement the essentials - `embed_prompt` before inference, `start_learn` after execution
2. **Use consistent playbook_id**: Same ID for both calls so context can be traced
3. **Don't poll**: The learn job runs in background - don't wait or check status
4. **Don't create optional data**: Only include `ground_truth`, `evaluation`, or additional instructions if they already exist
5. **Preserve markers**: Keep `**PLAYBOOK_BEGIN**` and `**PLAYBOOK_END**` in trajectory so ACE knows what context was used

## What NOT to Do

- ❌ Don't create or manage playbooks manually (they're auto-created)
- ❌ Don't poll for learn job status
- ❌ Don't generate ground_truth or evaluation if they don't already exist
- ❌ Don't add additional instructions unless explicitly needed
- ❌ Don't wait for learn job to complete before next run
- ❌ Don't over-engineer the trajectory format

## What TO Do

- ✅ Call `embed_prompt` right before inference
- ✅ Collect `user_message` and `trajectory` during execution
- ✅ Call `start_learn` after execution completes
- ✅ Use the same `playbook_id` for both calls
- ✅ Include optional fields only if they already exist in your system
- ✅ Let ACE run in background and improve prompts automatically
