#!/bin/bash
pip install -r requirements.txt
python3 setup_db.py
gunicorn backend:app