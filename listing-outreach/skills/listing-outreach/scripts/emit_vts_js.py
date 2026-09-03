#!/usr/bin/env python3
"""Emit ready-to-run JS for the VTS write plan, in batches, to paste into javascript_tool
on an OPEN, logged-in VTS deals tab for the target property.

    python3 emit_vts_js.py counts
    python3 emit_vts_js.py submitted 0 12    # create + comment, 12 at a time
    python3 emit_vts_js.py dead 0 12         # create + comment + mark dead (reason required)
    python3 emit_vts_js.py stage             # apply recorded stage moves (e.g. tour)
    python3 emit_vts_js.py bryan             # comment onto existing deal ids (no create)

Reads ~/.listing-outreach/vts_plan.json. Each payload re-reads the property's existing deals
and SKIPS any tenant already present, so re-running is safe.

THE STAGE-CHANGE CONTRACT (this cost an hour to work out — do not "simplify" it):
  * POST activity_log_iterations REQUIRES `date` AND an inline `comment`. With just
    {status, reason_ids} it returns 200 but the stage SILENTLY does not move (the iteration
    is appended as history and never adopted as current). With no comment at all -> 422.
  * That inline comment is VALIDATION-ONLY — it does NOT persist as a visible comment.
    The comment that shows on the deal must be a SEPARATE /activity_log_iteration_comments
    POST. So logging a dead deal = create, then flip-with-throwaway-comment, then post the
    real comment. Never delete the "duplicate" — the inline one was never saved.
  * dead_deal requires a reason id; other stages reject one.
  * "Cannot change deal stage to the same stage" (422) = the deal is already internally at
    that stage from a failed retry — bounce via initial_inquiry, then set the target.
  * VTS normalizes new tenant names (EVgo->EVGo, IONNA->Ionna, Cook Out->Cook out) — match
    created deals back by a normalized (lowercase-alphanumeric) key, never the exact string.
"""
import json, sys, os

P = os.path.join(os.path.expanduser("~"), ".listing-outreach", "vts_plan.json")
plan = json.load(open(P))

PRELUDE = """
const CSRF=document.querySelector('meta[name="csrf-token"]').content;
const H={'Content-Type':'application/json','Accept':'application/json','X-CSRF-Token':CSRF,'X-Requested-With':'XMLHttpRequest'};
const RO={'Accept':'application/json','X-Requested-With':'XMLHttpRequest'};
const P=%(prop)d, UID=%(uid)d, IND=%(ind)d, DT=%(dt)d;
const NOW=new Date().toISOString().replace(/\\.\\d+Z$/,'-04:00');
const norm=s=>(s||'').toLowerCase().replace(/[^a-z0-9]/g,'');
const sleep=ms=>new Promise(s=>setTimeout(s,ms));
async function DEALS(){const u=`/api/horse/deals?activity_report_filter[properties][]=${P}&activity_report_filter[page]=1&activity_report_filter[page_size]=100&properties[]=${P}&page=1&page_size=100`;
  return ((await (await fetch(u,{headers:RO,credentials:'same-origin'})).json()).activity_logs||[]);}
async function latestIter(id){
  const a=await (await fetch(`/api/horse/deal_artifacts?activity_log_ids[]=${id}`,{headers:RO,credentials:'same-origin'})).json();
  const it=(a||[]).filter(x=>x.class_name==='ActivityLogIteration').map(x=>x.id);
  return it.length?Math.max(...it):null;}
async function makeDeal(name, contact){
  const body={activity_log:{contacts:[],status:"initial_inquiry",date:NOW,undisclosedTenant:false,
    space_ids:[],property_ids:[P],office_park_ids:[],can_update_stage:true,deal_type_id:DT,
    tenant:name,tenant_industry_id:IND,deal_leads:[{id:UID,label:"%(uname)s",value:UID}],
    deal_lead_ids:[UID],submarket_ids:[],activity_log_tenants_attributes:[],
    activity_log_brokers_attributes: contact?[contact]:[],custom_tenant_name:null}};
  const r=await fetch('/activity_logs',{method:'POST',headers:H,credentials:'same-origin',body:JSON.stringify(body)});
  return r.status;
}
async function postComment(id,text){
  const it=await latestIter(id);
  const r=await fetch('/activity_log_iteration_comments',{method:'POST',headers:H,credentials:'same-origin',
    body:JSON.stringify({activity_log_iteration_comment:{comment:text,mentions_attributes:[],documents:[],
      space_ids:[],isTour:false,comment_date:NOW,activity_log_iteration_id:it,activity_log_id:id}})});
  return r.status;
}
async function setStage(id,status,reason){          // see the contract in the header
  const body={activity_log_iteration:{status:status, date:NOW, comment:"stage change"}};
  if(reason) body.activity_log_iteration.activity_log_iteration_reason_ids=[reason];
  let r=await fetch(`/activity_logs/${id}/activity_log_iterations`,{method:'POST',headers:H,credentials:'same-origin',body:JSON.stringify(body)});
  if(r.status===422 && /same stage/i.test(await r.clone().text())){
    await fetch(`/activity_logs/${id}/activity_log_iterations`,{method:'POST',headers:H,credentials:'same-origin',
      body:JSON.stringify({activity_log_iteration:{status:"initial_inquiry",date:NOW}})});
    await sleep(400);
    r=await fetch(`/activity_logs/${id}/activity_log_iterations`,{method:'POST',headers:H,credentials:'same-origin',body:JSON.stringify(body)});
  }
  return r.status;
}
const out=[];
""" % {"prop": plan["property_id"], "uid": plan["user_id"], "ind": plan["tenant_industry_id"],
       "dt": plan["deal_type_id"], "uname": plan["user_name"]}


