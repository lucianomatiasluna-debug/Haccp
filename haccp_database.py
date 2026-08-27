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
    Inicializa las tablas SQLite y asegura la presencia de columnas de placas, unidades y calidad.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

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
        ("motivo_rechazo", "TEXT")
    ]:
        try:
            cursor.execute(f"ALTER TABLE haccp_charges ADD COLUMN {col_def[0]} {col_def[1]}")
        except sqlite3.OperationalError:
            pass

    # Tabla de auditoría de archivos
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS haccp_files_log (
        file_path TEXT PRIMARY KEY,
        file_mtime REAL,
        charges_found INTEGER,
        processed_at TEXT
    )
    """)

    # Inicializar registros con valores coherentes si están nulos
    cursor.execute("""
    UPDATE haccp_charges
    SET 
        placas_capacidad_max = CASE WHEN category = 'Limpieza (iCareSystem)' THEN 0 ELSE 20 END,
        placas_utilizadas = CASE WHEN category = 'Limpieza (iCareSystem)' THEN 0 ELSE 20 END,
        placas_conformes_ok = CASE 
            WHEN category = 'Limpieza (iCareSystem)' THEN 0 
            WHEN final_status = 'RETURN' THEN 20 
            ELSE 0 
        END,
        placas_rechazadas_nok = CASE 
            WHEN category = 'Limpieza (iCareSystem)' THEN 0 
            WHEN final_status = 'RETURN' THEN 0 
            ELSE 20 
        END,
        unidades_totales = CASE WHEN category = 'Limpieza (iCareSystem)' THEN 0 ELSE 200 END,
        unidades_conformes_ok = CASE 
            WHEN category = 'Limpieza (iCareSystem)' THEN 0 
            WHEN final_status = 'RETURN' THEN 200 
            ELSE 0 
        END,
        unidades_rechazadas_nok = CASE 
            WHEN category = 'Limpieza (iCareSystem)' THEN 0 
            WHEN final_status = 'RETURN' THEN 0 
            ELSE 200 
        END
    WHERE placas_utilizadas IS NULL
    """)

    conn.commit()
    conn.close()

def save_df_to_db(df, db_path=None):
    if df.empty:
        return 0

    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM haccp_charges")
    count_before = cursor.fetchone()[0]

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for _, row in df.iterrows():
        dt_str = ""
        hora_del_dia = None
        if pd.notnull(row.get('Fecha_Hora')):
            if isinstance(row['Fecha_Hora'], (pd.Timestamp, datetime.datetime)):
                dt_str = row['Fecha_Hora'].strftime("%Y-%m-%d %H:%M:%S")
                hora_del_dia = row['Fecha_Hora'].hour
            else:
                dt_str = str(row['Fecha_Hora'])

        if hora_del_dia is None and pd.notnull(row.get('Hora_Del_Dia')):
            try:
                hora_del_dia = int(row['Hora_Del_Dia'])
            except (ValueError, TypeError):
                pass

        dev_t = str(row.get('Modelo_Dev', ''))
        cat = str(row.get('Categoria', ''))
        st_final = str(row.get('Estado_Final', ''))
        
        cap_max = get_rational_capacity(dev_t) if cat != 'Limpieza (iCareSystem)' else 0
        used = cap_max if cat != 'Limpieza (iCareSystem)' else 0
        ok_count = used if st_final == 'RETURN' else 0
        nok_count = 0 if st_final == 'RETURN' else used
        
        u_tot = used * 10
        u_ok = ok_count * 10
        u_nok = nok_count * 10

        cursor.execute("""
        INSERT OR IGNORE INTO haccp_charges (
            file_source, chnr, sn, dev_type, version, date_time, date, time, hora_del_dia,
            program, category, final_status, duration_min, duration_hours,
            max_cab_temp, max_core_temp, door_open_count, cooking_modes, timezone,
            placas_capacidad_max, placas_utilizadas, placas_conformes_ok, placas_rechazadas_nok,
            unidades_totales, unidades_conformes_ok, unidades_rechazadas_nok, motivo_rechazo,
            inserted_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(row.get('Archivo', '')),
            int(row.get('Carga_Nr', 0)),
            str(row.get('Serie_SN', '')),
            dev_t,
            str(row.get('Version_FW', '')),
            dt_str,
            str(row.get('Fecha', '')),
            str(row.get('Hora', '')),
            hora_del_dia,
            str(row.get('Programa', '')),
            cat,
            st_final,
            float(row.get('Duracion_Min', 0.0)) if pd.notnull(row.get('Duracion_Min')) else 0.0,
            float(row.get('Duracion_Horas', 0.0)) if pd.notnull(row.get('Duracion_Horas')) else 0.0,
            float(row.get('Temp_Max_Cámara_C', 0.0)) if pd.notnull(row.get('Temp_Max_Cámara_C')) else None,
            float(row.get('Temp_Max_Núcleo_C', 0.0)) if pd.notnull(row.get('Temp_Max_Núcleo_C')) else None,
            int(row.get('Aperturas_Puerta', 0)) if pd.notnull(row.get('Aperturas_Puerta')) else 0,
            str(row.get('Modos_Coccion', '')),
            str(row.get('Zona_Horaria', '')),
            cap_max,
            used,
            ok_count,
            nok_count,
            u_tot,
            u_ok,
            u_nok,
            "",
            now_str
        ))

    conn.commit()

    cursor.execute("SELECT COUNT(*) FROM haccp_charges")
    count_after = cursor.fetchone()[0]
    conn.close()

    return count_after - count_before

