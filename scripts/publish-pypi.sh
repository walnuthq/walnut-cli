#!/bin/bash
# Publish Walnut CLI to PyPI

set -e

echo "Publishing Walnut CLI to PyPI..."

# Clean previous builds
rm -rf dist build *.egg-info

# Install build tools
pip install --upgrade build twine

# Build the package
python -m build

# Check the distribution
twine check dist/*

# Upload to PyPI (will prompt for credentials)
echo "Uploading to PyPI..."
twine upload dist/*

echo "Package published successfully!"
echo "Users can now install with: pip install walnut-cli"