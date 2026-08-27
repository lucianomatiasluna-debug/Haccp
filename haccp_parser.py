import re
import os
import io
import zipfile
import datetime
import pandas as pd

def parse_haccp_content(content_str, filename=""):
    """
    Parsea el contenido de texto de un archivo HACCP de Rational.
    Retorna un DataFrame de Pandas con la lista de cargas (procesos) y sus métricas asociadas.
    """
    blocks = content_str.split('*** H A C C P ***')
    charges = []

    for b in blocks[1:]:
        chnr_m = re.search(r'Ch-nr\.\s*>>(\d+)<<', b)
        if not chnr_m:
            continue
        
        chnr = int(chnr_m.group(1))
        dev_m = re.search(r'Dev-Typ\s*>>([^<]+)<<', b)
        sn_m = re.search(r'S/N\s*>>([^<]+)<<', b)
        ver_m = re.search(r'Version\s*>>([^<]+)<<', b)
        time_m = re.search(r'Time\s*>>([^<]+)<<', b)
        prog_m = re.search(r'Progr\.\s*>>([^<]+)<<', b)
        tz_m = re.search(r'Timezone\s*>>([^<]+)<<', b)
        end_m = re.search(r';\s*end\s*\(([^)]+)\)', b)

        sn = sn_m.group(1).strip() if sn_m else "DESCONOCIDO"
        dev_type = dev_m.group(1).strip() if dev_m else "DESCONOCIDO"
        version = ver_m.group(1).strip() if ver_m else ""
        raw_time_str = time_m.group(1).strip() if time_m else ""
        prog_name = prog_m.group(1).strip() if prog_m else "Sin Nombre"
        timezone = tz_m.group(1).strip() if tz_m else ""
        end_status = end_m.group(1).strip() if end_m else "EN CURSO / INCOMPLETO"

        # Formatear Fecha / Hora y Hora del Día
        dt = None
        hora_num = None
        if raw_time_str:
            try:
                dt = datetime.datetime.strptime(raw_time_str, "%Y.%m.%d %H:%M:%S")
                hora_num = dt.hour
            except ValueError:
                pass
        
        # Categorizar programa (Cocción vs Limpieza)
        prog_lower = prog_name.lower()
        if any(k in prog_lower for k in ['limpieza', 'clean', 'lavado', 'abrillantado', 'reinigung']):
            category = "Limpieza (iCareSystem)"
        else:
            category = "Cocción / Preparación"

        # Parsear líneas de lecturas de temperatura y eventos
        lines = b.splitlines()
        cab_temps = []
        core_temps = []
        door_open_count = 0
        modes_found = set()
        max_time_sec = 0

        for line in lines:
            if not line.strip():
                continue
            
            # Eventos
            if 'Door opened' in line or 'Tür auf' in line or 'porte ouverte' in line:
                door_open_count += 1
            if 'Mode STEAM' in line:
                modes_found.add('Vapor (Steam)')
            elif 'Mode HOT AIR' in line:
                modes_found.add('Aire Caliente (Hot Air)')
            elif 'Mode COMBINATION' in line:
                modes_found.add('Combinado (Combimode)')

            # Lecturas periódicas de datos
            parts = line.strip().split()
            if len(parts) >= 5 and parts[3].count(':') == 2 and parts[4] in ['C', 'F']:
                try:
                    c_temp = float(parts[0])
                    cab_temps.append(c_temp)
                except ValueError:
                    pass

                try:
                    cr_temp = float(parts[2])
                    core_temps.append(cr_temp)
                except ValueError:
                    pass

                # Parsear tiempo HH:MM:SS
                t_str = parts[3]
                t_parts = t_str.split(':')
                if len(t_parts) == 3:
                    try:
                        secs = int(t_parts[0]) * 3600 + int(t_parts[1]) * 60 + int(t_parts[2])
                        if secs > max_time_sec:
                            max_time_sec = secs
                    except ValueError:
                        pass

        # Cálculo de métricas
        max_cab_temp = max(cab_temps) if cab_temps else None
        max_core_temp = max(core_temps) if core_temps else None
        duration_min = round(max_time_sec / 60.0, 2)
        duration_hours = round(max_time_sec / 3600.0, 2)
        modes_str = ", ".join(sorted(modes_found)) if modes_found else "Estándar"

        charges.append({
            'Archivo': filename,
            'Carga_Nr': chnr,
            'Serie_SN': sn,
            'Modelo_Dev': dev_type,
            'Version_FW': version,
            'Fecha_Hora': dt,
            'Fecha': dt.strftime('%Y-%m-%d') if dt else '',
            'Hora': dt.strftime('%H:%M:%S') if dt else '',
            'Hora_Del_Dia': hora_num,
            'Programa': prog_name,
            'Categoria': category,
            'Estado_Final': end_status,
            'Duracion_Min': duration_min,
            'Duracion_Horas': duration_hours,
            'Temp_Max_Cámara_C': max_cab_temp,
            'Temp_Max_Núcleo_C': max_core_temp,
            'Aperturas_Puerta': door_open_count,
            'Modos_Coccion': modes_str,
            'Zona_Horaria': timezone
        })

    return pd.DataFrame(charges)


