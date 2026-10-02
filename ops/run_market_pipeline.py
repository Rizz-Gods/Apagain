import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from oth.core.kernel import OTHKernel

k = OTHKernel(Path("."))
root = k.submit("scout", "scan", {
    "queries": ["appointment scheduling software for small business"],
    "next": [{"capability": "review-mining", "action": "mine", "priority": 68}]
})
scout = k.dispatch(root.id)
print("SCOUT", json.dumps({
    "status": scout["status"],
    "count": scout.get("count"),
    "spawned": scout.get("spawned")
}, ensure_ascii=False))

children = [x for x in k.tasks() if x["id"] in scout.get("spawned", [])]
for child in children:
    review = k.dispatch(child["id"])
    print("REVIEW", json.dumps({
        "status": review["status"],
        "count": review.get("count"),
        "spawned": review.get("spawned")
    }, ensure_ascii=False))
    for grand in [x for x in k.tasks() if x["id"] in review.get("spawned", [])]:
        analysis = k.dispatch(grand["id"])
        print("ANALYSIS", json.dumps({
            "status": analysis["status"],
            "count": analysis.get("count")
        }, ensure_ascii=False))

print("TOP")
for row in k.db.top_opportunities(10):
    print(json.dumps({
        "title": row["title"],
        "url": row["url"],
        "score": row["score"],
        "reasons": row["reasons"]
    }, ensure_ascii=False))
k.close()
