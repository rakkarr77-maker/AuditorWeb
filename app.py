"""
app.py — Auditor de sitio web, todo desde una página en tu navegador.

Revisa: enlaces rotos, desempeño básico, ortografía/gramática y,
opcionalmente, compatibilidad entre Chromium/Firefox/WebKit.

Instalación:
    pip install flask requests beautifulsoup4 pandas openpyxl
    pip install language-tool-python          # opcional (ortografía, requiere Java)
    pip install playwright && playwright install   # opcional (compatibilidad de navegadores)

Uso:
    python app.py
    Abre http://127.0.0.1:5000 en tu navegador
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from flask import Flask, request, render_template_string, send_file
import pandas as pd

try:
    import language_tool_python
    LANGUAGE_TOOL_DISPONIBLE = True
except ImportError:
    LANGUAGE_TOOL_DISPONIBLE = False

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_DISPONIBLE = True
except ImportError:
    PLAYWRIGHT_DISPONIBLE = False

app = Flask(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; SiteAuditor/1.0)"}
TIMEOUT = 10
MAX_WORKERS = 10
IDIOMA_ORTOGRAFIA = "es"
MOTORES = ["chromium", "firefox", "webkit"]

ULTIMO_REPORTE = {"df_links": None, "dominio": None}


# ---------- Lógica de análisis ----------

def check_link(url):
    try:
        start = time.time()
        r = requests.head(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        if r.status_code in (405, 403, 501):
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True, stream=True)
        elapsed_ms = round((time.time() - start) * 1000)
        return r.status_code, elapsed_ms, None
    except requests.exceptions.RequestException as e:
        return None, None, type(e).__name__


def clasificar(status, error):
    if error or status is None:
        return "ROTO"
    if status >= 400:
        return "ROTO"
    if status >= 300:
        return "REDIRECCIÓN"
    return "OK"


def analizar_pagina(url, tool):
    try:
        start = time.time()
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        tiempo_carga_ms = round((time.time() - start) * 1000)
        peso_kb = round(len(r.content) / 1024, 1)

        soup = BeautifulSoup(r.text, "html.parser")
        num_imagenes = len(soup.find_all("img"))
        num_scripts = len(soup.find_all("script"))
        num_css = len(soup.find_all("link", rel="stylesheet"))

        errores_ortografia = "N/A"
        if tool:
            texto = soup.get_text(separator=" ", strip=True)[:5000]
            errores_ortografia = len(tool.check(texto))

        return {
            "Tiempo carga (ms)": tiempo_carga_ms,
            "Peso (KB)": peso_kb,
            "Imágenes": num_imagenes,
            "Scripts": num_scripts,
            "CSS": num_css,
            "Errores ortografía": errores_ortografia,
        }
    except requests.exceptions.RequestException:
        return {
            "Tiempo carga (ms)": "N/A", "Peso (KB)": "N/A", "Imágenes": "N/A",
            "Scripts": "N/A", "CSS": "N/A", "Errores ortografía": "N/A",
        }


def analizar_sitio(base_url):
    if not base_url.startswith(("http://", "https://")):
        base_url = "https://" + base_url

    r = requests.get(base_url, headers=HEADERS, timeout=TIMEOUT)
    soup = BeautifulSoup(r.text, "html.parser")

    ignorar = ("mailto:", "tel:", "javascript:", "#")
    raw_links = {a["href"].strip() for a in soup.find_all("a", href=True)}
    links = sorted({
        urljoin(base_url, href) for href in raw_links
        if href and not href.startswith(ignorar)
    })

    base_dominio = urlparse(base_url).netloc

    tool = None
    if LANGUAGE_TOOL_DISPONIBLE:
        try:
            tool = language_tool_python.LanguageTool(IDIOMA_ORTOGRAFIA)
        except Exception:
            tool = None

    resultados = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_link = {executor.submit(check_link, link): link for link in links}
        for future in as_completed(future_to_link):
            link = future_to_link[future]
            status, ms, error = future.result()
            estado = clasificar(status, error)
            es_interno = urlparse(link).netloc == base_dominio

            fila = {
                "Link": link,
                "Tipo": "Interno" if es_interno else "Externo",
                "Status": status if status else "N/A",
                "Tiempo (ms)": ms if ms else "N/A",
                "Estado": estado,
                "Error": error or "",
            }
            if estado == "OK" and es_interno:
                fila.update(analizar_pagina(link, tool))

            resultados.append(fila)

    if tool:
        tool.close()

    df = pd.DataFrame(resultados).sort_values(by="Estado", ascending=False)
    return df, base_dominio


def revisar_en_navegador(playwright, motor, url):
    errores_consola = []
    resultado = {
        "Navegador": motor, "Carga exitosa": False,
        "Tiempo carga (ms)": "N/A", "Errores JS": 0, "Detalle": "",
    }
    try:
        browser = getattr(playwright, motor).launch()
        page = browser.new_page()
        page.on("console", lambda msg: errores_consola.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda exc: errores_consola.append(str(exc)))

        start = time.time()
        page.goto(url, timeout=20000, wait_until="load")
        tiempo_ms = round((time.time() - start) * 1000)

        resultado.update({
            "Carga exitosa": True,
            "Tiempo carga (ms)": tiempo_ms,
            "Errores JS": len(errores_consola),
            "Detalle": " | ".join(errores_consola[:5]),
        })
        browser.close()
    except Exception as e:
        resultado["Detalle"] = str(e)
    return resultado


def analizar_navegadores(url):
    resultados = []
    with sync_playwright() as playwright:
        for motor in MOTORES:
            resultados.append(revisar_en_navegador(playwright, motor, url))
    return pd.DataFrame(resultados)


# ---------- Página HTML ----------

PLANTILLA = """
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Auditor de sitio web</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 1000px; margin: 40px auto; padding: 0 20px; color: #1a1a1a; background: #fafafa; }
  h1 { font-size: 1.5rem; }
  form { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 1px 4px rgba(0,0,0,.08); margin-bottom: 24px; }
  input[type=text] { width: 60%; padding: 10px; border: 1px solid #ccc; border-radius: 6px; font-size: 1rem; }
  label { display: block; margin: 10px 0; font-size: .9rem; }
  button { background: #2563eb; color: white; border: none; padding: 10px 20px; border-radius: 6px; font-size: 1rem; cursor: pointer; margin-top: 10px; }
  button:hover { background: #1d4ed8; }
  table { border-collapse: collapse; width: 100%; margin-bottom: 30px; background: white; box-shadow: 0 1px 4px rgba(0,0,0,.08); border-radius: 8px; overflow: hidden;}
  th, td { padding: 8px 10px; text-align: left; border-bottom: 1px solid #eee; font-size: .85rem; word-break: break-all; }
  th { background: #f3f4f6; }
  .OK { color: #15803d; font-weight: 600; }
  .ROTO { color: #dc2626; font-weight: 600; }
  .REDIRECCIÓN { color: #d97706; font-weight: 600; }
  .resumen { display: flex; gap: 16px; margin-bottom: 20px; flex-wrap: wrap;}
  .card { background: white; padding: 14px 18px; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,.08); min-width: 120px;}
  .card .num { font-size: 1.4rem; font-weight: 700; }
  .aviso { background: #fef9c3; border: 1px solid #fde047; padding: 10px 14px; border-radius: 6px; font-size: .85rem; margin-bottom: 16px;}
  a.download { display: inline-block; margin-bottom: 20px; color: #2563eb; }
</style>
</head>
<body>
  <h1>🔍 Auditor de sitio web</h1>
  <form method="post">
    <input type="text" name="url" placeholder="https://ejemplo.com" value="{{ url_actual or '' }}" required>
    <label><input type="checkbox" name="navegadores" {% if navegadores_check %}checked{% endif %}> Incluir prueba de compatibilidad de navegadores (más lento, requiere Playwright)</label>
    <button type="submit">Analizar</button>
  </form>

  {% if not language_tool_disponible %}
    <div class="aviso">⚠️ Ortografía desactivada: instala <code>language-tool-python</code> (requiere Java) para activarla.</div>
  {% endif %}
  {% if navegadores_check and not playwright_disponible %}
    <div class="aviso">⚠️ Compatibilidad de navegadores desactivada: instala <code>playwright</code> y corre <code>playwright install</code>.</div>
  {% endif %}

  {% if df_links is not none %}
    <div class="resumen">
      <div class="card"><div class="num">{{ total }}</div>Enlaces totales</div>
      <div class="card"><div class="num" style="color:#15803d">{{ ok }}</div>OK</div>
      <div class="card"><div class="num" style="color:#d97706">{{ redir }}</div>Redirecciones</div>
      <div class="card"><div class="num" style="color:#dc2626">{{ rotos }}</div>Rotos</div>
    </div>

    <a class="download" href="/descargar">⬇ Descargar reporte en Excel</a>

    <h2>Enlaces</h2>
    <table>
      <tr>{% for col in df_links.columns %}<th>{{ col }}</th>{% endfor %}</tr>
      {% for _, fila in df_links.iterrows() %}
        <tr>
          {% for col in df_links.columns %}
            <td class="{{ fila['Estado'] if col == 'Estado' else '' }}">{{ fila[col] }}</td>
          {% endfor %}
        </tr>
      {% endfor %}
    </table>
  {% endif %}

  {% if df_navegadores is not none %}
    <h2>Compatibilidad entre navegadores</h2>
    <table>
      <tr>{% for col in df_navegadores.columns %}<th>{{ col }}</th>{% endfor %}</tr>
      {% for _, fila in df_navegadores.iterrows() %}
        <tr>{% for col in df_navegadores.columns %}<td>{{ fila[col] }}</td>{% endfor %}</tr>
      {% endfor %}
    </table>
  {% endif %}
</body>
</html>
"""


@app.route("/", methods=["GET", "POST"])
def index():
    df_links = None
    df_navegadores = None
    url_actual = ""
    navegadores_check = False

    if request.method == "POST":
        url_actual = request.form.get("url", "").strip()
        navegadores_check = "navegadores" in request.form

        if url_actual:
            df_links, dominio = analizar_sitio(url_actual)
            ULTIMO_REPORTE["df_links"] = df_links
            ULTIMO_REPORTE["dominio"] = dominio

            if navegadores_check and PLAYWRIGHT_DISPONIBLE:
                df_navegadores = analizar_navegadores(url_actual)

    total = len(df_links) if df_links is not None else 0
    ok = int((df_links["Estado"] == "OK").sum()) if df_links is not None else 0
    redir = int((df_links["Estado"] == "REDIRECCIÓN").sum()) if df_links is not None else 0
    rotos = int((df_links["Estado"] == "ROTO").sum()) if df_links is not None else 0

    return render_template_string(
        PLANTILLA,
        df_links=df_links,
        df_navegadores=df_navegadores,
        url_actual=url_actual,
        navegadores_check=navegadores_check,
        language_tool_disponible=LANGUAGE_TOOL_DISPONIBLE,
        playwright_disponible=PLAYWRIGHT_DISPONIBLE,
        total=total, ok=ok, redir=redir, rotos=rotos,
    )


@app.route("/descargar")
def descargar():
    df = ULTIMO_REPORTE["df_links"]
    dominio = ULTIMO_REPORTE["dominio"] or "reporte"
    if df is None:
        return "No hay ningún reporte generado todavía.", 404

    nombre_archivo = f"reporte_{dominio.replace('.', '_')}.xlsx"
    df.to_excel(nombre_archivo, index=False)
    return send_file(nombre_archivo, as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