def emit(rows, kind):
    body = ["let d=await DEALS(); const have=new Set(d.map(x=>norm(x.deal_name)));",
            "const ROWS=" + json.dumps(rows, ensure_ascii=False) + ";"]
    if kind in ("submitted", "dead"):
        body.append("""
const made=[];
for(const x of ROWS){
  if(have.has(norm(x.tenant))){ out.push(`SKIP ${x.tenant}`); continue; }
  const st=await makeDeal(x.tenant, x.contact||null);
  if(st>=200&&st<300) made.push(x); else out.push(`FAIL ${st} ${x.tenant}`);
  await sleep(320);
}
d=await DEALS(); const byNorm={}; for(const z of d) byNorm[norm(z.deal_name)]=z.id;
for(const x of made){
  const id=byNorm[norm(x.tenant)];
  if(!id){ out.push(`NOID ${x.tenant}`); continue; }
  if(x.reason){ await setStage(id,'dead_deal',x.reason); await sleep(250); }
  const cs=await postComment(id, x.comment);
  out.push(`OK ${id} ${x.tenant} comment=${cs}${x.reason?' dead':''}`);
  await sleep(300);
}""")
    elif kind == "stage":
        body.append("""
d=await DEALS(); const byNorm={}; for(const z of d) byNorm[norm(z.deal_name)]=z.id;
for(const x of ROWS){
  const id=byNorm[norm(x.tenant)];
  if(!id){ out.push(`NOID ${x.tenant}`); continue; }
  const ss=await setStage(id, x.status, x.reason||null); await sleep(250);
  const cs=await postComment(id, x.comment);
  out.push(`OK ${id} ${x.tenant} stage=${ss} comment=${cs}`);
  await sleep(300);
}""")
    else:  # bryan — comment on existing deal ids, no create
        body.append("""
for(const x of ROWS){
  const cs=await postComment(x.deal_id, x.comment);
  out.push(`OK #${x.deal_id} ${x.tenant} comment=${cs}`);
  await sleep(300);
}""")
    body.append("out.join('\\n')")
    return PRELUDE + "\n".join(body)


if len(sys.argv) < 2 or sys.argv[1] == "counts":
    for k in ("submitted", "dead", "stage", "bryan_comments"):
        print(f"{k:<16}: {len(plan.get(k, []))}")
    raise SystemExit

kind = sys.argv[1]
key = {"submitted": "submitted", "dead": "dead", "stage": "stage", "bryan": "bryan_comments"}[kind]
rows = plan[key]
if len(sys.argv) > 3:
    s, c = int(sys.argv[2]), int(sys.argv[3])
    rows = rows[s:s + c]
print(emit(rows, kind))
