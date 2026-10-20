import io
import pandas as pd
import streamlit as st
from datetime import date
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

#============================================================================================================================
# --- CONFIGURACIÓN DE PÁGINA -----------------------------------------------------------------------------------------------
#============================================================================================================================
st.set_page_config(
    page_title="Gestión de Trabajo - Base CCP",
    page_icon="📊",  # Puedes cambiarlo por "📡", "🛠️", "📋", etc.
    layout="wide",
)
#============================================================================================================================
# --- MÓDULO DE AUTENTICACIÓN -----------------------------------------------------------------------------------------------
#============================================================================================================================
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
#============================================================================================================================
# --- SERVICIO GOOGLE DRIVE -------------------------------------------------------------------------------------------------
#============================================================================================================================
def obtener_servicio_drive():
    """Crea la conexión cliente con Google Drive API usando Service Account."""
    creds = service_account.Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    )
    return build("drive", "v3", credentials=creds)
#============================================================================================================================
# --- FUNCIÓN PARA DESCARGAR Y CARGAR CSV DESDE GOOGLE DRIVE ----------------------------------------------------------------
#============================================================================================================================
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
#============================================================================================================================
# --- PANEL PRINCIPAL -------------------------------------------------------------------------------------------------------
#============================================================================================================================
st.title("🌐 Panel de Control - Operaciones, Calidad y NPS")
#============================================================================================================================
#--- CARGA DE DATOS ---------------------------------------------------------------------------------------------------------
#============================================================================================================================
ORDENES = "ordenes.csv"
#CALIDAD = 
NPS = "nps.xlsx"


df_orden = cargar_csv_desde_drive(ORDENES)
df_nps = cargar_csv_desde_drive(NPS)
df_copy = df_orden.copy()
#============================================================================================================================
# --- RENOMBRAR COLUMNAS ----------------------------------------------------------------------------------------------------
#============================================================================================================================
columnas_orden = {
    'Appointment Number': 'Cita',
    'ID Técnico Telecom': 'Tecnico',
    'Address': 'Direccion',
    'Status Category': 'Estado',
    'Internal SLR Geolocation (Latitude)': 'Latitud',
    'Internal SLR Geolocation (Longitude)': 'Longitud',
    'Record Type': 'Tipo de Trabajo',
    'Work Type': 'Tipo OT',
    'Duration': 'Duracion',
    'Last Modified Date': 'Fecha Cita',
    'State/Province': 'Provincia',
    'Service Territory': 'Territorio',
    'Contact': 'Cliente'
}
# Pandas ignora automáticamente las columnas que no existen en el DataFrame
df_orden = df_orden.rename(columns=columnas_orden)
#============================================================================================================================
# --- NORMALIZACION DE COLUMNAS ---------------------------------------------------------------------------------------------
#============================================================================================================================
# 1. Aplicamos rsplit desde la derecha, limitando a 2 cortes
# expand=True convierte el resultado en nuevas columnas independientes
columna_direccion = df_orden['Direccion'].str.rsplit(',', n=2, expand=True)

# 2. Asignamos los resultados a tu DataFrame
df_orden['Direccion'] = columna_direccion[0].str.strip()
df_orden['Localidad2'] = columna_direccion[1].str.strip()
df_orden['Resto'] = columna_direccion[2].str.strip()

# Extraer la localidad desde la columna 'Descripcion' sin importar el formato (mayúsculas o minúsculas)
df_orden['Localidad3'] = (
    df_orden['Description']
    .str.extract(r'(?i)localidad\s*:\s*([^\n]+)', expand=False)
    .str.strip()
)

# Creamos la columna definitiva 'Localidad':
# Si Localidad2 tiene un valor, lo usa. Si es nulo (NaN), lo completa con Localidad3.
df_orden['Localidad'] = df_orden['Localidad2'].fillna(df_orden['Localidad3'])

