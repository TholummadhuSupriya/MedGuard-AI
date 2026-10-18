from __future__ import annotations
import csv,io,json,sqlite3
from datetime import datetime,timezone
from fastapi import APIRouter,Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel,Field
from auth_demo import allow_roles
from database_demo import DB_PATH
router=APIRouter(prefix="/api/extensions",tags=["Workflow extensions"])
STAFF=("doctor","nurse","pharmacist","admin")
def connect():
 c=sqlite3.connect(DB_PATH);c.row_factory=sqlite3.Row;c.execute("PRAGMA foreign_keys=ON");return c
def initialize_clinical_extensions():
 with connect() as c:c.execute("CREATE TABLE IF NOT EXISTS clinical_audit_events(event_id INTEGER PRIMARY KEY AUTOINCREMENT,event_type TEXT NOT NULL,outcome TEXT NOT NULL,detail_json TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL)")
def audit(kind,outcome,details=None):
 with connect() as c:c.execute("INSERT INTO clinical_audit_events(event_type,outcome,detail_json,created_at) VALUES(?,?,?,?)",(kind,outcome,json.dumps(details or {}),datetime.now(timezone.utc).isoformat()))
def norm(s):return " ".join(str(s or "").strip().lower().split())
class ReconcileRequest(BaseModel):
 patient_id:str|None=None
 current_medications:list[str]=Field(default_factory=list,max_length=50)
 proposed_medications:list[str]=Field(default_factory=list,max_length=50)
class ContextRequest(BaseModel):
 patient_id:str|None=None
 medications:list[str]=Field(default_factory=list,max_length=50)
 age:int|None=Field(default=None,ge=0,le=125)
 egfr:float|None=Field(default=None,ge=0,le=250)
 pregnancy_status:str|None=None
@router.get('/summary')
def summary(staff:dict=Depends(allow_roles(*STAFF))):
 with connect() as c:n=c.execute('SELECT COUNT(*) FROM patients').fetchone()[0];a=c.execute('SELECT COUNT(*) FROM clinical_audit_events').fetchone()[0]
 return {'synthetic_demo_only':True,'patients':n,'audit_events':a,'modules':{'reconciliation':'available','context_review':'available','department_summary':'available','audit':'available','synthetic_evaluation':'available','csv_export':'admin only','real_biometrics':'not configured','cloud_storage':'not configured'}}
@router.post('/reconcile')
def reconcile(r:ReconcileRequest,staff:dict=Depends(allow_roles(*STAFF))):
 cur={norm(x):x.strip() for x in r.current_medications if norm(x)};new={norm(x):x.strip() for x in r.proposed_medications if norm(x)}
 result={'synthetic_demo_only':True,'patient_id':r.patient_id,'unchanged':sorted([cur[k] for k in cur.keys()&new.keys()],key=str.lower),'added':sorted([new[k] for k in new.keys()-cur.keys()],key=str.lower),'removed':sorted([cur[k] for k in cur.keys()-new.keys()],key=str.lower),'note':'Text comparison only. Confirm dose, formulation, route, timing and intent with an authorized clinician.'}
 audit('reconciliation','completed',{'current_count':len(cur),'proposed_count':len(new),'added_count':len(result['added']),'removed_count':len(result['removed'])});return result
@router.post('/context-review')
def context_review(r:ContextRequest,staff:dict=Depends(allow_roles(*STAFF))):
 meds=[x.strip() for x in r.medications if x and x.strip()];alerts=[]
 if meds and r.age is None:alerts.append({'severity':'review','message':'Age not supplied; verify patient context.'})
 if meds and r.egfr is None:alerts.append({'severity':'review','message':'eGFR not supplied; renal considerations cannot be assessed by this demo.'})
 if meds and not r.pregnancy_status:alerts.append({'severity':'review','message':'Pregnancy status not supplied; confirm whether relevant.'})
 if r.egfr is not None and r.egfr<30:alerts.append({'severity':'high','message':'Low eGFR context entered: request clinician/pharmacist review of the full medication list. This demo does not determine dosing.'})
 if (r.pregnancy_status or '').strip().lower() in {'pregnant','yes','true'}:alerts.append({'severity':'review','message':'Pregnancy context entered: verify each medicine against an authoritative, current clinical source.'})
 audit('context_review','completed',{'medication_count':len(meds),'alert_count':len(alerts)});return {'synthetic_demo_only':True,'patient_id':r.patient_id,'alerts':alerts,'summary':'Context prompts only. No diagnosis, treatment recommendation, or dose calculation is provided.'}
@router.get('/departments')
def departments(staff:dict=Depends(allow_roles(*STAFF))):
 with connect() as c:rows=c.execute("SELECT COALESCE(NULLIF(TRIM(department),''),'Unassigned') department,COUNT(*) patient_count FROM patients GROUP BY COALESCE(NULLIF(TRIM(department),''),'Unassigned') ORDER BY department").fetchall()
 audit('department_summary','viewed',{'count':len(rows)});return {'synthetic_demo_only':True,'departments':[dict(x) for x in rows]}
@router.get('/audit')
def get_audit(limit:int=50,staff:dict=Depends(allow_roles(*STAFF))):
 limit=max(1,min(limit,200))
 with connect() as c:rows=c.execute('SELECT * FROM clinical_audit_events ORDER BY event_id DESC LIMIT ?',(limit,)).fetchall()
 return {'synthetic_demo_only':True,'events':[{'event_id':x['event_id'],'event_type':x['event_type'],'outcome':x['outcome'],'details':json.loads(x['detail_json']),'created_at':x['created_at']} for x in rows]}
@router.get('/export/patients.csv')
def export_patients(staff:dict=Depends(allow_roles('admin'))):
 with connect() as c:rows=c.execute('SELECT patient_id,display_name,age,department,created_at FROM patients ORDER BY patient_id').fetchall()
 stream=io.StringIO();w=csv.writer(stream);w.writerow(['patient_id','display_name','age','department','created_at'])
 for r in rows:w.writerow([r['patient_id'],r['display_name'],r['age'],r['department'],r['created_at']])
 audit('synthetic_patient_export','completed',{'row_count':len(rows)});stream.seek(0)
 return StreamingResponse(iter([stream.getvalue()]),media_type='text/csv',headers={'Content-Disposition':'attachment; filename=medguard_synthetic_patients.csv'})
@router.post('/evaluation/run')
def evaluation(staff:dict=Depends(allow_roles(*STAFF))):
 from safety_engine_demo import check_medication_list,load_reference_data
 _,interactions,names=load_reference_data();candidates=sorted(names);name=candidates[0] if candidates else None
 dup=check_medication_list([name,name]) if name else {};unknown=check_medication_list(['medguard-unknown-demo-name'])
 tests=[{'name':'duplicate exact ingredient','passed':any('duplicate' in str(a.get('alert_type','')).lower() for a in dup.get('alerts',[]))},{'name':'unknown medicine requires review','passed':bool(unknown.get('manual_review_required'))}]
 if len(interactions):
  row=interactions.iloc[0];pair=check_medication_list([str(row['drug_a']),str(row['drug_b'])]);tests.append({'name':'first configured interaction rule','passed':bool(pair.get('alerts'))})
 result={'synthetic_demo_only':True,'clinical_validation':False,'passed':sum(t['passed'] for t in tests),'total':len(tests),'tests':tests,'note':'Smoke tests use local demo CSVs only; they do not establish clinical accuracy.'};audit('synthetic_evaluation','completed',{'passed':result['passed'],'total':result['total']});return result
