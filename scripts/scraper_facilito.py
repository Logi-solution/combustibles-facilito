"""
Extraccion diaria de precios de combustibles desde Facilito (OSINERGMIN).

Genera UN solo archivo por dia en data_historica/, nombrado con la fecha
(YYYY-MM-DD_combustibles.csv). Nunca sobrescribe un archivo de un dia anterior.
Si el archivo del dia ya existe, no se vuelve a generar (evita duplicar/perder
informacion si el script corre dos veces el mismo dia).

Columnas del CSV: Fecha,Region,Provincia,Distrito,Establecimiento,Tipo_Combustible,Precio_Soles_Galon

Uso:
    python scraper_facilito.py            (corre normal, se salta si ya existe el archivo de hoy)
    python scraper_facilito.py --force    (fuerza regenerar el archivo de hoy, sobrescribiendolo)
"""

import asyncio
import csv
import logging
import sys
from datetime import date, datetime
from pathlib import Path

from playwright.async_api import async_playwright

# ---------------------------------------------------------------------------
# Configuracion
# ---------------------------------------------------------------------------

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data_historica"
LOG_DIR = PROJECT_DIR / "logs"

BASE_URL = "https://www.facilito.gob.pe/facilito/actions/PreciosCombustibleAutomotorAction.do"
BUSCADOR_URL = "https://www.facilito.gob.pe/facilito/pages/facilito/buscadorEESS.jsp"
RECAPTCHA_SITE_KEY = "6Le5C4cfAAAAABbO98BHMzZKAUVimVJSzcKrbK03"

# Regiones a extraer: codigo de departamento -> nombre
REGIONES = {
    "130000": "LA LIBERTAD",
    "110000": "ICA",
    "200000": "PIURA",
    "150000": "LIMA",
    "140000": "LAMBAYEQUE",
}

# Orden de presentacion en el CSV final
REGION_ORDER = list(REGIONES.values())

# Productos a extraer: codigo -> nombre tal como se reporta en el CSV
PRODUCTOS = {
    "126": "Gasolina Regular",
    "127": "Gasolina Premium",
    "40": "Diesel DB5",
}

CSV_HEADER = [
    "Fecha",
    "Región",
    "Provincia",
    "Distrito",
    "Establecimiento",
    "Tipo_Combustible",
    "Precio_Soles_Galon",
]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "scraper.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("facilito")

# ---------------------------------------------------------------------------
# JS que corre DENTRO del navegador: obtiene token reCAPTCHA v3 y hace el
# POST exacto que hace el formulario real de Facilito, decodificando la
# respuesta en windows-1252 (la pagina reporta ese charset; si se decodifica
# como UTF-8 se corrompen tildes y enies).
# ---------------------------------------------------------------------------

JS_SCRAPE = """
async ({ baseUrl, siteKey, regiones, productos }) => {
  function getToken() {
    return new Promise((resolve) => {
      grecaptcha.ready(function () {
        grecaptcha.execute(siteKey, { action: 'PreciosCombustibleAutomotorAction' }).then(resolve);
      });
    });
  }

  async function post(params) {
    const token = await getToken();
    params['g-recaptcha-response'] = token;
    const body = new URLSearchParams(params);
    const res = await fetch(baseUrl, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: body.toString(),
    });
    const buf = await res.arrayBuffer();
    return new TextDecoder('windows-1252').decode(buf);
  }

  function parseProvincias(html) {
    const doc = new DOMParser().parseFromString(html, 'text/html');
    const sel = doc.querySelector('select[name="provincia"]');
    if (!sel) return [];
    return Array.from(sel.options)
      .filter((o) => o.value !== '9999999')
      .map((o) => ({ code: o.value, name: o.text.trim() }));
  }

  function parseEstaciones(html) {
    const doc = new DOMParser().parseFromString(html, 'text/html');
    const table = doc.querySelector('#tblPreciosAutomotor');
    if (!table) return null; // null = pagina inesperada (posible fallo de token/sesion)
    const trs = Array.from(table.querySelectorAll('tbody tr'));
    const rows = [];
    for (const tr of trs) {
      const tds = Array.from(tr.children).map((td) => td.textContent.trim());
      if (tds.length < 5 || tds[0] === '' || tr.querySelector('.dataTables_empty')) continue;
      const precio = parseFloat(tds[4].replace(',', '.'));
      if (isNaN(precio)) continue;
      rows.push({ distrito: tds[0], establecimiento: tds[1], precio });
    }
    return rows; // [] = pagina valida pero sin estaciones (provincia real sin datos)
  }

  const warnings = [];
  const stationRows = [];
  const provMap = {};

  // 1) Provincias por departamento
  for (const depCode of Object.keys(regiones)) {
    const depName = regiones[depCode];
    const html = await post({
      method: 'cambiarDepartamento',
      departamentoAux: depCode,
      departamento: depCode,
      provincia: '9999999',
      distrito: '9999999',
      producto: '',
      nameRedirectfile: 'buscadorEESS',
    });
    provMap[depCode] = parseProvincias(html);
    if (provMap[depCode].length === 0) warnings.push(`SIN_PROVINCIAS ${depName}`);
  }

  // 2) Estaciones por provincia x producto (distrito=TODOS trae todo de una vez)
  async function fetchProvProducto(depCode, depName, prov, prodCode, prodName, maxAttempts) {
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      const html = await post({
        method: 'cambiarProducto',
        departamentoAux: depCode,
        departamento: depCode,
        provincia: prov.code,
        distrito: '9999999',
        producto: prodCode,
        nameRedirectfile: 'buscadorEESS',
      });
      const rows = parseEstaciones(html);
      if (rows === null) {
        warnings.push(`NO_TABLE ${depName}/${prov.name}/${prodName} intento ${attempt}`);
        continue; // reintentar: probablemente fallo de token/sesion
      }
      return rows; // puede ser [] legitimamente (provincia sin estaciones para ese producto)
    }
    return null; // agoto reintentos
  }

  for (const depCode of Object.keys(regiones)) {
    const depName = regiones[depCode];
    for (const prov of provMap[depCode]) {
      for (const prodCode of Object.keys(productos)) {
        const prodName = productos[prodCode];
        const rows = await fetchProvProducto(depCode, depName, prov, prodCode, prodName, 3);
        if (rows === null) {
          warnings.push(`FALLO_DEFINITIVO ${depName}/${prov.name}/${prodName}`);
          continue;
        }
        for (const r of rows) {
          stationRows.push({
            dep: depName,
            prov: prov.name,
            distrito: r.distrito,
            establecimiento: r.establecimiento,
            producto: prodName,
            precio: r.precio,
          });
        }
      }
    }
  }

  return { stationRows, warnings, provMap };
}
"""


