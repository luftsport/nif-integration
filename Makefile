# Minimal makefile for Sphinx documentation

# You can set these variables from the command line, and also
# from the environment for the first two.
SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
SOURCEDIR     = docs-source
BUILDDIR      = docs
SHELL:=/bin/bash

# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)


gh-pages:

	@if [[ -z $$(git status -s) ]]; then sphinx-build -b html $(SOURCEDIR) $(BUILDDIR); git checkout gh-pages; else echo "[!!] Git repo is not clean, commit your changes"; git status; exit 1; fi;
	@if [[ $$(git branch | grep "*" | sed "s/\* //") == "gh-pages" ]]; then git ls-files --other --exclude-standard -z | xargs -0 rm -f; git reset HEAD; cp -ar $(BUILDDIR)/* .; 
git add -A; git commit -m "Generated gh-pages for `git log master -1 --pretty=short --abbrev-commit`" && git push origin gh-pages ; git checkout develop; else echo "[!!] Not on 
gh-pages branch"; exit 2; fi;
	@echo done


.PHONY: help Makefile
# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
