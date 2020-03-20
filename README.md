# NIF Integration

A pythonic integration of [NIF Webservices](https://itinfo.nif.no/Integrasjon_Web_servicer) for [Lungo](luftsport/lungo).

See docs at https://luftsport.github.io/nif-integration

## Install

```
git clone https://github.com/luftsport/nif-integration.git
virtualenv nif-integration
cd nif-integration
source bin/activate
pip install -r requirements.txt
```
## Building the docs

Docs source folder `docs-source/` and build directory at `docs/`.

```
make gh-pages
```