import io
import re
import tempfile
import unittest
from contextlib import closing

from PIL import Image
from werkzeug.test import EnvironBuilder

from app import create_app


class BoardTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config = {'TESTING': True, 'DATA_DIR': self.directory.name, 'STORAGE_CONNECTION': None}
        self.app = create_app(self.config)
        self.client = self.app.test_client()

    def token(self, client, path):
        return re.search(r'name="csrf" value="([^"]+)"', client.get(path).text).group(1)

    def publish(self, **extra):
        data = {'csrf': self.token(self.client, '/new'), 'category': 'study',
                'title': '数学ＡＢＣ', 'body': '<script>本文</script>', **extra}
        with closing(EnvironBuilder(path='/new', method='POST', data=data)) as builder:
            environ = builder.get_environ()
            with environ['wsgi.input']:
                return self.client.open(environ)

    def test_post_search_filter_and_persistence(self):
        response = self.publish()
        self.assertEqual(response.status_code, 303)
        for path in ('/', '/?q=abc&category=study', response.location):
            self.assertIn('数学ＡＢＣ', self.client.get(path).text)
        self.assertNotIn('数学ＡＢＣ', self.client.get('/?category=club').text)
        self.assertNotIn('数学ＡＢＣ', self.client.get('/?q=部活').text)
        page = self.client.get(response.location)
        self.assertIn('&lt;script&gt;本文&lt;/script&gt;', page.text)
        restarted = create_app(self.config).test_client()
        self.assertIn('数学ＡＢＣ', restarted.get(response.location).text)
        self.assertEqual(restarted.get('/health').json['storage'], 'local')

    def test_comment_reaction_and_post_owner_resolution(self):
        path = self.publish().location
        guest = self.app.test_client()
        token = self.token(guest, path)
        self.assertEqual(guest.post(path + '/comment', data={'csrf': token, 'body': '参考になった！'}).status_code, 303)
        for _ in range(2):
            self.assertEqual(guest.post(path + '/react', data={'csrf': token}).status_code, 303)
        self.assertIn('共感済み 1', guest.get(path).text)
        self.assertIn('参考になった！', guest.get(path).text)
        self.assertEqual(guest.post(path + '/resolve', data={'csrf': token}).status_code, 403)
        owner = self.token(self.client, path)
        self.assertEqual(self.client.post(path + '/resolve', data={'csrf': owner}).status_code, 303)
        self.assertIn('✓ 解決済み', guest.get(path).text)
        self.assertIn('✓ 解決済み', guest.get('/').text)

    def test_image_content_validation_and_serving(self):
        original = io.BytesIO()
        Image.new('RGB', (12, 12), 'green').save(original, 'PNG')
        original.seek(0)
        post = self.publish(image=(original, 'image.png'))
        self.assertEqual(post.status_code, 303)
        image = self.client.get(post.location.replace('/posts/', '/images/'))
        self.assertEqual(image.mimetype, 'image/jpeg')
        with Image.open(io.BytesIO(image.data)) as parsed:
            self.assertEqual(parsed.size, (12, 12))
        self.assertEqual(self.publish(image=(io.BytesIO(b'wrong'), 'bad.png')).status_code, 400)
        self.assertEqual(self.publish(image=(io.BytesIO(b'x' * (5 * 1024 * 1024 + 1)), 'big.png')).status_code, 413)

    def test_input_validation_and_csrf(self):
        self.assertEqual(self.client.post('/new').status_code, 403)
        self.assertEqual(self.publish(category='unknown').status_code, 400)
        self.assertEqual(self.publish(title=' ' * 10).status_code, 400)
        self.assertEqual(self.publish(body='a' * 2001).status_code, 400)
        self.assertEqual(self.client.get('/posts/11111111-1111-1111-1111-111111111111').status_code, 404)


if __name__ == '__main__':
    unittest.main()
