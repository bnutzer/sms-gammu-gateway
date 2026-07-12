import json
import logging
import os
import re
import sys
from datetime import datetime

import gammu

DEFAULT_CREDENTIALS = ('admin', 'password')


def load_user_data(filename='credentials.txt'):
    """Collect basic-auth credentials from an optional file and env vars.

    Credentials may come from a ``credentials.txt`` file (one ``user:password``
    per line, optional) and/or the ``AUTH_USERNAME``/``AUTH_PASSWORD`` env vars,
    which take precedence. The process refuses to start without credentials or
    with the shipped default, so an unconfigured gateway is never reachable.
    """
    users = {}

    if os.path.exists(filename):
        with open(filename) as credentials:
            for line in credentials:
                if ':' not in line:
                    continue
                username, password = line.partition(":")[::2]
                users[username.strip()] = password.strip()

    env_user = os.getenv('AUTH_USERNAME')
    env_pass = os.getenv('AUTH_PASSWORD')
    if env_user and env_pass:
        users[env_user] = env_pass

    if not users:
        print("No credentials configured. Set AUTH_USERNAME/AUTH_PASSWORD "
              "or mount a credentials.txt file.", file=sys.stderr)
        sys.exit(1)

    default_user, default_pass = DEFAULT_CREDENTIALS
    if users.get(default_user) == default_pass:
        print("Refusing to start with the default credentials "
              "(admin:password). Please configure your own.", file=sys.stderr)
        sys.exit(1)

    return users


def init_state_machine(pin, filename='gammu.config'):
    sm = gammu.StateMachine()
    sm.ReadConfig(Filename=filename)
    sm.Init()

    if sm.GetSecurityStatus() == 'PIN':
        if pin is None or pin == '':
            print("PIN is required.")
            sys.exit(1)
        else:
            sm.EnterSecurityCode('PIN', pin)
    return sm


def retrieveAllSms(machine):
    status = machine.GetSMSStatus()
    allMultiPartSmsCount = status['SIMUsed'] + status['PhoneUsed'] + status['TemplatesUsed']

    allMultiPartSms = []
    start = True

    while len(allMultiPartSms) < allMultiPartSmsCount:
        if start:
            currentMultiPartSms = machine.GetNextSMS(Start = True, Folder = 0)
            start = False
        else:
            currentMultiPartSms = machine.GetNextSMS(Location = currentMultiPartSms[0]['Location'], Folder = 0)
        allMultiPartSms.append(currentMultiPartSms)

    allSms = gammu.LinkSMS(allMultiPartSms)

    results = []
    for sms in allSms:
        smsPart = sms[0]

        result = {
            "Date": str(smsPart['DateTime']),
            "Number": smsPart['Number'],
            "State": smsPart['State'],
            "Locations": [smsPart['Location'] for smsPart in sms],
        }

        decodedSms = gammu.DecodeSMS(sms)
        if decodedSms == None:
            result["Text"] = smsPart['Text']
        else:
            text = ""
            for entry in decodedSms['Entries']:
                if entry['Buffer'] != None:
                    text += entry['Buffer']

            result["Text"] = text

        results.append(result)

    return results


def deleteSms(machine, sms):
    list(map(lambda location: machine.DeleteSMS(Folder=0, Location=location), sms["Locations"]))


def encodeSms(smsinfo):
    return gammu.EncodeSMS(smsinfo)


def archive_sms(archive_path, direction, sms):
    """Persist a single SMS to the archive, if archiving is enabled.

    ``archive_path`` is the ``ARCHIVE_PATH`` env value (``None``/empty disables
    archiving entirely). ``direction`` is ``"inbox"`` or ``"outbox"`` and names
    the subfolder. ``sms`` is a dict from which a known set of fields is stored.

    Archiving is best effort: any failure (unwritable path, full disk) is logged
    as a warning and swallowed, so the archive never blocks sending or receiving.
    """
    if not archive_path:
        return

    try:
        folder = os.path.join(archive_path, direction)
        os.makedirs(folder, exist_ok=True)

        now = datetime.now()
        number = sms.get("Number") or "unknown"
        # Keep the number readable in the filename but strip anything that is
        # awkward in a path; microseconds keep concurrent writes from colliding.
        safe_number = re.sub(r"[^0-9A-Za-z+]", "_", str(number))
        filename = "{}-{}.json".format(now.strftime("%Y%m%d-%H%M%S-%f"), safe_number)

        record = {
            "Direction": direction,
            "ArchivedAt": now.isoformat(),
            "Number": sms.get("Number"),
            "Text": sms.get("Text"),
            "Date": sms.get("Date"),
            "State": sms.get("State"),
            "SMSC": sms.get("SMSC"),
        }
        record = {key: value for key, value in record.items() if value is not None}

        path = os.path.join(folder, filename)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False, indent=2)

        logging.getLogger("archive").debug("Archived %s SMS to %s", direction, path)
    except Exception as exc:
        logging.getLogger("archive").warning(
            "Failed to archive %s SMS: %s", direction, exc
        )
