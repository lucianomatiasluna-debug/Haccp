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
    get_base_app_dir, get_default_db_path
)

# ---------------------------------------------------------
# CONFIGURACIÓN DE PÁGINA STREAMLIT
# ---------------------------------------------------------
st.set_page_config(
    page_title="Rational OEE Analytics | Eficiencia General de Hornos",
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
</style>
""", unsafe_allow_html=True)

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

# Leer base de datos SQLite
init_db(default_db_file)
df_db = get_all_charges_from_db(default_db_file)

# ---------------------------------------------------------
# BARRA LATERAL (SIDEBAR): INGESTA Y PARÁMETROS OEE
# ---------------------------------------------------------
st.sidebar.markdown("### ⚙️ Ingesta de Datos")

uploaded_files = st.sidebar.file_uploader(
    "Cargar archivos de logs (.txt o .zip):",
    type=["txt", "zip"],
    accept_multiple_files=True,
    help="Arrastra los archivos TXT descargados de los hornos Rational o un ZIP comprimido."
)

if uploaded_files:
    with st.spinner("Procesando e indexando registros HACCP..."):
        df_uploaded = load_multiple_haccp_files(uploaded_files)
        if not df_uploaded.empty:
            added_count = save_df_to_db(df_uploaded, db_path=default_db_file)
            st.sidebar.success(f"✅ {len(df_uploaded)} registros leídos ({added_count} nuevos en BD).")
            st.rerun()
        else:
            st.sidebar.warning("No se encontraron registros válidos.")

st.sidebar.markdown("---")
st.sidebar.markdown("### 🎚️ Parámetros de Cálculo OEE")

theoretical_cadence = st.sidebar.slider(
    "Cadencia Teórica (cargas/hora):",
    min_value=0.5,
    max_value=4.0,
    value=1.5,
    step=0.1,
    help="Número estimado de cargas/ciclos de cocción ideales que el horno debería procesar por cada hora de operación."
)

door_loss_factor = st.sidebar.slider(
    "Factor Pérdida por Puerta Abierta (%):",
    min_value=0.5,
    max_value=5.0,
    value=2.0,
    step=0.5,
    help="Penalización estimada en el rendimiento por cada apertura de puerta durante el ciclo."
) / 100.0

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
selected_cats = st.sidebar.multiselect("Categoría de Proceso:", categorias, default=categorias)

# Filtrado reactivo de datos
filtered_df = df_db.copy() if not df_db.empty else pd.DataFrame()
if not filtered_df.empty:
    if selected_series:
        filtered_df = filtered_df[filtered_df['Serie_SN'].isin(selected_series)]
    if len(date_range) == 2:
        start_d, end_d = date_range
        filtered_df = filtered_df[(filtered_df['Fecha_Hora'].dt.date >= start_d) & (filtered_df['Fecha_Hora'].dt.date <= end_d)]
    if selected_cats:
        filtered_df = filtered_df[filtered_df['Categoria'].isin(selected_cats)]

# ---------------------------------------------------------
# ENCABEZADO PRINCIPAL
# ---------------------------------------------------------
st.markdown('<div class="main-title">⚡ Rational OEE Analytics</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Monitoreo de Eficiencia General de Equipos (OEE), Rendimiento Operativo y Control de Calidad HACCP</div>', unsafe_allow_html=True)

# Barra de estado
total_records = len(filtered_df)
total_ovens = filtered_df['Serie_SN'].nunique() if not filtered_df.empty else 0
date_span_str = f"{min_date} al {max_date}" if not filtered_df.empty and len(date_range) == 2 else "Sin registros"

st.markdown(f"""
<div class="status-bar">
    <div>🏭 <b>Flota Activa:</b> {total_ovens} Horno(s) Rational &nbsp;|&nbsp; 📋 <b>Cargas Analizadas:</b> {total_records}</div>
    <div>📅 <b>Ventana Temporal:</b> {date_span_str}</div>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# MOTOR DE CÁLCULO OEE
# ---------------------------------------------------------
if not filtered_df.empty:
    total_operating_hours = filtered_df['Duracion_Horas'].sum()
    cooking_hours = filtered_df[filtered_df['Categoria'] != 'Limpieza (iCareSystem)']['Duracion_Horas'].sum()
    cleaning_hours = filtered_df[filtered_df['Categoria'] == 'Limpieza (iCareSystem)']['Duracion_Horas'].sum()
    
    # 1. Disponibilidad (A) - Base 24h continuas
    if len(date_range) == 2:
        days_span = max(1, (date_range[1] - date_range[0]).days + 1)
    else:
        days_span = max(1, filtered_df['Fecha'].nunique())
    
    ovens_count = max(1, total_ovens)
    total_calendar_hours = days_span * 24.0 * ovens_count
    availability = min(1.0, max(0.0, total_operating_hours / total_calendar_hours))

    # 2. Calidad (Q) - Tasa de éxito RETURN vs ABORT
    successful_charges = (filtered_df['Estado_Final'] == 'RETURN').sum()
    quality = (successful_charges / total_records) if total_records > 0 else 1.0

    # 3. Rendimiento (P) - Cadencia de cargas y pérdidas por aperturas de puerta
    total_door_opens = filtered_df['Aperturas_Puerta'].sum()
    avg_door_opens = (total_door_opens / total_records) if total_records > 0 else 0
    door_loss_pct = min(0.35, avg_door_opens * door_loss_factor)
    
    actual_cadence = (total_records / total_operating_hours) if total_operating_hours > 0 else 0
    cadence_ratio = min(1.0, actual_cadence / theoretical_cadence) if theoretical_cadence > 0 else 1.0
    performance = min(1.0, max(0.0, cadence_ratio * (1.0 - door_loss_pct)))

    # 4. OEE Global
    oee = availability * performance * quality
else:
    total_operating_hours = cooking_hours = cleaning_hours = days_span = total_calendar_hours = 0
    availability = performance = quality = oee = 0.0

# ---------------------------------------------------------
# TARJETAS RESUMEN OEE (KPIs)
# ---------------------------------------------------------
col_oee, col_a, col_p, col_q, col_hrs = st.columns(5)

def get_oee_badge(val):
    if val >= 0.85:
        return '<span class="kpi-badge badge-success">Clase Mundial (≥85%)</span>'
    elif val >= 0.65:
        return '<span class="kpi-badge badge-info">Aceptable (65-84%)</span>'
    elif val >= 0.40:
        return '<span class="kpi-badge badge-warning">Mejorable (40-64%)</span>'
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
        <div class="kpi-badge badge-info">{total_operating_hours:.1f}h / {total_calendar_hours:.0f}h</div>
    </div>
    """, unsafe_allow_html=True)

with col_p:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-label">Rendimiento (P)</div>
        <div class="kpi-value" style="color: #0B2545;">{performance*100:.1f}%</div>
        <div class="kpi-badge badge-info">{actual_cadence:.2f} cargas/h</div>
    </div>
    """, unsafe_allow_html=True)

