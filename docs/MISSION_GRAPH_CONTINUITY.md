# Mission Graph Continuity

Mission Graph Continuity extends Mission Continuity from root-task tracking to the full descendant task graph.

## Guarantees

- Child handoffs inherit mission_id and conversation_id.
- Event-triggered child tasks inherit the same mission identity.
- Mission status is aggregated across roots and all reachable descendants.
- A succeeded root does not close a mission while a spawned child is still queued or running.
- A mission reaches succeeded only when every observed graph task succeeds.
- A failed descendant prevents a mission from being reported as successful.
- The Console mission endpoint exposes graph nodes, edges, and status counts.

## Runtime path

Console conversation -> MissionStateStore -> root task -> task edge -> descendant task -> MissionStateStore

The kernel performs the final mission-state refresh after handoffs and event triggers are spawned so newly-created children cannot be missed by the aggregate.

## API

GET /api/conversations/{conversation_id}/mission

Each returned mission includes root_task_ids, latest_task_id, durable mission outcome, graph.nodes, graph.edges, and graph.counts.

graph.counts reports total, queued, running, blocked, succeeded, and failed tasks.

## Safety

The graph walker is bounded to 512 nodes for API reads. Existing task policy, lane routing, verification, and worker contracts remain unchanged.

## Verification

- Focused Mission Continuity, Mission Kernel Bridge, and workflow tests: PASS.
- Full OTH test suite: PASS, exit code 0.
- Live validation against the real OTH data/oth.db and data/console.db: PASS.
  - Root succeeded while child remained queued.
  - Graph reported 2 total tasks and 1 queued child.
  - Child inherited the mission and conversation identity.
  - Child succeeded.
  - Mission closed as succeeded with the child as the latest task.

## Continuation

Mission Graph Continuity is infrastructure for future resumable multi-stage missions, approvals, parallel branches, and long-running workflows.
