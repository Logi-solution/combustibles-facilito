"""
Visita la app de Streamlit Community Cloud con un navegador real
(Playwright + Chromium) para contar como trafico valido y evitar que se
duerma por inactividad. Si la encuentra dormida ("Zzzz"), hace clic en
"Yes, get this app back up!" y espera a que termine de reconstruirse.

Pensado para correr en GitHub Actions (ver
.github/workflows/keep-alive-streamlit.yml), donde SI hay salida libre a
internet (a diferencia del contenedor cloud de Claude, que la tiene
bloqueada por politica de la organizacion).
"""

import sys
import time

from playwright.sync_api import sync_playwright

URL = "https://precios-combustibles.streamlit.app/"
SLEEP_TEXT = "This app has gone to sleep due to inactivity"
WAKE_BUTTON_TEXT = "Yes, get this app back up!"
OVEN_TEXT = "in the oven"
WAKE_TIMEOUT_SECONDS = 90


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context().new_page()

        page.goto(URL, timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)

        body_text = page.locator("body").inner_text(timeout=10000)
        was_asleep = SLEEP_TEXT in body_text

        if not was_asleep:
            print("OK: la app ya estaba despierta.")
            browser.close()
            return 0

        print("La app estaba dormida (Zzzz). Haciendo clic para despertarla...")
        try:
            page.get_by_text(WAKE_BUTTON_TEXT, exact=False).first.click(timeout=10000)
        except Exception as exc:  # noqa: BLE001
            print(f"No se pudo hacer clic en el boton directamente ({exc}), reintentando por rol...")
            page.get_by_role("button", name=WAKE_BUTTON_TEXT).click(timeout=10000)

        deadline = time.time() + WAKE_TIMEOUT_SECONDS
        while time.time() < deadline:
            page.wait_for_timeout(5000)
            try:
                current_text = page.locator("body").inner_text(timeout=10000)
            except Exception:  # noqa: BLE001
                continue
            if SLEEP_TEXT not in current_text and OVEN_TEXT not in current_text:
                print("OK: la app estaba dormida y se reactivo correctamente.")
                browser.close()
                return 0
            print(f"Reconstruyendo todavia... ({int(deadline - time.time())}s restantes)")

        print("FALLO: pasaron 90s y la app no termino de cargar.")
        browser.close()
        return 1


if __name__ == "__main__":
    sys.exit(main())
