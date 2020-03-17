# NIF Integration

## Installing

```
git clone repo
virtualenv - nif-integration
cd nif-integration
source bin/activate
pip install -r requirements.txt
```
scp -r typings nif_api eve_api app_logger.py decorators.py geocoding.py integration.py organizations.py rebuild_api_resources.py reset_api.py stream.py streamdaemon.py sync.py syncdaemon.py merit:/home/einar/nif-integration/

## Building the docs

Docs source folder `docs-source/` and build directory at `docs/`.
This makes it easy to use the `docs/` folder for github pages. 

Run in root folder `nif-integration`

```sphinx-build -b html ./docs-source ./docs```

If no rst's have been built then run:

```sphinx-apidoc . -o ./docs-source -f ```