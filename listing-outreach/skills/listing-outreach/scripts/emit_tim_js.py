#!/usr/bin/env python3
"""Bring each tenant's REQUIREMENT into line with VTS Database Handbook 2.0 (Steps 4/5/6).

A deal is not a requirement. `emit_vts_js.py` creates deals (property pipeline); the master
database the handbook is about is the **Requirements** tab -- internally "TIMs". Creating a
deal does NOT create a TIM, which is why the 2026-09-03 Westview blast left ~50 tenants with
no size and no category.

    python3 emit_tim_js.py plan          # what would change, no writes
    python3 emit_tim_js.py apply 0 20    # emit JS for 20 at a time -> javascript_tool

VERIFIED against live VTS (2026-09-09):
    GET  /api/horse/tims/tims?page=N&page_size=M&tim_list_ids[]=55554   list (array form only)
    GET  /api/horse/tims/tims/<id>                                      detail, has `description`
    PUT  /api/horse/tims/tims/<id>   {"tim":{...}}  -> 200              confirmed by no-op write
    tim_list_id 55554 = "H&R MASTER DATABASE 2.0"   (12103 is the older list, 39546 dev/owner)

NOT verified: creating a TIM that does not exist yet. Those are reported by `plan` and left
for a human -- guessing a create payload across 5,800 shared rows is not worth the risk.
"""
import json
import os
import pathlib
import sys

REF = pathlib.Path(__file__).resolve().parents[3] / "references"
sys.path.insert(0, str(REF))
import categories as cat            # noqa: E402
import sizing                       # noqa: E402

MASTER_LIST_ID = 55554
PLAN = os.path.join(os.path.expanduser("~"), ".listing-outreach", "vts_plan.json")

PRELUDE = """
const CSRF=document.querySelector('meta[name="csrf-token"]').content;
const H={'Content-Type':'application/json','Accept':'application/json','X-CSRF-Token':CSRF,'X-Requested-With':'XMLHttpRequest'};
const RO={'Accept':'application/json','X-Requested-With':'XMLHttpRequest'};
const LIST=%(list)d;
const norm=s=>(s||'').toLowerCase().replace(/[^a-z0-9]/g,'');
const sleep=ms=>new Promise(s=>setTimeout(s,ms));
// The renderer wedges under heavy sequential fetching -- keep batches small and paced.
async function findTim(name){
  for(let pg=1; pg<=12; pg++){
    const j=await (await fetch(`/api/horse/tims/tims?page=${pg}&page_size=500&tim_list_ids[]=${LIST}`,
      {headers:RO,credentials:'same-origin'})).json();
    const arr=j.tims||j.data||[];
    const hit=arr.find(t=>norm(t.tenant_name)===norm(name));
    if(hit) return hit.id;
    if(arr.length<500) break;
  }
  return null;
}
async function setTim(id, desc, lo, hi){
  const tim={};
  if(desc) tim.description=desc;
  if(lo){ tim.req_size_from=lo; tim.req_size_to=hi; }
  tim.tim_list_id=LIST;
  const r=await fetch(`/api/horse/tims/tims/${id}`,{method:'PUT',headers:H,
    credentials:'same-origin',body:JSON.stringify({tim})});
  return r.status;
}
"""


def rows_from_plan():
    if not os.path.exists(PLAN):
        raise SystemExit("no plan at %s -- run build_vts_plan.py first" % PLAN)
    plan = json.load(open(PLAN))
    out = []
    for s in (plan.get("submitted") or []) + (plan.get("dead") or []):
        name = s.get("tenant")
        if not name:
            continue
        raw = s.get("category") or s.get("description") or ""
        desc = cat.normalize(raw)[0] if raw else ""
        lo, hi, why = sizing.size_for(tenant=name, category=raw)
        out.append({"tenant": name, "description": desc, "min": lo, "max": hi, "basis": why})
    return out


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "plan"
    rows = rows_from_plan()
    if cmd == "plan":
        print("%-34s %-26s %-14s %s" % ("TENANT", "CATEGORY", "SIZE", "BASIS"))
        for r in rows:
            size = "%s-%s" % (r["min"], r["max"]) if r["min"] else "(blank)"
            print("%-34s %-26s %-14s %s" % (r["tenant"][:34], (r["description"] or "(none)")[:26],
                                            size, r["basis"]))
        n_cat = sum(1 for r in rows if r["description"])
        n_size = sum(1 for r in rows if r["min"])
        print("\n%d tenants | %d with a category | %d with a size guess" % (len(rows), n_cat, n_size))
        print("Pads/ground-lease: leave size blank -- acreage is the real number and VTS has "
              "no field for it.")
        return

    lo_i = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    hi_i = int(sys.argv[3]) if len(sys.argv) > 3 else lo_i + 20
    batch = rows[lo_i:hi_i]
    body = [PRELUDE % {"list": MASTER_LIST_ID}, "(async()=>{ const done=[],missing=[];"]
    for r in batch:
        body.append(
            "{const id=await findTim(%s); if(!id){missing.push(%s);} else {"
            "const st=await setTim(id,%s,%s,%s); done.push([%s,st]);} await sleep(400);}"
            % (json.dumps(r["tenant"]), json.dumps(r["tenant"]),
               json.dumps(r["description"] or None),
               r["min"] or "null", r["max"] or "null", json.dumps(r["tenant"])))
    body.append("console.log(JSON.stringify({done,missing}));"
                "window.__timR=JSON.stringify({done,missing});})();\"started\"")
    print("\n".join(body))


if __name__ == "__main__":
    main()
