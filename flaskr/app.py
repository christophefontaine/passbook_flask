# -*- coding: utf-8 -*-
import asyncio
import httpx
import os
import re
from datetime import datetime
from urllib.parse import urlparse
from time import sleep

from flask import Flask, request, jsonify, send_file, make_response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import validates


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
    response = make_response(send_file("pkpass/"+serial_number+".pkpass",
                     mimetype='application/vnd.apple.pkpass',
                     download_name=serial_number+".pkpass"))
    print(str(response.headers))
    # Need to send since unix epoch in seconds
    response.headers['Last-Modified'] = p.updated_at.strftime('%a, %d %b %Y %H:%M:%S %Z')
#    response.headers['Last-Modified'] = int(p.updated_at.timestamp())
    return response


async def push(pushToken, retry=3):
    ENDPOINT = "api.push.apple.com:443"
    ENDPOINT = "api.push.apple.com:2197"
    cert = ("wallet.certificate.der", "wallet.private.key")
    with httpx.Client(http2=True, cert=cert) as client:
#                        data={'aps': {'apns-priority': 10, 'apns-push-type': 'alert' }},
        r = client.post("https://" + ENDPOINT + "/3/device/" + pushToken,
                        data={'aps': {}},
                        headers={'Content-Type': 'application/json'})

    if r.status_code != 200 and retry > 0:
        sleep(1)
        r = await push(pushToken, retry-1)
    print(r)
    return r


@app.route('/v1/passes/<pass_type_identifier>/<serial_number>', methods=['PUT'])  # noqa 501
async def update_pass(pass_type_identifier, serial_number):
    """
    Getting the latest version of a Pass

    Keyword arguments:
    pass_type_identifier -- The pass’s type, as specified in the pass
    serial_number -- The unique pass identifier, as specified in the pass
    """
    p = Pass.query.filter_by(pass_type_identifier=pass_type_identifier,
                             serial_number=serial_number).first()

    if not p:
        p = Pass(pass_type_identifier, serial_number, None)
        db.session.add(p)
        db.session.commit()

    for r in p.registrations.all():
        print("device: %s token: %s" % (r.device_library_identifier,
                                        r.push_token))
        asyncio.create_task(push(r.push_token))
        # await push(r.push_token)

    if 'file' not in request.files:
        print('No file in request')
        return ('KO', 500)

    file = request.files['file']
    file.save(os.path.join(app.config['UPLOAD_FOLDER'],
                           serial_number + '.pkpass'))

    p.updated_at = datetime.utcnow().replace(microsecond=0)
    db.session.commit()
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
    p = Pass.query.filter_by(
            pass_type_identifier=pass_type_identifier).first_or_404()

    r = p.registrations.filter_by(
            device_library_identifier=device_library_identifier)
    if 'passesUpdatedSince' in request.args:
        print('passesUpdatedSince')
        print('pass updated_at: ' + str(p.updated_at))
        print('request date: ' + str(request.args['passesUpdatedSince']))

        r = r.filter(Registration.updated_at >
                     datetime.strptime(request.args['passesUpdatedSince'],
                                       '%a, %d %b %Y %H:%M:%S %Z'))

    if r:
        return jsonify({
            'lastUpdated': p.updated_at,
            'serialNumbers': [p.serial_number]
        })
    else:
        return ('No Content', 204)


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
        return ('', 200)  # Already exists

    if not p:
        p = Pass(pass_type_identifier, serial_number, None)
        db.session.add(p)

    try:
        r = Registration(device_library_identifier,
                         request.json['pushToken'], p)
        print(r)
        db.session.add(r)
        db.session.commit()
    except Exception as e:
        print(str(e))

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
