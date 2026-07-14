# revisar_navegadores.py
#
# Este programa abre una página web en varios navegadores distintos
# para ver si carga bien en todos: Chrome, Edge, Firefox y Safari.
#
# COMO USARLO:
#  1. Escribe en la terminal:  py revisar_navegadores.py
#  2. Cuando te pida la URL, escribe la página que quieres revisar
#  3. Espera a que termine (tarda un poco porque prueba varios navegadores)
#  4. Al final se genera un archivo Excel con los resultados

from playwright.sync_api import sync_playwright
import pandas as pd
import time

# Cada navegador real se apoya en uno de los 3 motores que trae Playwright
# (chromium, firefox, webkit). Chrome y Edge usan el motor "chromium" pero
# con el navegador de verdad instalado en tu computadora (channel).
navegadores_a_probar = [
    {"nombre": "Google Chrome",   "motor": "chromium", "canal": "chrome"},
    {"nombre": "Microsoft Edge",  "motor": "chromium", "canal": "msedge"},
    {"nombre": "Mozilla Firefox", "motor": "firefox",  "canal": None},
    {"nombre": "Safari (WebKit)", "motor": "webkit",   "canal": None},
]


def probar_navegador(playwright, navegador, url):
    nombre = navegador["nombre"]
    print(f"Probando en {nombre}...")

    resultado = {
        "Navegador": nombre,
        "Cargó bien": "No",
        "Tiempo de carga (ms)": "N/A",
        "Errores encontrados": 0,
    }

    try:
        motor = getattr(playwright, navegador["motor"])
        if navegador["canal"]:
            instancia = motor.launch(channel=navegador["canal"])
        else:
            instancia = motor.launch()

        pagina = instancia.new_page()

        errores = []
        pagina.on("pageerror", lambda error: errores.append(str(error)))

        inicio = time.time()
        pagina.goto(url, timeout=20000)
        tiempo = round((time.time() - inicio) * 1000)

        resultado["Cargó bien"] = "Sí"
        resultado["Tiempo de carga (ms)"] = tiempo
        resultado["Errores encontrados"] = len(errores)

        instancia.close()
    except Exception as error:
        # Lo más común aquí es que ese navegador (Chrome o Edge) no esté
        # instalado en la computadora. El programa sigue con los demás.
        resultado["Errores encontrados"] = "No se pudo abrir (¿está instalado?)"

    return resultado


def main():
    url = input("URL: ").strip()
    if not url.startswith("http"):
        url = "https://" + url

    resultados = []
    with sync_playwright() as playwright:
        for navegador in navegadores_a_probar:
            resultado = probar_navegador(playwright, navegador, url)
            resultados.append(resultado)

    tabla = pd.DataFrame(resultados)
    nombre_archivo = "reporte_navegadores.xlsx"
    tabla.to_excel(nombre_archivo, index=False)

    print(f"\n¡Listo! Reporte guardado como: {nombre_archivo}")
    print(tabla.to_string(index=False))


if __name__ == "__main__":
    main()
