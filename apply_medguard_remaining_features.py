from pathlib import Path
import shutil, sys
root=Path.cwd(); app=root/'frontend/src/App.jsx'; main=root/'backend/main.py'; css=root/'frontend/src/App.css'
if not app.exists() or not main.exists(): sys.exit('Run from MedGuard-AI project root containing frontend/ and backend/.')
def backup(p):
 b=p.with_suffix(p.suffix+'.before_remaining_features.bak')
 if not b.exists(): shutil.copy2(p,b)
backup(app); backup(main)
module=r'''from __future__ import annotations
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
'''
(root/'backend/clinical_extensions.py').write_text(module,encoding='utf-8')
m=main.read_text(encoding='utf-8')
if 'clinical_extensions import' not in m:
 line='from clinical_extensions import router as clinical_extensions_router, initialize_clinical_extensions\n';p=m.find('from safety_engine_demo import')
 if p>=0:e=m.find('\n',p);m=m[:e+1]+line+m[e+1:]
 else:m=line+m
if 'initialize_clinical_extensions()' not in m:
 if 'initialize_database()' not in m:sys.exit('Could not find initialize_database() in main.py; backup preserved.')
 m=m.replace('initialize_database()','initialize_database()\ninitialize_clinical_extensions()',1)
if 'app.include_router(clinical_extensions_router)' not in m:m=m.replace('initialize_clinical_extensions()','initialize_clinical_extensions()\napp.include_router(clinical_extensions_router)',1)
main.write_text(m,encoding='utf-8')
s=app.read_text(encoding='utf-8')
if '{ id: "clinical", icon:' not in s:s=s.replace('{ id: "access", icon: "▣", label: "QR & identity access" },','{ id: "clinical", icon: "⚕", label: "Clinical tools" },\n    { id: "access", icon: "▣", label: "QR & identity access" },',1)
if 'const [clinicalCurrent, setClinicalCurrent]' not in s:
 anchor='const [analyticsError, setAnalyticsError] = useState("");'
 state='''\nconst [clinicalCurrent, setClinicalCurrent] = useState("");\nconst [clinicalProposed, setClinicalProposed] = useState("");\nconst [clinicalPatientId, setClinicalPatientId] = useState("");\nconst [clinicalAge, setClinicalAge] = useState("");\nconst [clinicalEgfr, setClinicalEgfr] = useState("");\nconst [clinicalPregnancy, setClinicalPregnancy] = useState("");\nconst [clinicalResult, setClinicalResult] = useState(null);\nconst [clinicalBusy, setClinicalBusy] = useState(false);\nconst [clinicalError, setClinicalError] = useState("");\nconst [clinicalDepartments, setClinicalDepartments] = useState([]);\nconst [clinicalEvaluation, setClinicalEvaluation] = useState(null);\n'''
 if anchor not in s:sys.exit('Could not find analytics state in App.jsx; backup preserved and backend module installed.')
 s=s.replace(anchor,anchor+state,1)
