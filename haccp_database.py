import os
import sys
import sqlite3
import datetime
import pandas as pd
from haccp_parser import load_multiple_haccp_files, parse_haccp_content

def get_base_app_dir():
    """
    Retorna la ruta absoluta del directorio base de la aplicación.
    Compatible con ejecución local, congelada (PyInstaller) o en Streamlit Cloud.
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def get_default_db_path():
    """
    Retorna la ruta absoluta al archivo SQLite haccp_data.db junto a la aplicación.
    """
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
    Inicializa las tablas SQLite si no existen.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Tabla de cargas/procesos HACCP
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
        inserted_at TEXT,
        UNIQUE(sn, chnr) ON CONFLICT IGNORE
    )
    """)

    # Tabla de auditoría de archivos procesados
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS haccp_files_log (
        file_path TEXT PRIMARY KEY,
        file_mtime REAL,
        charges_found INTEGER,
        processed_at TEXT
    )
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

        cursor.execute("""
        INSERT OR IGNORE INTO haccp_charges (
            file_source, chnr, sn, dev_type, version, date_time, date, time, hora_del_dia,
            program, category, final_status, duration_min, duration_hours,
            max_cab_temp, max_core_temp, door_open_count, cooking_modes, timezone, inserted_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(row.get('Archivo', '')),
            int(row.get('Carga_Nr', 0)),
            str(row.get('Serie_SN', '')),
            str(row.get('Modelo_Dev', '')),
            str(row.get('Version_FW', '')),
            dt_str,
            str(row.get('Fecha', '')),
            str(row.get('Hora', '')),
            hora_del_dia,
            str(row.get('Programa', '')),
            str(row.get('Categoria', '')),
            str(row.get('Estado_Final', '')),
            float(row.get('Duracion_Min', 0.0)) if pd.notnull(row.get('Duracion_Min')) else 0.0,
            float(row.get('Duracion_Horas', 0.0)) if pd.notnull(row.get('Duracion_Horas')) else 0.0,
            float(row.get('Temp_Max_Cámara_C', 0.0)) if pd.notnull(row.get('Temp_Max_Cámara_C')) else None,
            float(row.get('Temp_Max_Núcleo_C', 0.0)) if pd.notnull(row.get('Temp_Max_Núcleo_C')) else None,
            int(row.get('Aperturas_Puerta', 0)) if pd.notnull(row.get('Aperturas_Puerta')) else 0,
            str(row.get('Modos_Coccion', '')),
            str(row.get('Zona_Horaria', '')),
            now_str
        ))

    conn.commit()

    cursor.execute("SELECT COUNT(*) FROM haccp_charges")
    count_after = cursor.fetchone()[0]
    conn.close()

    return count_after - count_before

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