with col_q:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-label">Calidad (Q)</div>
        <div class="kpi-value" style="color: #059669;">{quality*100:.1f}%</div>
        <div class="kpi-badge badge-success">{successful_charges}/{total_records} exitosos</div>
    </div>
    """, unsafe_allow_html=True)

with col_hrs:
    prom_diario = (total_operating_hours / days_span) if days_span > 0 else 0
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-label">Uso Promedio / Día</div>
        <div class="kpi-value" style="color: #0B2545;">{prom_diario:.1f}h</div>
        <div class="kpi-badge badge-info">{prom_diario/24.0*100:.1f}% de 24h</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------
# PESTAÑAS PRINCIPALES DEL DASHBOARD
# ---------------------------------------------------------
tab_main, tab_fleet, tab_quality, tab_data = st.tabs([
    "📊 Tablero Central OEE & Pérdidas",
    "🎛️ Benchmarking de Flota (Multi-Horno)",
    "🔍 Calidad, Abortos y Control HACCP",
    "📥 Ingesta de Datos y Exportación"
])

# =========================================================
# PESTAÑA 1: TABLERO CENTRAL OEE & PÉRDIDAS
# =========================================================
with tab_main:
    if filtered_df.empty:
        st.markdown("""
        <div class="empty-state">
            <h3>No hay datos cargados para los filtros seleccionados</h3>
            <p>Sube archivos de log .txt o .zip desde la barra lateral para generar los indicadores OEE.</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        # Fila 1: Indicadores Gauge (Tacómetros)
        st.markdown("#### 🎯 Indicadores Clave de Eficiencia")
        
        col_g1, col_g2, col_g3, col_g4 = st.columns(4)
        
        def create_gauge(val, title, color):
            fig = go.Figure(go.Indicator(
                mode="gauge+number",
                value=round(val * 100, 1),
                number={'suffix': "%", 'font': {'size': 28, 'color': '#0B2545', 'family': 'Inter'}},
                title={'text': title, 'font': {'size': 14, 'color': '#64748B', 'family': 'Inter'}},
                gauge={
                    'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "#CBD5E1"},
                    'bar': {'color': color, 'thickness': 0.25},
                    'bgcolor': "#F1F5F9",
                    'borderwidth': 0,
                    'steps': [
                        {'range': [0, 65], 'color': '#FEE2E2'},
                        {'range': [65, 85], 'color': '#FEF3C7'},
                        {'range': [85, 100], 'color': '#D1FAE5'}
                    ],
                    'threshold': {
                        'line': {'color': "#0B2545", 'width': 3},
                        'thickness': 0.75,
                        'value': 85
                    }
                }
            ))
            fig.update_layout(
                height=180,
                margin=dict(l=15, r=15, t=30, b=10),
                paper_bgcolor="rgba(0,0,0,0)",
                font={'family': 'Inter'}
            )
            return fig

        with col_g1:
            st.plotly_chart(create_gauge(oee, "OEE Global", "#10B981"), use_container_width=True)
        with col_g2:
            st.plotly_chart(create_gauge(availability, "Disponibilidad (A)", "#1D4ED8"), use_container_width=True)
        with col_g3:
            st.plotly_chart(create_gauge(performance, "Rendimiento (P)", "#0B2545"), use_container_width=True)
        with col_g4:
            st.plotly_chart(create_gauge(quality, "Calidad (Q)", "#059669"), use_container_width=True)

        st.markdown("---")

        # Fila 2: Cascada de Pérdidas OEE y Evolución Temporal
        col_w, col_t = st.columns([1, 1])

        with col_w:
            st.markdown("#### 📉 Cascada de Pérdidas de Capacidad (Waterfall)")
            
            # Horas teóricas y pérdidas
            downtime_hours = max(0.0, total_calendar_hours - total_operating_hours)
            perf_loss_hours = max(0.0, total_operating_hours * (1.0 - performance))
            qual_loss_hours = max(0.0, total_operating_hours * performance * (1.0 - quality))
            effective_oee_hours = total_operating_hours * performance * quality

            fig_waterfall = go.Figure(go.Waterfall(
                name="Pérdidas OEE",
                orientation="v",
                measure=["absolute", "relative", "relative", "relative", "total"],
                x=[
                    "Tiempo Total (24h)",
                    "Inactividad / Paradas",
                    "Pérdida Rendimiento",
                    "Pérdida Calidad (Aborts)",
                    "Tiempo Efectivo OEE"
                ],
                textposition="outside",
                text=[
                    f"{total_calendar_hours:.1f}h",
                    f"-{downtime_hours:.1f}h",
                    f"-{perf_loss_hours:.1f}h",
                    f"-{qual_loss_hours:.1f}h",
                    f"{effective_oee_hours:.1f}h"
                ],
                y=[
                    total_calendar_hours,
                    -downtime_hours,
                    -perf_loss_hours,
                    -qual_loss_hours,
                    effective_oee_hours
                ],
                connector={"line": {"color": "#94A3B8"}},
                decreasing={"marker": {"color": "#EF4444"}},
                increasing={"marker": {"color": "#10B981"}},
                totals={"marker": {"color": "#0B2545"}}
            ))

            fig_waterfall.update_layout(
                height=380,
                margin=dict(l=20, r=20, t=30, b=20),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                yaxis=dict(title="Horas Acumuladas", showgrid=True, gridcolor="#F1F5F9"),
                xaxis=dict(tickangle=-15)
            )
            st.plotly_chart(fig_waterfall, use_container_width=True)

        with col_t:
            st.markdown("#### 📈 Evolución Diaria de Eficiencia")
            
            # Agrupar OEE por día
            daily_stats = filtered_df.groupby('Fecha').agg(
                Horas=('Duracion_Horas', 'sum'),
                Cargas=('Carga_Nr', 'count'),
                Exitosos=('Estado_Final', lambda s: (s == 'RETURN').sum()),
                Aperturas=('Aperturas_Puerta', 'sum')
            ).reset_index()

            daily_stats['Disponibilidad_%'] = (daily_stats['Horas'] / (24.0 * ovens_count) * 100).clip(upper=100.0)
            daily_stats['Calidad_%'] = (daily_stats['Exitosos'] / daily_stats['Cargas'] * 100)
            daily_stats['OEE_%'] = (daily_stats['Disponibilidad_%'] * (daily_stats['Calidad_%'] / 100) * performance).round(1)

            fig_trend = go.Figure()
            fig_trend.add_trace(go.Scatter(
                x=daily_stats['Fecha'], y=daily_stats['OEE_%'],
                mode='lines+markers', name='OEE Global (%)',
                line=dict(color='#10B981', width=3),
                marker=dict(size=6)
            ))
            fig_trend.add_trace(go.Scatter(
                x=daily_stats['Fecha'], y=daily_stats['Disponibilidad_%'],
                mode='lines', name='Disponibilidad (%)',
                line=dict(color='#1D4ED8', width=2, dash='dot')
            ))
            fig_trend.add_trace(go.Scatter(
                x=daily_stats['Fecha'], y=daily_stats['Calidad_%'],
                mode='lines', name='Calidad (%)',
                line=dict(color='#0B2545', width=1.5, dash='dash')
            ))

            fig_trend.update_layout(
                height=380,
                margin=dict(l=20, r=20, t=30, b=20),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                yaxis=dict(title="Porcentaje (%)", range=[0, 105], showgrid=True, gridcolor="#F1F5F9"),
                xaxis=dict(title="Fecha", tickangle=-45),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_trend, use_container_width=True)

        st.markdown("---")

        # Fila 3: Perfil Horario de Uso (24 Horas)
        st.markdown("#### ⏰ Distribución del Uso por Franja Horaria (00:00 a 23:00)")
        
        df_hourly = filtered_df[filtered_df['Hora_Del_Dia'].notnull()].copy()
        if not df_hourly.empty:
            df_hourly['Hora_Del_Dia'] = df_hourly['Hora_Del_Dia'].astype(int)
            hourly_summary = df_hourly.groupby('Hora_Del_Dia').agg(
                Horas_Uso=('Duracion_Horas', 'sum'),
                Total_Cargas=('Carga_Nr', 'count')
            ).reindex(range(24), fill_value=0).reset_index()
            
            hourly_summary['Hora_Label'] = hourly_summary['Hora_Del_Dia'].apply(lambda h: f"{h:02d}:00")

            col_h1, col_h2 = st.columns([2, 1])

            with col_h1:
                fig_h_bar = px.bar(
                    hourly_summary, x='Hora_Label', y='Horas_Uso',
                    labels={'Hora_Label': 'Hora del Día', 'Horas_Uso': 'Horas Totales'},
                    title="Horas de Operación por Franja Horaria",
                    color='Horas_Uso',
                    color_continuous_scale=['#EFF6FF', '#1D4ED8', '#0B2545']
                )
                fig_h_bar.update_layout(
                    height=300,
                    margin=dict(l=10, r=10, t=30, b=10),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)"
                )
                st.plotly_chart(fig_h_bar, use_container_width=True)

            with col_h2:
                time_dist = pd.DataFrame({
                    'Tipo': ['Cocción / Producción', 'Higiene iCareSystem', 'Capacidad No Utilizada'],
                    'Horas': [cooking_hours, cleaning_hours, downtime_hours]
                })
                fig_pie = px.pie(
                    time_dist, values='Horas', names='Tipo',
                    title="Distribución Total de Tiempo Calendario",
                    color='Tipo',
                    color_discrete_map={
                        'Cocción / Producción': '#10B981',
                        'Higiene iCareSystem': '#1D4ED8',
                        'Capacidad No Utilizada': '#CBD5E1'
                    }
                )
                fig_pie.update_layout(
                    height=300,
                    margin=dict(l=10, r=10, t=30, b=10),
                    paper_bgcolor="rgba(0,0,0,0)"
                )
                st.plotly_chart(fig_pie, use_container_width=True)

