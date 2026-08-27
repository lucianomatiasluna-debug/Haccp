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
    get_equipos_catalogo, insert_carga_inicial, registrar_salida_calidad, delete_operacion,
    update_charge_production_records,
    get_base_app_dir, get_default_db_path,
    RATIONAL_MANUAL_CAPACITIES, get_rational_capacity
)

# ---------------------------------------------------------
# CONFIGURACIÓN DE PÁGINA STREAMLIT & PWA TABLET READY
# ---------------------------------------------------------
st.set_page_config(
    page_title="Rational OEE & Terminal de Cocina",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inyección PWA y soporte para pantalla completa en Tablets (iPad / Android / Windows)
st.markdown("""
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="Rational OEE">
    <meta name="theme-color" content="#0B2545">
    <link rel="manifest" href="data:application/manifest+json,%7B%22name%22%3A%22Rational%20OEE%20Analytics%22%2C%22short_name%22%3A%22Rational%20OEE%22%2C%22start_url%22%3A%22%2F%22%2C%22display%22%3A%22standalone%22%2C%22background_color%22%3A%22%23FFFFFF%22%2C%22theme_color%22%3A%22%230B2545%22%7D">
</head>
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
        color: #0B2545;
        touch-action: manipulation;
    }
    
    .main-title {
        font-size: 2.1rem;
        font-weight: 800;
        color: #0B2545;
        letter-spacing: -0.5px;
        margin-bottom: 2px;
    }
    
    .sub-title {
        font-size: 0.95rem;
        color: #475569;
        margin-bottom: 16px;
        font-weight: 400;
    }

    .touch-box {
        background: #FFFFFF;
        border: 2px solid #E2E8F0;
        border-radius: 16px;
        padding: 24px;
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);
        margin-bottom: 20px;
    }

    .kpi-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        text-align: center;
    }
    .kpi-label {
        font-size: 0.8rem;
        font-weight: 600;
        text-transform: uppercase;
        color: #64748B;
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

    .touch-indicator {
        background: #F0FDF4;
        border: 2px solid #86EFAC;
        border-radius: 12px;
        padding: 14px;
        text-align: center;
        margin-top: 8px;
    }
    
    .touch-warning {
        background: #FEF2F2;
        border: 2px solid #FECACA;
        border-radius: 12px;
        padding: 14px;
        text-align: center;
        margin-top: 8px;
    }

    .login-box {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 16px;
        padding: 32px;
        box-shadow: 0 10px 15px -3px rgba(0,0,0,0.05);
        margin-top: 40px;
    }

    /* Optimización de controles para pantallas táctiles */
    .stSlider > div {
        padding-top: 8px;
        padding-bottom: 8px;
    }
    .stButton > button {
        min-height: 48px;
        font-size: 1.05rem;
        font-weight: 600;
        border-radius: 10px;
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
# CATÁLOGO DE RECETAS EN CASCADA (100% SELECCIONABLE EN TABLET)
# ---------------------------------------------------------
CATALOGO_RECETAS = {
    "🥩 Proteínas y Carnes": [
        "Pollo Asado / Cuartos de Pollo",
        "Supremas / Pechugas de Pollo",
        "Carne Vacuna Asada (Peceto / Lomo / Tapa)",
        "Carne Vacuna Braseada / Estofada",
        "Bondiola / Costillar de Cerdo",
        "Hamburguesas / Albóndigas de Carne",
        "Filet de Pescado / Merluza al Horno",
        "Milanesas al Horno (Vacuna / Pollo)"
    ],
    "🥔 Guarniciones y Vegetales": [
        "Papas Rústicas / Cuña al Horno",
        "Vegetales Asados Mixtos (Zanahoria, Morrón, Cebolla)",
        "Calabaza / Zapallo Asado al Horno",
        "Zanahorias Glaseadas al Vapor",
        "Batatas Asadas / Horneadas",
        "Brócoli / Coliflor al Vapor",
        "Puré Mixto / Puré de Papas"
    ],
    "🍝 Pastas, Arroces y Masas": [
        "Lasaña de Carne / Verdura",
        "Canelones Gratinados al Horno",
        "Pastel de Papas al Horno",
        "Arroz Blanco / Arroz Pilaf",
        "Arroz Primavera / Risotto",
        "Polenta Horneada con Queso",
        "Tartas / Empanadas Horneadas"
    ],
    "🥣 Salsas, Guisos y Marmitas": [
        "Salsa Fileto / Pomodoro",
        "Salsa Bolognesa con Carne",
        "Salsa Blanca / Bechamel",
        "Guiso de Lentejas / Porotos",
        "Estofado de Carne con Verduras",
        "Caldo de Ave / Caldo de Verduras",
        "Salsa de Cuatro Quesos"
    ],
    "🥖 Panadería y Horneados": [
        "Pan de Mesa / Flautitas",
        "Medialunas / Croissants",
        "Budines / Muffins",
        "Pizzas / Focaccias",
        "Bizcochuelo / Postres al Horno"
    ],
    "♨️ Regeneración y Mantención": [
        "Regeneración Platos Servidos GN 1/1",
        "Regeneración Bandejas Proteína",
        "Mantenimiento Térmico HACCP"
    ]
}

# Motivos de rechazo estándar
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

# =========================================================
# 👨‍🍳 VISTA OPERARIO: TABLET TOUCH 100% (CERO TECLADO)
# =========================================================
if user_role == "Operario":
    st.markdown('<div class="main-title">📱 Terminal Táctil de Cocina</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sub-title">Cocinero: <b>{user_name}</b> | Modo Tablet: 100% Seleccionable y Sliders (Sin Teclado)</div>', unsafe_allow_html=True)

    equipos_dict = {
        r['id']: f"{r['nombre']} ({r['tipo']})"
        for _, r in df_catalogo.iterrows()
    }

    # 2 PESTAÑAS INDEPENDIENTES PARA TABLET
    tab_p1, tab_p2 = st.tabs([
        "📥 Proceso 1: Carga Inicial de Placas / Kg (Al Iniciar)",
        "📦 Proceso 2: Control de Unidades y Calidad (Al Terminar)"
    ])

    # ---------------------------------------------------------
    # PROCESO 1: CARGA INICIAL (100% SELECTORES & SLIDERS)
    # ---------------------------------------------------------
    with tab_p1:
        st.markdown("#### 📥 1. Entrada al Horno o Marmita")
        st.caption("Selecciona el equipo y el alimento mediante los desplegables táctiles y ajusta las placas/kilos con el slider.")

        with st.container():
            st.markdown('<div class="touch-box">', unsafe_allow_html=True)

            # Selector de Equipo
            sel_eq_1 = st.selectbox("1. Selecciona el Horno o Marmita:", options=list(equipos_dict.keys()), format_func=lambda x: equipos_dict[x], key="touch_p1_eq")
            eq_info_1 = df_catalogo[df_catalogo['id'] == sel_eq_1].iloc[0]
            es_marmita_1 = (eq_info_1['tipo'] == 'Marmita Industrial')
            cap_max_1 = float(eq_info_1['capacidad_nominal'])
            unidad_txt_1 = "Kg" if es_marmita_1 else "Placas"

            col_cat, col_prod = st.columns(2)
            with col_cat:
                cat_elegida_1 = st.selectbox("2. Categoría de Alimento:", list(CATALOGO_RECETAS.keys()), key="touch_cat_1")
            with col_prod:
                recetas_disponibles = CATALOGO_RECETAS.get(cat_elegida_1, [])
                prod_elegido_1 = st.selectbox("3. Producto / Receta a Cocinar:", recetas_disponibles, key="touch_prod_1")

            st.markdown("---")

            col_sl1, col_sl2 = st.columns(2)
            with col_sl1:
                dur_1 = st.slider("4. Duración Estimada de Cocción (Minutos):", min_value=10, max_value=180, value=45, step=5, key="touch_dur_1")
            
            with col_sl2:
                if not es_marmita_1:
                    placas_cargadas_in = st.slider(f"5. Placas Introducidas en el Horno (Máx: {cap_max_1:.0f} Placas):", min_value=1, max_value=int(cap_max_1), value=min(20, int(cap_max_1)), step=1, key="touch_placas_1")
                    kg_cargados_in = 0.0
                    pct_ocup = round(placas_cargadas_in / cap_max_1 * 100, 1)
                    st.info(f"🍞 **Carga:** {placas_cargadas_in} de {cap_max_1:.0f} guías ({pct_ocup}% de capacidad ocupada)")
                else:
                    kg_cargados_in = st.slider(f"5. Kilos Cargados en la Marmita (Máx: {cap_max_1:.0f} Kg):", min_value=10.0, max_value=cap_max_1, value=min(150.0, cap_max_1), step=5.0, key="touch_kg_1")
                    placas_cargadas_in = 0
                    pct_ocup = round(kg_cargados_in / cap_max_1 * 100, 1)
                    st.info(f"🥣 **Carga:** {kg_cargados_in:.1f} Kg de {cap_max_1:.0f} Kg ({pct_ocup}% de capacidad ocupada)")

            st.markdown("<br>", unsafe_allow_html=True)
            hoy_str = datetime.date.today().strftime("%Y-%m-%d")
            hora_act_str = datetime.datetime.now().strftime("%H:%M:%S")

            if st.button("🚀 INICIAR COCCIÓN Y GUARDAR ENTRADA", type="primary", use_container_width=True, key="touch_btn_p1"):
                new_id = insert_carga_inicial(
                    equipo_alias=eq_info_1['nombre'],
                    tipo_equipo=eq_info_1['tipo'],
                    fecha=hoy_str,
                    hora=hora_act_str,
                    producto=prod_elegido_1,
                    duracion_min=dur_1,
                    placas_usadas=placas_cargadas_in,
                    kilos_cargados=kg_cargados_in,
                    operador=user_name,
                    db_path=default_db_file
                )
                st.success(f"✅ ¡Cocción #{new_id} de '{prod_elegido_1}' iniciada en {eq_info_1['nombre']}!")
                st.rerun()

            st.markdown('</div>', unsafe_allow_html=True)

    # ---------------------------------------------------------
    # PROCESO 2: CONTROL DE CALIDAD (100% SELECTORES & SLIDERS)
    # ---------------------------------------------------------
    with tab_p2:
        st.markdown("#### 📦 2. Salida y Control de Calidad")
        st.caption("Selecciona la cocción terminada y ajusta con los sliders las unidades/kilos totales y los que salieron con falla (merma).")

        df_todas_cal = get_all_charges_from_db(default_db_file)
        hoy_str = datetime.date.today().strftime("%Y-%m-%d")
        df_hoy_cal = df_todas_cal[df_todas_cal['Fecha'] == hoy_str].copy() if not df_todas_cal.empty else pd.DataFrame()

        if not df_hoy_cal.empty:
            cargas_abiertas = df_hoy_cal.to_dict('records')
            opciones_cal = {
                c['id']: f"ID #{c['id']} | {c['Hora']} | {c['Equipo_Alias'] or c['Modelo_Dev']} | {c['Programa']} ({c['Placas_Utilizadas']} Placas / {c['Kilos_Totales']} Kg)"
                for c in cargas_abiertas
            }

            sel_c_id_cal = st.selectbox("1. Selecciona la Cocción Terminada:", options=list(opciones_cal.keys()), format_func=lambda x: opciones_cal[x], key="touch_p2_sel_c")
            c_item_cal = df_hoy_cal[df_hoy_cal['id'] == sel_c_id_cal].iloc[0]
            es_marm_cal = ("Marmita" in str(c_item_cal['Modelo_Dev']) or "Marmita" in str(c_item_cal['Equipo_Alias']))

            with st.container():
                st.markdown('<div class="touch-box">', unsafe_allow_html=True)

                st.markdown(f"📍 **Lote Activo:** `{c_item_cal['Programa']}` en `{c_item_cal['Equipo_Alias'] or c_item_cal['Modelo_Dev']}` ({c_item_cal['Hora']} hs)")

                if not es_marm_cal:
                    # Hornos: Sliders de Unidades
                    def_u_tot = int(c_item_cal['Unidades_Totales'] if c_item_cal['Unidades_Totales'] > 0 else (c_item_cal['Placas_Utilizadas'] * 10))
                    def_u_nok = int(c_item_cal['Unidades_Rechazadas'] if c_item_cal['Unidades_Rechazadas'] > 0 else 0)

                    col_sl_u1, col_sl_u2 = st.columns(2)
                    with col_sl_u1:
                        u_tot_in = st.slider("2. Total Unidades Obtenidas de la Cocción:", min_value=10, max_value=500, value=max(10, min(500, def_u_tot)), step=5, key="touch_sl_utot")
                    with col_sl_u2:
                        u_nok_in = st.slider("3. Unidades Defectuosas / Rechazadas (Merma):", min_value=0, max_value=min(100, u_tot_in), value=min(def_u_nok, u_tot_in), step=1, key="touch_sl_unok")

                    u_ok_in = u_tot_in - u_nok_in
                    pct_ok = round(u_ok_in / u_tot_in * 100, 1)

                    col_res1, col_res2 = st.columns(2)
                    with col_res1:
                        st.markdown(f"""
                        <div class="touch-indicator">
                            <div style="font-size: 0.85rem; font-weight: 700; color: #166534;">✅ UNIDADES BIEN (CONFORMES)</div>
                            <div style="font-size: 2.2rem; font-weight: 800; color: #15803D;">{u_ok_in} un.</div>
                            <div style="font-size: 0.85rem; color: #166534;">Tasa de Calidad: <b>{pct_ok}%</b></div>
                        </div>
                        """, unsafe_allow_html=True)
                    with col_res2:
                        st.markdown(f"""
                        <div class="touch-warning">
                            <div style="font-size: 0.85rem; font-weight: 700; color: #991B1B;">⚠️ UNIDADES MAL (MERMA)</div>
                            <div style="font-size: 2.2rem; font-weight: 800; color: #DC2626;">{u_nok_in} un.</div>
                            <div style="font-size: 0.85rem; color: #991B1B;">Pérdida: <b>{round(u_nok_in/u_tot_in*100, 1)}%</b></div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    kg_ok_in = kg_nok_in = 0.0
                else:
                    # Marmitas: Sliders de Kilos
                    def_kg_tot = float(c_item_cal['Kilos_Totales'] if c_item_cal['Kilos_Totales'] > 0 else 150.0)
                    def_kg_nok = float(c_item_cal['Kilos_Rechazados'] if c_item_cal['Kilos_Rechazados'] > 0 else 0.0)

                    col_sl_k1, col_sl_k2 = st.columns(2)
                    with col_sl_k1:
                        kg_tot_in = st.slider("2. Kilos Totales Obtenidos (Kg):", min_value=10.0, max_value=250.0, value=max(10.0, min(250.0, def_kg_tot)), step=5.0, key="touch_sl_kgtot")
                    with col_sl_k2:
                        kg_nok_in = st.slider("3. Kilos de Merma / Scrap (Kg):", min_value=0.0, max_value=min(50.0, kg_tot_in), value=min(def_kg_nok, kg_tot_in), step=0.5, key="touch_sl_kgnok")

                    kg_ok_in = round(kg_tot_in - kg_nok_in, 1)
                    pct_ok = round(kg_ok_in / kg_tot_in * 100, 1)

                    col_res1, col_res2 = st.columns(2)
                    with col_res1:
                        st.markdown(f"""
                        <div class="touch-indicator">
                            <div style="font-size: 0.85rem; font-weight: 700; color: #166534;">✅ KILOS CONFORMES (OK)</div>
                            <div style="font-size: 2.2rem; font-weight: 800; color: #15803D;">{kg_ok_in:.1f} Kg</div>
                            <div style="font-size: 0.85rem; color: #166534;">Rendimiento: <b>{pct_ok}%</b></div>
                        </div>
                        """, unsafe_allow_html=True)
                    with col_res2:
                        st.markdown(f"""
                        <div class="touch-warning">
                            <div style="font-size: 0.85rem; font-weight: 700; color: #991B1B;">⚠️ MERMA / RECHAZO (KG)</div>
                            <div style="font-size: 2.2rem; font-weight: 800; color: #DC2626;">{kg_nok_in:.1f} Kg</div>
                            <div style="font-size: 0.85rem; color: #991B1B;">Pérdida: <b>{round(kg_nok_in/kg_tot_in*100, 1)}%</b></div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    u_tot_in = u_ok_in = u_nok_in = 0

                st.markdown("<br>", unsafe_allow_html=True)

                # Desplegable táctil de motivos
                mot_cur_p2 = str(c_item_cal['Motivo_Rechazo'] or "")
                idx_p2 = MOTIVOS_RECHAZO_LIST.index(mot_cur_p2) if mot_cur_p2 in MOTIVOS_RECHAZO_LIST else 0
                motivo_sel_p2 = st.selectbox("4. Motivo del Desvío o Merma:", MOTIVOS_RECHAZO_LIST, index=idx_p2, key="touch_p2_mot_sel")

                st.markdown("<br>", unsafe_allow_html=True)

                if st.button("💾 GUARDAR CONTROL DE CALIDAD", type="primary", use_container_width=True, key="touch_btn_p2"):
                    registrar_salida_calidad(
                        charge_id=sel_c_id_cal,
                        unidades_tot=u_tot_in,
                        unidades_ok=u_ok_in,
                        unidades_nok=u_nok_in,
                        kilos_ok=kg_ok_in,
                        kilos_nok=kg_nok_in,
                        motivo_rechazo=motivo_sel_p2 if motivo_sel_p2 != "100% Conforme (Sin Desvío)" else "",
                        operador=user_name,
                        db_path=default_db_file
                    )
                    st.success(f"✅ ¡Calidad de Cocción #{sel_c_id_cal} registrada con éxito!")
                    st.rerun()

                st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.info("No hay cocciones registradas hoy. Realiza la carga en el 'Proceso 1' primero.")

    # ---------------------------------------------------------
    # HISTORIAL DEL DÍA EN TABLET
    # ---------------------------------------------------------
    st.markdown("---")
    st.markdown(f"### 📋 Operaciones Realizadas Hoy ({datetime.date.today().strftime('%d/%m/%Y')})")
    df_todas_op = get_all_charges_from_db(default_db_file)
    df_dia_op = df_todas_op[df_todas_op['Fecha'] == hoy_str].copy() if not df_todas_op.empty else pd.DataFrame()

    if not df_dia_op.empty:
        df_dia_op['Equipo'] = df_dia_op['Equipo_Alias'].fillna(df_dia_op['Modelo_Dev'])
        df_tabla_op = df_dia_op[[
            'id', 'Hora', 'Equipo', 'Programa', 'Duracion_Min',
            'Placas_Utilizadas', 'Unidades_OK', 'Unidades_Rechazadas',
            'Kilos_OK', 'Kilos_Rechazados', 'Motivo_Rechazo', 'Estado_Final'
        ]].copy()
        df_tabla_op.columns = [
            'ID', 'Hora', 'Equipo', 'Producto / Receta', 'Minutos',
            'Placas', 'Unidades OK', 'Unidades Mal',
            'Kg OK', 'Kg Merma', 'Motivo de Desvío', 'Estado'
        ]
        st.dataframe(df_tabla_op, hide_index=True, use_container_width=True)
    else:
        st.info("No se han registrado operaciones hoy.")

# =========================================================
# 📊 VISTA SUPERVISOR: DASHBOARD COMPLETO OEE RATIONAL
# =========================================================
else:
    # Filtros para Supervisor
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

    # Filtrar datos
    filtered_df = df_db.copy() if not df_db.empty else pd.DataFrame()
    if not filtered_df.empty:
        if selected_series:
            filtered_df = filtered_df[filtered_df['Serie_SN'].isin(selected_series)]
        if len(date_range) == 2:
            start_d, end_d = date_range
            filtered_df = filtered_df[(filtered_df['Fecha_Hora'].dt.date >= start_d) & (filtered_df['Fecha_Hora'].dt.date <= end_d)]
        if selected_cats:
            filtered_df = filtered_df[filtered_df['Categoria'].isin(selected_cats)]

    date_span_str = f"{date_range[0]} al {date_range[1]}" if len(date_range) == 2 else "Histórico Completo"

    # CÁLCULOS OEE
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

    st.markdown('<div class="main-title">⚡ Rational OEE Analytics</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sub-title">Panel Ejecutivo de Eficiencia General de Equipos (OEE) | Supervisor: <b>{user_name}</b></div>', unsafe_allow_html=True)

    st.markdown(f"""
    <div class="status-bar">
        <div>🏭 <b>Flota Activa:</b> {total_ovens} Horno(s) Rational &nbsp;|&nbsp; 📋 <b>Cargas:</b> {len(filtered_df)} &nbsp;|&nbsp; 🍞 <b>Placas:</b> {total_placas_utilizadas:.0f} / {total_capacidad_teorica_placas:.0f}</div>
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
    tab_sup_main, tab_sup_fleet, tab_sup_grid, tab_sup_haccp, tab_sup_data = st.tabs([
        "📊 Tablero Central OEE & Cascada",
        "🎛️ Benchmarking de Flota",
        "📋 Auditoría de Lotes y Placas",
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

    with tab_sup_haccp:
        st.markdown("### 🔍 Calidad, Temperaturas y Control HACCP")
        col_hp1, col_hp2 = st.columns(2)
        with col_hp1:
            st.markdown("#### 🛑 Tasa de Finalización (RETURN vs ABORT)")
            st_counts = filtered_df['Estado_Final'].value_counts().reset_index()
            st_counts.columns = ['Estado', 'Cantidad']
            fig_st = px.pie(st_counts, names='Estado', values='Cantidad', color='Estado', color_discrete_map={'RETURN': '#10B981', 'ABORT': '#EF4444', 'EN CURSO / INCOMPLETO': '#F59E0B', 'EN COCCIÓN / PENDIENTE CALIDAD': '#3B82F6', 'CON RECHAZO': '#EF4444'})
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
