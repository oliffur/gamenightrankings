#!/bin/bash
cd "$(dirname "$0")"
pipenv run python3 parse_results.py
git add --all
git commit -m "update rankings"
git push
exit 0