# Renombrarmos para normalizar los datos de la columna 'Localidad'
# 1. Opcional pero recomendado: Pasar a mayúsculas y limpiar espacios iniciales/finales
df_orden['Localidad'] = df_orden['Localidad'].astype(str).str.upper().str.strip()
# 2. Diccionario con los reemplazos para normalizar variaciones comunes
mapeo_localidades = {
    'ALDERETE': 'ALDERETES',
    'BANDA DEL RIO SALI': 'BANDA DEL RIO SALI',
    'BANDA DEL RIO SALÍ': 'BANDA DEL RIO SALI',
    'DRU': 'BANDA DEL RIO SALI',
    'CHICLIGASTA': 'CONCEPCION',
    'CONCEPCION - CH': 'CONCEPCION',
    'CONCEPCION-CH': 'CONCEPCION',
    'JUAN BAUTISTA ALBERDI': 'JUAN B ALBERDI',
    'VILLA BURRUYACU': 'BURRUYACU',
    'CEK': 'YERBA BUENA',
    'AGL': 'SAN MIGUEL DE TUCUMAN',
    'CAPITAL': 'SAN MIGUEL DE TUCUMAN',
    'CFC': 'SAN MIGUEL DE TUCUMAN',
    'CIM': 'SAN MIGUEL DE TUCUMAN',
    'DLX': 'SAN MIGUEL DE TUCUMAN',
    'IMA': 'SAN MIGUEL DE TUCUMAN',
    'ISC': 'SAN MIGUEL DE TUCUMAN',
    'SAN MIGUEL DE TUCUMÁN': 'SAN MIGUEL DE TUCUMAN',
    'KAM': 'SAN MIGUEL DE TUCUMAN',
    'KEN': 'SAN MIGUEL DE TUCUMAN',
    'TUCUMAN': 'SAN MIGUEL DE TUCUMAN',
    'KYL': 'SAN MIGUEL DE TUCUMAN',
    'SD': 'JUAN B ALBERDI'    
}

# 3. Aplicamos el mapeo (si una localidad no está en el diccionario, se mantiene como está)
df_orden['Localidad'] = df_orden['Localidad'].replace(mapeo_localidades)

# Normalizacion de Fecha de Cita
# Convvierte 'Fecha Cita' indicando que el formato es mes/día/año (MM/DD/YYYY)
df_orden['Fecha Cita'] = pd.to_datetime(df_orden['Fecha Cita'],dayfirst=False,errors='coerce')
# Esta linea omite la hora:
df_orden['Fecha Cita'] = pd.to_datetime(df_orden['Fecha Cita']).dt.date
#============================================================================================================================
# --- SELECCION DE COLUMNAS A MOSTRAR ---------------------------------------------------------------------------------------
#============================================================================================================================
columnas_seleccionadas = [
    'Cita',
    'Work Order',
    'Tipo de Trabajo',
    'Tipo OT',
    'Direccion',
    'Localidad',
    'Cliente',
    'Territorio',
    'Tecnico',
    'Estado',
    'Fecha Cita'
]

columnas_existentes = [col for col in columnas_seleccionadas if col in df_orden.columns]

df_normalizado = df_orden[columnas_existentes]
#============================================================================================================================
# --- NAVEGACIÓN POR SECCIONES Y SUBSECCIONES -------------------------------------------------------------------------------
#============================================================================================================================
st.sidebar.title("📌 Menú de Navegación")
seccion_principal = st.sidebar.pills(
    "Selecciona una Sección",
    ["📋 Órdenes", "📈 Calidad", "📊 NPS"]
)
st.markdown("---")

#============================================================================================================================    
# --- MUESTRA DE DATOS EN PANTALLA ------------------------------------------------------------------------------------------
#============================================================================================================================

