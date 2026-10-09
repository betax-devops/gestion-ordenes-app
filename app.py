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


# --- FUNCIÓN PARA DESCARGAR Y CARGAR CSV DESDE GOOGLE DRIVE ---
def descargar_csv(service, file_name):
    # 1. Intentar listar el archivo en Google Drive
    try:
        results = service.files().list(
            q=f"name = '{file_name}' and trashed = false",
            fields="files(id, name)"
        ).execute()
    except Exception:
        # Reintentar obteniendo un nuevo servicio si el token/sesión expiró
        service = obtener_servicio_drive()
        results = service.files().list(
            q=f"name = '{file_name}' and trashed = false",
            fields="files(id, name)"
        ).execute()

    items = results.get('files', [])

    if not items:
        return None, None

    file_id = items[0]['id']

    # 2. Descargar el archivo a la memoria
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    
    while not done:
        _, done = downloader.next_chunk()
        
    fh.seek(0)

    # 3. Intentar combinaciones de codificación y delimitador
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
                
                # Si logró parsear al menos 1 columna y filas válidas, lo consideramos correcto
                if len(df_temp.columns) >= 1:
                    # Preferimos separadores que dividan en más de 1 columna si el dataset es multivariable
                    if len(df_temp.columns) > 1:
                        df = df_temp
                        break
                    elif df is None:
                        df = df_temp # Guardar como fallback por si realmente era de 1 columna
            except Exception:
                continue
        if df is not None and len(df.columns) > 1:
            break

    # 4. Intento final básico si todos los intentos anteriores fallaron
    if df is None:
        try:
            fh.seek(0)
            df = pd.read_csv(fh, encoding='latin1', on_bad_lines='skip', engine='python')
        except Exception:
            return None, file_id

    return df, file_id


# --- PANEL PRINCIPAL ---
st.title("📊 Ordenes de Trabajo")

ORDENES = "ordenes.csv"

# Cargar datos desde Google Drive
df_orden = descargar_csv(ORDENES)

st.dataframe(df_orden, use_container_width=True)
