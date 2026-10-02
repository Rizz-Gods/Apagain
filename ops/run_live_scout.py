import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from oth.core.kernel import OTHKernel
k=OTHKernel(Path("."))
t=k.submit("scout","scan",{
  "queries":[
    "small business owners software complaints manual spreadsheets",
    "site:reddit.com/r/smallbusiness scheduling invoicing software complaint alternative"
  ],
  "next":[{"capability":"opportunity-analysis","action":"score","priority":65}]
})
print("TASK",t.id)
print(k.dispatch(t.id))
print("QUEUED",[(x["id"],x["capability"]) for x in k.tasks() if x["status"]=="queued"][-5:])
k.close()
