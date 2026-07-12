import os

from flask import Flask, request, current_app
from flask_httpauth import HTTPBasicAuth
from flask_restful import reqparse, Api, Resource, abort

from support import load_user_data, init_state_machine, retrieveAllSms, deleteSms, encodeSms, archive_sms
from gammu import GSMNetworks

import argparse
import logging
import threading
from hmac import compare_digest
from pprint import pformat

pin = os.getenv('PIN', None)
# A non-empty ARCHIVE_PATH both enables archiving and names the target
# directory; an unset/empty value disables it. No separate on/off toggle.
archive_path = os.getenv('ARCHIVE_PATH') or None
ssl = os.getenv('SSL', '').lower() in ('1', 'true', 'yes', 'on')
port = os.getenv('PORT', '5000')
host = os.getenv('BINDHOST', '0.0.0.0')
user_data = load_user_data()
machine = init_state_machine(pin)
# The modem is a single serial device and python-gammu's StateMachine is not
# thread-safe. Serialize every modem interaction through this lock so the app
# stays correct under a multi-threaded WSGI server (e.g. waitress).
machine_lock = threading.Lock()
app = Flask(__name__)
# Set on the module level so the endpoints keep working when the app is served
# via a WSGI server (gunicorn etc.) instead of the __main__ block below.
app.config.setdefault("DRY_RUN", False)
api = Api(app)
auth = HTTPBasicAuth()

@auth.verify_password
def verify(username, password):
    if not (username and password):
        return False
    stored = user_data.get(username)
    if stored is None:
        return False
    return compare_digest(stored, password)


class Sms(Resource):
    def __init__(self, sm):
        self.parser = reqparse.RequestParser()
        self.parser.add_argument('text')
        self.parser.add_argument('number')
        self.parser.add_argument('smsc')
        self.parser.add_argument('unicode')
        self.machine = sm

    @auth.login_required
    def get(self):
        with machine_lock:
            allSms = retrieveAllSms(machine)
        list(map(lambda sms: sms.pop("Locations"), allSms))
        return allSms

    @auth.login_required
    def post(self):
        args = self.parser.parse_args()
        if args['text'] is None or args['number'] is None:
            abort(404, message="Parameters 'text' and 'number' are required.")
        smsinfo = {
            "Class": -1,
            "Unicode": args.get('unicode') if args.get('unicode') else False,
            "Entries": [
                {
                    "ID": "ConcatenatedTextLong",
                    "Buffer": args['text'],
                }
            ],
        }
        messages = []
        for number in args.get("number").split(','):
            for message in encodeSms(smsinfo):
                message["SMSC"] = {'Number': args.get("smsc")} if args.get("smsc") else {'Location': 1}
                message["Number"] = number
                messages.append(message)

        app.logger.debug('Sending message(s): %s', pformat(messages))

        if current_app.config["DRY_RUN"]:
            app.logger.info("Dry run, will not actually send message.")
            result = "[OK]"
        else:
            with machine_lock:
                result = [machine.SendSMS(message) for message in messages]
            for number in args.get("number").split(','):
                archive_sms(archive_path, "outbox", {
                    "Number": number,
                    "Text": args['text'],
                    "SMSC": args.get("smsc"),
                })

        app.logger.debug('Done -- %s', str(result))

        return {"status": 200, "message": str(result)}, 200


class Signal(Resource):
    def __init__(self, sm):
        self.machine = sm

    def get(self):
        with machine_lock:
            return machine.GetSignalQuality()


class Reset(Resource):
    def __init__(self, sm):
        self.machine = sm

    @auth.login_required
    def get(self):
        with machine_lock:
            machine.Reset(False)
        return {"status":200, "message": "Reset done"}, 200


class Network(Resource):
    def __init__(self, sm):
        self.machine = sm

    def get(self):
        with machine_lock:
            network = machine.GetNetworkInfo()
        network["NetworkName"] = GSMNetworks.get(network["NetworkCode"], 'Unknown')
        return network