# Aquí evalúas en qué sección estás parado
if seccion_principal == "📋 Órdenes":
    st.header("Gestión de Órdenes")
    # Creamos las pestañas para las subsecciones
    tab_volumen, tab_analisis, tab_geo, tab_monitoreo = st.tabs([
      "📋 Ordenes de Trabajo",
      "📊 Análisis",
      "🗺️ Distribución Geográfica",
      "📌 Monitoreo",
    ])
    # --- SECCIÓN 1: ÓRDENES ---
    with tab_volumen:
        if seccion_principal == "📋 Órdenes":
            st.title("💾 Carga de Ordenes de Trabajo")  
            st.header("📋 Sección: Órdenes (Operación y Logística)")
        
            # --- SECCIÓN DE BÚSQUEDA ---
            st.subheader("🔍 Buscador Integrado")
            c1, c2, c3, c4, c5, c6 = st.columns(6)
        
            with c1:
                search_dir = st.text_input("Buscar por Dirección")
            with c2:
                opciones_localidad = (
                    df_normalizado['Localidad'].dropna().unique().tolist()
                    )
                opciones_localidad.sort()
                # Agregar una opción general por si el usuario quiere ver todo
                opciones_localidad.insert(0, "Todas")
                search_localidad = st.selectbox("Localidad", opciones_localidad)
            with c3:
                opciones_territorio = (
                    df_normalizado['Territorio'].dropna().unique().tolist()
                    )
                opciones_territorio.sort()
                opciones_territorio.insert(0, "Todas")
                search_territorio = st.selectbox("Territorio", opciones_territorio)
            with c4:
                opciones_estado = (
                    df_normalizado['Estado'].dropna().unique().tolist()
                    )
                opciones_estado.sort()
                opciones_estado.insert(0, "Todas")
                search_estado = st.selectbox("Estado", opciones_estado)
            with c5:
                opciones_trabajo = (
                    df_normalizado['Tipo de Trabajo'].dropna().unique().tolist()
                    )
                opciones_trabajo.sort()
                opciones_trabajo.insert(0, "Todas")
                search_trabajo = st.selectbox("Tipo de Trabajo", opciones_trabajo)
            with c6:
                search_cliente = st.text_input("Buscar por Cliente")
                
            # --- APLICAR FILTROS --- 
            
            if search_dir and 'Direccion' in df_normalizado.columns:
                df_normalizado = df_normalizado[df_normalizado['Direccion'].astype(str).str.contains(search_dir, case=False, na=False)]
                
            if search_localidad != "Todas" and 'Localidad' in df_normalizado.columns:
                df_normalizado = df_normalizado[df_normalizado['Localidad'].astype(str).str.strip().str.upper() == str(search_localidad).upper()]
        
            if search_territorio != "Todas" and 'Territorio' in df_normalizado.columns:
                df_normalizado = df_normalizado[df_normalizado['Territorio'].astype(str).str.strip().str.upper() == str(search_territorio).upper()]
                
            if search_estado != "Todas" and 'Estado' in df_normalizado.columns:
                df_normalizado = df_normalizado[df_normalizado['Estado'].astype(str).str.strip().str.upper() == str(search_estado).upper()]
                
            if search_trabajo != "Todas" and 'Tipo de Trabajo' in df_normalizado.columns:
                df_normalizado = df_normalizado[df_normalizado['Tipo de Trabajo'].astype(str).str.strip().str.upper() == str(search_trabajo).upper()]
        
            if search_cliente and 'Cliente' in df_normalizado.columns:
                df_normalizado = df_normalizado[df_normalizado['Cliente'].astype(str).str.contains(search_cliente, case=False, na=False)]
    
            st.subheader("Volumen de Órdenes por Fecha")
            if df_normalizado is not None:
                st.write(f"Total de órdenes cargadas: **{len(df_normalizado)}**")
                st.write(f"La última fecha de actualización es: {df_normalizado['Fecha Cita'].max()}")
                # Muestra de los datos Normalizados
                st.dataframe(df_normalizado, use_container_width=True)
            else:
                st.info("No se pudieron cargar los datos del archivo especificado.")
            
            # Data frame completo sin filtros
            st.write(f"Total de órdenes cargadas: **{len(df_copy)}**")
            st.dataframe(df_copy, use_container_width=True)
            
    with tab_analisis:
        st.subheader("Duración de los Trabajos")
        st.info(
            "Aquí puedes mostrar métricas de tiempos promedio por tipo de trabajo."
        )
    
    with tab_geo:
        st.subheader("Distribución Geográfica")
        st.info("Visualización por Localidad y Provincia.")
    
    with tab_monitoreo:
        st.subheader("Listado de Órdenes para Monitorear")
        





    elif seccion_principal == "📈 Calidad":
        st.header("Métricas de Calidad")
        # Todo el código de calidad aquí...
    
    elif seccion_principal == "📊 NPS":
        st.header("Análisis de NPS")
        # Todo el código de NPS aquí...


