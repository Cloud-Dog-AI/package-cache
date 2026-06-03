# Build Instructions

## Package
`cloud_dog_cache` - caching helpers for platform services.

## Prerequisites
- Python 3.11+
- pip

## Development Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip build twine pytest
pip install -e .
```

To include the optional Redis extra:
```bash
pip install -e .[redis]
```

## Local Use
```bash
python -c "import cloud_dog_cache; print('package import ok')"
```

## Run Tests
```bash
python -m pytest tests/unit -v
```

## Build Distribution
```bash
python -m build
```

## Publish
```bash
twine upload --repository-url $PYPI_URL dist/*
```

## Docker Packaging
```bash
PYPI_URL=https://packages.example.com/simple/ \
PYPI_USERNAME=build-user \
PYPI_PASSWORD=build-password \
docker build -t cloud_dog_cache:latest .
```

## Dependencies
- optional Redis support is available through the `redis` extra
- see `pyproject.toml` for the exact dependency set

## Configuration
This package does not require a dedicated env overlay for unit testing; configure cache backends with standard shell environment variables when embedding it in an application.

## Vault Integration
```bash
export VAULT_ADDR=https://vault.example.com
export VAULT_TOKEN=your-token
export VAULT_MOUNT_POINT=your-mount
export VAULT_CONFIG_PATH=your-path
```
