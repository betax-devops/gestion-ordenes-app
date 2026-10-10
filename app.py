import io
import pandas as pd
import streamlit as st
from datetime import date
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

""" --- CONFIGURACIÓN DE PÁGINA --- """
st.set_page_config(page_title="Gestión de OTs", layout="wide")


""" --- MÓDULO DE AUTENTICACIÓN --- """
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


""" --- SERVICIO GOOGLE DRIVE --- """
def obtener_servicio_drive():
    """Crea la conexión cliente con Google Drive API usando Service Account."""
    creds = service_account.Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    )
    return build("drive", "v3", credentials=creds)


""" --- FUNCIÓN PARA DESCARGAR Y CARGAR CSV DESDE GOOGLE DRIVE --- """
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


""" --- PANEL PRINCIPAL --- """
st.title("💾 Carga de Ordenes de Trabajo")

""" --- CARGA DE DATOS --- """
ORDENES = "ordenes.csv"
df_orden = cargar_csv_desde_drive(ORDENES)
df_copy = df_orden.copy()

""" --- RENOMBRAR COLUMNAS --- """
columnas_renombrar = {
    'Appointment Number': 'Cita',
    'ID Técnico Telecom': 'Tecnico',
    'Address': 'Direccion',
    'Status': 'Estado',
    'Internal SLR Geolocation (Latitude)': 'Latitud',
    'Internal SLR Geolocation (Longitude)': 'Longitud',
    'Record Type': 'Tipo de Trabajo',
    'Duration': 'Duracion',
    'Arrival Window Start': 'Fecha Cita',
    'State/Province': 'Provincia'
}

# Pandas ignora automáticamente las columnas que no existen en el DataFrame
df_orden = df_orden.rename(columns=columnas_renombrar)

""" --- NORMALIZACION DE COLUMNAS --- """
# 1. Aplicamos rsplit desde la derecha, limitando a 2 cortes
# expand=True convierte el resultado en nuevas columnas independientes
columnas_nuevas = df_orden['Direccion'].str.rsplit(',', n=2, expand=True)

# 2. Asignamos los resultados a tu DataFrame
df_orden['Direccion'] = columnas_nuevas[0].str.strip()
df_orden['Localidad'] = columnas_nuevas[1].str.strip()
df_orden['Resto'] = columnas_nuevas[2].str.strip()

""" --- CAMBIO DE TIPO DE DATO DE COLUMNA --- """



# --- SELECCION DE COLUMNAS A MOSTRAR ---
columnas_seleccionadas = [
    'Cita',
    'Work Order',
    'Direccion',
    'Localidad',
    'Provincia',
    'Tecnico',
    'Estado',
    'Fecha Cita'
]

columnas_existentes = [col for col in columnas_seleccionadas if col in df_orden.columns]

df_normalizado = df_orden[columnas_existentes]


# --- MUESTRA DE DATOS EN PANTALLA ---
# Dataframe Normalizado
if df_normalizado is not None:
    st.write(f"Total de órdenes cargadas: **{len(df_normalizado)}**")
    st.dataframe(df_normalizado, use_container_width=True)
else:
    st.info("No se pudieron cargar los datos del archivo especificado.")

#Data frame completo
st.write(f"Total de órdenes cargadas: **{len(df_copy)}**")
st.dataframe(df_copy, use_container_width=True)
