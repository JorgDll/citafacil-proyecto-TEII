/* Cuentas del panel (HU-6): tarjetas "Usuarios" y "Actividad" con sus ventanas.
 *
 * Depende de globales que define admin.html: $, api, post, can, ME, toast, logout.
 * Todo texto que viene del servidor se inserta con textContent (nunca con innerHTML).
 */

const staff = { catalog: null, users: [], editing: null, audit: { offset: 0, limit: 20, total: 0 } };

const ACTION_LABEL = {
  "appointment.confirmed": "Confirmó una reserva",
  "appointment.done": "Marcó una reserva como realizada",
  "appointment.cancelled": "Canceló una reserva",
  "appointment.reopened": "Devolvió una reserva a pendiente",
  "appointment.deleted": "Eliminó una reserva",
  "appointment.customer_cancelled": "El cliente canceló su cita (enlace)",
  "appointment.customer_rescheduled": "El cliente reprogramó su cita (enlace)",
  "service.created": "Creó un servicio",
  "service.updated": "Editó un servicio",
  "service.deleted": "Eliminó un servicio",
  "reminders.run": "Envió recordatorios",
  "user.created": "Creó un usuario",
  "user.updated": "Editó un usuario",
  "user.deactivated": "Desactivó un usuario",
  "user.reactivated": "Reactivó un usuario",
  "user.password_reset": "Restableció una contraseña",
  "auth.login": "Inició sesión",
  "auth.login_failed": "Intento de acceso fallido",
  "auth.logout": "Cerró sesión",
  "auth.password_changed": "Cambió su contraseña",
};
const ACTION_GROUPS = [
  ["", "Todas las acciones"], ["appointment.", "Reservas"], ["service.", "Servicios"],
  ["user.", "Usuarios"], ["auth.", "Acceso"], ["reminders.run", "Recordatorios"],
];

/* ---------- utilidades ---------- */
function mk(tag, props, text){
  const e = document.createElement(tag);
  Object.assign(e, props || {});
  if(text != null) e.textContent = text;
  return e;
}
// created_at de las cuentas está en UTC sin zona; el del registro ya viene en hora local del negocio.
const whenUtc = iso => iso ? new Date(iso + "Z").toLocaleString("es-CL", {dateStyle:"short", timeStyle:"short"}) : "Nunca";
const whenLocal = iso => iso ? new Date(iso).toLocaleString("es-CL", {dateStyle:"short", timeStyle:"short"}) : "";
const shortWhen = iso => iso ? new Date(iso).toLocaleString("es-CL", {day:"2-digit", month:"2-digit", hour:"2-digit", minute:"2-digit"}) : "";

function openModal(id){ $(id).classList.add("open"); }
function closeModal(id){ $(id).classList.remove("open"); }

function initStaff(){
  const mount = $("staffMount");
  mount.innerHTML = "";
  if(can("users.manage")){ mount.insertAdjacentHTML("beforeend", USERS_HTML); bindUsers(); loadUsers(); }
  if(can("audit.view")){ mount.insertAdjacentHTML("beforeend", AUDIT_HTML); bindAudit(); loadAuditActors(); loadAudit(0); }
}

