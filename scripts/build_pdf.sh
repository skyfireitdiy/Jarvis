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
#   - graphviz (for PlantUML)
#   - PrinceXML (https://www.princexml.com/download/)
#
# Usage:
#   ./build_pdf.sh [<input.md>] [<output.pdf>]

set -e # Exit immediately if a command exits with a non-zero status.
set -u # Treat unset variables as an error.

# --- Dependency Check ---
check_deps() {
  local missing=0
  for cmd in pandoc java dot prince; do
    if ! command -v "$cmd" &> /dev/null; then
      echo "Error: Required command '$cmd' not found."
      missing=1
    fi
  done
  if [ $missing -ne 0 ]; then
    echo "Please install the missing dependencies and try again."
    echo "  - pandoc, java, graphviz can usually be installed via your package manager."
    echo "  - PrinceXML must be downloaded from https://www.princexml.com/download/"
    exit 1
  fi
}
check_deps

# --- Configuration ---
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$(realpath "$SCRIPT_DIR/..")"
STYLE_CSS="$SCRIPT_DIR/style.css"
DEFAULT_INPUT_FILE="$PROJECT_ROOT/docs/technical_documentation.md"
DEFAULT_OUTPUT_FILE="$PROJECT_ROOT/Jarvis_Technical_Documentation_Prince.pdf"
TEMP_HTML_FILE=$(mktemp --suffix=.html)

# --- Input Validation ---
if [ "$#" -gt 2 ]; then
    echo "Usage: $0 [<input.md>] [<output.pdf>]"
    exit 1
fi

INPUT_FILE="${1:-$DEFAULT_INPUT_FILE}"
OUTPUT_FILE="${2:-$DEFAULT_OUTPUT_FILE}"

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
export _JAVA_OPTIONS="-Djava.awt.headless=true"

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
echo "Temporary HTML file removed."
