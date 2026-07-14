# revisar_sitio.py
#
# Este programa revisa una página web y busca:
#  - Enlaces rotos
#  - Problemas de desempeño (tiempo de carga, peso de la página)
#  - Errores de ortografía y gramática
#
# COMO USARLO:
#  1. Escribe en la terminal:  py revisar_sitio.py
#  2. Cuando te pida la URL, escribe la página que quieres revisar
#  3. Espera a que termine (va mostrando el avance en pantalla)
#  4. Al final se genera un archivo Excel con los resultados

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import pandas as pd
import time

# Si tienes instalado el corrector de ortografía, lo usamos.
# Si no, el programa sigue funcionando pero sin esa parte.
try:
    import language_tool_python
    tiene_ortografia = True
except ImportError:
    tiene_ortografia = False

HEADERS = {"User-Agent": "Mozilla/5.0"}


def revisar_enlace(url):
    """Revisa si un enlace funciona. Regresa el estado y el código de respuesta."""
    try:
        respuesta = requests.get(url, headers=HEADERS, timeout=10)
        if respuesta.status_code >= 400:
            return "ROTO", respuesta.status_code
        elif respuesta.status_code >= 300:
            return "REDIRECCIÓN", respuesta.status_code
        else:
            return "OK", respuesta.status_code
    except Exception:
        return "ROTO", "Sin respuesta"


def main():
    url = input("URL: ").strip()
    if not url.startswith("http"):
        url = "https://" + url

    print("\nDescargando la página principal...")
    pagina_principal = requests.get(url, headers=HEADERS, timeout=10)
    print("Status de la página principal:", pagina_principal.status_code)

    sopa = BeautifulSoup(pagina_principal.text, "html.parser")

    # Sacamos todos los enlaces que hay en la página
    enlaces_encontrados = set()
    for etiqueta in sopa.find_all("a", href=True):
        enlace_completo = urljoin(url, etiqueta["href"])
        if enlace_completo.startswith("http"):
            enlaces_encontrados.add(enlace_completo)

    print(f"Se encontraron {len(enlaces_encontrados)} enlaces. Revisando uno por uno...\n")

    corrector = None
    if tiene_ortografia:
        print("Cargando corrector de ortografía (puede tardar un momento)...")
        try:
            corrector = language_tool_python.LanguageTool("es")
        except Exception:
            print("No se pudo cargar el corrector, seguimos sin esa parte.")

    dominio_principal = urlparse(url).netloc
    resultados = []

    for i, enlace in enumerate(enlaces_encontrados, 1):
        estado, codigo = revisar_enlace(enlace)
        print(f"[{i}/{len(enlaces_encontrados)}] {estado} - {enlace}")

        fila = {
            "Enlace": enlace,
            "Estado": estado,
            "Código": codigo,
        }

        # Si el enlace es del mismo sitio y funciona, revisamos desempeño y ortografía
        es_del_mismo_sitio = urlparse(enlace).netloc == dominio_principal
        if estado == "OK" and es_del_mismo_sitio:
            try:
                inicio = time.time()
                respuesta = requests.get(enlace, headers=HEADERS, timeout=10)
                tiempo_carga = round((time.time() - inicio) * 1000)
                peso_pagina = round(len(respuesta.content) / 1024, 1)

                fila["Tiempo de carga (ms)"] = tiempo_carga
                fila["Peso (KB)"] = peso_pagina

                if corrector:
                    texto = BeautifulSoup(respuesta.text, "html.parser").get_text()
                    texto = texto[:3000]  # solo un fragmento, para que sea rápido
                    errores = corrector.check(texto)
                    fila["Errores de ortografía"] = len(errores)
            except Exception:
                pass

        resultados.append(fila)

    if corrector:
        corrector.close()

    tabla = pd.DataFrame(resultados)
    nombre_archivo = "reporte_enlaces.xlsx"
    tabla.to_excel(nombre_archivo, index=False)

    print(f"\n¡Listo! Reporte guardado como: {nombre_archivo}")


if __name__ == "__main__":
    main()
