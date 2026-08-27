import os
import sys
import sqlite3
import datetime
import pandas as pd
from haccp_parser import load_multiple_haccp_files, parse_haccp_content

# Catálogo oficial de capacidades de manual Rational
RATIONAL_MANUAL_CAPACITIES = {
    "G202": {"nombre": "Rational Gas 20-2/1", "placas_max": 20, "formato": "GN 2/1 (40 GN 1/1)", "kg_max": 200},
    "E202": {"nombre": "Rational Eléctrico 20-2/1", "placas_max": 20, "formato": "GN 2/1 (40 GN 1/1)", "kg_max": 200},
    "G201": {"nombre": "Rational Gas 20-1/1", "placas_max": 20, "formato": "GN 1/1", "kg_max": 100},
    "E201": {"nombre": "Rational Eléctrico 20-1/1", "placas_max": 20, "formato": "GN 1/1", "kg_max": 100},
    "G102": {"nombre": "Rational Gas 10-2/1", "placas_max": 10, "formato": "GN 2/1 (20 GN 1/1)", "kg_max": 100},
    "E102": {"nombre": "Rational Eléctrico 10-2/1", "placas_max": 10, "formato": "GN 2/1 (20 GN 1/1)", "kg_max": 100},
    "G101": {"nombre": "Rational Gas 10-1/1", "placas_max": 10, "formato": "GN 1/1", "kg_max": 50},
    "E101": {"nombre": "Rational Eléctrico 10-1/1", "placas_max": 10, "formato": "GN 1/1", "kg_max": 50},
    "G62":  {"nombre": "Rational Gas 6-2/1", "placas_max": 6, "formato": "GN 2/1 (12 GN 1/1)", "kg_max": 60},
    "E62":  {"nombre": "Rational Eléctrico 6-2/1", "placas_max": 6, "formato": "GN 2/1 (12 GN 1/1)", "kg_max": 60},
    "G61":  {"nombre": "Rational Gas 6-1/1", "placas_max": 6, "formato": "GN 1/1", "kg_max": 30},
    "E61":  {"nombre": "Rational Eléctrico 6-1/1", "placas_max": 6, "formato": "GN 1/1", "kg_max": 30},
    "XS":   {"nombre": "Rational iCombi XS", "placas_max": 6, "formato": "GN 2/3", "kg_max": 20},
}

def get_rational_capacity(dev_type):
    if not dev_type:
        return 20
    dt_clean = str(dev_type).strip().upper()
    for k, v in RATIONAL_MANUAL_CAPACITIES.items():
        if k in dt_clean:
            return v["placas_max"]
    if "202" in dt_clean or "20-2" in dt_clean:
        return 20
    elif "201" in dt_clean or "20-1" in dt_clean:
        return 20
    elif "102" in dt_clean or "10-2" in dt_clean:
        return 10
    elif "101" in dt_clean or "10-1" in dt_clean:
        return 10
    elif "62" in dt_clean or "6-2" in dt_clean:
        return 6
    elif "61" in dt_clean or "6-1" in dt_clean:
        return 6
    return 20

def get_base_app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def get_default_db_path():
    return os.path.join(get_base_app_dir(), "haccp_data.db")

DEFAULT_DB_NAME = get_default_db_path()

