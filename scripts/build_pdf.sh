#!/bin/bash

# build_pdf.sh - Converts Markdown documentation to a professional PDF using PrinceXML.
#
# This script uses a two-stage process:
# 1. Pandoc converts Markdown to a standalone HTML file, using pandoc-plantuml
#    to render diagrams as PNG images.
# 2. PrinceXML takes the styled HTML file and produces a high-quality PDF.
#
# This approach offers excellent CSS support and reliable line breaking.
#
# Prerequisites:
#   - pandoc
#   - pandoc-plantuml filter (pip install pandoc-plantuml)
#   - java (for PlantUML)
#   - PrinceXML (https://www.princexml.com/download/)
#
# Usage:
#   ./build_pdf.sh [<input.md>] [<output.pdf>]

set -e # Exit immediately if a command exits with a non-zero status.
set -u # Treat unset variables as an error.

# --- Dependency Management ---
ensure_deps() {
    echo "Checking and installing dependencies..."

    # Install system dependencies (pandoc, java) for Ubuntu if missing
    if [ -f /etc/os-release ] && grep -q "ID=ubuntu" /etc/os-release; then
        local missing_pkgs=""
        if ! command -v pandoc &> /dev/null; then
            missing_pkgs+=" pandoc"
        fi
        if ! command -v java &> /dev/null; then
            missing_pkgs+=" default-jre" # For PlantUML
        fi
        # Additional dependencies for PlantUML rendering and CJK fonts
        if ! command -v dot &> /dev/null; then
            missing_pkgs+=" graphviz"
        fi
        if ! command -v fc-list &> /dev/null; then
            missing_pkgs+=" fontconfig"
        fi
        if command -v fc-list &> /dev/null; then
            if ! fc-list | grep -Ei "Noto Sans CJK|Source Han Sans|WenQuanYi|Microsoft YaHei|PingFang" >/dev/null; then
                missing_pkgs+=" fonts-noto-cjk"
            fi
        else
            missing_pkgs+=" fonts-noto-cjk"
        fi

        if [ -n "$missing_pkgs" ]; then
            echo "The following system packages are missing and will be installed:$missing_pkgs"
            echo "This requires sudo privileges."
            sudo apt-get update
            sudo apt-get install -y $missing_pkgs
            if command -v fc-cache &> /dev/null; then
                fc-cache -f >/dev/null 2>&1 || true
            fi
        fi
    else
        echo "Warning: Not an Ubuntu system. Please ensure pandoc and java are installed manually."
        # Simple check for non-ubuntu systems
          for cmd in pandoc java dot; do
            if ! command -v "$cmd" &> /dev/null; then
              echo "Error: Required command '$cmd' not found."
              exit 1
            fi
          done
    fi

    # Install Python dependency (pandoc-plantuml-filter) using uv
    echo "Ensuring Python dependency 'pandoc-plantuml-filter' is installed..."
    if command -v uv &> /dev/null; then
        uv pip install pandoc-plantuml-filter
    else
        echo "Warning: 'uv' command not found. Trying with 'pip'."
        if command -v pip &> /dev/null; then
            pip install pandoc-plantuml-filter
        else
            echo "Error: Neither 'uv' nor 'pip' found. Cannot install 'pandoc-plantuml'."
            exit 1
        fi
    fi

    # Check for PrinceXML (manual installation required)
    if ! command -v prince &> /dev/null; then
        echo "Error: Required command 'prince' not found."
        echo "PrinceXML must be downloaded and installed manually from https://www.princexml.com/download/"
        exit 1
    fi

    echo "All dependencies are satisfied."
}
ensure_deps

# --- Configuration ---
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$(realpath "$SCRIPT_DIR/..")"
STYLE_CSS="$SCRIPT_DIR/style.css"
DEFAULT_INPUT_FILE="$PROJECT_ROOT/docs/technical_documentation.md"
# DEFAULT_OUTPUT_FILE is no longer needed as the output filename is derived from the input filename.
TEMP_HTML_FILE=$(mktemp --suffix=.html)

