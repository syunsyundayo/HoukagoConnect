import json
import sqlite3
from contextlib import closing
from pathlib import Path


class Local:
    def __init__(self, directory):
        Path(directory).mkdir(parents=True, exist_ok=True)
        self.path = Path(directory) / 'board.sqlite3'
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS records (bucket TEXT, id TEXT, data TEXT, PRIMARY KEY (bucket, id))')
            db.execute('CREATE TABLE IF NOT EXISTS images (id TEXT PRIMARY KEY, data BLOB)')

    def put(self, bucket, key, data):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('INSERT OR IGNORE INTO records VALUES (?, ?, ?)', (bucket, key, json.dumps(data)))

    def get(self, bucket, key):
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute('SELECT data FROM records WHERE bucket=? AND id=?', (bucket, key)).fetchone()
            return json.loads(row[0]) if row else None

    def list(self, bucket):
        with closing(sqlite3.connect(self.path)) as db:
            return [json.loads(row[0]) for row in db.execute('SELECT data FROM records WHERE bucket=?', (bucket,))]

    def check(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('SELECT id FROM records LIMIT 1').fetchone()

    def save_image(self, key, data):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('INSERT INTO images VALUES (?, ?)', (key, data))

    def image(self, key):
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute('SELECT data FROM images WHERE id=?', (key,)).fetchone()
            return row[0] if row else None


class Azure:
    def __init__(self, connection):
        from azure.data.tables import TableClient
        from azure.storage.blob import ContainerClient
        self.table = TableClient.from_connection_string(connection, table_name='HoukagoConnectBoard')
        self.blobs = ContainerClient.from_connection_string(connection, container_name='houkagoconnect-images')

    def put(self, bucket, key, data):
        from azure.core.exceptions import ResourceExistsError
        try:
            self.table.create_entity({'PartitionKey': bucket, 'RowKey': key, 'Data': json.dumps(data, ensure_ascii=False)})
        except ResourceExistsError:
            pass

    def get(self, bucket, key):
        from azure.core.exceptions import ResourceNotFoundError
        try:
            return json.loads(self.table.get_entity(bucket, key)['Data'])
        except ResourceNotFoundError:
            return None

    def list(self, bucket):
        rows = self.table.query_entities('PartitionKey eq @bucket', parameters={'bucket': bucket})
        return [json.loads(row['Data']) for row in rows]

    def check(self):
        rows = self.table.query_entities('PartitionKey eq @bucket', parameters={'bucket': 'health'})
        next(iter(rows), None)
        self.blobs.get_container_properties()

    def save_image(self, key, data):
        self.blobs.upload_blob(key, data)

    def image(self, key):
        from azure.core.exceptions import ResourceNotFoundError
        try:
            return self.blobs.download_blob(key).readall()
        except ResourceNotFoundError:
            return None
