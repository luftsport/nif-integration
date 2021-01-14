from decorators import async
from zeep import Client
from settings import NOTIFICATIONS
import smtplib
import email.message

@async
def _send_async_sms(mobile, message, client):
    # print client
    result = client.service.Send(username=NOTIFICATIONS['sms']['username'],
                                 password=NOTIFICATIONS['sms']['password'],
                                 sender="NIF Integration",
                                 destination=mobile,
                                 pricegroup=0,
                                 contentTypeID=1,
                                 contentHeader="",
                                 content=message,
                                 dlrUrl=NOTIFICATIONS['sms']['wsdl_url'],
                                 ageLimit=0,
                                 extID="",
                                 sendDate="",
                                 refID="",
                                 priority=0,
                                 gwID=0,
                                 pid=0,
                                 dcs=0)
    ##
    # (SendResult){
    # MessageID = "703cd4f8-b2f7-4396-853c-60b98388a8d0"
    # ErrorNumber = 0
    # Success = True
    # }
    # print(result.Success)
    return


def send_sms(message):
    """ Loops through and fixes everything about phone numbers etc
    @todo: verify mobile number - norwegian ONLY
    @todo: verify message length, we do not allow...
    """
    client = Client(NOTIFICATIONS['sms']['wsdl_url'])
    client.set_options(port='ContentSoap')

    for mobile in NOTIFICATIONS['sms']['recepients']:
        _send_async_sms(mobile, message, client)

@async
def _send_email_async(recepient, subject, message, priority='2'):

    msg = email.message.Message()
    msg['From'] = 'notifications@nlf.no'
    msg['To'] = recepient
    msg['Subject'] = "[NIF Integration] {}".format(subject)
    msg.add_header('Content-Type', 'text')
    msg.set_payload(message)

    msg['X-Priority'] = priority

    s = smtplib.SMTP(NOTIFICATIONS['email']['smtp'], NOTIFICATIONS['email']['smtp_port'])
    s.ehlo()
    s.starttls()
    s.ehlo()

    # s.login(NOTIFICATIONS['email']['username'], NOTIFICATIONS['email']['password'])

    # s.send_message(message)
    s.sendmail(msg['From'], [msg['To']], msg.as_string())
    s.quit()

def send_email(subject='Feilvarsling', message='En ukjent feil oppstod i synk eller stream'):
    try:
        for recepient in NOTIFICATIONS['email']['recepients']:
            _send_email_async(recepient, subject, message)

    except Exception as e:
        pass