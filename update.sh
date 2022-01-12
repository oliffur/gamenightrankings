#!/bin/bash
pipenv run python3 parse_results.py
git add --all
git commit -m "update rankings"
git push
