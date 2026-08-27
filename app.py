import os
import io
import datetime
import streamlit as st
import pandas as pd
import plotly.express as px

from haccp_database import (
    init_db, get_all_charges_from_db, get_equipos_catalogo,
    insert_operacion_manual, delete_operacion,
    get_base_app_dir, get_default_db_path
)

# ---------------------------------------------------------
# CONFIGURACIÓN DE PÁGINA STREAMLIT
# ---------------------------------------------------------
st.set_page_config(
    page_title="Terminal de Registro Diario | Cocina y Operaciones",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="collapsed"
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
        font-size: 2.0rem;
        font-weight: 700;
        color: #0B2545;
        letter-spacing: -0.5px;
        margin-bottom: 2px;
    }
    
    .sub-title {
        font-size: 0.95rem;
        color: #475569;
        margin-bottom: 20px;
    }

    .kpi-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 14px 18px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        text-align: center;
    }
    .kpi-label {
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        color: #64748B;
        margin-bottom: 4px;
    }
    .kpi-value {
        font-size: 1.6rem;
        font-weight: 700;
        color: #0B2545;
    }

    .form-box {
        background: #FFFFFF;
        border: 1px solid #CBD5E1;
        border-radius: 12px;
        padding: 24px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.03);
        margin-bottom: 28px;
    }

    .login-box {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 16px;
        padding: 32px;
        box-shadow: 0 10px 15px -3px rgba(0,0,0,0.05);
        margin-top: 50px;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# SISTEMA DE AUTENTICACIÓN
# ---------------------------------------------------------
DEFAULT_USERS = {
    "fvannella@foodservice.com.ar": {"password": "Rational2026!", "nombre": "F. Vannella (Cocinero)"},
    "lucianomatiasluna@gmail.com": {"password": "Rational2026!", "nombre": "Luciano Luna"},
    "bjaillita@foodservice.com.ar": {"password": "Rational2026!", "nombre": "B. Jaillita"},
    "lrivero@foodservice.com.ar": {"password": "Rational2026!", "nombre": "L. Rivero"}
}

def get_authorized_users():
    if hasattr(st, "secrets") and "passwords" in st.secrets:
        custom_dict = {}
        for mail, pwd in st.secrets["passwords"].items():
            base_info = DEFAULT_USERS.get(mail.strip().lower(), {"nombre": mail.split('@')[0]})
            custom_dict[mail.strip().lower()] = {
                "password": str(pwd).strip(),
                "nombre": base_info.get("nombre", mail)
            }
        return custom_dict
    return DEFAULT_USERS

def check_login():
    if st.session_state.get("authenticated", False):
        return True

    users_db = get_authorized_users()

    col_a, col_b, col_c = st.columns([1, 1.2, 1])
    with col_b:
        st.markdown("""
        <div class="login-box">
            <div style="text-align: center; margin-bottom: 20px;">
                <div style="font-size: 2.2rem;">📝</div>
                <h2 style="color: #0B2545; font-size: 1.4rem; font-weight: 700; margin: 0;">Terminal de Cocina</h2>
                <p style="color: #64748B; font-size: 0.85rem; margin-top: 4px;">Ingreso de Operaciones de Hornos y Marmitas</p>
            </div>
        """, unsafe_allow_html=True)

        with st.form("login_form"):
            email_input = st.text_input("Correo Electrónico:", placeholder="usuario@foodservice.com.ar")
            pass_input = st.text_input("Contraseña:", type="password", placeholder="••••••••")
            submit_btn = st.form_submit_button("🔓 Ingresar", use_container_width=True)

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
                    st.session_state["user_name"] = user_found.get("nombre", clean_email)
                    st.success("¡Ingreso exitoso!")
                    st.rerun()
                else:
                    st.error("Credenciales incorrectas.")

        st.markdown("""
            <div style="text-align: center; color: #94A3B8; font-size: 0.75rem; margin-top: 12px;">
                Food Service America • Registro Rápido en Planta
            </div>
        </div>
        """, unsafe_allow_html=True)

    return False

if not check_login():
    st.stop()

# ---------------------------------------------------------
# INICIALIZACIÓN DE BASE DE DATOS
# ---------------------------------------------------------
default_db_file = get_default_db_path()
init_db(default_db_file)
df_catalogo = get_equipos_catalogo(default_db_file)

user_name = st.session_state.get("user_name", "Operario")
user_email = st.session_state.get("user_email", "")

# ---------------------------------------------------------
# BARRA LATERAL (SIMPLE)
# ---------------------------------------------------------
st.sidebar.markdown(f"**👤 Cocinero/Operador:** `{user_name}`")
if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
    st.session_state["authenticated"] = False
    st.session_state["user_email"] = ""
    st.rerun()

# ---------------------------------------------------------
# ENCABEZADO PRINCIPAL
# ---------------------------------------------------------
col_h_left, col_h_right = st.columns([3, 1])
with col_h_left:
    st.markdown('<div class="main-title">📝 Terminal de Registro Diario de Cocina</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sub-title">Cocinero: <b>{user_name}</b> | Registro ágil de operaciones en <b>Hornos Rational y Marmitas</b></div>', unsafe_allow_html=True)
with col_h_right:
    hoy_date = datetime.date.today()
    filtro_fecha = st.date_input("📅 Fecha de Registro:", hoy_date)

# Motivos de rechazo estándar
MOTIVOS_LISTA = [
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
# SECCIÓN 1: FORMULARIO DE DATA ENTRY (REGISTRO RÁPIDO)
# ---------------------------------------------------------
st.markdown("### ➕ Registrar Nueva Operación de Cocción / Elaboración")

equipos_dict = {
    r['id']: f"{r['nombre']} ({r['tipo']})"
    for _, r in df_catalogo.iterrows()
}

with st.container():
    st.markdown('<div class="form-box">', unsafe_allow_html=True)

    col_eq, col_prod, col_dur = st.columns([1.5, 2, 1])
    with col_eq:
        sel_equipo_id = st.selectbox("1. Selecciona el Equipo:", options=list(equipos_dict.keys()), format_func=lambda x: equipos_dict[x])
        eq_info = df_catalogo[df_catalogo['id'] == sel_equipo_id].iloc[0]
        es_marmita = (eq_info['tipo'] == 'Marmita Industrial')
        cap_max = float(eq_info['capacidad_nominal'])
        unidad_txt = "Kg" if es_marmita else "Placas"

    with col_prod:
        producto_input = st.text_input("2. Producto / Receta Elaborada:", placeholder="Ej: Pollo Asado, Arroz Primavera, Salsa Fileto, Cerdo")
    with col_dur:
        duracion_input = st.number_input("3. Duración (min):", min_value=5, max_value=480, value=45, step=5)

    st.markdown("---")

    col_c1, col_c2, col_c3, col_c4 = st.columns(4)

    if not es_marmita:
        # Hornos Rational: Placas y Unidades
        with col_c1:
            placas_val = st.number_input(f"Placas Cargadas (Máx: {cap_max:.0f}):", min_value=1, max_value=int(cap_max), value=min(20, int(cap_max)), step=1)
        with col_c2:
            unidades_tot_val = st.number_input("Total Unidades Producidas:", min_value=1, value=placas_val * 10, step=5)
        with col_c3:
            unidades_ok_val = st.number_input("Unidades que Salieron BIEN (OK):", min_value=0, max_value=unidades_tot_val, value=unidades_tot_val, step=5)
        with col_c4:
            unidades_nok_val = unidades_tot_val - unidades_ok_val
            st.metric("Unidades MAL (Merma):", f"{unidades_nok_val} un.", delta=f"{round(unidades_nok_val/unidades_tot_val*100, 1)}% merma" if unidades_tot_val>0 else "0%", delta_color="inverse")
        
        kilos_tot_val = kilos_ok_val = kilos_nok_val = 0.0
    else:
        # Marmitas: Kilos
        with col_c1:
            kilos_tot_val = st.number_input(f"Kilos Cargados en Marmita (Máx: {cap_max:.0f} Kg):", min_value=1.0, max_value=cap_max, value=min(150.0, cap_max), step=5.0)
        with col_c2:
            kilos_ok_val = st.number_input("Kilos que Salieron BIEN (Kg OK):", min_value=0.0, max_value=kilos_tot_val, value=kilos_tot_val, step=5.0)
        with col_c3:
            kilos_nok_val = round(kilos_tot_val - kilos_ok_val, 1)
            st.metric("Kilos de Merma (Kg NOK):", f"{kilos_nok_val} Kg", delta=f"{round(kilos_nok_val/kilos_tot_val*100, 1)}% merma" if kilos_tot_val>0 else "0%", delta_color="inverse")
        with col_c4:
            st.write(f"**Capacidad Ocupada:** `{round(kilos_tot_val/cap_max*100, 1)}%`")

        placas_val = unidades_tot_val = unidades_ok_val = unidades_nok_val = 0

    col_mot1, col_mot2 = st.columns([2, 1])
    with col_mot1:
        motivo_sel = st.selectbox("📋 Motivo del Desvío o Merma:", MOTIVOS_LISTA, index=0)
    with col_mot2:
        motivo_otro = ""
        if motivo_sel == "Otro":
            motivo_otro = st.text_input("Especificar motivo:", placeholder="Escribe el detalle...")

    hora_actual_str = datetime.datetime.now().strftime("%H:%M:%S")

    if st.button("💾 Guardar Operación en el Registro", type="primary", use_container_width=True):
        if not producto_input.strip():
            st.error("Por favor, ingresa el nombre del Producto / Receta antes de guardar.")
        else:
            motivo_guardar = motivo_otro if motivo_sel == "Otro" else (motivo_sel if motivo_sel != "100% Conforme (Sin Desvío)" else "")
            
            insert_operacion_manual(
                equipo_alias=eq_info['nombre'],
                tipo_equipo=eq_info['tipo'],
                fecha=filtro_fecha.strftime("%Y-%m-%d"),
                hora=hora_actual_str,
                producto=producto_input.strip(),
                duracion_min=duracion_input,
                placas_usadas=placas_val,
                placas_ok=placas_val if unidades_nok_val == 0 else max(0, placas_val - 1),
                placas_nok=0 if unidades_nok_val == 0 else 1,
                unidades_tot=unidades_tot_val,
                unidades_ok=unidades_ok_val,
                unidades_nok=unidades_nok_val,
                kilos_tot=kilos_tot_val,
                kilos_ok=kilos_ok_val,
                kilos_nok=kilos_nok_val,
                motivo_rechazo=motivo_guardar,
                operador=user_name,
                db_path=default_db_file
            )
            st.success(f"✅ ¡Operación de '{producto_input}' en {eq_info['nombre']} guardada con éxito!")
            st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------------------------------------
# SECCIÓN 2: LISTA DE OPERACIONES REALIZADAS EN EL DÍA
# ---------------------------------------------------------
st.markdown(f"### 📋 Operaciones Realizadas en el Día ({filtro_fecha.strftime('%d/%m/%Y')})")

df_todas = get_all_charges_from_db(default_db_file)
fecha_str = filtro_fecha.strftime("%Y-%m-%d")

# Filtrar solo el día seleccionado
df_dia = df_todas[df_todas['Fecha'] == fecha_str].copy() if not df_todas.empty else pd.DataFrame()

if not df_dia.empty:
    # Métricas de resumen del día
    tot_ops = len(df_dia)
    tot_u_ok = df_dia['Unidades_OK'].sum()
    tot_u_nok = df_dia['Unidades_Rechazadas'].sum()
    tot_kg_ok = df_dia['Kilos_OK'].sum()
    tot_kg_nok = df_dia['Kilos_Rechazados'].sum()
    
    col_k1, col_k2, col_k3, col_k4 = st.columns(4)
    with col_k1:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">Operaciones Realizadas Hoy</div>
            <div class="kpi-value">{tot_ops}</div>
        </div>
        """, unsafe_allow_html=True)
    with col_k2:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">Unidades Hornos (OK)</div>
            <div class="kpi-value" style="color: #059669;">{tot_u_ok:.0f}</div>
        </div>
        """, unsafe_allow_html=True)
    with col_k3:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">Kilos Marmitas (OK)</div>
            <div class="kpi-value" style="color: #1D4ED8;">{tot_kg_ok:.1f} Kg</div>
        </div>
        """, unsafe_allow_html=True)
    with col_k4:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">Total Mermas / Scrap</div>
            <div class="kpi-value" style="color: #DC2626;">{tot_u_nok:.0f} un. / {tot_kg_nok:.1f} Kg</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Preparar tabla limpia para visualización
    cols_mostrar = []
    df_vista = df_dia.copy()
    df_vista['Equipo'] = df_vista['Equipo_Alias'].fillna(df_vista['Modelo_Dev'])
    
    # Formatear columnas
    df_tabla = df_vista[[
        'id', 'Hora', 'Equipo', 'Programa', 'Duracion_Min',
        'Placas_Utilizadas', 'Unidades_OK', 'Unidades_Rechazadas',
        'Kilos_OK', 'Kilos_Rechazados', 'Motivo_Rechazo', 'Operador'
    ]].copy()

    df_tabla.columns = [
        'ID', 'Hora', 'Equipo', 'Producto / Receta', 'Minutos',
        'Placas', 'Unidades OK', 'Unidades Mal',
        'Kg OK', 'Kg Merma', 'Motivo de Desvío', 'Registrado Por'
    ]

    st.dataframe(df_tabla, hide_index=True, use_container_width=True)

    col_del, col_exp = st.columns([1.5, 2])
    with col_del:
        id_a_eliminar = st.selectbox("Eliminar Registro Erróneo:", options=df_dia['id'].tolist(), format_func=lambda x: f"ID #{x} - {df_dia[df_dia['id']==x]['Programa'].iloc[0]}")
        if st.button("🗑️ Eliminar Operación Seleccionada"):
            delete_operacion(id_a_eliminar, db_path=default_db_file)
            st.warning(f"Operación #{id_a_eliminar} eliminada.")
            st.rerun()

    with col_exp:
        buf_excel = io.BytesIO()
        with pd.ExcelWriter(buf_excel, engine='openpyxl') as writer:
            df_tabla.to_excel(writer, index=False, sheet_name='Registro_Diario')
        buf_excel.seek(0)
        st.download_button(
            label="📥 Descargar Planilla del Día (.xlsx)",
            data=buf_excel,
            file_name=f"Registro_Cocina_{filtro_fecha.strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
else:
    st.info(f"No hay operaciones registradas aún para la fecha {filtro_fecha.strftime('%d/%m/%Y')}. Ingresa la primera operación arriba.")