# --- Input Validation ---
if [ "$#" -gt 2 ]; then
    echo "Usage: $0 [<input.md>] [<output.pdf>]"
    exit 1
fi

INPUT_FILE="${1:-$DEFAULT_INPUT_FILE}"
# If output file is not provided, derive it from input file name
if [ -z "${2:-}" ]; then
    INPUT_BASENAME=$(basename "$INPUT_FILE" .md)
    OUTPUT_FILE="./$INPUT_BASENAME.pdf"
else
    OUTPUT_FILE="$2"
fi

# Derive document title from the output filename
DOC_BASENAME=$(basename "$OUTPUT_FILE" .pdf)
DOC_TITLE="${DOC_BASENAME//_/ }"

# Resolve paths to be absolute
INPUT_FILE_ABS="$(realpath "$INPUT_FILE")"
OUTPUT_FILE_ABS="$(realpath "$OUTPUT_FILE")"
STYLE_CSS_ABS="$(realpath "$STYLE_CSS")"

if [ ! -f "$INPUT_FILE_ABS" ]; then
    echo "Error: Input file not found at '$INPUT_FILE_ABS'"
    exit 1
fi
if [ ! -f "$STYLE_CSS_ABS" ]; then
    echo "Error: Style file not found at '$STYLE_CSS_ABS'"
    exit 1
fi

echo "--- Starting PDF Generation via PrinceXML ---"
echo "Input Markdown: $INPUT_FILE_ABS"
echo "Temp HTML:      $TEMP_HTML_FILE"
echo "Output PDF:     $OUTPUT_FILE_ABS"
echo "---------------------------------------------"

# Set PLANTUML_JAR and _JAVA_OPTIONS for pandoc-plantuml
export PLANTUML_JAR="$SCRIPT_DIR/plantuml.jar"
export PLANTUML_BIN="java -jar $PLANTUML_JAR"
export _JAVA_OPTIONS="-Djava.awt.headless=true"
# Enforce PlantUML font/DPI to avoid text overlapping in diagrams
PLANTUML_CFG=$(mktemp --suffix=.puml.cfg)
cat > "$PLANTUML_CFG" <<'EOF'
skinparam defaultFontName "Noto Sans CJK SC"
skinparam ClassFontName "Noto Sans CJK SC"
skinparam ActivityFontName "Noto Sans CJK SC"
skinparam SequenceMessageFontName "Noto Sans CJK SC"
skinparam SequenceParticipantFontName "Noto Sans CJK SC"
skinparam NoteFontName "Noto Sans CJK SC"
skinparam PackageFontName "Noto Sans CJK SC"
skinparam ArrowFontName "Noto Sans CJK SC"
skinparam defaultFontSize 12
skinparam maxMessageSize 120
skinparam dpi 200
skinparam wrapWidth 180
EOF
export PLANTUML_CONFIG="$PLANTUML_CFG"
export PANDOC_PLANTUML_FORMAT=png

# --- Stage 1: Pandoc Markdown -> HTML ---
echo "Step 1: Converting Markdown to HTML..."
pandoc "$INPUT_FILE_ABS" \
        --self-contained \
    -s \
    --filter pandoc-plantuml \
    --toc \
    --toc-depth=3 \
    --metadata title="$DOC_TITLE" \
    -c "$STYLE_CSS_ABS" \
    -o "$TEMP_HTML_FILE"
echo "HTML generation complete."


# --- Stage 2: Prince HTML -> PDF ---
echo "Step 2: Converting HTML to PDF with Prince..."
prince "$TEMP_HTML_FILE" -o "$OUTPUT_FILE_ABS"
echo "✅ PDF generation complete: '$OUTPUT_FILE_ABS'"

# --- Cleanup ---
rm "$TEMP_HTML_FILE"
[ -n "${PLANTUML_CFG:-}" ] && rm -f "$PLANTUML_CFG"
echo "Temporary HTML file removed."