if 'async function runClinicalReconciliation' not in s:
 marker='\n  return (\n\n\n\n    <div className="mg-app">'
 if marker not in s:marker='\n  return (\n    <div className="mg-app">'
 if marker not in s:sys.exit('Could not find App render marker; backup preserved.')
 handlers=r'''
  async function runClinicalReconciliation(event) {
    event.preventDefault();setClinicalBusy(true);setClinicalError("");setClinicalResult(null);
    try {const r=await apiFetch("/api/extensions/reconcile",{method:"POST",headers:{"Content-Type":"application/json","Accept":"application/json"},body:JSON.stringify({patient_id:clinicalPatientId||selected?.id||null,current_medications:clinicalCurrent.split(/\n|,|;/).map(x=>x.trim()).filter(Boolean),proposed_medications:clinicalProposed.split(/\n|,|;/).map(x=>x.trim()).filter(Boolean)})});const d=await r.json().catch(()=>null);if(!r.ok)throw new Error(d?.detail||`Reconciliation failed (${r.status}).`);setClinicalResult({type:"reconciliation",data:d});}catch(e){setClinicalError(e.message||"Reconciliation failed.");}finally{setClinicalBusy(false);}
  }
  async function runClinicalContextReview(event) {
    event.preventDefault();setClinicalBusy(true);setClinicalError("");setClinicalResult(null);
    try {const r=await apiFetch("/api/extensions/context-review",{method:"POST",headers:{"Content-Type":"application/json","Accept":"application/json"},body:JSON.stringify({patient_id:clinicalPatientId||selected?.id||null,medications:clinicalProposed.split(/\n|,|;/).map(x=>x.trim()).filter(Boolean),age:clinicalAge===""?null:Number(clinicalAge),egfr:clinicalEgfr===""?null:Number(clinicalEgfr),pregnancy_status:clinicalPregnancy||null})});const d=await r.json().catch(()=>null);if(!r.ok)throw new Error(d?.detail||`Context review failed (${r.status}).`);setClinicalResult({type:"context",data:d});}catch(e){setClinicalError(e.message||"Context review failed.");}finally{setClinicalBusy(false);}
  }
  async function loadClinicalDepartments() {
    setClinicalBusy(true);setClinicalError("");try{const r=await apiFetch("/api/extensions/departments");const d=await r.json().catch(()=>null);if(!r.ok)throw new Error(d?.detail||`Departments failed (${r.status}).`);setClinicalDepartments(d?.departments||[]);}catch(e){setClinicalError(e.message||"Could not load departments.");}finally{setClinicalBusy(false);}
  }
  async function runClinicalEvaluation() {
    setClinicalBusy(true);setClinicalError("");setClinicalEvaluation(null);try{const r=await apiFetch("/api/extensions/evaluation/run",{method:"POST"});const d=await r.json().catch(()=>null);if(!r.ok)throw new Error(d?.detail||`Evaluation failed (${r.status}).`);setClinicalEvaluation(d);}catch(e){setClinicalError(e.message||"Evaluation failed.");}finally{setClinicalBusy(false);}
  }
'''
 s=s.replace(marker,'\n'+handlers+marker,1)