# =========================================================
# PESTAÑA 2: BENCHMARKING DE FLOTA (MULTI-HORNO)
# =========================================================
with tab_fleet:
    st.markdown("### 🎛️ Comparativa de Rendimiento y Eficiencia por Horno")
    
    if not filtered_df.empty:
        # Calcular OEE individual por número de serie
        fleet_rows = []
        for sn, grp in filtered_df.groupby('Serie_SN'):
            model = grp['Modelo_Dev'].iloc[0]
            sn_total_charges = len(grp)
            sn_hours = grp['Duracion_Horas'].sum()
            sn_success = (grp['Estado_Final'] == 'RETURN').sum()
            sn_cleaning = (grp['Categoria'] == 'Limpieza (iCareSystem)').sum()
            sn_doors = grp['Aperturas_Puerta'].sum()
            
            # Disponibilidad
            sn_avail = min(1.0, sn_hours / (days_span * 24.0))
            # Calidad
            sn_qual = (sn_success / sn_total_charges) if sn_total_charges > 0 else 1.0
            # Rendimiento
            sn_cadence = (sn_total_charges / sn_hours) if sn_hours > 0 else 0
            sn_door_loss = min(0.35, (sn_doors / sn_total_charges if sn_total_charges > 0 else 0) * door_loss_factor)
            sn_perf = min(1.0, max(0.0, (sn_cadence / theoretical_cadence if theoretical_cadence > 0 else 1.0) * (1.0 - sn_door_loss)))
            # OEE
            sn_oee = sn_avail * sn_perf * sn_qual
            
            fleet_rows.append({
                'Serie_SN': sn,
                'Modelo': model,
                'Cargas_Totales': sn_total_charges,
                'Horas_Uso': round(sn_hours, 1),
                'Horas_Prom_Dia': round(sn_hours / days_span, 1),
                'Disponibilidad_%': round(sn_avail * 100, 1),
                'Rendimiento_%': round(sn_perf * 100, 1),
                'Calidad_%': round(sn_qual * 100, 1),
                'OEE_%': round(sn_oee * 100, 1),
                'Limpiezas': sn_cleaning,
                'Aperturas_Prom': round(sn_doors / sn_total_charges, 1) if sn_total_charges > 0 else 0
            })

        df_fleet = pd.DataFrame(fleet_rows).sort_values(by='OEE_%', ascending=False)

        col_f1, col_f2 = st.columns(2)

        with col_f1:
            st.markdown("#### 🏆 Ranking de OEE por Horno")
            fig_fleet_oee = px.bar(
                df_fleet, x='Serie_SN', y='OEE_%', color='OEE_%',
                text='OEE_%',
                color_continuous_scale=['#EFF6FF', '#1D4ED8', '#10B981'],
                labels={'Serie_SN': 'Horno (S/N)', 'OEE_%': 'OEE Global (%)'}
            )
            fig_fleet_oee.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
            fig_fleet_oee.update_layout(
                height=350,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                yaxis=dict(range=[0, 115])
            )
            st.plotly_chart(fig_fleet_oee, use_container_width=True)

        with col_f2:
            st.markdown("#### ⚖️ Comparativa de Factores A, P y Q")
            df_factors = df_fleet.melt(
                id_vars=['Serie_SN'],
                value_vars=['Disponibilidad_%', 'Rendimiento_%', 'Calidad_%'],
                var_name='Factor', value_name='Valor'
            )
            fig_factors = px.bar(
                df_factors, x='Serie_SN', y='Valor', color='Factor', barmode='group',
                color_discrete_map={
                    'Disponibilidad_%': '#1D4ED8',
                    'Rendimiento_%': '#0B2545',
                    'Calidad_%': '#10B981'
                },
                labels={'Serie_SN': 'Horno (S/N)', 'Valor': 'Porcentaje (%)'}
            )
            fig_factors.update_layout(
                height=350,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                yaxis=dict(range=[0, 115])
            )
            st.plotly_chart(fig_factors, use_container_width=True)

        st.markdown("#### 📋 Matriz Ejecutiva de Flota")
        st.dataframe(df_fleet, use_container_width=True)
    else:
        st.info("No hay datos disponibles para comparar la flota.")

