# ⚡ Rational OEE Analytics Dashboard

Panel de control interactivo para el cálculo y monitoreo de **OEE (Overall Equipment Effectiveness / Eficiencia General de los Equipos)** enfocado en hornos combinados **Rational** (iCombi Pro, iCombi Classic, SelfCookingCenter, CombiMaster) a partir de sus registros de auditoría HACCP.

---

## 🎯 Modelo de Métricas OEE

$$\text{OEE} = \text{Disponibilidad (A)} \times \text{Rendimiento (P)} \times \text{Calidad (Q)}$$

* **Disponibilidad ($A$):** Horas reales de operación (cocción + limpiezas iCareSystem) vs. Tiempo total calendario base 24h.
* **Rendimiento ($P$):** Cadencia de cargas por hora real de operación comparada con la capacidad teórica, penalizada por pérdidas de calor por aperturas de puerta.
* **Calidad ($Q$):** Cargas exitosas (`RETURN`) vs. cargas abortadas/canceladas (`ABORT`).
* **Estándar OEE:**
  * 🟢 **Clase Mundial:** $\ge 85\%$
  * 🔵 **Aceptable:** $65\% - 84\%$
  * 🟡 **Mejorable:** $40\% - 64\%$
  * 🔴 **Bajo:** $< 40\%$

---

## 🚀 Ejecución Local

### Prerrequisitos
Tener Python 3.10+ instalado.

### Instalación y Lanzamiento
```bash
# 1. Clonar o descargar el repositorio
cd rational_haccp_dashboard

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Iniciar la aplicación
streamlit run app.py
```

---

## ☁️ Despliegue Gratuito en Streamlit Community Cloud

Puedes desplegar esta aplicación de forma **100% gratuita** en la nube en menos de 2 minutos:

1. Sube esta carpeta a un repositorio en tu cuenta de **[GitHub](https://github.com)**.
2. Inicia sesión en **[share.streamlit.io](https://share.streamlit.io)** con tu cuenta de GitHub.
3. Haz clic en **"New app"** y selecciona:
   * **Repository:** Tu repositorio de GitHub.
   * **Branch:** `main`.
   * **Main file path:** `app.py`.
4. Haz clic en **"Deploy!"** y obtendrás una URL pública o privada (ejemplo: `https://rational-oee-analytics.streamlit.app`) accesible desde cualquier PC, tablet o celular.

---

## 📥 Ingesta de Datos
* **Archivos Individuales:** Arrastra archivos `.txt` descargados del USB del horno Rational.
* **Archivos ZIP:** Puedes arrastrar un `.zip` que contenga cientos de archivos `.txt`.
* **Carpeta Compartida / Servidor:** Ingresa la ruta de red (ej. `Z:\lLuna\HACCP_DATOS\logs`) y haz clic en *Escanear y Cargar Carpeta*.

---

## 🛠️ Tecnologías
* **Python 3.10+**
* **Streamlit**
* **Plotly Express / Graph Objects**
* **Pandas**
* **SQLite3**
