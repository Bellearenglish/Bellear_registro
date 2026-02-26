import webview
import threading
import time
from Registro_jornada import app


def start_flask():
    app.run()


if __name__ == '__main__':
    t = threading.Thread(target=start_flask)
    t.daemon = True
    t.start()

    time.sleep(1.5)

    webview.create_window(
        "Registro de Jornada - Bellear English",
        "http://127.0.0.1:5000",
        width=1100,
        height=750,
        resizable=True
    )

    webview.start()