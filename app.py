import io
import os
import secrets
import unicodedata
from datetime import datetime, timezone
from uuid import uuid4

from flask import Flask, abort, redirect, render_template, request, send_file, session, url_for
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.exceptions import HTTPException

from storage import Azure, Local

CATEGORIES = {'study': '勉強', 'club': '部活', 'career': '進路', 'chat': '雑談'}


def create_app(config=None):
    app = Flask(__name__)
    cloud = bool(os.getenv('WEBSITE_SITE_NAME'))
    app.config.from_mapping(
        SECRET_KEY=os.getenv('FLASK_SECRET_KEY'),
        STORAGE_CONNECTION=os.getenv('AZURE_STORAGE_CONNECTION_STRING'),
        DATA_DIR=os.getenv('HOUKAGO_DATA_DIR', app.instance_path),
        MAX_CONTENT_LENGTH=6 * 1024 * 1024,
        SESSION_COOKIE_SECURE=cloud,
        SESSION_COOKIE_SAMESITE='Lax',
        PERMANENT_SESSION_LIFETIME=86400 * 30,
    )
    app.config.update(config or {})
    connection = app.config['STORAGE_CONNECTION']
    if cloud and not connection:
        raise RuntimeError('AZURE_STORAGE_CONNECTION_STRING is required on App Service')
    if not app.secret_key:
        if cloud or connection:
            raise RuntimeError('FLASK_SECRET_KEY is required for Azure')
        app.secret_key = secrets.token_hex(32)
    db = Azure(connection) if connection else Local(app.config['DATA_DIR'])

    @app.before_request
    def visitor():
        if request.method == 'POST':
            expected = session.get('csrf')
            actual = request.form.get('csrf', '')
            if not expected or not secrets.compare_digest(expected.encode(), actual.encode()):
                abort(403)
        if request.endpoint in {'index', 'new_post', 'detail'} and 'visitor' not in session:
            session['visitor'] = uuid4().hex
            session['csrf'] = secrets.token_hex(24)
            session.permanent = True

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = "default-src 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'"
        if response.mimetype == 'text/html':
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.context_processor
    def shared():
        return {'categories': CATEGORIES, 'csrf': session.get('csrf', '')}

    def field(name, limit):
        value = request.form.get(name, '').strip()
        if not value or len(value) > limit:
            abort(400, f'入力は1〜{limit}文字で入力してください。')
        return value

    def now():
        return datetime.now(timezone.utc).isoformat(timespec='seconds')

    def normalize(text):
        return unicodedata.normalize('NFKC', text).casefold()

    @app.get('/')
    def index():
        query = request.args.get('q', '').strip()[:100]
        category = request.args.get('category', '')
        posts = db.list('posts')
        posts = [
            post for post in posts
            if (not category or post['category'] == category)
            and normalize(query) in normalize(post['title'] + ' ' + post['body'])
        ]
        posts.sort(key=lambda post: (post['time'], post['id']), reverse=True)
        solved = {item['id'] for item in db.list('solved')}
        return render_template('index.html', posts=posts, query=query, category=category, solved=solved)

    @app.route('/new', methods=['GET', 'POST'])
    def new_post():
        if request.method == 'GET':
            return render_template('new.html')
        category = request.form.get('category')
        if category not in CATEGORIES:
            abort(400, 'カテゴリを選んでください。')
        key = str(uuid4())
        post = {'id': key, 'title': field('title', 80), 'body': field('body', 2000), 'category': category,
                'owner': session['visitor'], 'time': now(), 'image': False}
        upload = request.files.get('image')
        if upload and upload.filename:
            try:
                raw = upload.read(5 * 1024 * 1024 + 1)
            finally:
                upload.close()
            if len(raw) > 5 * 1024 * 1024:
                abort(413)
            try:
                with Image.open(io.BytesIO(raw), formats=['JPEG', 'PNG', 'WEBP']) as source:
                    if source.width * source.height > 16_000_000:
                        abort(400, '画像の解像度が大きすぎます。')
                    photo = ImageOps.exif_transpose(source)
                    photo.thumbnail((1600, 1600))
                    clean = Image.new('RGB', photo.size, 'white')
                    rgba = photo.convert('RGBA')
                    clean.paste(rgba, mask=rgba.getchannel('A'))
                    output = io.BytesIO()
                    clean.save(output, format='JPEG', quality=85)
            except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
                abort(400, 'JPEG・PNG・WebP の画像を選んでください。')
            db.save_image(key, output.getvalue())
            post['image'] = True
        db.put('posts', key, post)
        return redirect(url_for('detail', post_id=key), 303)

    def find(post_id):
        post = db.get('posts', str(post_id))
        if post is None:
            abort(404)
        return post

    @app.get('/posts/<uuid:post_id>')
    def detail(post_id):
        post = find(post_id)
        key = post['id']
        comments = sorted(db.list('comments-' + key), key=lambda comment: comment['time'])
        reactions = db.list('reactions-' + key)
        return render_template('detail.html', post=post, comments=comments, count=len(reactions),
                               reacted=any(item['visitor'] == session['visitor'] for item in reactions),
                               owner=post['owner'] == session['visitor'], solved=db.get('solved', key))

    @app.post('/posts/<uuid:post_id>/<any(comment,react,resolve):action>')
    def interact(post_id, action):
        post = find(post_id)
        key = post['id']
        if action == 'comment':
            db.put('comments-' + key, uuid4().hex, {'body': field('body', 500), 'time': now()})
        elif action == 'react':
            db.put('reactions-' + key, session['visitor'], {'visitor': session['visitor']})
        else:
            if post['owner'] != session['visitor']:
                abort(403)
            db.put('solved', key, {'id': key, 'time': now()})
        return redirect(url_for('detail', post_id=key), 303)

    @app.get('/images/<uuid:post_id>')
    def image(post_id):
        if not find(post_id)['image']:
            abort(404)
        data = db.image(str(post_id))
        if data is None:
            abort(404)
        return send_file(io.BytesIO(data), mimetype='image/jpeg', max_age=86400)

    @app.get('/health')
    def health():
        db.check()
        return {'status': 'ok', 'storage': 'azure' if connection else 'local'}

    @app.errorhandler(HTTPException)
    def error(exc):
        messages = {403: '操作できません。ページを開き直してください。', 404: 'ページが見つかりません。',
                    413: '画像は5 MB以下にしてください。', 500: '時間をおいてもう一度お試しください。'}
        return render_template('error.html', message=messages.get(exc.code, exc.description)), exc.code

    return app
