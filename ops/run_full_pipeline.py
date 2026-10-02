import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from oth.core.kernel import OTHKernel

k=OTHKernel(Path("."))
signal={
    "source":"pipeline-test",
    "query":"appointment scheduling software complaints",
    "title":"Appointment Scheduling Software",
    "url":"https://example.test/scheduling",
    "snippet":"Small businesses complain that appointment scheduling is manual, expensive, frustrating, difficult, slow, and time-consuming. Owners compare software alternatives and review scheduling tools and services because the repetitive workflow is hard to manage.",
    "signal_type":"review",
    "quality":1.0,
    "score":{"score":86,"demand":84,"pain":90,"automation":88,"differentiation":70,
             "reasons":["manual customer workflow","high automation potential"]},
}
k.db.add_opportunities([signal])
oid=k.db.get_opportunity_id("pipeline-test",signal["url"],signal["query"])
k.db.score_opportunity(oid,signal["score"],"2026-10-02T00:00:00+00:00")

root_task=k.submit("opportunity-analysis","score",{
    "input":{"opportunities":[signal]}
})
print("ROOT",root_task.id)
queue=[root_task.id]
visited=set()
while queue:
    tid=queue.pop(0)
    if tid in visited:
        continue
    visited.add(tid)
    result=k.dispatch(tid)
    print("TASK",tid,result.get("status"),"SPAWNED",result.get("spawned",[]))
    queue.extend(result.get("spawned",[]))

print("BUILDS")
for row in k.db.list_build_artifacts(5):
    print(dict(row))
k.close()
