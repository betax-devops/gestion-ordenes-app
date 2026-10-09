import io
import pandas as pd
import streamlit as st
from datetime import date
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Gestión de OTs", layout="wide")


# --- MÓDULO DE AUTENTICACIÓN ---
def verificar_password():
    """Retorna True si el usuario ingresó la contraseña correcta."""
    if "autenticado" not in st.session_state:
        st.session_state.autenticado = False

    if st.session_state.autenticado:
        return True

    st.subheader("🔒 Acceso Restringido - Base CCP")

    try:
        correct_password = st.secrets["APP_PASSWORD"]
    except KeyError:
        st.error(
            "⚠️ La contraseña del sistema no está configurada en los Secrets de Streamlit."
        )
        return False

    password_ingresada = st.text_input(
        "Ingresa la contraseña de acceso:", type="password"
    )

    if st.button("Ingresar"):
        if password_ingresada == correct_password:
            st.session_state.autenticado = True
            st.rerun()
        else:
            st.error("Contraseña incorrecta")

    return False

# Bloquear la ejecución si el usuario no ingresó la contraseña
if not verificar_password():
    st.stop()


# --- SERVICIO GOOGLE DRIVE ---
def obtener_servicio_drive():
    """Crea la conexión cliente con Google Drive API usando Service Account."""
    creds = service_account.Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    )
    return build("drive", "v3", credentials=creds)


# --- FUNCIÓN PARA DESCARGAR Y CARGAR CSV DESDE GOOGLE DRIVE ---
@st.cache_data(ttl=300)  # Caché de 5 minutos
def cargar_csv_desde_drive(file_name):
    """Busca y descarga un archivo CSV desde Google Drive en memoria."""
    service = obtener_servicio_drive()

    # 1. Buscar archivo por nombre
    try:
        results = service.files().list(
            q=f"name = '{file_name}' and trashed = false",
            fields="files(id, name)"
        ).execute()
    except Exception as e:
        st.error(f"Error al conectar con Google Drive: {e}")
        return None

    items = results.get('files', [])

    if not items:
        st.warning(f"No se encontró el archivo '{file_name}' en Google Drive.")
        return None

    file_id = items[0]['id']

    # 2. Descargar contenido en memoria
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    
    while not done:
        _, done = downloader.next_chunk()
        
    fh.seek(0)

    # 3. Parsear CSV probando combinaciones de encoding y delimitadores
    encodings = ['utf-8', 'utf-8-sig', 'latin1', 'cp1252']
    separators = [';', ',', '\t']
    
    df = None

    for enc in encodings:
        for sep in separators:
            try:
                fh.seek(0)
                df_temp = pd.read_csv(
                    fh, 
                    encoding=enc, 
                    sep=sep, 
                    on_bad_lines='skip', 
                    engine='python'
                )
                
                if len(df_temp.columns) >= 1:
                    if len(df_temp.columns) > 1:
                        df = df_temp
                        break
                    elif df is None:
                        df = df_temp
            except Exception:
                continue
        if df is not None and len(df.columns) > 1:
            break

    # Fallback si no se detectó separador multicolumna
    if df is None:
        try:
            fh.seek(0)
            df = pd.read_csv(fh, encoding='latin1', on_bad_lines='skip', engine='python')
        except Exception:
            return None

    return df


# --- PANEL PRINCIPAL ---
st.title("💾 Carga de Ordenes de Trabajo")

# --- CARGA DE DATOS ---
ORDENES = "ordenes.csv"
df_orden = cargar_csv_desde_drive(ORDENES)

# --- RENOMBRAR COLUMNAS ---
columnas_renombrar = {}
if 'Appointment Numbre' in df_orden.columns:
    columnas_renombrar['Appointment Numbre'] = 'Cita'
elif 'ID Técnico Telecom' in df_orden.columns:
    columnas_renombrar['ID Técnico Telecom'] = 'Tecnico'
elif 'Address' in df_orden.columns:
    columnas_renombrar['Address'] = 'Direccion'
elif 'Status' in df_orden.columns:
    columnas_renombrar['Status'] = 'Estado'
elif 'Internal SLR Geolocation (Latitude)' in df_orden.columns:
    columnas_renombrar['Internal SLR Geolocation (Latitude)'] = 'Latidud'
elif 'Internal SLR Geolocation (Longitude)' in df_orden.columns:
    columnas_renombrar['Internal SLR Geolocation (Longitude)'] = 'Longitud'
elif 'Record Type' in df_orden.columns:
    columnas_renombrar['Record Type'] = 'Tipo de Trabajo'
elif 'Internal SLR Geolocation (Longitude)' in df_orden.columns:
    columnas_renombrar['Internal SLR Geolocation (Longitude)'] = 'Longitud'
elif 'Duration' in df_orden.columns:
    columnas_renombrar['Duration'] = 'Duracion'
elif 'Arrival Window Start' in df_orden.columns:
    columnas_renombrar['Arrival Window Start'] = 'Fecha Inicio'


if columnas_renombrar:
    df_orden = df_orden.rename(columns=columnas_renombrar)


# --- MUESTRA DE DATOS EN PANTALLA ---
if df_orden is not None:
    st.write(f"Total de órdenes cargadas: **{len(df_orden)}**")
    st.dataframe(df_orden, use_container_width=True)
else:
    st.info("No se pudieron cargar los datos del archivo especificado.")
