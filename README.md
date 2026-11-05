# PokeVault

Aplicación de escritorio para organizar una colección personal de cartas Pokémon TCG. Permite buscar cartas, gestionar la colección, organizar una lista de deseos en álbumes y consultar precios de referencia y ofertas de CardTrader.

## Funciones

- Búsqueda de cartas por nombre o expansión.
- Colección con idioma, estado, acabado y cantidad.
- Lista de deseos organizada en álbumes.
- Precios generales orientativos obtenidos mediante TCGdex.
- Consultas de ofertas de CardTrader por idioma, cuando se configura un token con permisos adecuados.
- Historial de cotizaciones y copias portátiles `.pvbackup`, con fotos manuales incluidas; también se restauran copias SQLite `.db` antiguas.

Las cotizaciones dependen de los datos y la disponibilidad del catálogo externo; puede que no haya ofertas compatibles para todas las cartas, impresiones o idiomas.

## Requisitos

- Python 3.11 o superior.
- Conexión a Internet para el catálogo y los servicios de precios.
- Opcional: cuenta y Bearer Auth Token JWT de CardTrader para consultar sus ofertas.

## Instalación y ejecución

### Ubuntu

Desde la carpeta del proyecto, crea el acceso directo de escritorio y configura las dependencias:

```bash
sudo apt install python3 python3-venv  # si aún no están instalados
chmod +x CREAR_LANZADOR_UBUNTU.sh
./CREAR_LANZADOR_UBUNTU.sh
```

El script instala las dependencias en `.venv-ubuntu` y crea un acceso en el menú de aplicaciones y, si existe, en el Escritorio. Si Ubuntu lo marca como no confiable, haz clic derecho en el icono y selecciona **Permitir iniciar**. El acceso apunta a esta carpeta: si la mueves, vuelve a ejecutar el script.

Para iniciar desde la terminal en lugar de usar el acceso directo:

```bash
.venv-ubuntu/bin/python code/main.py
```

### Windows

Instala Python 3.11 o superior. En PowerShell, desde la carpeta del proyecto:

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe code\main.py
```

También puedes ejecutar `CREAR_EXE_WINDOWS.bat` para compilar la aplicación. El resultado se genera en `dist\PokeVault\PokeVault.exe`; para distribuirlo, copia la carpeta completa `dist\PokeVault`, no solo el ejecutable. La compilación debe hacerse en Windows.

## Token y datos personales

El token se introduce desde el diálogo de CardTrader de la aplicación. Al validarlo y guardarlo, PokeVault lo almacena fuera del proyecto en:

```text
~/.pokevault/cardtrader_token
```

En Linux se guarda con permisos privados para tu usuario. El token no se guarda en el código ni en la base de datos. No publiques ni compartas ese archivo.

La colección, la lista de deseos, los precios guardados, la caché, los registros y las copias automáticas se almacenan localmente en `~/.pokevault/` (en Windows, `%USERPROFILE%\.pokevault\`). Esa carpeta está fuera del repositorio. Las nuevas copias `.pvbackup` empaquetan las fotos manuales de la colección y la lista de deseos para poder restaurarlas en otro equipo. Las antiguas copias `.db` siguen siendo restaurables, pero no llevan las fotos dentro; esas fotos solo se recuperan si sus archivos aún existen en el equipo. El `.gitignore` excluye bases de datos, tokens, entornos virtuales, registros y copias locales; revisa los archivos antes de subir cambios a GitHub.

## Estructura del proyecto

```text
code/main.py             Inicio de la aplicación y ventana principal
code/app_core.py         Base de datos, servicios y componentes compartidos
code/search_tab.py       Pestaña de búsqueda
code/collection_tab.py   Pestaña Mi colección y precios
code/wishlist_tab.py     Lista de deseos y álbumes
assets/                  Logo y recursos gráficos
requirements.txt         Dependencias Python
CREAR_LANZADOR_UBUNTU.sh Instalador del acceso directo de Ubuntu
CREAR_EXE_WINDOWS.bat    Compilación del ejecutable para Windows
```

## Licencia

Este proyecto se distribuye bajo la licencia MIT. Consulta el archivo `LICENSE`.

## Servicios externos

PokeVault consulta TCGdex para datos del catálogo y precios generales. Las ofertas por idioma se consultan mediante la API de CardTrader con tu token. CardTrader puede exigir permisos específicos para las rutas de mercado.
