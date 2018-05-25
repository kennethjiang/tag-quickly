"""
remotes.py

The client and web server needed to control a car remotely.
"""

import time
from datetime import datetime
import json
import io
import os
import copy
import math
from threading import Thread
import numpy as np

import requests
import tornado.ioloop
import tornado.web
import tornado.gen

from PIL import Image


class TaggingApplication(tornado.web.Application):

    def __init__(self, mydonkey_path='~/mydonkey/'):
        '''
        Create and publish variables needed on many of
        the web handlers.
        '''

        print('Starting Donkey Server...')
        if not os.path.exists(os.path.expanduser(mydonkey_path)):
            raise ValueError('Could not find mydonkey folder. Please run "python scripts/setup.py"')


        self.vehicles = {}

        this_dir = os.path.dirname(os.path.realpath(__file__))
        self.static_file_path = os.path.join(this_dir, 'templates', 'static')

        self.mydonkey_path = os.path.expanduser(mydonkey_path)
        self.sessions_path = os.path.join(self.mydonkey_path, 'sessions')
        self.models_path = os.path.join(self.mydonkey_path, 'models')

        handlers = [

            (r"/api/tags/", TagGetAPI),
            (r"/api/tags/?(?P<tag>[^/]+)?/", TagAPI),

            (r"/sessions/", SessionListView),
            (r"/sessions/?(?P<session_id>[^/]+)?/?(?P<page>[^/]+)?",
                SessionView),
            (r"/session_image/?(?P<session_id>[^/]+)?/?(?P<img_name>[^/]+)?",
                SessionImageView
            ),

            (r"/static/(.*)", tornado.web.StaticFileHandler, {"path": self.static_file_path}),

            ]

        settings = {'debug': True}

        super().__init__(handlers, **settings)

    def start(self, port=8887):
        ''' Start the tornado webserver. '''
        print(port)
        self.port = int(port)
        self.listen(self.port)
        tornado.ioloop.IOLoop.instance().start()


class TagGetAPI(tornado.web.RequestHandler):

    def get(self):
        self.write(json.dumps(Tags(self.application.sessions_path).tags))

class TagAPI(tornado.web.RequestHandler):
    def put(self, tag):
        targets = tornado.escape.json_decode(self.request.body)['targets']
        Tags(self.application.sessions_path).add_tag_to_session(tag, targets)

    def delete(self, session_id, tag):
        Tags(self.application.sessions_path).delete_tag_from_session(session_id, tag)


class SessionImageView(tornado.web.RequestHandler):
    def get(self, session_id, img_name):
        ''' Returns jpg images from a session folder '''

        sessions_path = self.application.sessions_path
        path = os.path.join(sessions_path, session_id, img_name)
        f = Image.open(path)
        o = io.BytesIO()
        f.save(o, format="JPEG")
        s = o.getvalue()

        self.set_header('Content-type', 'image/jpg')
        self.set_header('Content-length', len(s))

        self.write(s)



class SessionListView(tornado.web.RequestHandler):

    def get(self):
        '''
        Serves a page showing a list of all the session folders.
        TODO: Move this list creation to the session handler.
        '''

        session_dirs = [f for f in os.scandir(self.application.sessions_path) if f.is_dir() ]
        data = {'session_dirs': session_dirs, 'tags': Tags(self.application.sessions_path)}
        self.render("templates/session_list.html", **data)



class SessionView(tornado.web.RequestHandler):

    def get(self, session_id, page):
        '''
        Shows all the images saved in the session.
        '''
        from operator import itemgetter

        sessions_path = self.application.sessions_path

        prev_session_id = next_session_id = None
        session_dirs = [f.name for f in os.scandir(self.application.sessions_path) if f.is_dir() ]
        cur_idx = session_dirs.index(session_id)
        if cur_idx > 0:
            prev_session_id = session_dirs[cur_idx - 1]
        if cur_idx < len(session_dirs) - 1:
            next_session_id = session_dirs[cur_idx + 1];

        path = os.path.join(sessions_path, session_id)
        imgs = [{'name':f.name} for f in os.scandir(path) if f.is_file() ]
        img_count = len(imgs)

        perpage = 500
        pages = math.ceil(img_count/perpage)
        if page is None:
            page = 1
        else:
            page = int(page)
        end = page * perpage
        start = end - perpage
        end = min(end, img_count)


        sorted_imgs = sorted(imgs, key=itemgetter('name'))
        page_list = [p+1 for p in range(pages)]
        session = {'name':session_id, 'imgs': sorted_imgs[start:end]}
        tags = Tags(self.application.sessions_path)
        data = {'session': session, 'page_list': page_list, 'this_page':page, 'prev': prev_session_id, 'next': next_session_id, 'tags': tags.all_tags(), 'session_tags': tags.session_tags(session_id)}
        self.render("templates/session.html", **data)


    def post(self, session_id, page):
        '''
        Deletes selected images
        TODO: move this to an api cal. Page is not needed.
        '''

        data = tornado.escape.json_decode(self.request.body)

        if data['action'] == 'delete_images':
            sessions_path = self.application.sessions_path
            path = os.path.join(sessions_path, session_id)

            for i in data['imgs']:
                os.remove(os.path.join(path, i))
                #print('%s removed' %i)


class Tags():
    def __init__(self, sessions_path):
        try:
            self.file_path = os.path.join(sessions_path, 'tags')
            with open(self.file_path) as f:
                self.tags = json.load(f)
        except:
            self.tags = {}

    def all_tags(self):
        return self.tags.get('all_tags', [])

    def session_tags(self, session_id):
        return self.tags.get('sessions', {}).get(session_id, [])

    def add_tag_to_session(self, tag, targets):
        import ipdb; ipdb.set_trace()
        self.tags['targets'] = self.tags.get('targets', {})
        for target in targets:
            file_path = target
            tags = self.tags.get('targets').get(file_path, [])
            new_tags = set(tags).union(set([tag]))
            self.tags['targets'][file_path] = list(new_tags)
        with open(self.file_path, 'w') as outfile:
                json.dump(self.tags, outfile, sort_keys=True, indent=4)

    def delete_tag_from_session(self, session_id, tag):
        tags = set(self.tags.get('sessions', {}).get(session_id, []))
        tags.discard(tag)
        self.tags.get('sessions', {})[session_id] = list(tags)
        with open(self.file_path, 'w') as outfile:
                json.dump(self.tags, outfile, sort_keys=True, indent=4)

TaggingApplication().start()
