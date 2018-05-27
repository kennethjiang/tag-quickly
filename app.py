"""
remotes.py

The client and web server needed to control a car remotely.
"""

import time
from datetime import datetime
import json
import io
import sys
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

    def __init__(self, dataset_path):
        '''
        Create and publish variables needed on many of
        the web handlers.
        '''

        if not os.path.exists(os.path.expanduser(dataset_path)):
            raise ValueError(dataset_path + " does not exist.")


        this_dir = os.path.dirname(os.path.realpath(__file__))
        self.static_file_path = os.path.join(this_dir, 'templates', 'static')

        self.dataset_path = dataset_path
        self.sessions_path = os.path.join(self.dataset_path, 'sessions')
        self.models_path = os.path.join(self.dataset_path, 'models')

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
        print("Tag-quick started on port: {0}".format(port))
        self.port = int(port)
        self.listen(self.port)
        tornado.ioloop.IOLoop.instance().start()


class TagGetAPI(tornado.web.RequestHandler):

    def get(self):
        self.write(json.dumps(Tags(self.application.dataset_path).tags))

class TagAPI(tornado.web.RequestHandler):
    def put(self, tag):
        targets = tornado.escape.json_decode(self.request.body)['targets']
        Tags(self.application.dataset_path).add_tag_to_session(tag, targets)

    def delete(self, session_id, tag):
        Tags(self.application.dataset_path).delete_tag_from_session(session_id, tag)


class SessionImageView(tornado.web.RequestHandler):
    def get(self, session_id, img_name):
        ''' Returns jpg images from a session folder '''

        dataset_path = self.application.dataset_path
        path = os.path.join(dataset_path, session_id, img_name)
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

        session_dirs = [f for f in os.scandir(self.application.dataset_path) if f.is_dir() ]
        data = {'session_dirs': session_dirs, 'tags': Tags(self.application.dataset_path)}
        self.render("templates/session_list.html", **data)



class SessionView(tornado.web.RequestHandler):

    def get(self, session_id, page):
        '''
        Shows all the images saved in the session.
        '''
        from operator import itemgetter

        dataset_path = self.application.dataset_path

        prev_session_id = next_session_id = None
        session_dirs = [f.name for f in os.scandir(self.application.dataset_path) if f.is_dir() ]
        cur_idx = session_dirs.index(session_id)
        if cur_idx > 0:
            prev_session_id = session_dirs[cur_idx - 1]
        if cur_idx < len(session_dirs) - 1:
            next_session_id = session_dirs[cur_idx + 1];

        path = os.path.join(dataset_path, session_id)
        imgs = [{'name':f.name} for f in os.scandir(path) if f.is_file() ]
        img_count = len(imgs)

        per_page = 504
        max_page_num = 11
        pages = math.ceil(img_count/per_page)
        if page is None:
            page = 1
        else:
            page = int(page)

        skip_back_page = page - math.ceil(max_page_num/2)
        skip_back_page = 1 if skip_back_page < 1 else skip_back_page
        skip_ahead_page = skip_back_page + max_page_num + 1
        skip_ahead_page = pages if skip_ahead_page > pages else skip_ahead_page

        page_list = list(range(skip_back_page+1, skip_ahead_page))

        pagination = {'cur_page': page, 'page_list': page_list, 'skip_back_page': skip_back_page, 'skip_ahead_page': skip_ahead_page}

        end = page * per_page
        start = end - per_page
        end = min(end, img_count)

        sorted_imgs = sorted(imgs, key=itemgetter('name'))
        session = {'name':session_id, 'imgs': sorted_imgs[start:end]}
        tags = Tags(self.application.dataset_path)
        data = {'session': session, 'pagination': pagination, 'prev': prev_session_id, 'next': next_session_id, 'tags': tags.all_tags(), 'session_tags': tags.session_tags(session_id)}
        self.render("templates/session.html", **data)


    def post(self, session_id, page):
        '''
        Deletes selected images
        TODO: move this to an api cal. Page is not needed.
        '''

        data = tornado.escape.json_decode(self.request.body)

        if data['action'] == 'delete_images':
            dataset_path = self.application.dataset_path
            path = os.path.join(dataset_path, session_id)

            for i in data['imgs']:
                os.remove(os.path.join(path, i))
                #print('%s removed' %i)


class Tags():
    def __init__(self, dataset_path):
        try:
            self.file_path = os.path.join(dataset_path, 'tags')
            with open(self.file_path) as f:
                self.tags = json.load(f)
        except:
            self.tags = {}

    def all_tags(self):
        return self.tags.get('all_tags', [])

    def session_tags(self, session_id):
        return self.tags.get('sessions', {}).get(session_id, [])

    def add_tag_to_session(self, tag, targets):
        self.tags['targets'] = self.tags.get('targets', {})
        for target in targets:
            file_path = target
            tags = self.tags.get('targets').get(file_path, [])
            new_tags = set(tags) ^ set([tag])
            self.tags['targets'][file_path] = list(new_tags)
        with open(self.file_path, 'w') as outfile:
                json.dump(self.tags, outfile, sort_keys=True, indent=4)

    def delete_tag_from_session(self, session_id, tag):
        tags = set(self.tags.get('sessions', {}).get(session_id, []))
        tags.discard(tag)
        self.tags.get('sessions', {})[session_id] = list(tags)
        with open(self.file_path, 'w') as outfile:
                json.dump(self.tags, outfile, sort_keys=True, indent=4)

TaggingApplication(sys.argv[1]).start()