def get_db_connection(db_path=None):
    if not db_path:
        db_path = get_default_db_path()
    
    parent = os.path.dirname(os.path.abspath(db_path))
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)

    conn = sqlite3.connect(db_path, timeout=60.0)
    try:
        conn.execute("PRAGMA busy_timeout = 60000;")
    except Exception:
        pass
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path=None):
    """
    Inicializa las tablas SQLite, catálogo de equipos y registros.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # 1. Tabla de Cargas / Operaciones
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS haccp_charges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_source TEXT,
        chnr INTEGER,
        sn TEXT,
        dev_type TEXT,
        version TEXT,
        date_time TEXT,
        date TEXT,
        time TEXT,
        hora_del_dia INTEGER,
        program TEXT,
        category TEXT,
        final_status TEXT,
        duration_min REAL,
        duration_hours REAL,
        max_cab_temp REAL,
        max_core_temp REAL,
        door_open_count INTEGER,
        cooking_modes TEXT,
        timezone TEXT,
        placas_capacidad_max INTEGER DEFAULT 20,
        placas_utilizadas INTEGER,
        placas_conformes_ok INTEGER,
        placas_rechazadas_nok INTEGER DEFAULT 0,
        unidades_totales INTEGER DEFAULT 0,
        unidades_conformes_ok INTEGER DEFAULT 0,
        unidades_rechazadas_nok INTEGER DEFAULT 0,
        kilos_totales REAL DEFAULT 0,
        kilos_conformes_ok REAL DEFAULT 0,
        kilos_rechazados_nok REAL DEFAULT 0,
        equipo_alias TEXT,
        motivo_rechazo TEXT,
        inserted_at TEXT,
        UNIQUE(sn, chnr) ON CONFLICT IGNORE
    )
    """)

    # Migraciones defensivas
    for col_def in [
        ("placas_capacidad_max", "INTEGER DEFAULT 20"),
        ("placas_utilizadas", "INTEGER"),
        ("placas_conformes_ok", "INTEGER"),
        ("placas_rechazadas_nok", "INTEGER DEFAULT 0"),
        ("unidades_totales", "INTEGER DEFAULT 0"),
        ("unidades_conformes_ok", "INTEGER DEFAULT 0"),
        ("unidades_rechazadas_nok", "INTEGER DEFAULT 0"),
        ("kilos_totales", "REAL DEFAULT 0"),
        ("kilos_conformes_ok", "REAL DEFAULT 0"),
        ("kilos_rechazados_nok", "REAL DEFAULT 0"),
        ("equipo_alias", "TEXT"),
        ("motivo_rechazo", "TEXT")
    ]:
        try:
            cursor.execute(f"ALTER TABLE haccp_charges ADD COLUMN {col_def[0]} {col_def[1]}")
        except sqlite3.OperationalError:
            pass

    # 2. Tabla de Catálogo de Equipos de Planta
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS catalogo_equipos (
        id TEXT PRIMARY KEY,
        tipo TEXT,
        nombre TEXT,
        sn TEXT,
        capacidad_nominal REAL,
        unidad TEXT,
        estado TEXT DEFAULT 'Activo'
    )
    """)

    # 3. Tabla de auditoría de archivos
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS haccp_files_log (
        file_path TEXT PRIMARY KEY,
        file_mtime REAL,
        charges_found INTEGER,
        processed_at TEXT
    )
    """)

    conn.commit()

    # Preconfigurar catálogo de equipos de cocina si está vacío
    cursor.execute("SELECT COUNT(*) FROM catalogo_equipos")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT OR REPLACE INTO catalogo_equipos (id, tipo, nombre, sn, capacidad_nominal, unidad, estado)
        VALUES 
            ('HORNO_1', 'Horno Rational', 'Horno Rational #1 (iCombi 20-2/1)', 'E21SH21082873738', 20.0, 'Placas', 'Activo'),
            ('HORNO_2', 'Horno Rational', 'Horno Rational #2 (iCombi 20-2/1)', 'E21SH21082873739', 20.0, 'Placas', 'Activo'),
            ('HORNO_3', 'Horno Rational', 'Horno Rational #3 (iCombi 10-1/1)', 'E11SH21082873740', 10.0, 'Placas', 'Activo'),
            ('MARMITA_1', 'Marmita Industrial', 'Marmita Industrial #1 (150 Kg)', 'MARM-01', 150.0, 'Kg', 'Activo'),
            ('MARMITA_2', 'Marmita Industrial', 'Marmita Industrial #2 (200 Kg)', 'MARM-02', 200.0, 'Kg', 'Activo')
        """)
        conn.commit()

    # Relleno histórico pre-septiembre
    cursor.execute("""
    UPDATE haccp_charges
    SET 
        placas_capacidad_max = CASE WHEN category = 'Limpieza (iCareSystem)' THEN 0 ELSE 20 END,
        placas_utilizadas = CASE WHEN category = 'Limpieza (iCareSystem)' THEN 0 ELSE 20 END,
        placas_conformes_ok = CASE WHEN category = 'Limpieza (iCareSystem)' THEN 0 ELSE 20 END,
        placas_rechazadas_nok = 0,
        unidades_totales = CASE WHEN category = 'Limpieza (iCareSystem)' THEN 0 ELSE 200 END,
        unidades_conformes_ok = CASE WHEN category = 'Limpieza (iCareSystem)' THEN 0 ELSE 200 END,
        unidades_rechazadas_nok = 0,
        kilos_totales = CASE WHEN category = 'Limpieza (iCareSystem)' THEN 0 ELSE 150.0 END,
        kilos_conformes_ok = CASE WHEN category = 'Limpieza (iCareSystem)' THEN 0 ELSE 150.0 END,
        kilos_rechazados_nok = 0,
        motivo_rechazo = ''
    WHERE date < '2026-09-01' OR placas_utilizadas IS NULL
    """)
    conn.commit()
    conn.close()

def get_equipos_catalogo(db_path=None):
    init_db(db_path)
    conn = get_db_connection(db_path)
    df = pd.read_sql_query("SELECT * FROM catalogo_equipos WHERE estado = 'Activo' ORDER BY tipo, id", conn)
    conn.close()
    return df

def insert_operacion_manual(
    equipo_alias, tipo_equipo, fecha, hora, producto, duracion_min,
    placas_usadas=0, placas_ok=0, placas_nok=0,
    unidades_tot=0, unidades_ok=0, unidades_nok=0,
    kilos_tot=0.0, kilos_ok=0.0, kilos_nok=0.0,
    motivo_rechazo="", operador="", db_path=None
):
    """
    Inserta una operación de cocción registrada por el operario/cocinero.
    """
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COALESCE(MAX(chnr), 0) + 1 FROM haccp_charges")
    next_chnr = cursor.fetchone()[0]

    dt_str = f"{fecha} {hora}"
    try:
        dt_obj = datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        hora_num = dt_obj.hour
    except Exception:
        try:
            dt_obj = datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
            hora_num = dt_obj.hour
        except Exception:
            hora_num = datetime.datetime.now().hour

    dur_h = round(float(duracion_min) / 60.0, 2)
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if (unidades_nok > 0 or kilos_nok > 0 or placas_nok > 0):
        st_final = "CON RECHAZO"
    else:
        st_final = "RETURN"

    cap_placas = 20 if tipo_equipo == "Horno Rational" else 0

    cursor.execute("""
    INSERT INTO haccp_charges (
        file_source, chnr, sn, dev_type, version, date_time, date, time, hora_del_dia,
        program, category, final_status, duration_min, duration_hours,
        placas_capacidad_max, placas_utilizadas, placas_conformes_ok, placas_rechazadas_nok,
        unidades_totales, unidades_conformes_ok, unidades_rechazadas_nok,
        kilos_totales, kilos_conformes_ok, kilos_rechazados_nok,
        equipo_alias, motivo_rechazo, timezone, inserted_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        f"Manual ({operador})" if operador else "Registro Manual",
        next_chnr,
        str(equipo_alias),
        str(tipo_equipo),
        "Terminal Cocina",
        dt_str,
        str(fecha),
        str(hora),
        hora_num,
        str(producto),
        "Cocción / Preparación",
        st_final,
        float(duracion_min),
        dur_h,
        cap_placas,
        int(placas_usadas),
        int(placas_ok),
        int(placas_nok),
        int(unidades_tot),
        int(unidades_ok),
        int(unidades_nok),
        float(kilos_tot),
        float(kilos_ok),
        float(kilos_nok),
        str(equipo_alias),
        str(motivo_rechazo),
        operador,
        now_str
    ))
    conn.commit()
    conn.close()

