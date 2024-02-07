# -*- coding: utf-8 -*-
import asyncio
# import httpx
import os
import re
from datetime import datetime
from urllib.parse import urlparse
from time import sleep
import uuid
import json
import gzip

from asgiref.wsgi import WsgiToAsgi
from flask import Flask, request, jsonify, send_file, make_response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import validates

from apns import notify


try:
    url = urlparse(os.environ['DATABASE_URL'])
    DATABASE = 'postgresql://{user}:{pwd}@{host}:{port}/{db}'.format(
        user=url.username,
        pwd=url.password,
        host=url.hostname,
        port=url.port,
        db=url.path[1:])
except KeyError:
    path = os.path.abspath(os.path.dirname(__file__))
    DATABASE = 'sqlite:////{path}/dev.db'.format(path=path)


app = Flask(__name__)
ALLOWED_EXTENSIONS = {'pkpass'}
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE
app.config['UPLOAD_FOLDER'] = "./pkpass/"
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
db = SQLAlchemy(app)

asgi_app = WsgiToAsgi(app)



class Pass(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pass_type_identifier = db.Column(db.String(255), unique=False)
    serial_number = db.Column(db.String(255), unique=True)
    data = db.Column(db.PickleType)
    created_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime)

    @validates
    def validate_pass_type_identifier(self, key, ident):
        assert re.match(r'([\w\d]\.?)+', ident)
        return ident

    def __init__(self, pass_type_identifier, serial_number, data):
        self.pass_type_identifier = pass_type_identifier
        self.serial_number = serial_number
        self.data = data
        self.created_at = datetime.utcnow().replace(microsecond=0)
        self.updated_at = datetime.utcnow().replace(microsecond=0)

    def __repr__(self):
        return '<Pass %s>' % self.pass_type_identifier

    def __str__(self):
        return f'{self.pass_type_identifier} - {self.serial_number} updated at: {self.updated_at}'


class Registration(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_library_identifier = db.Column(db.String(255), unique=True)
    push_token = db.Column(db.String(255))
    created_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime)
    pass_id = db.Column(db.Integer, db.ForeignKey('pass.id'))
    p = db.relationship('Pass', backref=db.backref('registrations',
                                                   lazy='dynamic'))

    def __init__(self, device_library_identifier, push_token, p):
        self.device_library_identifier = device_library_identifier
        self.push_token = push_token
        self.p = p
        self.created_at = datetime.utcnow().replace(microsecond=0)
        self.updated_at = datetime.utcnow().replace(microsecond=0)

    def __repr__(self):
        return '<Registration %s>' % self.device_library_identifier

    def __str__(self):
        return f'Registration {self.device_library_identifier} with push token: {self.push_token} for pass {self.p}'


@app.route('/v1/passes/<pass_type_identifier>/<serial_number>', methods=['GET'])  # noqa 501
def show(pass_type_identifier, serial_number):
    """
    Getting the latest version of a Pass

    Keyword arguments:
    pass_type_identifier -- The pass’s type, as specified in the pass
    serial_number -- The unique pass identifier, as specified in the pass
    """
    p = Pass.query.filter_by(pass_type_identifier=pass_type_identifier,
                             serial_number=serial_number).first_or_404()
    if 'if-modified-since' in request.headers:
        print(f'show {p}')
        try:
            if p.updated_at <= datetime.fromisoformat(request.headers['if-modified-since']):
                p = None
        except Exception as e:
            print(f'{e}')
            pass

    if p:
        response = make_response(send_file("pkpass/"+serial_number+".pkpass",
                         mimetype='application/vnd.apple.pkpass',
                         download_name=serial_number+".pkpass"))
        # TODO
        response.headers['Last-Modified'] = p.updated_at.isoformat()
        response.headers['Last-Modified'] = datetime.utcnow().replace(microsecond=0).isoformat()
        print(str(response.headers))
        return response
    else:
        return ('No Content', 304)


@app.route('/v1/passes/<pass_type_identifier>/<serial_number>', methods=['PUT'])  # noqa 501
async def update_pass(pass_type_identifier, serial_number):
    """
    Getting the latest version of a Pass

    Keyword arguments:
    pass_type_identifier -- The pass’s type, as specified in the pass
    serial_number -- The unique pass identifier, as specified in the pass
    """
    if 'file' not in request.files:
        print('No file in request')
        return ('KO', 500)

    p = Pass.query.filter_by(pass_type_identifier=pass_type_identifier,
                             serial_number=serial_number).first()

    if p:
        print(f'PUT {p} before update')
        p.updated_at = datetime.utcnow()
    else:
        p = Pass(pass_type_identifier, serial_number, None)
        db.session.add(p)
    db.session.commit()
    p = Pass.query.filter_by(pass_type_identifier=pass_type_identifier,
                             serial_number=serial_number).first()
    print(f'PUT {p} after update')

    file = request.files['file']
    file.save(os.path.join(app.config['UPLOAD_FOLDER'],
                           serial_number + '.pkpass'))

    for r in p.registrations.all():
        print("device: %s token: %s" % (r.device_library_identifier,
                                        r.push_token))
        await notify(r.push_token)

    return ('OK', 201)


