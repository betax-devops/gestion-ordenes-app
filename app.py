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


# --- FUNCIÓN PARA DESCARGAR Y CARGAR EXCEL DESDE GOOGLE DRIVE ---
@st.cache_data(ttl=300)  # Guarda en caché durante 5 minutos
def cargar_excel_desde_drive(nombre_archivo):
    # 1. Autenticación vía Service Account en Secrets
    creds = service_account.Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    )
    service = build("drive", "v3", credentials=creds)

    # 2. Buscar archivo en Google Drive por nombre
    query = f"name = '{nombre_archivo}' and trashed = false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    items = results.get("files", [])

    if not items:
        st.error(f"No se encontró el archivo '{nombre_archivo}' en Google Drive.")
        return None

    file_id = items[0]["id"]

    # 3. Descargar el archivo Excel a la memoria
    request = service.files().get_media(fileId=file_id)
    file_stream = io.BytesIO()
    downloader = MediaIoBaseDownload(file_stream, request)

    done = False
    while not done:
        _, done = downloader.next_chunk()

    file_stream.seek(0)

    # 4. Leer el archivo Excel usando pandas y openpyxl
    return pd.read_csv(file_stream, engine="openpyxl")

# --- FUNCIÓN PARA DESCARGAR Y CARGAR CSV DESDE GOOGLE DRIVE ---
def descargar_csv(service, file_name):
    try:
        results = service.files().list(
            q=f"name = '{file_name}' and trashed = false",
            fields="files(id, name)"
        ).execute()
    except Exception:
        service = obtener_servicio_drive()
        results = service.files().list(
            q=f"name = '{file_name}' and trashed = false",
            fields="files(id, name)"
        ).execute()

    items = results.get('files', [])

    if not items:
        return None, None

    file_id = items[0]['id']
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.seek(0)
    
    # Intentar combinaciones de codificación y delimitador
    encodings = ['utf-8', 'latin1', 'utf-8-sig', 'cp1252']
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
                    on_bad_lines='skip',  # Salta filas corruptas o inconsistentes
                    engine='python'
                )
                # Validar que realmente haya separado en múltiples columnas (no todo en 1 columna)
                if len(df_temp.columns) > 1:
                    df = df_temp
                    break
            except Exception:
                continue
        if df is not None:
            break

    # Si falló la detección multicolumna, intento final básico
    if df is None:
        fh.seek(0)
        df = pd.read_csv(fh, encoding='latin1', on_bad_lines='skip', engine='python')

    return df, file_id


# --- PANEL PRINCIPAL ---
st.title("📊 Ordenes de Trabajo")

ORDENES = "ordenes.csv"

# Cargar datos desde Google Drive
df_orden = cargar_excel_desde_drive(ORDENES)

st.dataframe(df_orden, use_container_width=True)