def _decode_bytes_content(raw_bytes):
    for enc in ['latin-1', 'utf-8', 'cp1252', 'iso-8859-1']:
        try:
            return raw_bytes.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw_bytes.decode('latin-1', errors='ignore')


def load_multiple_haccp_files(file_objects):
    """
    Procesa una lista de objetos de archivo (ej. UploadedFile de Streamlit, archivos ZIP o paths de sistema).
    Retorna un DataFrame consolidado.
    """
    dfs = []
    
    if not isinstance(file_objects, (list, tuple)):
        file_objects = [file_objects]

    for f in file_objects:
        filename = getattr(f, 'name', str(f))
        
        # Caso 1: Archivo ZIP
        if filename.lower().endswith('.zip'):
            try:
                if hasattr(f, 'read'):
                    zip_bytes = io.BytesIO(f.read())
                    if hasattr(f, 'seek'):
                        f.seek(0)
                    with zipfile.ZipFile(zip_bytes, 'r') as z:
                        for inner_name in z.namelist():
                            if inner_name.lower().endswith('.txt') and not inner_name.startswith('__MACOSX'):
                                with z.open(inner_name) as inner_f:
                                    raw_b = inner_f.read()
                                    content = _decode_bytes_content(raw_b)
                                    df = parse_haccp_content(content, filename=os.path.basename(inner_name))
                                    if not df.empty:
                                        dfs.append(df)
                else:
                    with zipfile.ZipFile(f, 'r') as z:
                        for inner_name in z.namelist():
                            if inner_name.lower().endswith('.txt') and not inner_name.startswith('__MACOSX'):
                                with z.open(inner_name) as inner_f:
                                    raw_b = inner_f.read()
                                    content = _decode_bytes_content(raw_b)
                                    df = parse_haccp_content(content, filename=os.path.basename(inner_name))
                                    if not df.empty:
                                        dfs.append(df)
            except Exception as e:
                print(f"Error extrayendo ZIP {filename}: {e}")
            continue

        # Caso 2: Archivo TXT individual o stream de bytes
        if hasattr(f, 'read'):
            raw_bytes = f.read()
            if hasattr(f, 'seek'):
                f.seek(0)
            content = _decode_bytes_content(raw_bytes)
        else:
            if not os.path.exists(f):
                continue
            with open(f, 'rb') as fp:
                raw_bytes = fp.read()
            content = _decode_bytes_content(raw_bytes)

        df = parse_haccp_content(content, filename=os.path.basename(filename))
        if not df.empty:
            dfs.append(df)

    if dfs:
        consolidated_df = pd.concat(dfs, ignore_index=True)
        if 'Fecha_Hora' in consolidated_df.columns:
            consolidated_df.sort_values(by=['Serie_SN', 'Fecha_Hora', 'Carga_Nr'], inplace=True)
        return consolidated_df
    return pd.DataFrame()