async def scrape() -> dict:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        log.info("Abriendo Facilito...")
        await page.goto(BUSCADOR_URL, wait_until="domcontentloaded")
        # No dependemos de los <select> del formulario (todo se hace via fetch()),
        # solo necesitamos que el script de reCAPTCHA haya cargado.
        await page.wait_for_function("() => typeof window.grecaptcha !== 'undefined'")
        await page.wait_for_timeout(1500)

        log.info("Extrayendo datos (departamentos, provincias, precios)...")
        result = await page.evaluate(
            JS_SCRAPE,
            {
                "baseUrl": BASE_URL,
                "siteKey": RECAPTCHA_SITE_KEY,
                "regiones": REGIONES,
                "productos": PRODUCTOS,
            },
        )

        await browser.close()
        return result


def to_title(s: str) -> str:
    return " ".join(w[:1].upper() + w[1:].lower() if w else w for w in s.split(" "))


def build_csv_rows(station_rows: list[dict], fecha: str) -> list[list[str]]:
    rows = []
    for r in station_rows:
        rows.append(
            [
                fecha,
                to_title(r["dep"]),
                to_title(r["prov"]),
                to_title(r["distrito"]),
                r["establecimiento"],
                r["producto"],
                f"{r['precio']:.2f}",
            ]
        )

    def sort_key(row):
        region_idx = REGION_ORDER.index(row[1].upper()) if row[1].upper() in REGION_ORDER else 999
        return (region_idx, row[2], row[3], row[5], row[4])

    # ordenar usando los valores originales (antes de title-case) para region
    rows_with_orig = list(zip(rows, station_rows))
    rows_with_orig.sort(
        key=lambda pair: (
            REGION_ORDER.index(pair[1]["dep"]) if pair[1]["dep"] in REGION_ORDER else 999,
            pair[1]["prov"],
            pair[1]["distrito"],
            pair[1]["producto"],
            pair[1]["establecimiento"],
        )
    )
    return [pair[0] for pair in rows_with_orig]


def main():
    force = "--force" in sys.argv
    today = date.today().isoformat()
    out_path = DATA_DIR / f"{today}_combustibles.csv"

    if out_path.exists() and not force:
        log.info(f"El archivo de hoy ya existe ({out_path.name}); no se sobrescribe. Usa --force para regenerar.")
        return

    log.info(f"=== Iniciando extraccion Facilito {today} ===")
    result = asyncio.run(scrape())

    station_rows = result["stationRows"]
    warnings = result["warnings"]
    prov_map = result["provMap"]

    for w in warnings:
        log.warning(w)

    if not station_rows:
        log.error("No se obtuvo ningun registro. No se genera archivo para evitar guardar un dia vacio por error.")
        sys.exit(1)

    csv_rows = build_csv_rows(station_rows, today)

    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADER)
        writer.writerows(csv_rows)

    # resumen por region para el log
    by_region = {}
    for r in station_rows:
        by_region[r["dep"]] = by_region.get(r["dep"], 0) + 1

    total_provincias = sum(len(v) for v in prov_map.values())

    log.info(f"Archivo generado: {out_path} ({len(csv_rows)} filas)")
    log.info(f"Provincias consultadas: {total_provincias}")
    for region in REGION_ORDER:
        log.info(f"  {region}: {by_region.get(region, 0)} registros de estacion")
    log.info(f"Advertencias durante la extraccion: {len(warnings)}")
    log.info(f"=== Extraccion {today} completada ===")


if __name__ == "__main__":
    main()
