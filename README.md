# IIT-Gn Finnovate 2025 Hackathon

### 1. Place .env parallel to manage.py

### 2. From root (finnovate_project), run
```
python -m venv env
env/scripts/activate
pip install -r requirements.txt
```

### 3. Run migrations
```
python fintech_project/manage.py makemigrations
```

### 4. Migrate
```
python fintech_project/manage.py migrate
```

### 5. Create superuser
```
python fintech_project/manage.py createsuperuser
```

### 6. To run from finnovate_project>
```
python fintech_project/manage.py
```

### 7. Login using admin creds