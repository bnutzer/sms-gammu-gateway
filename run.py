import os

from flask import Flask, request, current_app
from flask_httpauth import HTTPBasicAuth
from flask_restful import reqparse, Api, Resource, abort

from support import load_user_data, init_state_machine, retrieveAllSms, deleteSms, encodeSms
from gammu import GSMNetworks

import argparse
import logging
from pprint import pformat

pin = os.getenv('PIN', None)
ssl = os.getenv('SSL', False)
port = os.getenv('PORT', '5000')
host = os.getenv('BINDHOST', '0.0.0.0')
user_data = load_user_data()
machine = init_state_machine(pin)
app = Flask(__name__)
api = Api(app)
auth = HTTPBasicAuth()

@auth.verify_password
def verify(username, password):
    if not (username and password):
        return False
    return user_data.get(username) == password


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
            result = [machine.SendSMS(message) for message in messages]

        app.logger.debug('Done -- %s', str(result))

        return {"status": 200, "message": str(result)}, 200


class Signal(Resource):
    def __init__(self, sm):
        self.machine = sm

    def get(self):
        return machine.GetSignalQuality()


class Reset(Resource):
    def __init__(self, sm):
        self.machine = sm

    def get(self):
        machine.Reset(False)
        return {"status":200, "message": "Reset done"}, 200


class Network(Resource):
    def __init__(self, sm):
        self.machine = sm

    def get(self):
        network = machine.GetNetworkInfo()
        network["NetworkName"] = GSMNetworks.get(network["NetworkCode"], 'Unknown')
        return network


class GetSms(Resource):
    def __init__(self, sm):
        self.machine = sm

    @auth.login_required
    def get(self):
        allSms = retrieveAllSms(machine)
        sms = {"Date": "", "Number": "", "State": "", "Text": "", "NewSms": False}
        if len(allSms) > 0:
            sms = allSms[0]
            sms['NewSms'] = True

            app.logger.debug('Received message: %s', pformat(sms))

            if current_app.config["DRY_RUN"]:
                app.logger.info("Dry run, will not delete message")
            else:
                deleteSms(machine, sms)

            sms.pop("Locations")

        return sms

class SmsById(Resource):
    def __init__(self, sm):
        self.machine = sm

    @auth.login_required
    def get(self, id):
        allSms = retrieveAllSms(machine)
        self.abort_if_id_doesnt_exist(id, allSms)
        sms = allSms[id]
        app.logger.debug('Received message %s: %s', id, pformat(sms))
        sms.pop("Locations")
        return sms

    def delete(self, id):
        allSms = retrieveAllSms(machine)
        self.abort_if_id_doesnt_exist(id, allSms)

        if current_app.config["DRY_RUN"]:
            app.logger.info("Dry run, will not actually delete message %s", id)
        else:
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

if __name__ == '__main__':

    args = parse_args()
    configure_logging(args)
    app.config["DRY_RUN"] = args.dry

    if ssl:
        app.run(port=port, host=host, ssl_context=('/ssl/cert.pem', '/ssl/key.pem'))
    else:
        app.run(port=port, host=host)
