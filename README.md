# Auditor de sitio web

Programa en Python que revisa un sitio web y detecta:

- **Enlaces rotos** — verifica el código de respuesta real de cada enlace (no un simple ping).
- **Desempeño** — tiempo de carga y peso de cada página.
- **Ortografía y gramática** — usando LanguageTool, marcando las palabras o frases exactas con error.
- **Compatibilidad de navegadores** — prueba que la página cargue en Google Chrome, Microsoft Edge, Mozilla Firefox y Safari (WebKit).

Al final genera un reporte en Excel con todos los resultados.

## Archivos

| Archivo | Qué hace |
|---|---|
| `auditor_gui.py` | **Programa principal.** Ventana con interfaz gráfica que integra los 4 análisis en uno solo. |
| `revisar_sitio.py` | Versión de terminal: enlaces rotos + desempeño + ortografía. |
| `revisar_navegadores.py` | Versión de terminal: solo compatibilidad de navegadores. |
| `app.py` | Versión con interfaz web local (Flask), como alternativa a la ventana. |

Para uso normal, solo necesitas `auditor_gui.py` — los demás son versiones anteriores que se quedaron como referencia.

## Requisitos

```bash
pip install requests beautifulsoup4 pandas openpyxl
pip install language-tool-python          # ortografía (requiere Java instalado)
pip install playwright && playwright install   # compatibilidad de navegadores
```

`tkinter` (la interfaz gráfica) ya viene incluido con Python en Windows, no requiere instalación aparte.

## Cómo usarlo

```bash
python auditor_gui.py
```

Se abre una ventana:

1. Escribe la URL del sitio a analizar.
2. Marca (opcional) "Incluir navegadores" si también quieres la prueba de compatibilidad.
3. Clic en **Analizar** y espera — la ventana va mostrando el avance en tiempo real.
4. Al terminar, el reporte se guarda como `reporte_<dominio>.xlsx` en la misma carpeta, y puedes abrirlo directo con el botón "Abrir reporte en Excel".

## Notas

- Solo se analiza a fondo (desempeño + ortografía) las páginas internas del mismo dominio que sí cargan correctamente — los enlaces externos solo se verifican que no estén rotos.
- Chrome y Edge se prueban usando el navegador real instalado en el sistema; si alguno no está instalado, esa fila del reporte lo indica sin detener el resto del análisis.
- Este proyecto se hizo como herramienta de apoyo para prácticas de Verificación y Validación de Software.