/* =====================  USUARIOS  ===================== */
const USERS_HTML = `
<div class="card" id="cardUsers">
  <h2><i class="fa-solid fa-users-gear"></i> Usuarios y permisos</h2>
  <div class="toolbar"><button class="btn sm" id="uNew"><i class="fa-solid fa-user-plus"></i> Nuevo usuario</button></div>
  <div style="overflow-x:auto">
    <table>
      <thead><tr><th>Usuario</th><th>Nombre</th><th>Rol</th><th>Estado</th><th>Último acceso</th><th>Acciones</th></tr></thead>
      <tbody id="uBody"><tr><td colspan="6" class="empty">Cargando…</td></tr></tbody>
    </table>
  </div>
</div>
<div class="modal-bg" id="uModal" role="dialog" aria-modal="true" aria-labelledby="uTitle">
  <div class="modal">
    <h3 id="uTitle"></h3>
    <div class="field" id="uUserField"><label for="uUsername">Usuario (minúsculas, números, . _ -)</label><input id="uUsername" autocomplete="off" autocapitalize="off" spellcheck="false" /></div>
    <div class="field"><label for="uDisplay">Nombre</label><input id="uDisplay" autocomplete="off" /></div>
    <div class="field"><label for="uRole">Rol (rellena los permisos de partida)</label><select id="uRole"></select></div>
    <label>Permisos</label>
    <div class="perm-grid" id="uPerms"></div>
    <div class="field" id="uPassField" style="margin-top:14px"><label for="uPass">Contraseña temporal (mínimo 10; deberá cambiarla al entrar)</label><input id="uPass" autocomplete="off" /></div>
    <label class="perm" id="uActiveField" style="margin-top:12px"><input type="checkbox" id="uActive" /> Cuenta activa</label>
    <div class="msg-err hide" id="uMsg"></div>
    <div class="actions" style="display:flex;gap:10px"><button class="btn ghost" id="uCancel">Cancelar</button><button class="btn" id="uSave"><i class="fa-solid fa-check"></i> Guardar</button></div>
  </div>
</div>
<div class="modal-bg" id="rModal" role="dialog" aria-modal="true" aria-labelledby="rTitle">
  <div class="modal">
    <h3 id="rTitle"></h3>
    <p style="color:var(--muted);font-size:.9rem;margin-bottom:14px">Se cerrarán sus sesiones y tendrá que cambiar esta contraseña temporal al entrar.</p>
    <div class="field"><label for="rPass">Contraseña temporal (mínimo 10)</label><input id="rPass" autocomplete="off" /></div>
    <div class="msg-err hide" id="rMsg"></div>
    <div class="actions" style="display:flex;gap:10px"><button class="btn ghost" id="rCancel">Cancelar</button><button class="btn" id="rSave">Restablecer</button></div>
  </div>
</div>`;

function bindUsers(){
  $("uNew").onclick = () => openUserModal(null);
  $("uCancel").onclick = () => closeModal("uModal");
  $("uSave").onclick = saveUser;
  $("uRole").onchange = () => fillPerms(staff.catalog.roles.find(r => r.key === $("uRole").value).permissions);
  $("rCancel").onclick = () => closeModal("rModal");
  $("rSave").onclick = saveReset;
  ["uModal","rModal"].forEach(id => $(id).addEventListener("mousedown", e => { if(e.target === $(id)) closeModal(id); }));
}

async function loadUsers(){
  try{
    if(!staff.catalog) staff.catalog = await api("/api/admin/permissions");
    staff.users = await api("/api/admin/users");
    renderUsers();
  }catch(e){
    if(e.status === 401){ logout(); return; }
    const td = mk("td", {colSpan: 6, className: "empty"}, "Error: " + e.message);
    $("uBody").replaceChildren(mk("tr", {}, null)); $("uBody").firstChild.appendChild(td);
  }
}

function badge(text, cls){ return mk("span", {className: "badge " + cls}, text); }

function renderUsers(){
  const body = $("uBody"); body.replaceChildren();
  staff.users.forEach(u => {
    const tr = mk("tr");
    tr.appendChild(mk("td", {className: "mono"}, u.username));
    tr.appendChild(mk("td", {}, u.display_name));
    tr.appendChild(mk("td", {}, u.role_label));
    const st = mk("td");
    st.appendChild(u.active ? badge("Activo", "b-done") : badge("Desactivado", "b-cancelled"));
    if(u.locked) st.append(" ", badge("Bloqueado", "b-pending"));
    if(u.must_change_password) st.append(" ", badge("Debe cambiar la clave", "b-neutral"));
    tr.appendChild(st);
    tr.appendChild(mk("td", {className: "mono"}, whenUtc(u.last_login_at)));

    const acts = mk("div", {className: "actions"});
    const mine = u.id === ME.id;
    const btn = (cls, title, icon, fn) => { const b = mk("button", {className: "ico " + cls, title}); b.appendChild(mk("i", {className: icon})); b.onclick = fn; return b; };
    // Solo un propietario gestiona cuentas de propietario (el servidor también lo exige).
    if(u.role !== "owner" || ME.role === "owner"){
      acts.appendChild(btn("warn", "Editar", "fa-solid fa-pen", () => openUserModal(u)));
      acts.appendChild(btn("warn", "Restablecer contraseña", "fa-solid fa-key", () => openResetModal(u)));
      if(!mine) acts.appendChild(btn(u.active ? "del" : "ok", u.active ? "Desactivar" : "Reactivar", "fa-solid fa-power-off", () => toggleActive(u)));
    }
    const td = mk("td"); td.appendChild(acts); tr.appendChild(td);
    body.appendChild(tr);
  });
}