# =========================================================
# PESTAÑA 3: CALIDAD, ABORTOS Y CONTROL HACCP
# =========================================================
with tab_quality:
    st.markdown("### 🔍 Análisis de Calidad, Procesos Abortados y Parámetros HACCP")
    
    if not filtered_df.empty:
        col_q1, col_q2 = st.columns(2)

        with col_q1:
            st.markdown("#### 🛑 Tasa de Finalización: RETURN vs ABORT")
            status_counts = filtered_df['Estado_Final'].value_counts().reset_index()
            status_counts.columns = ['Estado', 'Cantidad']
            
            fig_status_pie = px.pie(
                status_counts, names='Estado', values='Cantidad',
                color='Estado',
                color_discrete_map={
                    'RETURN': '#10B981',
                    'ABORT': '#EF4444',
                    'EN CURSO / INCOMPLETO': '#F59E0B'
                }
            )
            fig_status_pie.update_layout(
                height=320,
                paper_bgcolor="rgba(0,0,0,0)"
            )
            st.plotly_chart(fig_status_pie, use_container_width=True)

        with col_q2:
            st.markdown("#### 🧼 Cumplimiento de Higiene iCareSystem")
            df_clean = filtered_df[filtered_df['Categoria'] == 'Limpieza (iCareSystem)']
            if not df_clean.empty:
                clean_counts = df_clean['Programa'].value_counts().reset_index()
                clean_counts.columns = ['Programa de Limpieza', 'Frecuencia']
                fig_clean = px.bar(
                    clean_counts, x='Frecuencia', y='Programa de Limpieza', orientation='h',
                    color='Frecuencia', color_continuous_scale=['#EFF6FF', '#1D4ED8']
                )
                fig_clean.update_layout(
                    height=320,
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    yaxis=dict(autorange="reversed")
                )
                st.plotly_chart(fig_clean, use_container_width=True)
            else:
                st.info("No se registraron ciclos de limpieza iCareSystem en el periodo.")

        st.markdown("---")

        col_t1, col_t2 = st.columns(2)

        with col_t1:
            st.markdown("#### 🌡️ Distribución de Temperatura Máxima de Cámara (°C)")
            fig_temp_cab = px.histogram(
                filtered_df[filtered_df['Temp_Max_Cámara_C'].notnull()],
                x='Temp_Max_Cámara_C', nbins=30,
                color_discrete_sequence=['#1D4ED8'],
                labels={'Temp_Max_Cámara_C': 'Temp Máxima Cámara (°C)'}
            )
            fig_temp_cab.update_layout(
                height=300,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                yaxis=dict(showgrid=True, gridcolor="#F1F5F9")
            )
            st.plotly_chart(fig_temp_cab, use_container_width=True)

        with col_t2:
            st.markdown("#### 🚪 Aperturas de Puerta por Carga")
            fig_doors = px.box(
                filtered_df, x='Modelo_Dev', y='Aperturas_Puerta',
                color='Modelo_Dev',
                labels={'Modelo_Dev': 'Modelo', 'Aperturas_Puerta': 'Aperturas de Puerta'}
            )
            fig_doors.update_layout(
                height=300,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)"
            )
            st.plotly_chart(fig_doors, use_container_width=True)
    else:
        st.info("No hay datos cargados para el análisis de calidad.")

