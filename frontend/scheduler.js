/* Calendario mensual + franjas horarias (HU-2), compartido por index.html y manage.html.
 *
 * createScheduler({
 *   els:        { prev, next, title, grid, slots }   // elementos del DOM
 *   ready():    true cuando ya se puede consultar (p. ej. hay un servicio elegido)
 *   fetchMonth(ym):   Promise<[{date,status,free}]>   // ym = "YYYY-MM"
 *   fetchSlots(date): Promise<[{time,available,reason}]>
 *   onDay(date):  se eligió un día
 *   onSlot(time): se eligió una franja libre
 * }) -> { loadCalendar, loadSlots, reset, get date }
 *
 * El servidor decide qué es "pasado", "cerrado" o "lleno"; aquí solo se pinta.
 */
function createScheduler(opts){
  const els = opts.els;
  const MONTHS = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"];
  const DAY_TITLE = { full:"Sin horarios libres", closed:"Cerrado", past:"Ya pasó" };
  const pad2 = n => String(n).padStart(2, "0");
  const monthIdx = c => c.y*12 + c.m;

  const now = new Date();
  const MIN_CAL = { y:now.getFullYear(), m:now.getMonth()+1 };    // no se navega a meses anteriores
  const TODAY_ISO = `${MIN_CAL.y}-${pad2(MIN_CAL.m)}-${pad2(now.getDate())}`;
  let cal = { y:MIN_CAL.y, m:MIN_CAL.m };
  let date = null;
  // Solo la última petición pinta (evita que una respuesta vieja pise a la nueva).
  let calReq = 0, slotsReq = 0;

  const empty = (html, full) => `<div class="empty"${full ? ' style="grid-column:1/-1"' : ""}>${html}</div>`;

  els.prev.addEventListener("click", ()=>{
    if(monthIdx(cal) <= monthIdx(MIN_CAL)) return;
    cal = cal.m===1 ? {y:cal.y-1, m:12} : {y:cal.y, m:cal.m-1};
    loadCalendar();
  });
  els.next.addEventListener("click", ()=>{
    cal = cal.m===12 ? {y:cal.y+1, m:1} : {y:cal.y, m:cal.m+1};
    loadCalendar();
  });

  async function loadCalendar(){
    if(!opts.ready()) return;
    els.title.textContent = `${MONTHS[cal.m-1]} ${cal.y}`;
    els.prev.disabled = monthIdx(cal) <= monthIdx(MIN_CAL);
    const myReq = ++calReq;
    els.grid.innerHTML = empty('<span class="spin"></span> Cargando calendario…', true);
    try{
      const days = await opts.fetchMonth(`${cal.y}-${pad2(cal.m)}`);
      if(myReq !== calReq) return;
      renderCalendar(days);
    }catch(e){
      if(myReq !== calReq) return;
      els.grid.innerHTML = empty("Error cargando el calendario. Prueba de nuevo.", true);
    }
  }

  function renderCalendar(days){
    els.grid.innerHTML = "";
    const offset = (new Date(cal.y, cal.m-1, 1).getDay() + 6) % 7;   // la semana empieza en lunes
    for(let i=0; i<offset; i++) els.grid.appendChild(document.createElement("span"));
    days.forEach(d=>{
      const el = document.createElement("button");
      el.type = "button";
      el.dataset.date = d.date;
      el.className = "cal-day " + (d.status==="available" ? "avail" : d.status)
        + (d.date===TODAY_ISO ? " today" : "") + (d.date===date ? " sel" : "");
      el.textContent = Number(d.date.slice(8));
      el.title = d.status==="available" ? `${d.free} horario${d.free===1?"":"s"} libre${d.free===1?"":"s"}` : DAY_TITLE[d.status];
      if(d.status === "available") el.onclick = ()=>selectDay(d.date);
      else el.disabled = true;
      els.grid.appendChild(el);
    });
  }

  function selectDay(d){
    date = d;
    els.grid.querySelectorAll(".cal-day").forEach(x=>x.classList.toggle("sel", x.dataset.date === d));
    if(opts.onDay) opts.onDay(d);
    loadSlots();
  }

  async function loadSlots(){
    if(!opts.ready() || !date) return;
    const myReq = ++slotsReq;
    els.slots.innerHTML = empty('<span class="spin"></span> Buscando horarios…');
    try{
      const list = await opts.fetchSlots(date);
      if(myReq !== slotsReq) return;                     // llegó tarde: hay una petición más nueva
      if(!Array.isArray(list) || !list.length){
        els.slots.innerHTML = empty("No hay horarios ese día. Prueba otro."); return;
      }
      els.slots.innerHTML = "";
      list.forEach(sl=>{
        const b = document.createElement("div"); b.textContent = sl.time;
        if(sl.available){
          b.className = "slot";
          b.onclick = ()=>{
            els.slots.querySelectorAll(".slot").forEach(x=>x.classList.remove("sel"));
            b.classList.add("sel");
            opts.onSlot(sl.time, date);
          };
        }else{
          b.className = "slot off" + (sl.reason==="past" ? " past" : "");
          b.title = sl.reason==="past" ? "Ya pasó" : "Ocupado";
          b.setAttribute("aria-disabled", "true");
        }
        els.slots.appendChild(b);
      });
    }catch(e){
      if(myReq !== slotsReq) return;
      els.slots.innerHTML = empty("Error cargando horarios. Prueba de nuevo.");
    }
  }

  // Olvida el día elegido y vacía las franjas (p. ej. al cambiar de servicio).
  function reset(msg){
    date = null; slotsReq++;
    els.slots.innerHTML = empty(msg || "Elige un día del calendario.");
  }

  return { loadCalendar, loadSlots, reset, get date(){ return date; } };
}
