"""Verificación funcional del reviewer en un navegador real (Playwright + Chromium).

Cubre lo que el reporte de QA (§8) dejó pendiente de ver en pantalla:
  R-1  QA-03: un servicio con HTML en el nombre se ve como texto y no ejecuta nada.
  R-2  QA-02: el enlace del recordatorio funciona y el de la confirmación deja de servir.
  R-3  Vistas en ancho móvil (390 px) sin desbordamiento horizontal.
  R-4  Flujo de cliente: calendario, página de autogestión y panel con roles y auditoría.

Uso (servidor ya levantado con BD recién sembrada, sin usuarios del panel):
    BASE_URL=http://localhost:8000 ADMIN_TOKEN=<clave> SERVER_LOG=<log de uvicorn> \
    python verificacion_funcional.py <carpeta de capturas>
"""
import datetime as dt
import os
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")
TOKEN = os.environ["ADMIN_TOKEN"]
LOG = Path(os.environ["SERVER_LOG"])
OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
X = {"X-Requested-With": "citafacil"}
XSS = '<img src=x onerror="window.__xss=1">Corte XSS'
resultados = []


def check(caso, ok, detalle=""):
    resultados.append(ok)
    print(f"[{'PASA ' if ok else 'FALLA'}] {caso}{' — ' + detalle if detalle else ''}")


def shot(page, nombre, full=True):
    page.screenshot(path=str(OUT / f"{nombre}.png"), full_page=full)


def ancho_contenido(page):
    # En modo móvil innerWidth crece con el contenido: se compara contra el ancho fijo del viewport.
    return page.evaluate("document.documentElement.scrollWidth")


def enlace_recordatorio_de(cliente, desde):
    """Enlace del recordatorio enviado a `cliente` (cada mensaje demo empieza con «[WhatsApp DEMO]»)."""
    texto = LOG.read_text(encoding="utf-8", errors="replace")[desde:]
    for msg in texto.split("[WhatsApp DEMO]"):
        if "te recordamos" in msg and cliente in msg:
            m = re.search(r"(https?://\S+/app/manage\.html#t=[\w-]+)", msg)
            return m.group(1) if m else None
    return None


manana = dt.date.today() + dt.timedelta(days=1)
if manana.weekday() == 6:
    manana += dt.timedelta(days=1)

with sync_playwright() as p:
    browser = p.chromium.launch()

    # ---------- preparación por API: dueño y servicio con HTML en el nombre ----------
    admin = browser.new_context(viewport={"width": 1440, "height": 900})
    api = admin.request
    r = api.post(f"{BASE}/api/admin/auth/setup", headers=X, data={
        "setup_token": TOKEN, "username": "dueno", "display_name": "Dueño", "password": "ClaveSegura123"})
    check("instalación del propietario", r.status == 200, str(r.status))
    r = api.post(f"{BASE}/api/admin/services", headers=X, data={"name": XSS, "duration_min": 30, "price": 5000})
    check("crear servicio con HTML en el nombre", r.status == 201, str(r.status))

    # ---------- R-1: página pública (escritorio) ----------
    pub = browser.new_context(viewport={"width": 1440, "height": 900})
    page = pub.new_page()
    dialogs = []
    page.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
    page.goto(f"{BASE}/app/")
    page.wait_for_selector("text=Corte XSS")
    page.wait_for_timeout(800)
    visible = page.locator("#svcGrid").inner_text()
    ejecutado = page.evaluate("window.__xss === 1")
    imgs = page.locator("#svcGrid img").count()
    check("R-1 QA-03: el nombre con HTML se muestra como texto", "<img src=x" in visible)
    check("R-1 QA-03: el código del nombre no se ejecuta", not ejecutado and imgs == 0 and not dialogs,
          f"__xss={ejecutado}, <img> en la grilla={imgs}")
    shot(page, "R1-servicio-xss-escapado-escritorio")

    # ---------- R-4: calendario y franjas ----------
    page.locator("#svcGrid .svc").first.click()
    page.wait_for_timeout(1200)
    shot(page, "R4-calendario-y-franjas-escritorio")

    # ---------- R-2: enlace de confirmación vs. enlace del recordatorio ----------
    r = api.post(f"{BASE}/api/appointments", data={
        "service_id": 1, "start_at": f"{manana}T10:00:00", "customer_name": "Reviewer Prueba",
        "customer_phone": "+50761234567"})
    check("reserva de prueba para mañana 10:00", r.status == 201, str(r.status))
    enlace_confirmacion = r.json()["manage_url"].replace("http://localhost:8000", BASE)

    m = pub.new_page()
    m.goto(enlace_confirmacion)
    m.wait_for_timeout(1200)
    shot(m, "R2a-enlace-confirmacion-antes-del-recordatorio")
    check("R-2 el enlace de la confirmación abre la cita", "Reviewer" in m.inner_text("body"))

    log_pos = LOG.stat().st_size
    r = api.post(f"{BASE}/api/admin/reminders/run", headers=X)
    check("disparar recordatorios desde el panel", r.status == 200, r.text()[:80])
    time.sleep(0.5)
    enlace_recordatorio = enlace_recordatorio_de("Reviewer Prueba", log_pos)
    check("R-2 QA-02: el recordatorio trae enlace", enlace_recordatorio is not None)
    enlace_recordatorio = enlace_recordatorio.replace("http://localhost:8000", BASE)

    m2 = pub.new_page()
    m2.goto(enlace_recordatorio)
    m2.wait_for_timeout(1200)
    shot(m2, "R2b-enlace-recordatorio-funciona")
    check("R-2 QA-02: el enlace del recordatorio abre la cita", "Reviewer" in m2.inner_text("body"))

    m3 = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()   # sin sessionStorage previo
    m3.goto(enlace_confirmacion)
    m3.wait_for_timeout(1200)
    shot(m3, "R2c-enlace-confirmacion-ya-no-sirve")
    check("R-2 QA-02: el enlace de la confirmación ya no sirve",
          "Reviewer" not in m3.inner_text("body"), m3.inner_text("body")[:90].replace("\n", " "))

    # ---------- R-4: panel admin con auditoría ----------
    a = admin.new_page()
    a.goto(f"{BASE}/app/admin.html")
    a.wait_for_timeout(2000)
    shot(a, "R4-panel-admin-escritorio")
    texto_admin = a.inner_text("body")
    check("R-4 el panel abre con la sesión del dueño", "Dueño" in texto_admin or "Propietario" in texto_admin)
    check("R-4 QA-03 en el panel: el nombre con HTML se ve como texto", not a.evaluate("window.__xss === 1"))

    # ---------- R-3: ancho móvil ----------
    movil = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True)
    for nombre, url in [("index", f"{BASE}/app/"), ("autogestion", enlace_recordatorio),
                        ("admin-login", f"{BASE}/app/admin.html")]:
        mp = movil.new_page()
        mp.goto(url)
        mp.wait_for_timeout(1500)
        ancho = ancho_contenido(mp)
        check(f"R-3 móvil 390 px sin desborde horizontal: {nombre}", ancho <= 391, f"ancho del contenido={ancho}px")
        shot(mp, f"R3-movil-{nombre}")

    browser.close()

print(f"\nTOTAL: {resultados.count(True)} pasan, {resultados.count(False)} fallan")
sys.exit(0 if all(resultados) else 1)