# =========================================================
# PESTAÑA 4: INGESTA DE DATOS Y EXPORTACIÓN
# =========================================================
with tab_data:
    st.markdown("### 📥 Gestión de Datos, Sincronización y Exportación")
    
    col_d1, col_d2 = st.columns(2)

    with col_d1:
        st.markdown("#### 🔄 Sincronizar Carpeta del Servidor o Disco Local")
        folder_input = st.text_input(
            "Ruta de carpeta con archivos TXT o ZIP:",
            value=st.session_state.get('server_sync_folder', default_logs_dir),
            help="Ingresa la ruta a la carpeta donde se descargan los logs (ej. Z:\\lLuna\\HACCP_DATOS\\logs)"
        )
        st.session_state['server_sync_folder'] = folder_input

        if st.button("🚀 Escanear y Cargar Carpeta", use_container_width=True):
            with st.spinner("Sincronizando archivos..."):
                sync_res = scan_and_sync_folder(folder_input, db_path=default_db_file)
                if sync_res.get("status") == "success":
                    st.success(sync_res.get("message"))
                    st.rerun()
                else:
                    st.error(sync_res.get("message"))

    with col_d2:
        st.markdown("#### 📊 Exportar Registros Consolidados")
        if not filtered_df.empty:
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                filtered_df.to_excel(writer, index=False, sheet_name='OEE_HACCP_Rational')
            excel_buffer.seek(0)

            st.download_button(
                label="📥 Descargar Reporte en Excel (.xlsx)",
                data=excel_buffer,
                file_name="Reporte_OEE_Rational.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

            csv_data = filtered_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📄 Descargar Datos en CSV (.csv)",
                data=csv_data,
                file_name="Reporte_OEE_Rational.csv",
                mime="text/csv",
                use_container_width=True
            )
        else:
            st.info("No hay datos para exportar.")

    st.markdown("---")
    st.markdown("#### 🗄️ Mantenimiento de Base de Datos SQLite")
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        if os.path.exists(default_db_file):
            with open(default_db_file, "rb") as db_f:
                st.download_button(
                    label="💾 Descargar Respaldo SQLite (haccp_data.db)",
                    data=db_f.read(),
                    file_name="haccp_data.db",
                    mime="application/x-sqlite3",
                    use_container_width=True
                )
    with col_m2:
        if st.button("⚠️ Vaciar Base de Datos", type="secondary"):
            clear_database(default_db_file)
            st.warning("La base de datos ha sido vaciada.")
            st.rerun()