class GetSms(Resource):
    def __init__(self, sm):
        self.machine = sm

    @auth.login_required
    def get(self):
        with machine_lock:
            allSms = retrieveAllSms(machine)
            sms = {"Date": "", "Number": "", "State": "", "Text": "", "NewSms": False}
            if len(allSms) > 0:
                sms = allSms[0]
                sms['NewSms'] = True

                app.logger.debug('Received message: %s', pformat(sms))

                if current_app.config["DRY_RUN"]:
                    app.logger.info("Dry run, will not delete message")
                else:
                    archive_sms(archive_path, "inbox", sms)
                    deleteSms(machine, sms)

                sms.pop("Locations")

        return sms

class SmsById(Resource):
    def __init__(self, sm):
        self.machine = sm

    @auth.login_required
    def get(self, id):
        with machine_lock:
            allSms = retrieveAllSms(machine)
        self.abort_if_id_doesnt_exist(id, allSms)
        sms = allSms[id]
        app.logger.debug('Received message %s: %s', id, pformat(sms))
        sms.pop("Locations")
        return sms

    @auth.login_required
    def delete(self, id):
        with machine_lock:
            allSms = retrieveAllSms(machine)
            self.abort_if_id_doesnt_exist(id, allSms)

            if current_app.config["DRY_RUN"]:
                app.logger.info("Dry run, will not actually delete message %s", id)
            else:
                archive_sms(archive_path, "inbox", allSms[id])
                deleteSms(machine, allSms[id])

        return '', 204

    def abort_if_id_doesnt_exist(self, id, allSms):
        if id < 0 or id >= len(allSms):
            abort(404, message = "Sms with id '{}' not found".format(id))

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry", action="store_true", help="Do not actually send sms")
    parser.add_argument("--verbose", "-v", action="store_true", help="Log sent and received sms")
    parser.add_argument("--silent", "-s", action="store_true", help="Suppress logs")
    return parser.parse_args()

def configure_logging(args):
    if args.silent:
        level = logging.ERROR
    elif args.verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

api.add_resource(Sms, '/sms', resource_class_args=[machine])
api.add_resource(SmsById, '/sms/<int:id>', resource_class_args=[machine])
api.add_resource(Signal, '/signal', resource_class_args=[machine])
api.add_resource(Network, '/network', resource_class_args=[machine])
api.add_resource(GetSms, '/getsms', resource_class_args=[machine])
api.add_resource(Reset, '/reset', resource_class_args=[machine])

class AccessLogMiddleware:
    """Emit one access-log line per request.

    Werkzeug's development server logs every request out of the box; waitress
    does not. This middleware restores that behaviour through the configured
    logging setup, so it honours the --verbose/--silent flags. The logged
    client is REMOTE_ADDR, matching Werkzeug; behind a reverse proxy that is
    the proxy's address (waitress strips X-Forwarded-For by default unless a
    trusted_proxy is configured).
    """

    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app
        self.logger = logging.getLogger("access")

    def __call__(self, environ, start_response):
        def log_start_response(status, headers, *args):
            client = environ.get("REMOTE_ADDR", "-")
            path = environ.get("PATH_INFO", "")
            query = environ.get("QUERY_STRING", "")
            if query:
                path = "%s?%s" % (path, query)
            self.logger.info(
                '%s "%s %s" %s',
                client,
                environ.get("REQUEST_METHOD", "-"),
                path,
                status.split(" ", 1)[0],
            )
            return start_response(status, headers, *args)

        return self.wsgi_app(environ, log_start_response)


if __name__ == '__main__':

    args = parse_args()
    configure_logging(args)
    app.config["DRY_RUN"] = args.dry

    if ssl:
        # waitress cannot terminate TLS, so fall back to Werkzeug's built-in
        # server for the (discouraged) direct-TLS setup. For production, put a
        # reverse proxy in front and leave SSL disabled here.
        app.run(port=port, host=host, ssl_context=('/ssl/cert.pem', '/ssl/key.pem'))
    else:
        # waitress has no built-in access log, so wrap the app to restore it.
        from waitress import serve
        serve(AccessLogMiddleware(app), host=host, port=int(port))
