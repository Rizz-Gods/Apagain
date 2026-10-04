# OTH Mission Continuity

## Purpose

Mission Continuity makes an OTH mission a durable object that survives conversation compaction and chat restarts.

## State model

Each mission stores:

- Console conversation ID
- Goal and Pilot strategy
- Root kernel task IDs
- Mission status: queued, running, blocked, succeeded, or failed
- Latest task and structured outcome
- Created, updated, and completion timestamps

The state lives in data/console.db through oth.core.mission_state.MissionStateStore.

## Execution bridge

The Console creates the mission before submitting root tasks. PilotPlanner.submit accepts optional metadata and attaches mission_id and conversation_id to root task payloads.

The kernel reads that identity after task execution and updates the corresponding mission state from the persisted root-task status. Root-task aggregation keeps the mission active while any root remains queued or running and terminal only when the root set reaches a terminal state.

## Context continuity

ConsoleStore.context_for_model injects structured mission state before compacted conversation memory and relevant older messages. A new turn can therefore resume an active mission without reconstructing its state from raw transcript text.

## API

GET /api/conversations/{conversation_id}/mission

Returns the durable mission records for a conversation.

## Verification

Focused unit coverage covers mission creation, success/failure transitions, context injection, and kernel bridging. A live Console-originated engineering mission also completed successfully through ollama-engineer and updated its durable mission record to succeeded.