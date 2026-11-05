#!/usr/bin/env bash
set -Eeuo pipefail

# La carpeta del proyecto es la ubicación del propio script.
APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$APP_DIR/.venv-ubuntu"

if ! command -v python3 >/dev/null 2>&1; then
    echo "No encuentro python3. Instálalo con: sudo apt install python3 python3-venv" >&2
    exit 1
fi

if ! python3 -c 'import venv' >/dev/null 2>&1; then
    echo "Falta el módulo venv. Instálalo con: sudo apt install python3-venv" >&2
    exit 1
fi

if [[ ! -f "$APP_DIR/code/main.py" ]]; then
    echo "No encuentro code/main.py. Ejecuta este script desde la carpeta del proyecto." >&2
    exit 1
fi

# Entorno separado de Windows: los entornos virtuales no se comparten entre SO.
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/python" -m pip install -r "$APP_DIR/requirements.txt"

APP_LAUNCHER="$HOME/.local/share/applications/pokevault.desktop"
mkdir -p "$(dirname -- "$APP_LAUNCHER")"

write_launcher() {
    local destination="$1"
    cat > "$destination" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=PokeVault
Comment=Organiza tu colección de cartas Pokémon
Exec="$VENV_DIR/bin/python" "$APP_DIR/code/main.py"
Path=$APP_DIR
Icon=$APP_DIR/assets/pokevault-mark.svg
Terminal=false
Categories=Utility;Education;
StartupNotify=true
EOF
    chmod +x "$destination"
}

write_launcher "$APP_LAUNCHER"
if [[ -d "$HOME/Desktop" ]]; then
    DESKTOP_ICON="$HOME/Desktop/PokeVault.desktop"
    write_launcher "$DESKTOP_ICON"
    if command -v gio >/dev/null 2>&1; then
        gio set "$DESKTOP_ICON" metadata::trusted true 2>/dev/null || true
    fi
    echo "Acceso directo creado en: $DESKTOP_ICON"
else
    echo "No existe ~/Desktop; el acceso está disponible en el menú de aplicaciones."
fi

echo "PokeVault está instalado para este usuario. Ábrelo desde el Escritorio o el menú de aplicaciones."
echo "La colección y el token siguen en ~/.pokevault, fuera del proyecto."
