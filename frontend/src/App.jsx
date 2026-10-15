import { useEffect, useState } from "react";

import { QRCodeSVG } from "qrcode.react";



import "./App.css";



const API = "http://127.0.0.1:8000";

// Attach the current staff bearer token to protected API requests.
async function apiFetch(input, options = {}) {
  const token = localStorage.getItem("medguard_access_token");
  const headers = {
    Accept: "application/json",
    ...(options.headers || {}),
  };

  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const url = input.startsWith("http://") || input.startsWith("https://")
    ? input
    : `${API}${input}`;

  return fetch(url, { ...options, headers });
}



function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(Boolean(localStorage.getItem("medguard_access_token")));
  const [loginUsername, setLoginUsername] = useState("doctor.demo");
  const [loginPassword, setLoginPassword] = useState("");
  const [loginError, setLoginError] = useState("");
  const [loginBusy, setLoginBusy] = useState(false);

  const [patients, setPatients] = useState([]);



  const [selected, setSelected] = useState(null);



  const [search, setSearch] = useState("");
  const [navSearch, setNavSearch] = useState("");



  const [page, setPage] = useState("overview");



  const [loading, setLoading] = useState(true);



  const [error, setError] = useState("");



  const [medicationInput, setMedicationInput] = useState("");



  const [safetyResult, setSafetyResult] = useState(null);



  const [safetyLoading, setSafetyLoading] = useState(false);



  const [safetyError, setSafetyError] = useState("");

  const [visitPatientId, setVisitPatientId] = useState("");

  const [visitDate, setVisitDate] = useState(() => new Date().toISOString().slice(0, 10));

  const [visitDepartment, setVisitDepartment] = useState("");

  const [visitNotes, setVisitNotes] = useState("");

  const [visitMedications, setVisitMedications] = useState("");

  const [visitSaving, setVisitSaving] = useState(false);

  const [visitMessage, setVisitMessage] = useState("");

  const [visitError, setVisitError] = useState("");

  const [qrToken, setQrToken] = useState("");

  const [qrPatientId, setQrPatientId] = useState("");

  const [qrBusy, setQrBusy] = useState(false);

  const [qrMessage, setQrMessage] = useState("");

  const [qrError, setQrError] = useState("");

  const [qrResolveInput, setQrResolveInput] = useState("");



  async function handleLogin(event) {
    event.preventDefault();
    setLoginBusy(true);
    setLoginError("");
    try {
      const response = await fetch(`${API}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ username: loginUsername.trim(), password: loginPassword }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error(payload?.detail || `Login failed (${response.status}).`);
      if (!payload?.access_token) throw new Error("Login response did not include an access token.");
      localStorage.setItem("medguard_access_token", payload.access_token);
      setIsAuthenticated(true);
      setLoginPassword("");
    } catch (err) {
      setLoginError(err.message || "Unable to log in.");
    } finally {
      setLoginBusy(false);
    }
  }

  function handleLogout() {
    localStorage.removeItem("medguard_access_token");
    setIsAuthenticated(false);
    setPatients([]);
    setSelected(null);
    setPage("overview");
  }

  useEffect(() => {
    if (!isAuthenticated) {
      setLoading(false);
      setPatients([]);
      return undefined;
    }

    let cancelled = false;



    async function loadPatients() {

      try {

        const response = await apiFetch("/api/db/patients");



if (!response.ok) {
  const details = await response.text();
  throw new Error(`Patient API failed: ${response.status} ${details}`);
}



const payload = await response.json();

        const rows = Array.isArray(payload)

          ? payload

          : Array.isArray(payload?.patients)

            ? payload.patients

            : Array.isArray(payload?.items)

              ? payload.items

              : [];



        const normalized = rows.map((patient) => ({

          ...patient,

          id: String(patient.id ?? patient.patient_id ?? patient.patientId ?? ""),

          name: patient.name ?? patient.full_name ?? patient.patient_name ?? "Demo patient",

          age: patient.age ?? "Not recorded",

          department: patient.department ?? patient.ward ?? "Not recorded",

          records_status: patient.records_status ?? patient.record_status ?? "Available",

        })).filter((patient) => patient.id);



        if (!cancelled) setPatients(normalized);

      } catch (err) {

        if (!cancelled) {

          setError(err.message || "Cannot load SQLite demo patients. Check FastAPI and /api/db/patients.");

        }

      } finally {

        if (!cancelled) setLoading(false);

      }

    }



    loadPatients();

    return () => { cancelled = true; };

  }, [isAuthenticated]);



  async function openPatient(id) {

    setError("");

    try {

      const response = await apiFetch(

        `${API}/api/db/patients/${encodeURIComponent(id)}/history`

      );

      if (!response.ok) throw new Error("Record unavailable");

      const payload = await response.json();

      const patient = payload?.patient ?? payload?.profile ?? payload;

      const asArray = (value) => Array.isArray(value) ? value : [];

      const diagnoses = asArray(patient?.diagnoses ?? payload?.diagnoses);

      const medications = asArray(patient?.medications ?? payload?.medications);

      const medicationHistory = asArray(payload?.medication_history);

      const visits = asArray(payload?.visits);



      const normalized = {

        ...patient,

        id: String(patient?.id ?? patient?.patient_id ?? id),

        name: patient?.name ?? patient?.full_name ?? patient?.patient_name ?? "Demo patient",

        age: patient?.age ?? "Not recorded",

        department: patient?.department ?? patient?.ward ?? "Not recorded",

        records_status: patient?.records_status ?? patient?.record_status ?? "Available",

        diagnoses: diagnoses.map((item) => typeof item === "string" ? item : (item.name ?? item.diagnosis ?? JSON.stringify(item))),

        medications,

        medication_history: medicationHistory,

        visits,

        is_synthetic: patient?.is_synthetic ?? payload?.is_synthetic ?? true,

      };

      setSelected(normalized);

      setPage("patients");

    } catch {

      setError("Unable to retrieve this SQLite demo patient record. Check the /api/db/patients/{id}/history endpoint.");

    }

  }



async function saveVisit(event) {

  event.preventDefault();

  const patientId = visitPatientId || selected?.id || "";

  const medications = visitMedications

    .split(/\n|,|;/)

    .map((name) => name.trim())

    .filter(Boolean);



  if (!patientId) {

    setVisitError("Select a demo patient before saving the visit.");

    setVisitMessage("");

    return;

  }

  if (medications.length > 50) {

    setVisitError("Enter no more than 50 medication names.");

    setVisitMessage("");

    return;

  }



  setVisitSaving(true);

  setVisitError("");

  setVisitMessage("");

  try {

    const response = await apiFetch(

      `${API}/api/db/patients/${encodeURIComponent(patientId)}/visits`,

      {

        method: "POST",

        headers: { "Content-Type": "application/json", Accept: "application/json" },

        body: JSON.stringify({

          visit_date: visitDate || null,

          department: visitDepartment.trim(),

          notes: visitNotes.trim(),

          medications,

        }),

      }

    );

    const payload = await response.json().catch(() => null);

    if (!response.ok) {

      throw new Error(payload?.detail || "The visit could not be saved.");

    }

    setVisitMessage(`Demo visit saved successfully (visit ID ${payload?.visit_id ?? "created"}). Refreshing patient history…`);

    setVisitNotes("");

    setVisitMedications("");

    await openPatient(patientId);

    setPage("access");

    setVisitMessage(`Demo visit saved successfully (visit ID ${payload?.visit_id ?? "created"}). Patient history refreshed.`);

  } catch (err) {

    setVisitError(err.message || "Unable to save the visit. Confirm the SQLite API is running.");

  } finally {

    setVisitSaving(false);

  }

}



async function createQrReference(event) {

  event.preventDefault();

  const patientId = qrPatientId || selected?.id || "";

  if (!patientId) {

    setQrError("Select a synthetic demo patient first.");

    setQrMessage("");

    return;

  }

  setQrBusy(true);

  setQrError("");

  setQrMessage("");

  setQrToken("");

  try {

    const response = await apiFetch(`${API}/api/qr/references`, {

      method: "POST",

      headers: { "Content-Type": "application/json", Accept: "application/json" },

      body: JSON.stringify({ patient_id: patientId, expires_in_hours: 8 }),

    });

    const payload = await response.json().catch(() => null);

    if (!response.ok) throw new Error(payload?.detail || "Could not create a QR reference.");

    setQrToken(payload.token);

    setQrResolveInput(payload.token);

    setQrMessage(`Demo reference created for ${patientId}. Expires at ${payload.expires_at}.`);

  } catch (err) {

    setQrError(`${err.message || "Unable to create reference."} Confirm the QR router is registered in FastAPI.`);

  } finally {

    setQrBusy(false);

  }

}



async function resolveQrReference(event) {

  event.preventDefault();

  const token = qrResolveInput.trim();

  if (!token) {

    setQrError("Paste a demo QR reference token first.");

    setQrMessage("");

    return;

  }

  setQrBusy(true);

  setQrError("");

  setQrMessage("");

  try {

    const response = await apiFetch(`${API}/api/qr/resolve`, {

      method: "POST",

      headers: { "Content-Type": "application/json", Accept: "application/json" },

      body: JSON.stringify({ token }),

    });

    const payload = await response.json().catch(() => null);

    if (!response.ok) throw new Error(payload?.detail || "Reference is invalid, expired or revoked.");

    setQrPatientId(payload.patient_id);

    await openPatient(payload.patient_id);

    setQrMessage(`Reference resolved. Loaded ${payload.patient_id}; continue reviewing the synthetic patient history.`);

  } catch (err) {

    setQrError(err.message || "Unable to resolve this reference.");

  } finally {

    setQrBusy(false);

  }

}



async function revokeQrReference() {

  const token = (qrToken || qrResolveInput).trim();

  if (!token) {

    setQrError("Create or enter a reference token to revoke it.");

    setQrMessage("");

    return;

  }

  setQrBusy(true);

  setQrError("");

  setQrMessage("");

  try {

    const response = await apiFetch(`${API}/api/qr/revoke`, {

      method: "POST",

      headers: { "Content-Type": "application/json", Accept: "application/json" },

      body: JSON.stringify({ token }),

    });

    const payload = await response.json().catch(() => null);

    if (!response.ok) throw new Error(payload?.detail || "Could not revoke this reference.");

    setQrMessage("Demo reference revoked. It can no longer be resolved.");

    setQrToken("");

  } catch (err) {

    setQrError(err.message || "Unable to revoke this reference.");

  } finally {

    setQrBusy(false);

  }

}



function medicationToDisplayName(item) {



  if (typeof item === "string") return item;



  if (item && typeof item === "object") {



    return (



      item.name ||



      item.generic_name ||



      item.medication_name ||



      item.brand_name ||



      ""



    );



  }



  return "";



}



function loadSelectedPatientMedications() {



  if (!selected) {



    setSafetyError("Open a patient record first, then load that patient's medication history.");



    return;



  }



const sourceMedications = [

    ...(Array.isArray(selected.medications) ? selected.medications : []),

    ...(Array.isArray(selected.medication_history) ? selected.medication_history : []),

  ];

  const names = [...new Set(sourceMedications

    .map(medicationToDisplayName)

    .map((name) => String(name).trim())

    .filter(Boolean))];



  if (names.length === 0) {



    setSafetyError("No medication history is available for this patient record.");



    setSafetyResult(null);



    return;



  }



  setMedicationInput(names.join("\n"));



  setSafetyResult(null);



  setSafetyError("");



}



async function runSafetyCheck(event) {



  event.preventDefault();



  const medications = medicationInput



    .split(/\n|,|;/)



    .map((name) => name.trim())



    .filter(Boolean);



  if (medications.length === 0) {



    setSafetyError("Enter at least one medication name.");



    setSafetyResult(null);



    return;



  }



  if (medications.length > 50) {



    setSafetyError("Enter no more than 50 medication names.");



    setSafetyResult(null);



    return;



  }



  setSafetyLoading(true);



  setSafetyError("");



  setSafetyResult(null);



  try {



    const response = await apiFetch(`${API}/api/safety/check`, {



      method: "POST",



      headers: {



        "Content-Type": "application/json",



        Accept: "application/json",



      },



      body: JSON.stringify({ medications }),



    });



    const data = await response.json().catch(() => null);



    if (!response.ok) {



      const detail = data?.detail;



      const message = Array.isArray(detail)



        ? detail.map((item) => item.msg).join(", ")



        : typeof detail === "string"



          ? detail



          : "The safety-check request failed.";



      throw new Error(message);



    }



    setSafetyResult(data);



  } catch (err) {



    setSafetyError(



      err.message ||



        "Unable to run the safety check. Confirm that the backend is running."



    );



  } finally {



    setSafetyLoading(false);



  }



}



  const filteredPatients = patients.filter((patient) =>



    `${patient.name} ${patient.id} ${patient.department}`



      .toLowerCase()



      .includes(search.toLowerCase())



  );



  const navItems = [



    { id: "overview", icon: "▦", label: "Dashboard" },



    { id: "patients", icon: "♙", label: "Patient records" },



    { id: "prescription", icon: "✚", label: "Prescription review" },



    { id: "access", icon: "▣", label: "QR & identity access" },



  ];



  const metrics = [



    {



      label: "Patients loaded",



      value: String(patients.length),



      note: "Demo records from backend",



      tone: "purple",



    },



    {



      label: "Patient record",



      value: selected ? "1" : "0",



      note: "Currently selected",



      tone: "blue",



    },



    {



      label: "Safety evaluation",



      value: "Pending",



      note: "Demo API connected",



      tone: "neutral",



    },



    {



      label: "Drug name review",



      value: "Pending",



      note: "Exact demo lookup available",



      tone: "neutral",



    },



    {



      label: "Interaction checks",



      value: "—",



      note: "Synthetic interaction table",



      tone: "neutral",



    },



    {



      label: "Renal dose checks",



      value: "—",



      note: "Awaiting supported rules",



      tone: "neutral",



    },



    {



      label: "QR record access",



      value: "Planned",



      note: "Not enabled yet",



      tone: "neutral",



    },



    {



      label: "Cloud visit uploads",



      value: "Planned",



      note: "Not enabled yet",



      tone: "neutral",



    },



  ];



  if (!isAuthenticated) {
    return (
      <div className="mg-app">
        <main className="mg-main-area" style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: "24px" }}>
          <section className="mg-panel" style={{ width: "min(100%, 440px)", padding: "32px" }}>
            <div className="mg-brand" style={{ marginBottom: "24px" }}>
              <div className="mg-brand-mark">M</div>
              <div><strong>MedGuard AI</strong><span>Medication safety</span></div>
            </div>
            <h1 style={{ marginBottom: "8px" }}>Staff sign in</h1>
            <p style={{ marginBottom: "24px" }}>Sign in with your configured demo staff account.</p>
            <form className="mg-visit-form" onSubmit={handleLogin}>
              <label htmlFor="mg-login-username">Username</label>
              <input id="mg-login-username" value={loginUsername} onChange={(event) => setLoginUsername(event.target.value)} autoComplete="username" required />
              <label htmlFor="mg-login-password">Password</label>
              <input id="mg-login-password" type="password" value={loginPassword} onChange={(event) => setLoginPassword(event.target.value)} autoComplete="current-password" required />
              {loginError && <div className="mg-error" role="alert">{loginError}</div>}
              <button className="mg-primary-button" type="submit" disabled={loginBusy}>{loginBusy ? "Signing in…" : "Sign in"}</button>
            </form>
            <p className="mg-safety-note" style={{ marginTop: "20px" }}>Synthetic local demo only. Use the credentials configured in your backend environment.</p>
          </section>
        </main>
      </div>
    );
  }

  return (



    <div className="mg-app">



      <aside className="mg-sidebar">



        <div className="mg-brand">



          <div className="mg-brand-mark">M</div>



          <div>



            <strong>MedGuard AI</strong>



            <span>Medication safety</span>



          </div>



        </div>



        <div className="mg-side-search">
          <span aria-hidden="true">⌕</span>
          <input
            type="text"
            placeholder="Filter navigation..."
            aria-label="Filter navigation"
            style={{ flex: 1, minWidth: 0, background: "transparent", border: 0, outline: "none", color: "inherit", font: "inherit" }}
            value={navSearch}
            onChange={(event) => setNavSearch(event.target.value)}
          />
          {navSearch && (
            <button
              type="button"
              className="mg-nav-search-clear"
              style={{ background: "transparent", border: 0, color: "inherit", cursor: "pointer", fontSize: "20px" }}
              aria-label="Clear navigation filter"
              onClick={() => setNavSearch("")}
            >
              ×
            </button>
          )}
        </div>



        <p className="mg-side-label">WORKSPACE</p>



        <nav className="mg-nav">



          {navItems
            .filter((item) =>
              item.label.toLowerCase().includes(navSearch.trim().toLowerCase())
            )
            .map((item) => (



            <button



              key={item.id}



              className={`mg-nav-item ${page === item.id ? "active" : ""}`}



              onClick={() => setPage(item.id)}



            >



              <span className="mg-nav-icon">{item.icon}</span>



              <span>{item.label}</span>



              {page === item.id && <span className="mg-nav-indicator" />}



            </button>



          ))}



        </nav>



        <div className="mg-sidebar-bottom">



          <span className="mg-status-dot" />



          <div>



            <strong>Prototype environment</strong>



            <small>Synthetic records only</small>



          </div>



        </div>



      </aside>



      <div className="mg-main-area">



        <header className="mg-topbar">



          <div className="mg-topbar-left">



            <button



              className="mg-menu-button"



              onClick={() => setPage("overview")}



              aria-label="Go to dashboard"



            >



              ☰



            </button>



            <span className="mg-topbar-divider" />



            <span className="mg-breadcrumb">MedGuard AI</span>



            <span className="mg-breadcrumb-separator">/</span>



            <strong>



              {navItems.find((item) => item.id === page)?.label}



            </strong>



          </div>



          <div className="mg-topbar-right">



            <span className="mg-environment-tag">DEMO</span>
            <button type="button" className="mg-secondary-button" onClick={handleLogout}>Sign out</button>



            <div className="mg-user-avatar">D</div>



          </div>



        </header>



        <main className="mg-content">



          <div className="mg-page-heading">



            <div>



              <p className="mg-eyebrow">CLINICAL WORKSPACE</p>



              <h1>



                {page === "overview"



                  ? "Medication Safety Dashboard"



                  : page === "patients"



                    ? "Patient Records"



                    : page === "prescription"



                      ? "Prescription Review"



                      : "QR & Identity Access"}



              </h1>



              <p className="mg-page-description">



                Review available history and prepare for medication-safety



                assessment.



              </p>



            </div>



            <span className="mg-demo-badge">



              <span /> Synthetic demo data



            </span>



          </div>



          {error && <div className="mg-error">{error}</div>}



          {page === "overview" && (



            <>



              <div className="mg-toolbar">



                <div className="mg-tabs">



                  <button



                    className="selected"



                    onClick={() => setPage("overview")}



                  >



                    Overview



                  </button>



                  <button onClick={() => setPage("patients")}>



                    Patient records



                  </button>



                  <button onClick={() => setPage("prescription")}>



                    Prescription review



                  </button>



                </div>



                <span className="mg-updated">



                  {loading ? "Loading records..." : "Backend connection checked"}



                </span>



              </div>



              <section className="mg-metric-grid">



                {metrics.map((metric, index) => (



                  <article



                    className={`mg-metric-card tone-${metric.tone}`}



                    key={metric.label}



                  >



                    <div className="mg-metric-top">



                      <span>{metric.label}</span>



                      <span className="mg-metric-symbol">



                        {["♙", "▤", "✚", "⌕", "⇄", "◈", "▣", "☁"][index]}



                      </span>



                    </div>



                    <strong className="mg-metric-value">{metric.value}</strong>



                    <span className="mg-metric-note">{metric.note}</span>



                  </article>



                ))}



              </section>



              <section className="mg-lower-grid">



                <article className="mg-panel">



                  <div className="mg-panel-heading">



                    <div>



                      <h2>Patient directory</h2>



                      <p>Select a record to inspect the available history.</p>



                    </div>



                    <button



                      className="mg-text-button"



                      onClick={() => setPage("patients")}



                    >



                      View all



                    </button>



                  </div>



                  <label className="mg-search-box">



                    <span>⌕</span>



                    <input



                      value={search}



                      onChange={(event) => setSearch(event.target.value)}



                      placeholder="Search patient, ID or department..."



                    />



                  </label>



                  {loading ? (



                    <p className="mg-empty-text">Loading patients...</p>



                  ) : (



                    <div className="mg-patient-list">



                      {filteredPatients.map((patient) => (



                        <button



                          key={patient.id}



                          className={`mg-patient-row ${



                            selected?.id === patient.id ? "selected" : ""



                          }`}



                          onClick={() => openPatient(patient.id)}



                        >



                          <span className="mg-patient-avatar">



                            {patient.name.charAt(0)}



                          </span>



                          <span className="mg-patient-info">



                            <strong>{patient.name}</strong>



                            <small>{patient.id}</small>



                            <small>{patient.department}</small>



                          </span>



                          <span className="mg-row-arrow">›</span>



                        </button>



                      ))}



                      {!loading && filteredPatients.length === 0 && (



                        <p className="mg-empty-text">No matching patients.</p>



                      )}



                    </div>



                  )}



                </article>



                <article className="mg-panel">



                  <div className="mg-panel-heading">



                    <div>



                      <h2>Medical history</h2>



                      <p>Available information for the selected patient.</p>



                    </div>



                    <span className="mg-outline-tag">DEMO</span>



                  </div>



                  {!selected ? (



                    <div className="mg-empty-state">



                      <div className="mg-empty-icon">▤</div>



                      <strong>Select a patient</strong>



                      <p>The retrieved record will appear here.</p>



                    </div>



                  ) : (



                    <div className="mg-history-content">



                      <div className="mg-selected-patient">



                        <span className="mg-patient-avatar large">



                          {selected.name.charAt(0)}



                        </span>



                        <div>



                          <strong>{selected.name}</strong>



                          <small>{selected.id}</small>



                        </div>



                      </div>



                      <div className="mg-detail-row">



                        <span>Age</span>



                        <strong>{selected.age}</strong>



                      </div>



                      <div className="mg-detail-row">



                        <span>Department</span>



                        <strong>{selected.department}</strong>



                      </div>



                      <div className="mg-detail-row">



                        <span>Record status</span>



                        <strong>{selected.records_status}</strong>



                      </div>



                      <h3>Diagnoses</h3>



                      {selected.diagnoses?.length ? (



                        <ul>



                          {selected.diagnoses.map((item, index) => (



                            <li key={index}>{item}</li>



                          ))}



                        </ul>



                      ) : (



                        <p className="mg-empty-text">No diagnoses loaded.</p>



                      )}



                      <h3>Medication history</h3>



                      {selected.medications?.length ? (



                        <ul>



                          {selected.medications.map((item, index) => (



                            <li key={index}>{item}</li>



                          ))}



                        </ul>



                      ) : (



                        <p className="mg-empty-text">No medications loaded.</p>



                      )}



                      <h3>Previous visits</h3>

                      {selected.visits?.length ? (

                        <ul className="mg-visit-list">

                          {selected.visits.map((visit, index) => (

                            <li key={visit.id ?? visit.visit_id ?? index}>

                              <strong>{visit.visit_date ?? visit.date ?? visit.created_at ?? "Date not recorded"}</strong>

                              {visit.department ? ` · ${visit.department}` : ""}

                              {visit.note ? <div>{visit.note}</div> : null}

                              {Array.isArray(visit.medications) && visit.medications.length > 0 ? (

                                <div>Medicines: {visit.medications.map(medicationToDisplayName).filter(Boolean).join(", ")}</div>

                              ) : null}

                            </li>

                          ))}

                        </ul>

                      ) : (

                        <p className="mg-empty-text">No previous visits are stored for this patient.</p>

                      )}



                    </div>



                  )}



                  <div className="mg-safety-note">



                    <strong>Safety status:</strong> Not evaluated. The medication



                    safety engine has not yet been connected.



                  </div>



                </article>



              </section>



            </>



          )}



          {page === "patients" && (



            <section className="mg-panel mg-full-panel">



              <div className="mg-panel-heading">



                <div>



                  <h2>Patient records</h2>



                  <p>Search the demo patient records provided by the backend.</p>



                </div>



                <span className="mg-outline-tag">{patients.length} records</span>



              </div>



              <label className="mg-search-box">



                <span>⌕</span>



                <input



                  value={search}



                  onChange={(event) => setSearch(event.target.value)}



                  placeholder="Search patient, ID or department..."



                />



              </label>



              <div className="mg-table-wrap">



                <table className="mg-patient-table">



                  <thead>



                    <tr>



                      <th>Patient</th>



                      <th>Patient ID</th>



                      <th>Age</th>



                      <th>Department</th>



                      <th>Record status</th>



                      <th>Action</th>



                    </tr>



                  </thead>



                  <tbody>



                    {filteredPatients.map((patient) => (



                      <tr key={patient.id}>



                        <td>{patient.name}</td>



                        <td>{patient.id}</td>



                        <td>{patient.age}</td>



                        <td>{patient.department}</td>



                        <td>{patient.records_status}</td>



                        <td>



                          <button



                            className="mg-text-button"



                            onClick={() => openPatient(patient.id)}



                          >



                            Open record



                          </button>



                        </td>



                      </tr>



                    ))}



                  </tbody>



                </table>



              </div>



              {selected && (



                <div className="mg-inline-record">



                  <h3>Selected record: {selected.name}</h3>



                  <p>Department: {selected.department}</p>



                  <p>Diagnoses: {selected.diagnoses?.join(", ") || "None loaded"}</p>



                  <p>



                    Medication history:{" "}



                    {selected.medications?.join(", ") || "None loaded"}



                  </p>



                </div>



              )}



            </section>



          )}



          {page === "prescription" && (



            <section className="mg-panel mg-full-panel">



              <div className="mg-panel-heading">



                <div>



                  <h2>Prescription review</h2>



                  <p>



                    Check a proposed medication list against the synthetic demo



                    interaction reference and review any unresolved medicine names.



                  </p>



                </div>



                <span className="mg-outline-tag">Demo safety check</span>



              </div>



              {selected ? (



                <div className="mg-prescription-patient">



                  <div className="mg-prescription-patient-heading">



                    <span className="mg-patient-avatar large">



                      {(selected.name || "P").charAt(0)}



                    </span>



                    <div>



                      <p className="mg-eyebrow">SELECTED PATIENT RECORD</p>



                      <strong>{selected.name}</strong>



                      <span>{selected.id} · {selected.department || "Department not recorded"}</span>



                    </div>



                    <button



                      type="button"



                      className="mg-secondary-button"



                      onClick={loadSelectedPatientMedications}



                    >



                      Load patient medicines



                    </button>



                  </div>



                  <div className="mg-patient-context-grid">



                    <div>



                      <span>Age</span>



                      <strong>{selected.age ?? "Not recorded"}</strong>



                    </div>



                    <div>



                      <span>Diagnoses on record</span>



                      <strong>



                        {Array.isArray(selected.diagnoses) && selected.diagnoses.length



                          ? selected.diagnoses.join(", ")



                          : "Not recorded"}



                      </strong>



                    </div>



                    <div>



                      <span>Medication history entries</span>



                      <strong>



                        {Array.isArray(selected.medications) ? selected.medications.length : 0}



                      </strong>



                    </div>

                    <div>

                      <span>Saved visits</span>

                      <strong>{Array.isArray(selected.visits) ? selected.visits.length : 0}</strong>

                    </div>



                  </div>



                </div>



              ) : (



                <div className="mg-empty-state mg-prescription-no-patient">



                  <div className="mg-empty-icon">♙</div>



                  <strong>No patient selected</strong>



                  <p>



                    You can enter a demo medication list below, or open a patient



                    record first to load their available medication history.



                  </p>



                  <button



                    type="button"



                    className="mg-secondary-button"



                    onClick={() => setPage("patients")}



                  >



                    Open patient records



                  </button>



                </div>



              )}



              <div className="mg-safety-note">



                Synthetic demonstration only. This is not a complete medication



                safety assessment. A qualified clinician or pharmacist must



                independently review all results. Only the fields displayed here



                are available; missing patient context is not inferred.



              </div>



              <form className="mg-safety-form" onSubmit={runSafetyCheck}>



                <label htmlFor="mg-medications">Medication names</label>



                <p className="mg-form-help">



                  Enter one medicine per line, or separate names with commas or



                  semicolons. Only names in the demo reference can be resolved.



                </p>



                <textarea



                  id="mg-medications"



                  className="mg-medication-input"



                  value={medicationInput}



                  onChange={(event) => setMedicationInput(event.target.value)}



                  placeholder={"Coumadin\nAdvil\nmysterymed"}



                  rows={6}



                  maxLength={5000}



                  required



                />



                <div className="mg-form-actions">



                  <button



                    type="submit"



                    className="mg-primary-button"



                    disabled={safetyLoading}



                  >



                    {safetyLoading ? "Checking..." : "Check prescription"}



                  </button>



                  <button



                    type="button"



                    className="mg-secondary-button"



                    onClick={() => {



                      setMedicationInput("");



                      setSafetyResult(null);



                      setSafetyError("");



                    }}



                    disabled={safetyLoading}



                  >



                    Clear



                  </button>



                  <button



                    type="button"



                    className="mg-text-button"



                    onClick={() => {



                      setMedicationInput("Coumadin\nAdvil\nmysterymed");



                      setSafetyResult(null);



                      setSafetyError("");



                    }}



                    disabled={safetyLoading}



                  >



                    Load demo example



                  </button>



                </div>



              </form>



              {safetyError && (



                <div className="mg-error mg-result-message" role="alert">



                  {safetyError}



                </div>



              )}



              {safetyResult && (



                <section className="mg-safety-results" aria-live="polite">



                  <div className="mg-results-heading">



                    <div>



                      <p className="mg-eyebrow">ANALYSIS RESULTS</p>



                      <h3>Medication review results</h3>



                    </div>



                    <span className="mg-demo-badge">Synthetic demo</span>



                  </div>



                  <div className="mg-safety-note">{safetyResult.summary}</div>



                  <h3>Medication name resolution</h3>



                  <div className="mg-resolution-list">



                    {(safetyResult.resolved_medications || []).map((item, index) => (



                      <article



                        className="mg-resolution-row"



                        key={`${item.input_name}-${index}`}



                      >



                        <div className="mg-resolution-main">



                          <strong>{item.input_name}</strong>



                          <span>



                            {item.generic_name



                              ? `Generic: ${item.generic_name}`



                              : "Generic name not confirmed"}



                          </span>



                          <small>{item.message}</small>



                          {item.suggested_matches?.length > 0 && (



                            <div className="mg-match-suggestions">



                              <strong>Possible matches — confirm manually:</strong>



                              {item.suggested_matches.map((match, matchIndex) => (



                                <span key={`${match.generic_name}-${matchIndex}`}>



                                  {match.candidate_name} → {match.generic_name}



                                  {" "}({Math.round(match.similarity * 100)}% text similarity)



                                </span>



                              ))}



                            </div>



                          )}



                        </div>



                        <span



                          className={



                            item.status === "resolved"



                              ? "mg-status-pill mg-status-resolved"



                              : "mg-status-pill mg-status-review"



                          }



                        >



                          {item.status === "resolved" ? "Resolved" : "Manual review"}



                        </span>



                      </article>



                    ))}



                  </div>



                  <h3>Interaction alerts ({safetyResult.alerts?.length || 0})</h3>



                  {safetyResult.alerts?.length ? (



                    <div className="mg-alert-list">



                      {safetyResult.alerts.map((alert, index) => (



                        <article className="mg-alert-card" key={index}>



                          <div className="mg-alert-topline">



                            <span className="mg-alert-type">



                              {(alert.alert_type || "alert").replaceAll("_", " ")}



                            </span>



                            <span



                              className={`mg-status-pill ${



                                alert.severity?.toLowerCase() === "high"



                                  ? "mg-status-high"



                                  : "mg-status-review"



                              }`}



                            >



                              {alert.severity} severity



                            </span>



                          </div>



                          <h4>{(alert.medications || []).join(" + ")}</h4>



                          <p>



                            <strong>Suggested review action:</strong>{" "}



                            {alert.suggested_action}



                          </p>



                          <p>



                            <strong>Evidence status:</strong> {alert.evidence_status}



                          </p>



                          <p>



                            <strong>Confidence:</strong> {alert.confidence}



                          </p>



                          <p className="mg-alert-limitation">{alert.limitations}</p>



                        </article>



                      ))}



                    </div>



                  ) : (



                    <div className="mg-empty-state">



                      <strong>No matching interaction rule found</strong>



                      <p>



                        No issue was found in the demo interaction table for the



                        recognized medication pairs. This does not mean the regimen



                        is safe.



                      </p>



                    </div>



                  )}



                  {safetyResult.manual_review_required?.length > 0 && (



                    <>



                      <h3>Manual review required</h3>



                      <div className="mg-manual-review">



                        {safetyResult.manual_review_required.map((item, index) => (



                          <p key={`${item.input_name}-${index}`}>



                            <strong>{item.input_name}:</strong> {item.message}



                          </p>



                        ))}



                      </div>



                    </>



                  )}



                  <p className="mg-disclaimer">



                    MedGuard AI is a decision-support prototype. These synthetic



                    rules are not clinically validated. Do not start, stop, or



                    change medication based on this demo. Clinical decisions remain



                    with the authorized care team.



                  </p>



                </section>



              )}



            </section>



          )}



          {page === "access" && (



            <section className="mg-panel mg-full-panel">



              <div className="mg-panel-heading">



                <div>



                  <h2>QR & identity access</h2>



                  <p>Planned secure retrieval of authorized patient records.</p>



                </div>



                <span className="mg-outline-tag">In development</span>



              </div>



              <div className="mg-feature-grid">



                <div className="mg-feature-card">



                  <span>01</span>



                  <h3>QR record reference</h3>



                  <p>Use a secure reference rather than storing medical details in the QR code.</p>



                </div>



                <div className="mg-feature-card">



                  <span>02</span>



                  <h3>Identity verification</h3>



                  <p>Authenticate the requester and check their permissions.</p>



                </div>



                <div className="mg-feature-card">



                  <span>03</span>



                  <h3>Visit record upload</h3>



                  <p>Save validated visit data and record access events.</p>



                </div>



              </div>



              <section className="mg-qr-panel">

                <div className="mg-panel-heading">

                  <div>

                    <h2>QR record reference</h2>

                    <p>Create a time-limited reference, resolve it to load a demo patient's history, or revoke it.</p>

                  </div>

                  <span className="mg-outline-tag">Demo token · 8 hours</span>

                </div>

                <form className="mg-visit-form" onSubmit={createQrReference}>

                  <label htmlFor="mg-qr-patient">Patient for reference</label>

                  <select id="mg-qr-patient" value={qrPatientId || selected?.id || ""} onChange={(event) => setQrPatientId(event.target.value)} required>

                    <option value="" disabled>Select a synthetic patient</option>

                    {patients.map((patient) => <option key={patient.id} value={patient.id}>{patient.name} ({patient.id})</option>)}

                  </select>

                  <div className="mg-form-actions">

                    <button className="mg-primary-button" type="submit" disabled={qrBusy || loading}>{qrBusy ? "Working…" : "Create reference"}</button>

                    <button className="mg-secondary-button" type="button" disabled={qrBusy} onClick={revokeQrReference}>Revoke current token</button>

                  </div>

                </form>

                {qrToken && (

                  <div className="mg-qr-token-block">

                    <strong>Scan this demo QR reference</strong>

                    <div className="mg-qr-image-frame" aria-label="QR code containing a temporary synthetic patient reference">

                      <QRCodeSVG value={qrToken} size={220} level="M" includeMargin />

                    </div>

                    <code>{qrToken}</code>

                    <button className="mg-secondary-button" type="button" onClick={() => { navigator.clipboard?.writeText(qrToken).then(() => setQrMessage("Reference copied to clipboard.")).catch(() => setQrMessage("Select and copy the token manually.")); }}>Copy token</button>

                    <p>The QR image contains only a temporary reference token, not patient details. Scanning with a camera is not yet connected; paste the token below to resolve it. Treat the token like a bearer credential.</p>

                  </div>

                )}

                <form className="mg-visit-form mg-qr-resolve-form" onSubmit={resolveQrReference}>

                  <label htmlFor="mg-qr-resolve-token">Resolve a reference</label>

                  <input id="mg-qr-resolve-token" value={qrResolveInput} onChange={(event) => setQrResolveInput(event.target.value)} maxLength={200} placeholder="Paste token from a generated reference" required />

                  <div className="mg-form-actions"><button className="mg-primary-button" type="submit" disabled={qrBusy}>{qrBusy ? "Resolving…" : "Resolve and open history"}</button></div>

                </form>

                {qrError && <div className="mg-error mg-result-message" role="alert">{qrError}</div>}

                {qrMessage && <div className="mg-success-message" role="status">{qrMessage}</div>}

                <div className="mg-safety-note">Prototype limitation: this demo has no user login or authorization, so the token is not sufficient for real patient-data security. Do not use real patient information. A production system must enforce authenticated roles, audit access, protect token transport and support consent/revocation.</div>

              </section>



              <section className="mg-visit-upload-panel">

                <div className="mg-panel-heading">

                  <div>

                    <h2>Save a current visit</h2>

                    <p>Store a synthetic demo visit in SQLite and reload the patient's history.</p>

                  </div>

                  <span className="mg-outline-tag">SQLite connected</span>

                </div>



                <form className="mg-visit-form" onSubmit={saveVisit}>

                  <label htmlFor="mg-visit-patient">Demo patient</label>

                  <select

                    id="mg-visit-patient"

                    value={visitPatientId || selected?.id || ""}

                    onChange={(event) => setVisitPatientId(event.target.value)}

                    required

                  >

                    <option value="" disabled>Select a patient</option>

                    {patients.map((patient) => (

                      <option key={patient.id} value={patient.id}>

                        {patient.name} ({patient.id})

                      </option>

                    ))}

                  </select>



                  <div className="mg-visit-form-grid">

                    <div>

                      <label htmlFor="mg-visit-date">Visit date</label>

                      <input id="mg-visit-date" type="date" value={visitDate} onChange={(event) => setVisitDate(event.target.value)} required />

                    </div>

                    <div>

                      <label htmlFor="mg-visit-department">Department / ward</label>

                      <input id="mg-visit-department" value={visitDepartment} onChange={(event) => setVisitDepartment(event.target.value)} maxLength={100} placeholder="e.g. Cardiology" />

                    </div>

                  </div>



                  <label htmlFor="mg-visit-notes">Visit notes</label>

                  <textarea id="mg-visit-notes" value={visitNotes} onChange={(event) => setVisitNotes(event.target.value)} maxLength={4000} rows={3} placeholder="Enter a short synthetic demo note" />



                  <label htmlFor="mg-visit-medications">Medicines for this visit</label>

                  <p className="mg-form-help">Enter one medicine per line, or separate with commas or semicolons. Maximum 50 names.</p>

                  <textarea id="mg-visit-medications" value={visitMedications} onChange={(event) => setVisitMedications(event.target.value)} maxLength={5000} rows={4} placeholder={"warfarin\nibuprofen"} />



                  <div className="mg-form-actions">

                    <button className="mg-primary-button" type="submit" disabled={visitSaving || loading}>

                      {visitSaving ? "Saving visit…" : "Save visit to SQLite"}

                    </button>

                    <button className="mg-secondary-button" type="button" disabled={visitSaving} onClick={() => { setVisitDate(new Date().toISOString().slice(0, 10)); setVisitDepartment(""); setVisitNotes(""); setVisitMedications(""); setVisitError(""); setVisitMessage(""); }}>

                      Clear form

                    </button>

                  </div>

                </form>

                {visitError && <div className="mg-error mg-result-message" role="alert">{visitError}</div>}

                {visitMessage && <div className="mg-success-message" role="status">{visitMessage}</div>}

              </section>



              <div className="mg-safety-note">

                Demo only: use synthetic data. QR scanning, biometric authentication and real cloud uploads are not connected. This form saves a visit to the local SQLite demo database; it is not a secure clinical record system.

              </div>



            </section>



          )}



          <footer className="mg-footer">



            <span>MedGuard AI</span>



            <span>Medication safety prototype · Synthetic data only</span>



          </footer>



        </main>



      </div>



    </div>



  );



}



export default App;
