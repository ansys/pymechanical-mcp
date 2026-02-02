#!/bin/bash
# Script to create the venv, and install the dependencies
echo "Starting local development container"

echo "Activating virtual environment..."

ln -s /home/mechanical/.venv /home/mechanical/pymechanical-mcp/.venv_pymechanical && echo "Linking venv original dir"
# shellcheck disable=SC1091
source ./.venv_pymechanical/bin/activate

echo "Installing PyMechanical-MCP package and dependencies for development"
# let's first update everything
git fetch && git pull

# Installation should be fast because the image is built with the dependencies installed.
pip install -e '.[tests]'

echo "Setting pre-commit..."
pre-commit install --install-hooks

echo "Done! Enjoy PyMechanical!"
