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

from tags import Tags


class DonkeyPilotApplication(tornado.web.Application):

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

            #temporary redirect until vehicles is not a singleton
            (r"/", HomeView),

            (r"/vehicles/", VehicleListView),

            (r"/vehicles/?(?P<vehicle_id>[A-Za-z0-9-]+)?/",
                VehicleView),

            (r"/vehicles/?(?P<vehicle_id>[A-Za-z0-9-]+)?/device_tilt",
                DeviceTiltView),


            (r"/api/vehicles/?(?P<vehicle_id>[A-Za-z0-9-]+)?/",
                VehicleAPI),


            (r"/api/vehicles/drive/?(?P<vehicle_id>[A-Za-z0-9-]+)?/",
                DriveAPI),

            (r"/api/vehicles/video/?(?P<vehicle_id>[A-Za-z0-9-]+)?",
                VideoAPI
            ),

            (r"/api/vehicles/control/?(?P<vehicle_id>[A-Za-z0-9-]+)?/",
                ControlAPI),

            (r"/api/sessions/", SessionAPI),

            (r"/api/sessions/?(?P<session_id>[^/]+)?/tags/?(?P<tag>[^/]+)?/", TagAPI),

            (r"/sessions/", SessionListView),
            (r"/sessions/?(?P<session_id>[^/]+)?/?(?P<page>[^/]+)?/download", SessionDownload),

            (r"/sessions/?(?P<session_id>[^/]+)?/?(?P<page>[^/]+)?",
                SessionView),

            (r"/session_image/?(?P<session_id>[^/]+)?/?(?P<img_name>[^/]+)?",
                SessionImageView
            ),


            (r"/pilots/", PilotListView),



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


    def get_vehicle(self, vehicle_id):
        ''' Returns vehicle if it exists or creates a new one '''

        if vehicle_id not in self.vehicles:
            print('new vehicle')
            self.vehicles[vehicle_id] = dict({
                        'id': vehicle_id,
                        'user_angle': 0,
                        'user_throttle': 0,
                        'drive_mode':'user',
                        'milliseconds': 0,
                        'pilot': dk.pilots.BasePilot()})

        #eprint(self.vehicles)
        return self.vehicles[vehicle_id]


#####################
#                   #
#      vehicles     #
#                   #
#####################


class HomeView(tornado.web.RequestHandler):
    def get(self):
        self.render("templates/home.html")


class VehicleListView(tornado.web.RequestHandler):
    def get(self):
        '''
        Serves a list of the vehicles posting requests to the server.
        '''
        data = {'vehicles':self.application.vehicles}

        self.render("templates/vehicle_list.html", **data)


class DeviceTiltView(tornado.web.RequestHandler):
    def get(self, vehicle_id):
        '''
        Serves page for users to control the vehicle.
        '''

        V = self.application.get_vehicle(vehicle_id)
        pilots = self.application.pilots
        data = {'vehicle': V, 'pilots': pilots}
        self.render("templates/device_tilt.html", **data)


class VehicleView(tornado.web.RequestHandler):
    def get(self, vehicle_id):
        '''
        Serves page for users to control the vehicle.
        '''

        V = self.application.get_vehicle(vehicle_id)
        pilots = self.application.pilots
        data = {'vehicle': V, 'pilots': pilots}
        self.render("templates/vehicle.html", **data)



class VehicleAPI(tornado.web.RequestHandler):


    def post(self, vehicle_id):
        '''
        Currently this only changes the pilot.
        '''

        V = self.application.get_vehicle(vehicle_id)

        data = tornado.escape.json_decode(self.request.body)
        print('pilot request')
        print(data)
        pilot = next(filter(lambda p: p.name == data['pilot'], self.application.pilots))
        pilot.load()
        V['pilot'] = pilot



class DriveAPI(tornado.web.RequestHandler):

    def post(self, vehicle_id):
        '''
        Receive post requests as user changes the angle
        and throttle of the vehicle on a the index webpage
        '''

        V = self.application.get_vehicle(vehicle_id)

        data = tornado.escape.json_decode(self.request.body)
        angle = data['angle']
        throttle = data['throttle']

        #set if vehicle is recording
        if 'recording' in data:
            if data['recording']:
                if not  V['session']:
                    V['session'] = dk.sessions.SessionHandler(self.application.sessions_path).new()
            else:
                V['session'] = None

        #update vehicle angel based on drive mode
        V['drive_mode'] = data['drive_mode']

        if angle is not "":
            V['user_angle'] = angle
        else:
            V['user_angle'] = 0

        if throttle is not "":
            V['user_throttle'] = throttle
        else:
            V['user_throttle'] = 0


