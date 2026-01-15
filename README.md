# IIT-Gn Finnovate 2025 Hackathon

## For Local:-

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

### 5. Create staticfiles directory: just run the command
```
python fintech_project/manage.py collectstatic
```

### 6. Create superuser
```
python fintech_project/manage.py createsuperuser
```

### 7. To run from finnovate_project>
```
python fintech_project/manage.py runserver
```

### 8. Login using admin creds
Th ones you used during createsuperuser cmd

## FOR PROD:-
Close the server if it is running on Windows terminal, we'll use NGINX+Gunicorn in WSL
### 9. (in WSL) 
```
cd /mnt/c/Users/krish/Desktop/FINTECH/finnovate_project
sudo apt install python-is-python3 -y
pip install -r requirements.txt
```
You'll need to restart WSL
```
cd /mnt/c/Users/krish/Desktop/FINTECH/finnovate_project/fintech_project
gunicorn --bind 0.0.0.0:8000 core.wsgi
```
Update the paths in your nginx.conf and test it by opening a new WSL terminal and running
```
sudo apt install nginx-core
sudo nginx -t -c /mnt/c/Users/krish/Desktop/FINTECH/finnovate_project/deploy/nginx/nginx.conf
```
Test it using
```
sudo nginx -t -c /mnt/c/Users/krish/Desktop/FINTECH/finnovate_project/deploy/nginx/nginx.conf
```
On one side, you need gunicorn to keep running from fintech_project using 
```
gunicorn --bind 0.0.0.0:8000 core.wsgi
```
On other side, you need NGINX to keep running using
```
sudo nginx -c /mnt/c/Users/krish/Desktop/FINTECH/finnovate_project/deploy/nginx/nginx.conf
```
Test using
```
curl localhost:8081
```
To stop it, use
```
sudo nginx -s stop
```

We'll be using localhost:8081 now, not port 8000
Gunicorn listens to 8000
NGINX listens to 8081
Please dont bypass NGINX, it is out cute little reverse proxy setup

## SAP ERP (HANA 2.0)

### Important Links:-
https://www.sap.com/products/data-cloud/hana/express-trial.html
https://tools.hana.ondemand.com/#hanatools

https://account.hanatrial.ondemand.com/trial/#/home/trial

TEST SAP HANA ERP CONNECTION:-

```
python -c "from hdbcli import dbapi; conn = dbapi.connect(address='ebdc3fa3-fb21-454f-bad4-f569d264fd7c.hana.trial-us10.hanacloud.ondemand.com', port=443, user='DBADMIN', password='AdaniPower@123', encrypt=True, sslValidateCertificate=False); print('Connected!'); conn.close()"
```

## RAG SETUP

### 1. Get ElasticSearch Docker Image to access ElasticSearch OSS

```
docker rm -f es-rag

docker run -d `
  --name es-rag `
  -p 9200:9200 `
  -e "discovery.type=single-node" `
  -e "xpack.security.enabled=false" `
  -e "ES_JAVA_OPTS=-Xms2g -Xmx2g" `
  docker.elastic.co/elasticsearch/elasticsearch:8.15.0
```
Test
```
curl http://localhost:9200
```