function fillPerms(selected){
  const box = $("uPerms"); box.replaceChildren();
  const isOwnerRole = $("uRole").value === "owner";
  staff.catalog.permissions.forEach(p => {
    const lbl = mk("label", {className: "perm"});
    const cb = mk("input", {type: "checkbox", value: p.key});
    cb.checked = isOwnerRole || selected.includes(p.key);
    // El propietario lo tiene todo; y nadie puede dar un permiso que él mismo no tiene.
    const blocked = isOwnerRole || (ME.role !== "owner" && !can(p.key));
    cb.disabled = blocked;
    if(blocked) lbl.classList.add("off");
    lbl.append(cb, mk("span", {}, p.label));
    box.appendChild(lbl);
  });
}

function openUserModal(user){
  staff.editing = user;
  $("uTitle").textContent = user ? "Editar a " + user.username : "Nuevo usuario";
  $("uUserField").classList.toggle("hide", !!user);
  $("uPassField").classList.toggle("hide", !!user);
  $("uActiveField").classList.toggle("hide", !user);
  $("uUsername").value = ""; $("uPass").value = "";
  $("uDisplay").value = user ? user.display_name : "";
  $("uActive").checked = user ? user.active : true;
  const sel = $("uRole"); sel.replaceChildren();
  staff.catalog.roles.forEach(r => {
    if(r.key === "owner" && ME.role !== "owner") return;           // no se puede crear propietarios sin serlo
    sel.appendChild(mk("option", {value: r.key}, r.label));
  });
  sel.value = user ? user.role : "reception";
  fillPerms(user ? user.permissions : staff.catalog.roles.find(r => r.key === sel.value).permissions);
  $("uMsg").classList.add("hide");
  openModal("uModal");
  (user ? $("uDisplay") : $("uUsername")).focus();
}

async function saveUser(){
  const perms = [...$("uPerms").querySelectorAll("input:checked")].map(i => i.value);
  const role = $("uRole").value, display_name = $("uDisplay").value.trim();
  const msg = $("uMsg"); msg.classList.add("hide");
  try{
    if(staff.editing){
      await api("/api/admin/users/" + staff.editing.id, {method: "PATCH", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({display_name, role, permissions: perms, active: $("uActive").checked})});
    }else{
      await post("/api/admin/users", {username: $("uUsername").value.trim(), display_name, role, permissions: perms, password: $("uPass").value});
    }
    closeModal("uModal"); toast("Usuario guardado", "ok"); loadUsers(); loadAuditActors(); loadAudit(0);
  }catch(e){ msg.textContent = e.message; msg.classList.remove("hide"); }
}

async function toggleActive(u){
  try{
    await api("/api/admin/users/" + u.id, {method: "PATCH", headers: {"Content-Type": "application/json"}, body: JSON.stringify({active: !u.active})});
    toast(u.active ? "Usuario desactivado" : "Usuario reactivado", "ok"); loadUsers(); loadAudit(0);
  }catch(e){ toast(e.message, "err"); }
}

function openResetModal(u){
  staff.editing = u;
  $("rTitle").textContent = "Restablecer la contraseña de " + u.username;
  $("rPass").value = ""; $("rMsg").classList.add("hide");
  openModal("rModal"); $("rPass").focus();
}

async function saveReset(){
  const msg = $("rMsg"); msg.classList.add("hide");
  try{
    await post("/api/admin/users/" + staff.editing.id + "/reset-password", {new_password: $("rPass").value});
    closeModal("rModal"); toast("Contraseña restablecida", "ok"); loadUsers(); loadAudit(0);
  }catch(e){ msg.textContent = e.message; msg.classList.remove("hide"); }
}

/* =====================  ACTIVIDAD  ===================== */
const AUDIT_HTML = `
<div class="card" id="cardAudit">
  <h2><i class="fa-solid fa-clipboard-list"></i> Actividad</h2>
  <div class="toolbar">
    <div class="field"><label for="aUser">Usuario</label><select id="aUser"><option value="">Todos</option></select></div>
    <div class="field"><label for="aAction">Acción</label><select id="aAction"></select></div>
    <div class="field"><label for="aFrom">Desde</label><input type="date" id="aFrom" /></div>
    <div class="field"><label for="aTo">Hasta</label><input type="date" id="aTo" /></div>
    <button class="btn ghost sm" id="aSearch"><i class="fa-solid fa-magnifying-glass"></i> Buscar</button>
    <button class="btn ghost sm" id="aClear">Limpiar</button>
  </div>
  <div style="overflow-x:auto">
    <table>
      <thead><tr><th>Fecha y hora</th><th>Quién</th><th>Acción</th><th>Detalle</th></tr></thead>
      <tbody id="aBody"><tr><td colspan="4" class="empty">Cargando…</td></tr></tbody>
    </table>
  </div>
  <div class="pager"><span id="aInfo"></span><span><button class="btn ghost sm" id="aPrev">&larr; Anteriores</button> <button class="btn ghost sm" id="aNext">Siguientes &rarr;</button></span></div>
</div>`;