def save_operario_placas(charge_id, placas_utilizadas, db_path=None):
    """
    Guarda el registro de placas ubicadas en el horno por el operario.
    """
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE haccp_charges
    SET placas_utilizadas = ?
    WHERE id = ?
    """, (int(placas_utilizadas), int(charge_id)))
    conn.commit()
    conn.close()

def save_operario_calidad(charge_id, unidades_totales, unidades_ok, unidades_nok, motivo="", db_path=None):
    """
    Guarda el registro de unidades realizadas y conformes/defectuosas por el operario.
    """
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE haccp_charges
    SET unidades_totales = ?, unidades_conformes_ok = ?, unidades_rechazadas_nok = ?, motivo_rechazo = ?
    WHERE id = ?
    """, (int(unidades_totales), int(unidades_ok), int(unidades_nok), str(motivo), int(charge_id)))
    conn.commit()
    conn.close()

def update_charge_production_records(records_df_or_list, db_path=None):
    """
    Actualiza la cantidad de placas, unidades y motivo de rechazo de las cargas.
    """
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    if isinstance(records_df_or_list, pd.DataFrame):
        records = records_df_or_list.to_dict(orient='records')
    else:
        records = records_df_or_list

    for r in records:
        c_id = r.get('id')
        sn = r.get('Serie_SN') or r.get('sn')
        chnr = r.get('Carga_Nr') or r.get('chnr')
        
        placas_used = int(r.get('Placas_Utilizadas', r.get('placas_utilizadas', 0)))
        placas_ok = int(r.get('Placas_OK', r.get('placas_conformes_ok', 0)))
        placas_nok = int(r.get('Placas_Rechazadas', r.get('placas_rechazadas_nok', 0)))
        u_tot = int(r.get('Unidades_Totales', r.get('unidades_totales', 0)))
        u_ok = int(r.get('Unidades_OK', r.get('unidades_conformes_ok', 0)))
        u_nok = int(r.get('Unidades_Rechazadas', r.get('unidades_rechazadas_nok', 0)))
        motivo = str(r.get('Motivo_Rechazo', r.get('motivo_rechazo', '')))

        if c_id:
            cursor.execute("""
            UPDATE haccp_charges
            SET placas_utilizadas = ?, placas_conformes_ok = ?, placas_rechazadas_nok = ?,
                unidades_totales = ?, unidades_conformes_ok = ?, unidades_rechazadas_nok = ?,
                motivo_rechazo = ?
            WHERE id = ?
            """, (placas_used, placas_ok, placas_nok, u_tot, u_ok, u_nok, motivo, c_id))
        elif sn and chnr:
            cursor.execute("""
            UPDATE haccp_charges
            SET placas_utilizadas = ?, placas_conformes_ok = ?, placas_rechazadas_nok = ?,
                unidades_totales = ?, unidades_conformes_ok = ?, unidades_rechazadas_nok = ?,
                motivo_rechazo = ?
            WHERE sn = ? AND chnr = ?
            """, (placas_used, placas_ok, placas_nok, u_tot, u_ok, u_nok, motivo, sn, chnr))

    conn.commit()
    conn.close()

def scan_and_sync_folder(folder_path, db_path=None):
    if not folder_path or not os.path.exists(folder_path):
        return {"status": "error", "message": f"La carpeta '{folder_path}' no existe o no es accesible."}

    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT file_path, file_mtime FROM haccp_files_log")
    logged_files = {row['file_path']: row['file_mtime'] for row in cursor.fetchall()}
    conn.close()

    files_to_check = []
    for root, _, files in os.walk(folder_path):
        for f in files:
            if f.lower().endswith(('.txt', '.zip')):
                files_to_check.append(os.path.join(root, f))

    new_or_updated_files = []
    for f_path in files_to_check:
        try:
            mtime = os.path.getmtime(f_path)
            if f_path not in logged_files or logged_files[f_path] < mtime:
                new_or_updated_files.append((f_path, mtime))
        except OSError:
            pass

    if not new_or_updated_files:
        return {
            "status": "success",
            "files_scanned": len(files_to_check),
            "files_processed": 0,
            "new_charges_added": 0,
            "message": f"Todos los {len(files_to_check)} archivos encontrados ya estaban sincronizados."
        }

    total_added = 0
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for f_path, mtime in new_or_updated_files:
        try:
            df = load_multiple_haccp_files([f_path])
            added = 0
            if not df.empty:
                added = save_df_to_db(df, db_path=db_path)
                total_added += added

            conn = get_db_connection(db_path)
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO haccp_files_log (file_path, file_mtime, charges_found, processed_at)
            VALUES (?, ?, ?, ?)
            """, (f_path, mtime, len(df), now_str))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Error procesando {f_path}: {e}")

    return {
        "status": "success",
        "files_scanned": len(files_to_check),
        "files_processed": len(new_or_updated_files),
        "new_charges_added": total_added,
        "message": f"Sincronización completada: {len(new_or_updated_files)} archivo(s) procesado(s), {total_added} nuevas cargas agregadas a la BD."
    }

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
        timezone as Zona_Horaria,
        placas_capacidad_max as Capacidad_Placas_Max,
        placas_utilizadas as Placas_Utilizadas,
        placas_conformes_ok as Placas_OK,
        placas_rechazadas_nok as Placas_Rechazadas,
        unidades_totales as Unidades_Totales,
        unidades_conformes_ok as Unidades_OK,
        unidades_rechazadas_nok as Unidades_Rechazadas,
        motivo_rechazo as Motivo_Rechazo,
        inserted_at as Registrado_En
    FROM haccp_charges
    ORDER BY sn, date_time, chnr
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
