# auditor_gui.py
#
# Programa único con ventana propia que revisa:
#  - Enlaces rotos
#  - Desempeño (tiempo de carga, peso de la página)
#  - Ortografía y gramática (mostrando las palabras mal escritas)
#  - Compatibilidad con Chrome, Edge, Firefox y Safari
#
# COMO USARLO:
#  1. Escribe en la terminal:  py auditor_gui.py
#  2. Se abre una ventana. Pega la URL, marca o no el checkbox de
#     navegadores, y dale clic a "Analizar".
#  3. Espera (la ventana te va diciendo qué está haciendo).
#  4. Al terminar, el Excel queda guardado en la misma carpeta y
#     puedes abrirlo con el botón de abajo.

import tkinter as tk
from tkinter import ttk, messagebox
import time
import os
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
import pandas as pd

# Estas dos son opcionales: si no están instaladas, el programa
# sigue funcionando pero sin esa parte.
try:
    import language_tool_python
    TIENE_ORTOGRAFIA = True
except ImportError:
    TIENE_ORTOGRAFIA = False

try:
    from playwright.sync_api import sync_playwright
    TIENE_PLAYWRIGHT = True
except ImportError:
    TIENE_PLAYWRIGHT = False

HEADERS = {"User-Agent": "Mozilla/5.0"}

NAVEGADORES = [
    {"nombre": "Google Chrome",   "motor": "chromium", "canal": "chrome"},
    {"nombre": "Microsoft Edge",  "motor": "chromium", "canal": "msedge"},
    {"nombre": "Mozilla Firefox", "motor": "firefox",  "canal": None},
    {"nombre": "Safari (WebKit)", "motor": "webkit",   "canal": None},
]


# ---------- Funciones de análisis ----------