@app.route('/v1/devices/<device_library_identifier>/registrations/<pass_type_identifier>', methods=['GET'])  # noqa 501
def index(device_library_identifier, pass_type_identifier):
    """
    Getting the serial numbers for passes associated with a device

    Keyword arguments:
    device_library_identifier -- A unique identifier that is used to identify
                                 and authenticate the device
    pass_type_identifier      -- The pass’s type, as specified in the pass

    If the passes_updated_since parameter is present, return only the passes
    that have been updated since the time indicated by tag. Otherwise, return
    all passes.
    """
    print(f'{request.url}')
    print(f'index {device_library_identifier}/{pass_type_identifier}')
    rs = Registration.query.filter_by(device_library_identifier=device_library_identifier).all()
    serial_numbers = []
    if 'passesUpdatedSince' in request.args:
        for r in rs:
            print('pass updated_at: ' + str(r.p.updated_at))
            print('request date: ' + str(request.args['passesUpdatedSince']))       
#            if r.p.updated_at <= datetime.fromisoformat(request.args['passesUpdatedSince']):
            serial_numbers.append(r.p.serial_number)

    print(f'index updated: {serial_numbers}')
    if len(serial_numbers) > 0:
        return jsonify({
    #        'lastUpdated': p.updated_at.isoformat(),
            'lastUpdated': datetime.utcnow().isoformat(),
            'serialNumbers': serial_numbers
        })
    else:
        return ('', 204)


@app.route('/v1/devices/<device_library_identifier>/registrations/<pass_type_identifier>/<serial_number>',  # noqa 501
           methods=['POST'])
def register_device(device_library_identifier,
                    pass_type_identifier,
                    serial_number):
    """
    Registering a device to receive push notifications for a pass

    Keyword arguments:
    device_library_identifier -- A unique identifier that is used to identify
                                 and authenticate the device
    pass_type_identifier      -- The pass’s type, as specified in the pass
    serial_number             -- The unique pass identifier, as specified in
                                 the pass
    """

    try:
        p = Pass.query.filter_by(pass_type_identifier=pass_type_identifier,
                                 serial_number=serial_number).first()
    except:
        p = None

    try:
        r = p.registrations.filter_by(
            device_library_identifier=device_library_identifier).first()
    except:
        r = None

    if p and r:
        print(r)
        return ('', 200)  # Already exists

    if not p:
        p = Pass(pass_type_identifier, serial_number, None)
        db.session.add(p)
        db.session.commit()

    try:
        r = Registration(device_library_identifier,
                         request.json['pushToken'], p)
        print(f"New registration:  {request.json['pushToken']} for pass {p} ")
        print(r)
        db.session.add(r)
        db.session.commit()
    except Exception as e:
        print(str(e))
        return ('Internal Error', 500)

    return ('Created', 201)


@app.route('/v1/devices/<device_library_identifier>/registrations/<pass_type_identifier>/<serial_number>',  # noqa 501
           methods=['DELETE'])
def unregister_device(device_library_identifier,
                      pass_type_identifier,
                      serial_number):
    """
    Unregistering a device

    Keyword arguments:
    device_library_identifier -- A unique identifier that is used to identify
                                 and authenticate the device
    pass_type_identifier      -- The pass’s type, as specified in the pass
    serial_number             -- The unique pass identifier, as specified in
                                 the pass
    """
    try:
        p = Pass.query.filter_by(pass_type_identifier=pass_type_identifier,
                                 serial_number=serial_number).first_or_404()
        registrations = p.registrations.filter_by(
            device_library_identifier=device_library_identifier).first_or_404()

        db.session.delete(registrations)
        db.session.commit()
    except Exception as e:
        print(str(e))

    return ('OK', 200)


@app.route('/v1/log', methods=['POST'])
def log():
    print(request.data)
    return ('OK', 200)


#@app.teardown_appcontext
#def close_connection(exception):
#    with app.app_context():
#        db.close()
#
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=port)
