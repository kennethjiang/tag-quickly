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
from operator import itemgetter

import requests
import tornado.ioloop
import tornado.web
import tornado.gen

from PIL import Image


class TaggingApplication(tornado.web.Application):

    def __init__(self, dir_path, tag_file_path):
        '''
        Create and publish variables needed on many of
        the web handlers.
        '''

        if not os.path.exists(os.path.expanduser(dir_path)):
            raise ValueError(dir_path + " does not exist.")
        if not os.path.exists(os.path.expanduser(tag_file_path)):
            raise ValueError(tag_file_path + " does not exist.")

        cur_dir = os.path.dirname(os.path.realpath(__file__))
        self.static_file_path = os.path.join(cur_dir, 'templates', 'static')

        self.dir_path = dir_path

        handlers = [

            #(r"/", tornado.web.RedirectHandler, dict(url="/")),
            (r"/api/tags/", TagGetAPI, dict(file_path=tag_file_path)),
            (r"/api/tags/?(?P<tag>[^/]+)?/", TagAPI, dict(file_path=tag_file_path)),

            (r"/?(?P<page>[^/]+)?", SessionView, dict(dir_path=dir_path, tag_file_path=tag_file_path)),

            (r"/static/(.*)", tornado.web.StaticFileHandler, {"path": self.static_file_path}),
            (r"/imgs/(.*)", tornado.web.StaticFileHandler, {"path": self.dir_path})

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
    def initialize(self, file_path):
        self.file_path = file_path

    def get(self):
        self.write(json.dumps(Tags(self.file_path).tags))

class TagAPI(tornado.web.RequestHandler):
    def initialize(self, file_path):
        self.file_path = file_path

    def put(self, tag):
        targets = tornado.escape.json_decode(self.request.body)['targets']
        tags = Tags(self.file_path)
        tags.update_tag(tag, targets)
        self.write(json.dumps(tags.tags))

class SessionImageView(tornado.web.RequestHandler):
    def get(self, session_id, img_name):
        ''' Returns jpg images from a session folder '''

        dir_path = self.application.dir_path
        path = os.path.join(dir_path, session_id, img_name)
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

        session_dirs = [f for f in os.scandir(self.application.dir_path) if f.is_dir() ]
        data = {'session_dirs': session_dirs, 'tags': Tags(self.application.dir_path)}
        self.render("templates/session_list.html", **data)



class SessionView(tornado.web.RequestHandler):
    def initialize(self, dir_path, tag_file_path):
        self.dir_path = dir_path
        self.tag_file_path = tag_file_path

    def get(self, page):
        imgs = [{'name':f.name} for f in os.scandir(self.dir_path) if f.is_file() ]
        img_count = len(imgs)

        per_page = 504
        max_page_num = 11
        total_pages = math.ceil(img_count/per_page)
        if page is None:
            page = 1
        else:
            page = int(page)

        if page <= math.floor(max_page_num/2):
            page_num_min = 1
            page_num_max = page_num_min + max_page_num - 1
            if max_page_num > total_pages:
                page_num_max = total_pages
        elif page + math.floor(max_page_num/2) > total_pages:
            page_num_max = total_pages
            page_num_min = page_num_max - max_page_num + 1
            if page_num_min < 1:
                page_num_min = 1
        else:
            page_num_min = page - math.floor(max_page_num/2)
            page_num_max = page + math.floor(max_page_num/2)

        page_list = list(range(page_num_min, page_num_max+1))  # Python `range` doesn't include the upper bound

        pagination = {
                'cur_page': page,
                'page_list': page_list,
                'total_pages': total_pages,
                'skip_back_page': page_num_min-1 if page_num_min > 1 else None,
                'skip_ahead_page': page_num_max + 1 if page_num_max < total_pages else None
        }

        end = page * per_page
        start = end - per_page
        end = min(end, img_count)

        sorted_imgs = sorted(imgs, key=itemgetter('name'))
        session = {'imgs': sorted_imgs[start:end]}
        tags = Tags(self.tag_file_path)
        data = {'session': session, 'pagination': pagination, 'tags': tags.all_tags()}
        self.render("templates/session.html", **data)


    def post(self, session_id, page):
        '''
        Deletes selected images
        TODO: move this to an api cal. Page is not needed.
        '''

        data = tornado.escape.json_decode(self.request.body)

        if data['action'] == 'delete_images':
            dir_path = self.application.dir_path
            path = os.path.join(dir_path, session_id)

            for i in data['imgs']:
                os.remove(os.path.join(path, i))
                #print('%s removed' %i)


class Tags():
    def __init__(self, tag_file_path):
        self.file_path = tag_file_path
        with open(self.file_path) as f:
            self.tags = json.load(f)

    def all_tags(self):
        return self.tags.get('all_tags', [])

    def session_tags(self, session_id):
        return self.tags.get('sessions', {}).get(session_id, [])

    def update_tag(self, tag, targets):
        self.tags['targets'] = self.tags.get('targets', {})
        for target in targets:
            file_path = target
            tags = self.tags.get('targets').get(file_path, [])
            new_tags = set(tags) ^ set([tag])
            self.tags['targets'][file_path] = list(new_tags)
        with open(self.file_path, 'w') as outfile:
            json.dump(self.tags, outfile, sort_keys=True, indent=4)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("-d", "--dir", required=True, help="Directory of images")
    ap.add_argument("-f", "--file", required=True, help="Tag files")
    args = vars(ap.parse_args())

    TaggingApplication(dir_path=args['dir'], tag_file_path=args['file']).start()