if '{page === "clinical" && (' not in s:
 panel=r'''
          {page === "clinical" && (
            <section className="mg-panel mg-full-panel">
              <div className="mg-panel-heading"><div><h2>Clinical workflow tools</h2><p>Medication reconciliation, context completeness, department view and smoke evaluation.</p></div><span className="mg-outline-tag">Synthetic demo only</span></div>
              <div className="mg-safety-note">Workflow prompts only, not clinical advice. Do not use real patient data. Real biometrics and cloud storage require configured providers and are not simulated.</div>
              <form className="mg-visit-form mg-extension-form" onSubmit={runClinicalReconciliation}><h3>Medication reconciliation</h3>
                <label htmlFor="mg-clinical-patient">Patient ID (optional)</label><input id="mg-clinical-patient" value={clinicalPatientId} onChange={e=>setClinicalPatientId(e.target.value)} placeholder={selected?.id||"Synthetic patient ID"}/>
                <div className="mg-visit-form-grid"><div><label htmlFor="mg-clinical-current">Current list (one per line)</label><textarea id="mg-clinical-current" rows="4" value={clinicalCurrent} onChange={e=>setClinicalCurrent(e.target.value)} placeholder={"Medicine A\nMedicine B"}/></div><div><label htmlFor="mg-clinical-proposed">Proposed list (one per line)</label><textarea id="mg-clinical-proposed" rows="4" value={clinicalProposed} onChange={e=>setClinicalProposed(e.target.value)} placeholder={"Medicine A\nMedicine C"}/></div></div>
                <button className="mg-primary-button" type="submit" disabled={clinicalBusy}>Compare medication lists</button></form>
              <form className="mg-visit-form mg-extension-form" onSubmit={runClinicalContextReview}><h3>Patient-context completeness review</h3><p className="mg-empty-text">Synthetic context only. This flags missing context and review triggers; it does not calculate doses.</p>
                <div className="mg-visit-form-grid"><div><label htmlFor="mg-context-age">Age</label><input id="mg-context-age" type="number" min="0" max="125" value={clinicalAge} onChange={e=>setClinicalAge(e.target.value)}/></div><div><label htmlFor="mg-context-egfr">eGFR (optional)</label><input id="mg-context-egfr" type="number" min="0" max="250" value={clinicalEgfr} onChange={e=>setClinicalEgfr(e.target.value)}/></div></div>
                <label htmlFor="mg-context-pregnancy">Pregnancy status</label><select id="mg-context-pregnancy" value={clinicalPregnancy} onChange={e=>setClinicalPregnancy(e.target.value)}><option value="">Not supplied</option><option value="not pregnant">Not pregnant</option><option value="pregnant">Pregnant</option><option value="not applicable">Not applicable</option><option value="unknown">Unknown</option></select><button className="mg-primary-button" type="submit" disabled={clinicalBusy}>Review context</button></form>
              {clinicalError&&<div className="mg-error" role="alert">{clinicalError}</div>}
              {clinicalResult&&<div className="mg-result-panel"><h3>{clinicalResult.type==="reconciliation"?"Reconciliation result":"Context review result"}</h3>{clinicalResult.type==="reconciliation"?<div className="mg-feature-grid">{["added","removed","unchanged"].map(k=><div className="mg-feature-card" key={k}><h4>{k} ({clinicalResult.data[k]?.length||0})</h4>{(clinicalResult.data[k]?.length?clinicalResult.data[k]:["None"]).map((x,i)=><p key={k+i}>{x}</p>)}</div>)}</div>:<>{clinicalResult.data.alerts?.length?clinicalResult.data.alerts.map((a,i)=><div className="mg-manual-review" key={i}><strong>{a.severity}</strong><p>{a.message}</p></div>):<p>No context prompts generated.</p>}<p>{clinicalResult.data.summary}</p></>}<p className="mg-disclaimer">{clinicalResult.data.note||"Synthetic workflow output only; clinician review is required."}</p></div>}
              <div className="mg-extension-actions"><button className="mg-secondary-button" type="button" onClick={loadClinicalDepartments} disabled={clinicalBusy}>Load department summary</button><button className="mg-primary-button" type="button" onClick={runClinicalEvaluation} disabled={clinicalBusy}>Run synthetic evaluation</button></div>
              {clinicalDepartments.length>0&&<div className="mg-table-wrap"><table className="mg-patient-table"><thead><tr><th>Department</th><th>Patients</th></tr></thead><tbody>{clinicalDepartments.map(d=><tr key={d.department}><td>{d.department}</td><td>{d.patient_count}</td></tr>)}</tbody></table></div>}
              {clinicalEvaluation&&<div className="mg-result-panel"><h3>Smoke evaluation: {clinicalEvaluation.passed}/{clinicalEvaluation.total} passed</h3>{clinicalEvaluation.tests?.map(t=><p key={t.name}>{t.passed?"✓":"✕"} {t.name}</p>)}<p className="mg-disclaimer">{clinicalEvaluation.note}</p></div>}
            </section>
          )}
'''
 if '{page === "access" && (' not in s:sys.exit('Could not find access panel insertion point; backups preserved.')
 s=s.replace('{page === "access" && (',panel+'\n          {page === "access" && (',1)
s=s.replace(': "QR & Identity Access"', ': page === "clinical" ? "Clinical Workflow Tools" : "QR & Identity Access"')
app.write_text(s,encoding='utf-8')
if css.exists():
 c=css.read_text(encoding='utf-8')
 if '.mg-extension-form' not in c:c+='''\n/* MedGuard AI remaining workflow features */\n.mg-extension-form,.mg-result-panel{margin-top:18px;padding:20px;border:1px solid var(--border,#e5e7eb);border-radius:14px;background:var(--surface,#fff)}\n.mg-extension-form h3,.mg-result-panel h3{margin:0 0 14px}.mg-extension-form textarea{width:100%;min-height:100px;resize:vertical}\n.mg-extension-form input,.mg-extension-form textarea,.mg-extension-form select{box-sizing:border-box;width:100%;margin:6px 0 14px;padding:11px 12px;border:1px solid var(--border,#dbe2ef);border-radius:9px;font:inherit;background:var(--surface,#fff);color:var(--text,#20213a)}\n.mg-extension-form label{display:block;font-weight:600}.mg-extension-actions{display:flex;flex-wrap:wrap;gap:10px;margin:18px 0}\n''';css.write_text(c,encoding='utf-8')
print('Patch applied. Backups are beside originals with .before_remaining_features.bak suffixes.')
print('Added backend/clinical_extensions.py and Clinical tools UI.')
print('Next: python -m compileall -q backend')
print('In backend folder: python -m unittest discover -s tests -v')
print('From project root: npm --prefix frontend run lint && npm --prefix frontend run build')