def revisar_enlace(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code >= 400:
            return "ROTO", r.status_code
        elif r.status_code >= 300:
            return "REDIRECCIÓN", r.status_code
        else:
            return "OK", r.status_code
    except Exception:
        return "ROTO", "Sin respuesta"


def analizar_pagina(url, tool):
    """Revisa desempeño y, si hay corrector disponible, ortografía.
    Regresa: tiempo de carga, peso, cantidad de errores y las palabras
    o frases exactas que el corrector marcó como incorrectas.

    Importante: el desempeño (tiempo/peso) y la ortografía se calculan
    en bloques try/except SEPARADOS. Así, si la ortografía falla por
    alguna razón, no se pierde el tiempo y peso que sí se calcularon bien."""
    tiempo = peso = "N/A"
    cantidad_errores = palabras_mal = "N/A"

    # --- Desempeño ---
    try:
        inicio = time.time()
        r = requests.get(url, headers=HEADERS, timeout=10)
        tiempo = round((time.time() - inicio) * 1000)
        peso = round(len(r.content) / 1024, 1)
    except Exception:
        return tiempo, peso, cantidad_errores, palabras_mal  # ni siquiera se pudo descargar

    # --- Ortografía (independiente del desempeño) ---
    if tool:
        try:
            texto = BeautifulSoup(r.text, "html.parser").get_text(separator=" ", strip=True)[:3000]
            coincidencias = tool.check(texto)
            cantidad_errores = len(coincidencias)

            # Sacamos el texto exacto que el corrector marcó como mal
            # (usando el offset y largo del error dentro del texto revisado)
            palabras_encontradas = []
            for m in coincidencias:
                # Versiones nuevas de la librería usan "error_length",
                # versiones viejas usaban "errorLength". Probamos ambas.
                largo = getattr(m, "error_length", None)
                if largo is None:
                    largo = getattr(m, "errorLength", 0)
                fragmento = texto[m.offset: m.offset + largo].strip()
                if fragmento and fragmento not in palabras_encontradas:
                    palabras_encontradas.append(fragmento)

            if palabras_encontradas:
                mostrar = palabras_encontradas[:8]
                palabras_mal = ", ".join(mostrar)
                if len(palabras_encontradas) > 8:
                    palabras_mal += f" (+{len(palabras_encontradas) - 8} más)"
            else:
                palabras_mal = "Ninguna"
        except Exception as e:
            # Mostramos el tipo de error para poder diagnosticarlo si vuelve a pasar
            cantidad_errores = f"Error: {type(e).__name__}"
            palabras_mal = "No se pudo revisar"

    return tiempo, peso, cantidad_errores, palabras_mal


def probar_navegador(playwright, navegador, url):
    nombre = navegador["nombre"]
    resultado = {"Navegador": nombre, "Cargó bien": "No", "Tiempo (ms)": "N/A", "Errores": 0}
    try:
        motor = getattr(playwright, navegador["motor"])
        instancia = motor.launch(channel=navegador["canal"]) if navegador["canal"] else motor.launch()
        pagina = instancia.new_page()
        errores = []
        pagina.on("pageerror", lambda e: errores.append(str(e)))
        inicio = time.time()
        pagina.goto(url, timeout=20000)
        tiempo = round((time.time() - inicio) * 1000)
        resultado.update({"Cargó bien": "Sí", "Tiempo (ms)": tiempo, "Errores": len(errores)})
        instancia.close()
    except Exception:
        resultado["Errores"] = "No instalado"
    return resultado


# ---------- Ventana ----------

class AuditorApp:
    def __init__(self, root):
        self.root = root
        self.ultimo_archivo = None
        root.title("Auditor de sitio web")
        root.geometry("1050x640")

        # Barra superior: campo de URL + checkbox + botón
        marco_superior = ttk.Frame(root, padding=10)
        marco_superior.pack(fill="x")

        ttk.Label(marco_superior, text="URL:").pack(side="left")
        self.entrada_url = ttk.Entry(marco_superior, width=50)
        self.entrada_url.pack(side="left", padx=5)
        self.entrada_url.insert(0, "https://")

        self.var_navegadores = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            marco_superior, text="Incluir navegadores (más lento)",
            variable=self.var_navegadores
        ).pack(side="left", padx=10)

        self.boton_analizar = ttk.Button(marco_superior, text="Analizar", command=self.analizar)
        self.boton_analizar.pack(side="left", padx=10)

        # Resumen numérico
        self.etiqueta_resumen = ttk.Label(root, text="", padding=10, font=("Segoe UI", 10, "bold"))
        self.etiqueta_resumen.pack(fill="x")

        # Tabla de enlaces (con scrollbar horizontal, porque "Palabras con error" puede ser larga)
        marco_tabla = ttk.Frame(root)
        marco_tabla.pack(fill="both", expand=True, padx=10, pady=5)

        columnas = ("Link", "Estado", "Código", "Tiempo (ms)", "Peso (KB)",
                    "Errores ortografía", "Palabras con error")
        self.tabla = ttk.Treeview(marco_tabla, columns=columnas, show="headings", height=12)
        anchos = {"Link": 260, "Estado": 90, "Código": 70, "Tiempo (ms)": 90,
                  "Peso (KB)": 80, "Errores ortografía": 110, "Palabras con error": 320}
        for col in columnas:
            self.tabla.heading(col, text=col)
            self.tabla.column(col, width=anchos[col], anchor="w")

        scroll_x = ttk.Scrollbar(marco_tabla, orient="horizontal", command=self.tabla.xview)
        scroll_y = ttk.Scrollbar(marco_tabla, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(xscrollcommand=scroll_x.set, yscrollcommand=scroll_y.set)

        self.tabla.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")
        marco_tabla.grid_rowconfigure(0, weight=1)
        marco_tabla.grid_columnconfigure(0, weight=1)

        # Tabla de navegadores
        ttk.Label(root, text="Compatibilidad de navegadores", padding=(10, 5)).pack(anchor="w")
        columnas_nav = ("Navegador", "Cargó bien", "Tiempo (ms)", "Errores")
        self.tabla_nav = ttk.Treeview(root, columns=columnas_nav, show="headings", height=5)
        for col in columnas_nav:
            self.tabla_nav.heading(col, text=col)
            self.tabla_nav.column(col, width=200, anchor="w")
        self.tabla_nav.pack(fill="x", padx=10, pady=5)

        # Barra inferior: estado + botón para abrir el Excel
        marco_inferior = ttk.Frame(root, padding=10)
        marco_inferior.pack(fill="x")

        self.etiqueta_estado = ttk.Label(marco_inferior, text="Listo.")
        self.etiqueta_estado.pack(side="left")

        self.boton_abrir = ttk.Button(
            marco_inferior, text="Abrir reporte en Excel",
            command=self.abrir_reporte, state="disabled"
        )
        self.boton_abrir.pack(side="right")

        avisos = []
        if not TIENE_ORTOGRAFIA:
            avisos.append("ortografía desactivada (falta language-tool-python)")
        if not TIENE_PLAYWRIGHT:
            avisos.append("navegadores desactivado (falta playwright)")
        if avisos:
            self.etiqueta_estado.config(text="Nota: " + " | ".join(avisos))

    def analizar(self):
        url = self.entrada_url.get().strip()
        if not url or url == "https://":
            messagebox.showwarning("Falta URL", "Escribe una URL para analizar.")
            return

        self.boton_analizar.config(state="disabled")
        self.boton_abrir.config(state="disabled")
        self.tabla.delete(*self.tabla.get_children())
        self.tabla_nav.delete(*self.tabla_nav.get_children())
        self.etiqueta_resumen.config(text="")
        self.etiqueta_estado.config(text="Analizando enlaces, espera un momento...")
        self.root.update()

        try:
            if not url.startswith("http"):
                url = "https://" + url

            r = requests.get(url, headers=HEADERS, timeout=10)
            sopa = BeautifulSoup(r.text, "html.parser")

            enlaces = set()
            for etiqueta in sopa.find_all("a", href=True):
                completo = urljoin(url, etiqueta["href"])
                if completo.startswith("http"):
                    enlaces.add(completo)
            enlaces = sorted(enlaces)

            corrector = None
            if TIENE_ORTOGRAFIA:
                self.etiqueta_estado.config(text="Cargando corrector de ortografía...")
                self.root.update()
                try:
                    corrector = language_tool_python.LanguageTool("es")
                except Exception:
                    corrector = None

            dominio = urlparse(url).netloc
            resultados = []
            ok = redir = rotos = 0

            for i, enlace in enumerate(enlaces, 1):
                estado, codigo = revisar_enlace(enlace)
                tiempo = peso = cant_errores = palabras_mal = "N/A"
                es_mismo = urlparse(enlace).netloc == dominio
                if estado == "OK" and es_mismo:
                    tiempo, peso, cant_errores, palabras_mal = analizar_pagina(enlace, corrector)

                if estado == "OK":
                    ok += 1
                elif estado == "REDIRECCIÓN":
                    redir += 1
                else:
                    rotos += 1

                resultados.append({
                    "Link": enlace, "Estado": estado, "Código": codigo,
                    "Tiempo (ms)": tiempo, "Peso (KB)": peso,
                    "Errores ortografía": cant_errores, "Palabras con error": palabras_mal,
                })

                self.tabla.insert("", "end", values=(
                    enlace, estado, codigo, tiempo, peso, cant_errores, palabras_mal))
                self.etiqueta_estado.config(text=f"Revisando enlace {i}/{len(enlaces)}...")
                self.root.update()

            if corrector:
                corrector.close()

            tabla_df = pd.DataFrame(resultados)
            nombre_archivo = f"reporte_{dominio.replace('.', '_')}.xlsx"
            tabla_df.to_excel(nombre_archivo, index=False)
            self.ultimo_archivo = os.path.abspath(nombre_archivo)

            self.etiqueta_resumen.config(
                text=f"Total: {len(enlaces)}   OK: {ok}   Redirecciones: {redir}   Rotos: {rotos}"
            )

            if self.var_navegadores.get() and TIENE_PLAYWRIGHT:
                self.etiqueta_estado.config(text="Probando navegadores...")
                self.root.update()
                with sync_playwright() as playwright:
                    for navegador in NAVEGADORES:
                        self.etiqueta_estado.config(text=f"Probando en {navegador['nombre']}...")
                        self.root.update()
                        resultado = probar_navegador(playwright, navegador, url)
                        self.tabla_nav.insert("", "end", values=(
                            resultado["Navegador"], resultado["Cargó bien"],
                            resultado["Tiempo (ms)"], resultado["Errores"]
                        ))
                        self.root.update()

            self.etiqueta_estado.config(text=f"Listo. Reporte guardado como: {nombre_archivo}")
            self.boton_abrir.config(state="normal")

        except Exception as e:
            messagebox.showerror("Error", str(e))
            self.etiqueta_estado.config(text="Ocurrió un error.")

        finally:
            self.boton_analizar.config(state="normal")

    def abrir_reporte(self):
        if self.ultimo_archivo and os.path.exists(self.ultimo_archivo):
            os.startfile(self.ultimo_archivo)


if __name__ == "__main__":
    ventana = tk.Tk()
    app = AuditorApp(ventana)
    ventana.mainloop()