class ControlAPI(tornado.web.RequestHandler):

    def post(self, vehicle_id):
        '''
        Receive post requests from a vehicle and returns
        the angle and throttle the car should use. Depending on
        the drive mode the values can come from the user or
        an autopilot.
        '''

        V = self.application.get_vehicle(vehicle_id)

        img = self.request.files['img'][0]['body']
        img = Image.open(io.BytesIO(img))
        img_arr = dk.utils.img_to_arr(img)


        #Get angle/throttle from pilot loaded by the server.
        if V['pilot'] is not None:
            pilot_angle, pilot_throttle = V['pilot'].decide(img_arr)
        else:
            print('no pilot')
            pilot_angle, pilot_throttle = 0.0, 0.0

        V['img'] = img
        V['pilot_angle'] = pilot_angle
        V['pilot_throttle'] = pilot_throttle

        #depending on the drive mode, return user or pilot values

        angle, throttle  = V['user_angle'], V['user_throttle']
        if V['drive_mode'] == 'auto_angle':
            angle, throttle  = V['pilot_angle'], V['user_throttle']
        elif V['drive_mode'] == 'auto':
            angle, throttle  = V['pilot_angle'], V['pilot_throttle']

        print('\r REMOTE: angle: {:+04.2f}   throttle: {:+04.2f}   drive_mode: {}'.format(angle, throttle, V['drive_mode']), end='')


        if 'session' in V and V['session']:
            #save image with encoded angle/throttle values
            V['session'].put(img,
                             angle=angle,
                             throttle=throttle,
                             milliseconds=0.0)

        #retun angel/throttle values to vehicle with json response
        self.write(json.dumps({'angle': str(angle), 'throttle': str(throttle), 'drive_mode': str(V['drive_mode']) }))



class VideoAPI(tornado.web.RequestHandler):
    '''
    Serves a MJPEG of the images posted from the vehicle.
    '''
    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def get(self, vehicle_id):

        ioloop = tornado.ioloop.IOLoop.current()
        self.set_header("Content-type", "multipart/x-mixed-replace;boundary=--boundarydonotcross")

        self.served_image_timestamp = time.time()
        my_boundary = "--boundarydonotcross"
        while True:

            interval = .2
            if self.served_image_timestamp + interval < time.time():


                img = self.application.vehicles[vehicle_id]['img']
                img = dk.utils.img_to_binary(img)

                self.write(my_boundary)
                self.write("Content-type: image/jpeg\r\n")
                self.write("Content-length: %s\r\n\r\n" % len(img))
                self.write(img)
                self.served_image_timestamp = time.time()
                yield tornado.gen.Task(self.flush)
            else:
                yield tornado.gen.Task(ioloop.add_timeout, ioloop.time() + interval)

class SessionAPI(tornado.web.RequestHandler):

    def delete(self):
        last_session = dk.sessions.SessionHandler(self.application.sessions_path).last()
        if not last_session:
            return

        if self.get_query_argument('3s', None, True):
            last_session.delete_3s()

        if self.get_query_argument('last', None, True):
            last_session.delete()

class TagAPI(tornado.web.RequestHandler):

    def put(self, session_id, tag):
        targets = tornado.escape.json_decode(self.request.body)['targets']
        Tags(self.application.sessions_path).add_tag_to_session(session_id, tag, targets)

    def delete(self, session_id, tag):
        Tags(self.application.sessions_path).delete_tag_from_session(session_id, tag)

#####################
#                   #
#      pilots       #
#                   #
#####################


class PilotListView(tornado.web.RequestHandler):
    def get(self):
        '''
        Render a list of pilots.
        '''
        ph = dk.pilots.PilotHandler(self.application.models_path)
        pilots = ph.default_pilots()
        data = {'pilots': pilots}
        self.render("templates/pilots_list.html", **data)




#####################
#                   #
#     sessions      #
#                   #
#####################



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

#@tornado.gen.coroutine
class SessionDownload(tornado.web.RequestHandler):

    def get(self, session_id, page):
        sessions_path = self.application.sessions_path
        session_path = os.path.join(sessions_path, session_id)

        zip_path = os.path.join(sessions_path, session_id + '.zip')
        dk.utils.zip_dir(session_path, zip_path)

        self.set_header('Content-Type', 'application/force-download')
        self.set_header('Content-Disposition', 'attachment; filename=%s' % session_id+ ".zip")
        with open(zip_path, "rb") as f:
            #try:
            while True:
                _buffer = f.read(4096)
                if _buffer:
                    self.write(_buffer)
                else:
                    f.close()
                    self.finish()
                    return
            #except:
            #    raise HTTPError(404)
        raise HTTPError(500)



DonkeyPilotApplication().start()