def delete_operacion(charge_id, db_path=None):
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM haccp_charges WHERE id = ?", (int(charge_id),))
    conn.commit()
    conn.close()

def get_all_charges_from_db(db_path=None):
    init_db(db_path)
    conn = get_db_connection(db_path)
    
    query = """
    SELECT 
        id,
        file_source as Archivo,
        chnr as Carga_Nr,
        sn as Serie_SN,
        dev_type as Modelo_Dev,
        version as Version_FW,
        date_time as Fecha_Hora,
        date as Fecha,
        time as Hora,
        hora_del_dia as Hora_Del_Dia,
        program as Programa,
        category as Categoria,
        final_status as Estado_Final,
        duration_min as Duracion_Min,
        duration_hours as Duracion_Horas,
        max_cab_temp as Temp_Max_Cámara_C,
        max_core_temp as Temp_Max_Núcleo_C,
        door_open_count as Aperturas_Puerta,
        cooking_modes as Modos_Coccion,
        timezone as Operador,
        placas_capacidad_max as Capacidad_Placas_Max,
        placas_utilizadas as Placas_Utilizadas,
        placas_conformes_ok as Placas_OK,
        placas_rechazadas_nok as Placas_Rechazadas,
        unidades_totales as Unidades_Totales,
        unidades_conformes_ok as Unidades_OK,
        unidades_rechazadas_nok as Unidades_Rechazadas,
        kilos_totales as Kilos_Totales,
        kilos_conformes_ok as Kilos_OK,
        kilos_rechazados_nok as Kilos_Rechazados,
        equipo_alias as Equipo_Alias,
        motivo_rechazo as Motivo_Rechazo,
        inserted_at as Registrado_En
    FROM haccp_charges
    ORDER BY id DESC
    """
    
    df = pd.read_sql_query(query, conn)
    conn.close()

    if not df.empty:
        if 'Fecha_Hora' in df.columns:
            df['Fecha_Hora'] = pd.to_datetime(df['Fecha_Hora'], errors='coerce')
        if 'Hora_Del_Dia' not in df.columns or df['Hora_Del_Dia'].isnull().all():
            if 'Fecha_Hora' in df.columns:
                df['Hora_Del_Dia'] = df['Fecha_Hora'].dt.hour
    else:
        if 'Hora_Del_Dia' not in df.columns:
            df['Hora_Del_Dia'] = pd.Series(dtype='int64')

    return df

def clear_database(db_path=None):
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM haccp_charges")
    cursor.execute("DELETE FROM haccp_files_log")
    conn.commit()
    conn.close()