function bindAudit(){
  const sel = $("aAction");
  ACTION_GROUPS.forEach(([v, label]) => sel.appendChild(mk("option", {value: v}, label)));
  $("aSearch").onclick = () => loadAudit(0);
  $("aClear").onclick = () => { ["aUser","aAction","aFrom","aTo"].forEach(id => $(id).value = ""); loadAudit(0); };
  $("aPrev").onclick = () => loadAudit(Math.max(0, staff.audit.offset - staff.audit.limit));
  $("aNext").onclick = () => loadAudit(staff.audit.offset + staff.audit.limit);
}

async function loadAuditActors(){
  if(!$("aUser")) return;
  try{
    const actors = await api("/api/admin/audit/actors");
    const sel = $("aUser"), keep = sel.value;
    sel.replaceChildren(mk("option", {value: ""}, "Todos"));
    actors.forEach(a => sel.appendChild(mk("option", {value: a.user_id}, a.name)));
    sel.value = keep;
  }catch(e){ /* el filtro por usuario queda en "Todos" */ }
}

function describe(i){
  const d = i.detail || {};
  switch(i.action){
    case "appointment.confirmed": case "appointment.done": case "appointment.cancelled":
    case "appointment.reopened": case "appointment.deleted":
      return [d.customer, d.service, shortWhen(d.start_at)].filter(Boolean).join(" · ");
    case "appointment.customer_cancelled": return [d.service, shortWhen(d.start_at)].filter(Boolean).join(" · ");
    case "appointment.customer_rescheduled": return [d.service, shortWhen(d.from) + " → " + shortWhen(d.to)].filter(Boolean).join(" · ");
    case "service.created": case "service.updated": case "service.deleted": return d.name || "";
    case "reminders.run": return (d.enviados ?? 0) + " enviados de " + (d.candidatas ?? 0);
    case "user.created": return "@" + (d.username || "") + (d.role ? " (" + d.role + ")" : "");
    case "user.updated": case "user.deactivated": case "user.reactivated": case "user.password_reset": return "@" + (d.username || "");
    case "auth.login_failed": return "Usuario: " + (d.username || "") + (d.locked ? " · cuenta bloqueada" : "");
    default: return "";
  }
}

async function loadAudit(offset){
  const body = $("aBody");
  const p = new URLSearchParams({limit: staff.audit.limit, offset});
  if($("aUser").value) p.set("user_id", $("aUser").value);
  if($("aAction").value) p.set("action", $("aAction").value);
  if($("aFrom").value) p.set("from", $("aFrom").value);
  if($("aTo").value) p.set("to", $("aTo").value);
  try{
    const page = await api("/api/admin/audit?" + p.toString());
    Object.assign(staff.audit, {offset: page.offset, total: page.total});
    body.replaceChildren();
    if(!page.items.length){ const tr = mk("tr"); tr.appendChild(mk("td", {colSpan: 4, className: "empty"}, "No hay actividad con esos filtros.")); body.appendChild(tr); }
    page.items.forEach(i => {
      const tr = mk("tr");
      tr.appendChild(mk("td", {className: "mono"}, whenLocal(i.created_at)));
      const who = mk("td", {}, i.actor_name || "—");
      if(i.actor_type === "customer") who.append(" ", badge("Cliente", "b-neutral"));
      if(i.actor_type === "system") who.append(" ", badge("Sistema", "b-neutral"));
      tr.appendChild(who);
      tr.appendChild(mk("td", {}, ACTION_LABEL[i.action] || i.action));
      tr.appendChild(mk("td", {className: "detail"}, describe(i)));
      body.appendChild(tr);
    });
    const from = page.total ? page.offset + 1 : 0, to = Math.min(page.offset + page.limit, page.total);
    $("aInfo").textContent = page.total ? `${from}–${to} de ${page.total} registros` : "0 registros";
    $("aPrev").disabled = page.offset === 0;
    $("aNext").disabled = page.offset + page.limit >= page.total;
  }catch(e){
    if(e.status === 401){ logout(); return; }
    body.replaceChildren(); const tr = mk("tr"); tr.appendChild(mk("td", {colSpan: 4, className: "empty"}, "Error: " + e.message)); body.appendChild(tr);
  }
}
