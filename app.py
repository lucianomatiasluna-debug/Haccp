import os
import io
import datetime
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from PIL import Image

from haccp_parser import load_multiple_haccp_files
from haccp_database import (
    init_db, save_df_to_db, scan_and_sync_folder,
    get_all_charges_from_db, clear_database,
    get_equipos_catalogo, save_operario_carga, save_operario_calidad_completa,
    update_charge_production_records,
    get_base_app_dir, get_default_db_path,
    RATIONAL_MANUAL_CAPACITIES, get_rational_capacity
)

# ---------------------------------------------------------
# CONFIGURACIÓN DE PÁGINA STREAMLIT
# ---------------------------------------------------------
st.set_page_config(
    page_title="Rational OEE Analytics | Planta y Operaciones",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------------------------------------------------------
# ESTILOS CSS PERSONALIZADOS (Blanco, Azul Marino y Verde Esmeralda)
# ---------------------------------------------------------
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
        color: #0B2545;
    }
    
    .main-title {
        font-size: 2.1rem;
        font-weight: 700;
        color: #0B2545;
        letter-spacing: -0.5px;
        margin-bottom: 0px;
    }
    
    .sub-title {
        font-size: 0.95rem;
        color: #475569;
        margin-bottom: 18px;
        font-weight: 400;
    }

    .kpi-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        text-align: center;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .kpi-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 6px rgba(0,0,0,0.08);
    }
    .kpi-label {
        font-size: 0.8rem;
        font-weight: 600;
        text-transform: uppercase;
        color: #64748B;
        letter-spacing: 0.5px;
        margin-bottom: 6px;
    }
    .kpi-value {
        font-size: 1.8rem;
        font-weight: 700;
        color: #0B2545;
    }
    .kpi-badge {
        font-size: 0.75rem;
        font-weight: 600;
        padding: 3px 8px;
        border-radius: 999px;
        display: inline-block;
        margin-top: 4px;
    }
    .badge-success { background: #ECFDF5; color: #059669; }
    .badge-info { background: #EFF6FF; color: #1D4ED8; }
    .badge-warning { background: #FFFBEB; color: #D97706; }
    .badge-danger { background: #FEF2F2; color: #DC2626; }

    .status-bar {
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 10px 16px;
        font-size: 0.85rem;
        color: #334155;
        margin-bottom: 20px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    
    .empty-state {
        background: #F8FAFC;
        border: 2px dashed #CBD5E1;
        border-radius: 12px;
        padding: 35px;
        text-align: center;
        color: #475569;
        margin: 25px 0;
    }

    .login-box {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 16px;
        padding: 32px;
        box-shadow: 0 10px 15px -3px rgba(0,0,0,0.05);
        margin-top: 40px;
    }
    
    .guide-slot-filled {
        background-color: #10B981;
        color: white;
        padding: 8px 12px;
        border-radius: 6px;
        font-weight: 600;
        text-align: center;
        margin-bottom: 4px;
        font-size: 0.85rem;
    }
    
    .guide-slot-empty {
        background-color: #E2E8F0;
        color: #64748B;
        padding: 8px 12px;
        border-radius: 6px;
        font-weight: 500;
        text-align: center;
        margin-bottom: 4px;
        font-size: 0.85rem;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# SISTEMA DE AUTENTICACIÓN Y ROLES DE ACCESO
# ---------------------------------------------------------
DEFAULT_USERS = {
    "lucianomatiasluna@gmail.com": {"password": "Rational2026!", "rol": "Supervisor", "nombre": "Luciano Luna"},
    "bjaillita@foodservice.com.ar": {"password": "Rational2026!", "rol": "Supervisor", "nombre": "B. Jaillita"},
    "lrivero@foodservice.com.ar": {"password": "Rational2026!", "rol": "Supervisor", "nombre": "L. Rivero"},
    "fvannella@foodservice.com.ar": {"password": "Rational2026!", "rol": "Operario", "nombre": "F. Vannella (Operario)"}
}

def get_authorized_users():
    if hasattr(st, "secrets") and "passwords" in st.secrets:
        custom_dict = {}
        for mail, pwd in st.secrets["passwords"].items():
            base_info = DEFAULT_USERS.get(mail.strip().lower(), {"rol": "Supervisor", "nombre": mail.split('@')[0]})
            custom_dict[mail.strip().lower()] = {
                "password": str(pwd).strip(),
                "rol": base_info.get("rol", "Supervisor"),
                "nombre": base_info.get("nombre", mail)
            }
        return custom_dict
    return DEFAULT_USERS

def check_login():
    if st.session_state.get("authenticated", False):
        return True

    users_db = get_authorized_users()

    col_a, col_b, col_c = st.columns([1, 1.3, 1])
    with col_b:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("""
        <div class="login-box">
            <div style="text-align: center; margin-bottom: 24px;">
                <div style="font-size: 2.2rem; margin-bottom: 6px;">⚡</div>
                <h2 style="color: #0B2545; font-size: 1.5rem; font-weight: 700; margin: 0;">Rational OEE Analytics</h2>
                <p style="color: #64748B; font-size: 0.88rem; margin-top: 4px;">Acceso Confidencial • Ingrese sus credenciales</p>
            </div>
        """, unsafe_allow_html=True)

        with st.form("login_form"):
            email_input = st.text_input("Correo Electrónico:", placeholder="usuario@foodservice.com.ar")
            pass_input = st.text_input("Contraseña:", type="password", placeholder="••••••••")
            submit_btn = st.form_submit_button("🔓 Iniciar Sesión", use_container_width=True)

            if submit_btn:
                clean_email = email_input.strip().lower()
                clean_pass = pass_input.strip()

                user_found = None
                for u_mail, u_data in users_db.items():
                    if u_mail.strip().lower() == clean_email and str(u_data["password"]).strip() == clean_pass:
                        user_found = u_data
                        break

                if user_found:
                    st.session_state["authenticated"] = True
                    st.session_state["user_email"] = clean_email
                    st.session_state["user_role"] = user_found.get("rol", "Operario")
                    st.session_state["user_name"] = user_found.get("nombre", clean_email)
                    st.success(f"¡Bienvenido {st.session_state['user_name']}! Cargando...")
                    st.rerun()
                else:
                    st.error("Credenciales incorrectas o usuario no autorizado.")

        st.markdown("""
            <div style="text-align: center; color: #94A3B8; font-size: 0.78rem; margin-top: 14px;">
                Food Service America • Control HACCP y Eficiencia Operativa
            </div>
        </div>
        """, unsafe_allow_html=True)

    return False

if not check_login():
    st.stop()

# ---------------------------------------------------------
# INICIALIZACIÓN DE BASE DE DATOS SQLITE
# ---------------------------------------------------------
app_dir = get_base_app_dir()
default_db_file = get_default_db_path()
default_logs_dir = os.path.join(app_dir, "logs")

if not os.path.exists(default_logs_dir):
    try:
        os.makedirs(default_logs_dir, exist_ok=True)
    except Exception:
        pass

init_db(default_db_file)
df_db = get_all_charges_from_db(default_db_file)
df_catalogo = get_equipos_catalogo(default_db_file)

user_role = st.session_state.get("user_role", "Supervisor")
user_name = st.session_state.get("user_name", "")
user_email = st.session_state.get("user_email", "")

# ---------------------------------------------------------
# BARRA LATERAL (SIDEBAR): SESIÓN Y CONTROLES
# ---------------------------------------------------------
st.sidebar.markdown(f"**👤 Usuario:** `{user_name}`")
st.sidebar.markdown(f"**🏷️ Rol:** `{user_role}`")

if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
    st.session_state["authenticated"] = False
    st.session_state["user_email"] = ""
    st.session_state["user_role"] = ""
    st.rerun()

st.sidebar.markdown("---")

# Filtros para Supervisor
if user_role == "Supervisor":
    st.sidebar.markdown("### ⚙️ Ingesta de Logs HACCP")
    uploaded_files = st.sidebar.file_uploader(
        "Cargar logs (.txt o .zip):",
        type=["txt", "zip"],
        accept_multiple_files=True
    )
    if uploaded_files:
        with st.spinner("Indexando registros HACCP..."):
            df_uploaded = load_multiple_haccp_files(uploaded_files)
            if not df_uploaded.empty:
                added = save_df_to_db(df_uploaded, db_path=default_db_file)
                st.sidebar.success(f"✅ {len(df_uploaded)} leídos ({added} nuevos).")
                st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🔍 Filtros de Consulta")

    series_unicas = sorted(df_db['Serie_SN'].dropna().unique().tolist()) if not df_db.empty else []
    selected_series = st.sidebar.multiselect("Número de Serie (S/N):", series_unicas, default=series_unicas)

    df_valid_dates = df_db[df_db['Fecha_Hora'].notnull()].copy() if not df_db.empty else pd.DataFrame()
    if not df_valid_dates.empty:
        min_date = df_valid_dates['Fecha_Hora'].min().date()
        max_date = df_valid_dates['Fecha_Hora'].max().date()
        date_range = st.sidebar.date_input("Rango de Fechas:", [min_date, max_date], min_value=min_date, max_value=max_date)
    else:
        date_range = []

    categorias = sorted(df_db['Categoria'].dropna().unique().tolist()) if not df_db.empty else []
    selected_cats = st.sidebar.multiselect("Categoría:", categorias, default=categorias)

    filtered_df = df_db.copy() if not df_db.empty else pd.DataFrame()
    if not filtered_df.empty:
        if selected_series:
            filtered_df = filtered_df[filtered_df['Serie_SN'].isin(selected_series)]
        if len(date_range) == 2:
            start_d, end_d = date_range
            filtered_df = filtered_df[(filtered_df['Fecha_Hora'].dt.date >= start_d) & (filtered_df['Fecha_Hora'].dt.date <= end_d)]
        if selected_cats:
            filtered_df = filtered_df[filtered_df['Categoria'].isin(selected_cats)]
else:
    filtered_df = df_db.copy() if not df_db.empty else pd.DataFrame()
    date_range = []

date_span_str = f"{date_range[0]} al {date_range[1]}" if len(date_range) == 2 else "Histórico Completo"

# ---------------------------------------------------------
# CÁLCULOS GENERALES DE OEE Y PLACAS
# ---------------------------------------------------------
df_cooking = filtered_df[filtered_df['Categoria'] != 'Limpieza (iCareSystem)'].copy() if not filtered_df.empty else pd.DataFrame()
df_cleaning = filtered_df[filtered_df['Categoria'] == 'Limpieza (iCareSystem)'].copy() if not filtered_df.empty else pd.DataFrame()

cooking_hours = df_cooking['Duracion_Horas'].sum() if not df_cooking.empty else 0.0
cleaning_hours = df_cleaning['Duracion_Horas'].sum() if not df_cleaning.empty else 0.0

total_ovens = filtered_df['Serie_SN'].nunique() if not filtered_df.empty else 0
ovens_count = max(1, total_ovens)

if len(date_range) == 2:
    days_span = max(1, (date_range[1] - date_range[0]).days + 1)
else:
    days_span = max(1, filtered_df['Fecha'].nunique()) if not filtered_df.empty else 1

total_calendar_hours = days_span * 24.0 * ovens_count
tiempo_disponible_coccion = max(0.1, total_calendar_hours - cleaning_hours)

# 1. Disponibilidad (A)
availability = min(1.0, max(0.0, cooking_hours / tiempo_disponible_coccion))

# 2. Rendimiento (P)
total_placas_utilizadas = df_cooking['Placas_Utilizadas'].fillna(df_cooking['Capacidad_Placas_Max']).sum() if not df_cooking.empty else 0
total_capacidad_teorica_placas = df_cooking['Capacidad_Placas_Max'].sum() if not df_cooking.empty else 0
performance = min(1.0, max(0.0, total_placas_utilizadas / total_capacidad_teorica_placas)) if total_capacidad_teorica_placas > 0 else 1.0

# 3. Calidad (Q)
total_unidades = df_cooking['Unidades_Totales'].sum() if not df_cooking.empty else 0
total_unidades_ok = df_cooking['Unidades_OK'].sum() if not df_cooking.empty else 0
total_unidades_nok = df_cooking['Unidades_Rechazadas'].sum() if not df_cooking.empty else 0

total_placas_ok = df_cooking['Placas_OK'].fillna(df_cooking['Placas_Utilizadas']).sum() if not df_cooking.empty else 0
quality = min(1.0, max(0.0, total_unidades_ok / total_unidades)) if total_unidades > 0 else (min(1.0, total_placas_ok / total_placas_utilizadas) if total_placas_utilizadas > 0 else 1.0)

# 4. OEE Global
oee = availability * performance * quality

# Lista de motivos de rechazo estandarizada
MOTIVOS_RECHAZO_LIST = [
    "100% Conforme (Sin Desvío)",
    "Cocción Quemada / Exceso de Calor",
    "Cocción Cruda / Falta de Temperatura",
    "Deshidratado / Seco",
    "Pérdida Térmica (Puerta Abierta / Falla)",
    "Deformación / Error de Textura o Corte",
    "Contaminación Cruzada o Caída",
    "Error en Dosificación de Receta",
    "Otro"
]

# =========================================================
# VISTA EXCLUSIVA: COCINERO / OPERARIO DE PLANTA (fvannella)
# =========================================================
if user_role == "Operario":
    st.markdown('<div class="main-title">👨‍🍳 Terminal de Operación de Cocina</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sub-title">Cocinero: <b>{user_name}</b> | Registro Rápido de Carga y Calidad</div>', unsafe_allow_html=True)

    # Selector de Equipo de Planta (Hornos vs Marmitas)
    st.markdown("#### 🏭 Selección de Equipo a Auditar")
    equipos_dict = {
        r['id']: f"{r['nombre']} [{r['tipo']} - Capacidad: {r['capacidad_nominal']:.0f} {r['unidad']}]"
        for _, r in df_catalogo.iterrows()
    }
    sel_eq_id = st.selectbox("Selecciona el Horno o Marmita:", options=list(equipos_dict.keys()), format_func=lambda x: equipos_dict[x], key="op_eq_sel")
    eq_row = df_catalogo[df_catalogo['id'] == sel_eq_id].iloc[0]
    
    es_marmita = (eq_row['tipo'] == 'Marmita Industrial')
    unidad_carga = "Kg" if es_marmita else "Placas"
    cap_eq_max = float(eq_row['capacidad_nominal'])

    st.info(f"📍 **Equipo Activo:** {eq_row['nombre']} | **Tipo:** {eq_row['tipo']} | **Capacidad Nominal:** {cap_eq_max:.0f} {unidad_carga}")

    # Indicadores rápidos del cocinero
    col_op1, col_op2, col_op3, col_op4 = st.columns(4)
    with col_op1:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">{'Kilos Procesados' if es_marmita else 'Placas Cargadas'}</div>
            <div class="kpi-value" style="color: #1D4ED8;">{total_placas_utilizadas:.0f} {unidad_carga}</div>
            <div class="kpi-badge badge-info">Capacidad: {total_capacidad_teorica_placas:.0f} {unidad_carga}</div>
        </div>
        """, unsafe_allow_html=True)
    with col_op2:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">Aprovechamiento de Cámara</div>
            <div class="kpi-value" style="color: #0B2545;">{performance*100:.1f}%</div>
            <div class="kpi-badge badge-info">Rendimiento Operativo</div>
        </div>
        """, unsafe_allow_html=True)
    with col_op3:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">{'Kilos Conformes (OK)' if es_marmita else 'Unidades Conformes (OK)'}</div>
            <div class="kpi-value" style="color: #059669;">{total_unidades_ok:.0f}</div>
            <div class="kpi-badge badge-success">De {total_unidades:.0f} producidas</div>
        </div>
        """, unsafe_allow_html=True)
    with col_op4:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">Tasa de Calidad</div>
            <div class="kpi-value" style="color: #059669;">{quality*100:.1f}%</div>
            <div class="kpi-badge badge-danger">Merma: {total_unidades_nok:.0f}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Las 2 ventanas exclusivas para el cocinero
    tab_op_carga, tab_op_calidad = st.tabs([
        f"📥 1. Registro de Carga ({'Kilos Introducidos' if es_marmita else 'Placas Depositadas'})",
        f"📦 2. Control de Calidad ({'Kilos OK vs Merma' if es_marmita else 'Unidades OK vs Mal'})"
    ])

    # --- VENTANA 1: CARGA DE PLACAS O KILOS ---
    with tab_op_carga:
        st.subheader(f"📥 1. Registro de Carga en {eq_row['nombre']}")
        
        if not df_cooking.empty:
            cargas_list = df_cooking.sort_values(by='id', ascending=False).to_dict('records')
            opciones_cargas = {
                c['id']: f"Carga #{c['id']} | {c['Fecha']} {c['Hora']} | Prog: {c['Programa']} ({c['Duracion_Min']} min)"
                for c in cargas_list
            }
            sel_c_id_1 = st.selectbox("Selecciona la Cocción en Curso:", options=list(opciones_cargas.keys()), format_func=lambda x: opciones_cargas[x], key="op_c_sel_1")
            carga_item_1 = df_cooking[df_cooking['id'] == sel_c_id_1].iloc[0]

            col_cp1, col_cp2 = st.columns([1, 1])

            with col_cp1:
                st.markdown("#### Datos de la Carga")
                if not es_marmita:
                    val_placas = int(carga_item_1['Placas_Utilizadas'] or cap_eq_max)
                    cant_ingresada = st.slider("Cantidad de Placas Depositadas:", 1, int(cap_eq_max), min(val_placas, int(cap_eq_max)))
                    pct_aprov = round((cant_ingresada / cap_eq_max) * 100, 1)
                    st.metric("Aprovechamiento de Cámara:", f"{pct_aprov}%", delta=f"{cant_ingresada} de {int(cap_eq_max)} guías")
                else:
                    val_kg = float(carga_item_1['Kilos_Totales'] or cap_eq_max)
                    cant_ingresada = st.number_input("Kilos Introducidos en Marmita (Kg):", min_value=1.0, max_value=cap_eq_max, value=min(val_kg, cap_eq_max), step=5.0)
                    pct_aprov = round((cant_ingresada / cap_eq_max) * 100, 1)
                    st.metric("Capacidad Ocupada de Marmita:", f"{pct_aprov}%", delta=f"{cant_ingresada:.1f} Kg de {cap_eq_max:.0f} Kg")

                if st.button("💾 Confirmar y Guardar Carga", type="primary", use_container_width=True):
                    save_operario_carga(sel_c_id_1, eq_row['nombre'], cant_ingresada, unidad=unidad_carga, db_path=default_db_file)
                    st.success(f"✅ ¡Carga #{sel_c_id_1} guardada con {cant_ingresada} {unidad_carga}!")
                    st.rerun()

            with col_cp2:
                if not es_marmita:
                    st.markdown(f"#### 🔲 Esquema de Niveles de {eq_row['nombre']}")
                    for nivel in range(int(cap_eq_max), 0, -1):
                        if nivel <= cant_ingresada:
                            st.markdown(f'<div class="guide-slot-filled">🟢 Guía #{nivel:02d}: PLACA OCUPADA</div>', unsafe_allow_html=True)
                        else:
                            st.markdown(f'<div class="guide-slot-empty">⚪ Guía #{nivel:02d}: Guía Libre</div>', unsafe_allow_html=True)
                else:
                    st.markdown(f"#### 🥣 Nivel de Llenado de {eq_row['nombre']}")
                    st.progress(min(1.0, cant_ingresada / cap_eq_max))
                    st.write(f"Ocupación: **{cant_ingresada:.1f} Kg / {cap_eq_max:.0f} Kg** ({pct_aprov}%)")
        else:
            st.info("No hay cargas disponibles para asignar.")

    # --- VENTANA 2: CONTROL DE CALIDAD Y MOTIVO DE RECHAZO ---
    with tab_op_calidad:
        st.subheader(f"📦 2. Control de Calidad de Producto en {eq_row['nombre']}")

        if not df_cooking.empty:
            sel_c_id_2 = st.selectbox("Selecciona la Cocción Finalizada:", options=list(opciones_cargas.keys()), format_func=lambda x: opciones_cargas[x], key="op_c_sel_2")
            carga_item_2 = df_cooking[df_cooking['id'] == sel_c_id_2].iloc[0]

            with st.form("form_calidad_cocinero"):
                st.markdown(f"#### Registro de Salida - Programa: **{carga_item_2['Programa']}**")

                col_cq1, col_cq2, col_cq3 = st.columns(3)
                if not es_marmita:
                    def_tot = int(carga_item_2['Unidades_Totales'] or 200)
                    def_ok = int(carga_item_2['Unidades_OK'] or def_tot)
                    with col_cq1:
                        tot_prod = st.number_input("Unidades Totales Producidas:", min_value=1, value=def_tot, step=5)
                    with col_cq2:
                        ok_prod = st.number_input("Unidades que Salieron BIEN (OK):", min_value=0, max_value=tot_prod, value=min(def_ok, tot_prod), step=5)
                    with col_cq3:
                        nok_prod = tot_prod - ok_prod
                        st.metric("Unidades MAL (Merma):", f"{nok_prod} un.", delta=f"{round(nok_prod/tot_prod*100, 1)}% rechazo" if tot_prod>0 else "0%", delta_color="inverse")
                else:
                    def_tot_kg = float(carga_item_2['Kilos_Totales'] or 150.0)
                    def_ok_kg = float(carga_item_2['Kilos_OK'] or def_tot_kg)
                    with col_cq1:
                        tot_prod = st.number_input("Kilos Totales Obtenidos (Kg):", min_value=1.0, value=def_tot_kg, step=5.0)
                    with col_cq2:
                        ok_prod = st.number_input("Kilos que Salieron BIEN (Kg OK):", min_value=0.0, max_value=tot_prod, value=min(def_ok_kg, tot_prod), step=5.0)
                    with col_cq3:
                        nok_prod = round(tot_prod - ok_prod, 1)
                        st.metric("Kilos de Merma (Kg NOK):", f"{nok_prod} Kg", delta=f"{round(nok_prod/tot_prod*100, 1)}% rechazo" if tot_prod>0 else "0%", delta_color="inverse")

                # Desplegable amigable de Motivos de Rechazo
                current_motivo = str(carga_item_2['Motivo_Rechazo'] or "")
                idx_mot = 0
                if current_motivo in MOTIVOS_RECHAZO_LIST:
                    idx_mot = MOTIVOS_RECHAZO_LIST.index(current_motivo)

                motivo_elegido = st.selectbox("📋 Motivo del Desvío o Rechazo:", MOTIVOS_RECHAZO_LIST, index=idx_mot)
                
                motivo_extra = ""
                if motivo_elegido == "Otro":
                    motivo_extra = st.text_input("Especificar otro motivo:", value=current_motivo if current_motivo not in MOTIVOS_RECHAZO_LIST else "")

                btn_save_qc = st.form_submit_button("💾 Guardar Control de Calidad", use_container_width=True)
                if btn_save_qc:
                    motivo_final = motivo_extra if motivo_elegido == "Otro" else (motivo_elegido if motivo_elegido != "100% Conforme (Sin Desvío)" else "")
                    save_operario_calidad_completa(sel_c_id_2, tot_prod, ok_prod, nok_prod, motivo=motivo_final, unidad="Kg" if es_marmita else "Unidades", db_path=default_db_file)
                    st.success(f"✅ ¡Calidad registrada! {ok_prod} {'Kg' if es_marmita else 'unidades'} conformes.")
                    st.rerun()

# =========================================================
# VISTA COMPLETA: SUPERVISORES Y GERENCIA
# =========================================================
else:
    st.markdown('<div class="main-title">⚡ Rational OEE Analytics</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sub-title">Panel Ejecutivo de Eficiencia General de Equipos (OEE) | Supervisor: <b>{user_name}</b></div>', unsafe_allow_html=True)

    st.markdown(f"""
    <div class="status-bar">
        <div>🏭 <b>Flota:</b> {total_ovens} Horno(s) Rational &nbsp;|&nbsp; 📋 <b>Cargas:</b> {len(filtered_df)} &nbsp;|&nbsp; 🍞 <b>Placas:</b> {total_placas_utilizadas:.0f} / {total_capacidad_teorica_placas:.0f}</div>
        <div>📅 <b>Rango:</b> {date_span_str}</div>
    </div>
    """, unsafe_allow_html=True)

    # Tarjetas KPI OEE
    col_oee, col_a, col_p, col_q, col_hrs = st.columns(5)
    def get_oee_badge(val):
        if val >= 0.85: return '<span class="kpi-badge badge-success">Clase Mundial (≥85%)</span>'
        elif val >= 0.65: return '<span class="kpi-badge badge-info">Aceptable (65-84%)</span>'
        elif val >= 0.40: return '<span class="kpi-badge badge-warning">Mejorable (40-64%)</span>'
        return '<span class="kpi-badge badge-danger">Bajo (<40%)</span>'

    with col_oee:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">OEE Global</div>
            <div class="kpi-value" style="color: #059669;">{oee*100:.1f}%</div>
            {get_oee_badge(oee)}
        </div>
        """, unsafe_allow_html=True)

    with col_a:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">Disponibilidad (A)</div>
            <div class="kpi-value" style="color: #1D4ED8;">{availability*100:.1f}%</div>
            <div class="kpi-badge badge-info">{cooking_hours:.1f}h / {tiempo_disponible_coccion:.0f}h disp.</div>
        </div>
        """, unsafe_allow_html=True)

    with col_p:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">Rendimiento (P)</div>
            <div class="kpi-value" style="color: #0B2545;">{performance*100:.1f}%</div>
            <div class="kpi-badge badge-info">{total_placas_utilizadas:.0f} / {total_capacidad_teorica_placas:.0f} placas</div>
        </div>
        """, unsafe_allow_html=True)

    with col_q:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">Calidad (Q)</div>
            <div class="kpi-value" style="color: #059669;">{quality*100:.1f}%</div>
            <div class="kpi-badge badge-success">{total_unidades_ok:.0f} un. OK ({total_placas_ok:.0f} placas)</div>
        </div>
        """, unsafe_allow_html=True)

    with col_hrs:
        prom_diario = (cooking_hours / days_span) if days_span > 0 else 0
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">Cocción Prom / Día</div>
            <div class="kpi-value" style="color: #0B2545;">{prom_diario:.1f}h</div>
            <div class="kpi-badge badge-info">{cleaning_hours:.1f}h limpiezas excluidas</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Pestañas Supervisor
    tab_sup_main, tab_sup_operario, tab_sup_grid, tab_sup_fleet, tab_sup_haccp, tab_sup_data = st.tabs([
        "📊 Tablero Central OEE & Cascada",
        "👨‍🍳 Terminal de Cocinero (Vista Directa)",
        "📋 Auditoría de Lotes y Placas",
        "🎛️ Benchmarking de Flota",
        "🔍 Control de Calidad y HACCP",
        "📥 Ingesta y Exportación"
    ])

    with tab_sup_main:
        st.markdown("#### 🎯 Indicadores Tacómetro de Eficiencia")
        col_g1, col_g2, col_g3, col_g4 = st.columns(4)
        def create_gauge(val, title, color):
            fig = go.Figure(go.Indicator(
                mode="gauge+number", value=round(val * 100, 1),
                number={'suffix': "%", 'font': {'size': 28, 'color': '#0B2545', 'family': 'Inter'}},
                title={'text': title, 'font': {'size': 14, 'color': '#64748B', 'family': 'Inter'}},
                gauge={
                    'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "#CBD5E1"},
                    'bar': {'color': color, 'thickness': 0.25},
                    'bgcolor': "#F1F5F9", 'borderwidth': 0,
                    'steps': [{'range': [0, 65], 'color': '#FEE2E2'}, {'range': [65, 85], 'color': '#FEF3C7'}, {'range': [85, 100], 'color': '#D1FAE5'}],
                    'threshold': {'line': {'color': "#0B2545", 'width': 3}, 'thickness': 0.75, 'value': 85}
                }
            ))
            fig.update_layout(height=180, margin=dict(l=15, r=15, t=30, b=10), paper_bgcolor="rgba(0,0,0,0)", font={'family': 'Inter'})
            return fig

        with col_g1: st.plotly_chart(create_gauge(oee, "OEE Global", "#10B981"), use_container_width=True)
        with col_g2: st.plotly_chart(create_gauge(availability, "Disponibilidad (A)", "#1D4ED8"), use_container_width=True)
        with col_g3: st.plotly_chart(create_gauge(performance, "Rendimiento (P)", "#0B2545"), use_container_width=True)
        with col_g4: st.plotly_chart(create_gauge(quality, "Calidad (Q)", "#059669"), use_container_width=True)

        st.markdown("---")
        col_w, col_t = st.columns([1, 1])
        with col_w:
            st.markdown("#### 📉 Cascada de Pérdidas OEE (Waterfall)")
            downtime_hours = max(0.0, tiempo_disponible_coccion - cooking_hours)
            perf_loss_hours = max(0.0, cooking_hours * (1.0 - performance))
            qual_loss_hours = max(0.0, cooking_hours * performance * (1.0 - quality))
            effective_oee_hours = cooking_hours * performance * quality

            fig_waterfall = go.Figure(go.Waterfall(
                orientation="v", measure=["absolute", "relative", "relative", "relative", "relative", "total"],
                x=["Tiempo Total (24h)", "Limpiezas iCareSystem", "Horas Inactivas", "Capacidad Ociosa (Placas)", "Merma Calidad", "Tiempo Efectivo OEE"],
                textposition="outside",
                text=[f"{total_calendar_hours:.1f}h", f"-{cleaning_hours:.1f}h", f"-{downtime_hours:.1f}h", f"-{perf_loss_hours:.1f}h", f"-{qual_loss_hours:.1f}h", f"{effective_oee_hours:.1f}h"],
                y=[total_calendar_hours, -cleaning_hours, -downtime_hours, -perf_loss_hours, -qual_loss_hours, effective_oee_hours],
                connector={"line": {"color": "#94A3B8"}}, decreasing={"marker": {"color": "#EF4444"}},
                increasing={"marker": {"color": "#10B981"}}, totals={"marker": {"color": "#0B2545"}}
            ))
            fig_waterfall.update_layout(height=390, margin=dict(l=20, r=20, t=30, b=20), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", yaxis=dict(title="Horas Acumuladas", showgrid=True, gridcolor="#F1F5F9"), xaxis=dict(tickangle=-20))
            st.plotly_chart(fig_waterfall, use_container_width=True)

        with col_t:
            st.markdown("#### 📈 Evolución de Eficiencia en el Tiempo")
            if not df_cooking.empty:
                daily_stats = df_cooking.groupby('Fecha').agg(
                    Horas_Coccion=('Duracion_Horas', 'sum'), Placas_Usadas=('Placas_Utilizadas', 'sum'),
                    Placas_Capacidad=('Capacidad_Placas_Max', 'sum'), Placas_OK=('Placas_OK', 'sum')
                ).reset_index()
                clean_by_date = df_cleaning.groupby('Fecha')['Duracion_Horas'].sum().to_dict() if not df_cleaning.empty else {}
                daily_stats['Horas_Limpieza'] = daily_stats['Fecha'].map(clean_by_date).fillna(0.0)
                daily_stats['Disp'] = (daily_stats['Horas_Coccion'] / (24.0 * ovens_count - daily_stats['Horas_Limpieza']) * 100).clip(upper=100.0)
                daily_stats['Rend'] = (daily_stats['Placas_Usadas'] / daily_stats['Placas_Capacidad'] * 100).fillna(100.0)
                daily_stats['Cal'] = (daily_stats['Placas_OK'] / daily_stats['Placas_Usadas'] * 100).fillna(100.0)
                daily_stats['OEE'] = (daily_stats['Disp'] * daily_stats['Rend'] * daily_stats['Cal'] / 10000.0).round(1)

                fig_trend = go.Figure()
                fig_trend.add_trace(go.Scatter(x=daily_stats['Fecha'], y=daily_stats['OEE'], mode='lines+markers', name='OEE Global (%)', line=dict(color='#10B981', width=3)))
                fig_trend.add_trace(go.Scatter(x=daily_stats['Fecha'], y=daily_stats['Disp'], mode='lines', name='Disponibilidad (%)', line=dict(color='#1D4ED8', width=2, dash='dot')))
                fig_trend.add_trace(go.Scatter(x=daily_stats['Fecha'], y=daily_stats['Rend'], mode='lines', name='Rendimiento Placas (%)', line=dict(color='#0B2545', width=2, dash='dash')))
                fig_trend.add_trace(go.Scatter(x=daily_stats['Fecha'], y=daily_stats['Cal'], mode='lines', name='Calidad (%)', line=dict(color='#059669', width=1.5, dash='dashdot')))
                fig_trend.update_layout(height=390, margin=dict(l=20, r=20, t=30, b=20), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", yaxis=dict(title="Porcentaje (%)", range=[0, 105], showgrid=True, gridcolor="#F1F5F9"), xaxis=dict(title="Fecha", tickangle=-45), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                st.plotly_chart(fig_trend, use_container_width=True)

    with tab_sup_operario:
        st.markdown("### 👨‍🍳 Terminal de Cocinero (Vista Supervisor)")
        st.info("Esta es la misma interfaz simplificada que ve el usuario cocinero (`fvannella@foodservice.com.ar`).")

        if not df_cooking.empty:
            cargas_list_sup = df_cooking.sort_values(by='id', ascending=False).to_dict('records')
            opciones_cargas_sup = {
                c['id']: f"ID #{c['id']} | Horno {c['Serie_SN'][-5:]} ({c['Modelo_Dev']}) | {c['Fecha']} {c['Hora']} | Prog: {c['Programa']}"
                for c in cargas_list_sup
            }
            sel_c_sup = st.selectbox("Seleccionar Carga para Registro Rápido:", options=list(opciones_cargas_sup.keys()), format_func=lambda x: opciones_cargas_sup[x])
            c_row = df_cooking[df_cooking['id'] == sel_c_sup].iloc[0]
            cap_m = int(c_row['Capacidad_Placas_Max']) if pd.notnull(c_row['Capacidad_Placas_Max']) and c_row['Capacidad_Placas_Max'] > 0 else 20

            col_sp1, col_sp2 = st.columns(2)
            with col_sp1:
                st.markdown(f"#### 📥 1. Placas en Horno (Capacidad: {cap_m})")
                p_carg = st.slider("Placas introducidas:", 1, cap_m, min(int(c_row['Placas_Utilizadas'] or cap_m), cap_m), key="sup_p_slider")
                if st.button("💾 Guardar Placas", key="btn_sup_p"):
                    save_operario_carga(sel_c_sup, "Horno Rational", p_carg, unidad="Placas", db_path=default_db_file)
                    st.success("Placas guardadas.")
                    st.rerun()

            with col_sp2:
                st.markdown("#### 📦 2. Unidades y Calidad")
                u_tot_s = st.number_input("Unidades Totales:", min_value=1, value=int(c_row['Unidades_Totales'] or p_carg*10), step=5, key="sup_u_tot")
                u_ok_s = st.number_input("Unidades BIEN (OK):", min_value=0, max_value=u_tot_s, value=min(int(c_row['Unidades_OK'] or u_tot_s), u_tot_s), step=5, key="sup_u_ok")
                u_nok_s = u_tot_s - u_ok_s
                st.write(f"**Unidades Rechazadas / Merma:** `{u_nok_s}`")
                
                mot_cur = str(c_row['Motivo_Rechazo'] or "")
                idx_m_sup = MOTIVOS_RECHAZO_LIST.index(mot_cur) if mot_cur in MOTIVOS_RECHAZO_LIST else 0
                mot_s = st.selectbox("Motivo del Rechazo:", MOTIVOS_RECHAZO_LIST, index=idx_m_sup, key="sup_mot_sel")
                
                if st.button("💾 Guardar Unidades y Calidad", key="btn_sup_q"):
                    save_operario_calidad_completa(sel_c_sup, u_tot_s, u_ok_s, u_nok_s, motivo=mot_s if mot_s!="100% Conforme (Sin Desvío)" else "", unidad="Unidades", db_path=default_db_file)
                    st.success("Calidad guardada.")
                    st.rerun()

    with tab_sup_grid:
        st.markdown("### 📋 Auditoría y Edición Masiva de Cargas")
        if not df_cooking.empty:
            cols_grid = ['id', 'Fecha', 'Hora', 'Serie_SN', 'Modelo_Dev', 'Programa', 'Estado_Final', 'Capacidad_Placas_Max', 'Placas_Utilizadas', 'Placas_OK', 'Unidades_Totales', 'Unidades_OK', 'Unidades_Rechazadas', 'Motivo_Rechazo']
            cols_show = [c for c in cols_grid if c in df_cooking.columns]
            
            edited_batch = st.data_editor(
                df_cooking[cols_show],
                disabled=['id', 'Fecha', 'Hora', 'Serie_SN', 'Modelo_Dev', 'Programa', 'Estado_Final', 'Capacidad_Placas_Max'],
                hide_index=True, use_container_width=True
            )
            if st.button("💾 Guardar Todos los Cambios de la Grilla", type="primary"):
                update_charge_production_records(edited_batch, db_path=default_db_file)
                st.success("¡Base de datos actualizada con éxito!")
                st.rerun()

    with tab_sup_fleet:
        st.markdown("### 🎛️ Benchmarking de Flota (Multi-Horno)")
        if not filtered_df.empty:
            fleet_rows = []
            for sn, grp in filtered_df.groupby('Serie_SN'):
                model = grp['Modelo_Dev'].iloc[0]
                cap_max = get_rational_capacity(model)
                grp_cook = grp[grp['Categoria'] != 'Limpieza (iCareSystem)']
                grp_clean = grp[grp['Categoria'] == 'Limpieza (iCareSystem)']

                sn_cook_h = grp_cook['Duracion_Horas'].sum()
                sn_clean_h = grp_clean['Duracion_Horas'].sum()
                sn_p_used = grp_cook['Placas_Utilizadas'].sum() if not grp_cook.empty else 0
                sn_p_max = grp_cook['Capacidad_Placas_Max'].sum() if not grp_cook.empty else 1
                sn_u_tot = grp_cook['Unidades_Totales'].sum() if not grp_cook.empty else 0
                sn_u_ok = grp_cook['Unidades_OK'].sum() if not grp_cook.empty else 0

                sn_disp = min(1.0, sn_cook_h / max(0.1, (days_span*24.0) - sn_clean_h))
                sn_perf = min(1.0, sn_p_used / sn_p_max) if sn_p_max > 0 else 1.0
                sn_qual = min(1.0, sn_u_ok / sn_u_tot) if sn_u_tot > 0 else 1.0
                sn_oee = sn_disp * sn_perf * sn_qual

                fleet_rows.append({
                    'Serie_SN': sn, 'Modelo': model, 'Capacidad_Manual': f"{cap_max} Placas",
                    'Horas_Coccion': round(sn_cook_h, 1), 'Horas_Limpieza': round(sn_clean_h, 1),
                    'Placas_Cargadas': int(sn_p_used), 'Unidades_OK': int(sn_u_ok),
                    'Disponibilidad_%': round(sn_disp*100, 1), 'Rendimiento_%': round(sn_perf*100, 1),
                    'Calidad_%': round(sn_qual*100, 1), 'OEE_%': round(sn_oee*100, 1)
                })

            df_fl_res = pd.DataFrame(fleet_rows).sort_values(by='OEE_%', ascending=False)
            st.dataframe(df_fl_res, use_container_width=True)

    with tab_sup_haccp:
        st.markdown("### 🔍 Calidad, Temperaturas y Control HACCP")
        col_hp1, col_hp2 = st.columns(2)
        with col_hp1:
            st.markdown("#### 🛑 Tasa de Finalización (RETURN vs ABORT)")
            st_counts = filtered_df['Estado_Final'].value_counts().reset_index()
            st_counts.columns = ['Estado', 'Cantidad']
            fig_st = px.pie(st_counts, names='Estado', values='Cantidad', color='Estado', color_discrete_map={'RETURN': '#10B981', 'ABORT': '#EF4444', 'EN CURSO / INCOMPLETO': '#F59E0B'})
            fig_st.update_layout(height=320, paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_st, use_container_width=True)

        with col_hp2:
            st.markdown("#### 🧼 Higiene iCareSystem")
            if not df_cleaning.empty:
                cl_counts = df_cleaning['Programa'].value_counts().reset_index()
                cl_counts.columns = ['Programa', 'Frecuencia']
                fig_cl = px.bar(cl_counts, x='Frecuencia', y='Programa', orientation='h', color='Frecuencia', color_continuous_scale=['#EFF6FF', '#1D4ED8'])
                fig_cl.update_layout(height=320, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_cl, use_container_width=True)

    with tab_sup_data:
        st.markdown("### 📥 Sincronización y Exportación")
        col_sd1, col_sd2 = st.columns(2)
        with col_sd1:
            folder_input = st.text_input("Ruta de carpeta de logs:", value=st.session_state.get('server_sync_folder', default_logs_dir))
            if st.button("🚀 Escanear y Cargar Carpeta"):
                res = scan_and_sync_folder(folder_input, db_path=default_db_file)
                if res.get("status") == "success": st.success(res.get("message")); st.rerun()
                else: st.error(res.get("message"))
        with col_sd2:
            if not filtered_df.empty:
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine='openpyxl') as writer:
                    filtered_df.to_excel(writer, index=False, sheet_name='OEE_Rational')
                buf.seek(0)
                st.download_button("📥 Descargar Reporte Excel (.xlsx)", data=buf, file_name="Reporte_OEE_Rational.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
                csv_bytes = filtered_df.to_csv(index=False).encode('utf-8')
                st.download_button("📄 Descargar CSV (.csv)", data=csv_bytes, file_name="Reporte_OEE_Rational.csv", mime="text/csv", use_container_width=True)
