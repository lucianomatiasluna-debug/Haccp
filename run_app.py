import os
import sys
import time
import threading
import webbrowser
import streamlit
from streamlit.web import cli as stcli

def get_base_dir():
    if getattr(sys, 'frozen', False):
        return getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.dirname(os.path.abspath(__file__))

def find_app_py(base_dir):
    candidates = [
        os.path.join(base_dir, 'app.py'),
        os.path.join(base_dir, '_internal', 'app.py'),
        os.path.join(os.path.dirname(sys.executable), 'app.py'),
        os.path.join(os.path.dirname(sys.executable), '_internal', 'app.py')
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return os.path.join(base_dir, 'app.py')

def main():
    base_dir = get_base_dir()
    app_path = find_app_py(base_dir)

    print("==================================================")
    print(" 🍳 Iniciando Rational HACCP Analytics Dashboard")
    print("==================================================")
    print(f" Ruta de la App: {app_path}")
    print(" Abriendo navegador en http://localhost:8501 ...")
    print(" No cierres esta ventana mientras usas la aplicación.")
    print("==================================================")

    def open_browser():
        time.sleep(2.0)
        webbrowser.open("http://localhost:8501")

    threading.Thread(target=open_browser, daemon=True).start()

    sys.argv = [
        "streamlit", "run", app_path,
        "--server.port=8501",
        "--server.headless=true",
        "--global.developmentMode=false"
    ]
    sys.exit(stcli.main())

if __name__ == '__main__':
    main()
