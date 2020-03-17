

"""
.. topic::
    Configuration of membership api.
"""

API_KEY = ''
API_URL = ''

API_HEADERS = {
    'Authorization': 'Basic {}'.format(API_KEY),
    'Accept': 'application/json',
    'Content-Type': 'application/json',
    'Accept-Encoding': 'gzip, deflate, br'
}

"""
.. topic::
    Pyro RPC settings
"""

#: Testing testing
RPC_SERVICE_NAME = 'integration.service'
RPC_SERVICE_HOST = 'localhost'
RPC_SERVICE_PORT = 5555
"""Set the desired port for the Pyro RPC service"""

"""
.. topic::
    NIF synchronization intervals
"""

NIF_POPULATE_INTERVAL = 30  # Days
NIF_SYNC_INTERVAL = 10  # Minutes
NIF_LICENSE_SYNC_INTERVAL = 10  # Minutes
NIF_COMPETENCE_SYNC_INTERVAL = 10  # Minutes

"""
.. topic::
    NIF soap api configuration
"""

# @TODO: Remove
ACLUBU = ''
ACLUBP = ''

#: NIF PLATFORM USER ()
#: Application ID
# FunctionID
#: Brukernavn
NIF_PLATFORM_USER = ''
NIF_PLATFORM_APP_ID = ''
NIF_PLATFORM_FUNCTION_ID = ''
NIF_PLATFORM_USERNAME = '{0}/{1}/{2}'.format(NIF_PLATFORM_APP_ID, NIF_PLATFORM_FUNCTION_ID, NIF_PLATFORM_USER)
NIF_PLATFORM_PASSWORD = ''

# NIF Federation user ()
NIF_FEDERATION_APP_ID = ''
NIF_FEDERATION_FUNCTION_ID = ''
NIF_FEDERATION_USERNAME = '{0}/{1}/'.format(NIF_FEDERATION_APP_ID, NIF_FEDERATION_FUNCTION_ID)
NIF_FEDERATION_PASSWORD = ''

# NIF CLUB INTEGRATION USERS
# First name 	Prefiks
# Lastname 	    Fast
# User name 	Prefiks
NIF_CLUB_APP_ID = ''
NIF_CLUB_FIRSTNAME_PREFIX = 'NLF{}'.format(NIF_CLUB_APP_ID)
NIF_CLUB_LASTNAME = 'NIF.Connect'
NIF_CLUB_USERNAME_PREFIX = 'IGNLF{}'.format(NIF_CLUB_APP_ID)

# Hardcoded
NIF_INTEGRATION_FUNCTION_TYPE_ID = ''

# NIF url's
NIF_BASE_URL = 'https://nswebdst.nif.no/v4ws'
NIF_SYNC_URL = '{}/SynchronizationService.svc?wsdl'.format(NIF_BASE_URL)
NIF_INTEGRATION_URL = '{}/IntegrationService.svc?wsdl'.format(NIF_BASE_URL)
NIF_INTEGRATION_COMPETENCE_URL = '{}/Competence2Service.svc?wsdl'.format(NIF_BASE_URL)

"""
.. topic::
    Zeep client exceptions.
    
"""

ZEEP_EXCEPTIONS = ['Error', 'Fault', 'IncompleteMessage', 'IncompleteOperation', 'LookupError', 'NamespaceError',
                   'SignatureVerificationFailed', 'TransportError', 'UnexpectedElementError', 'ValidationError',
                   'WsdlSyntaxError', 'XMLParseError', 'XMLSyntaxError', 'ZeepWarning']

"""
.. topic::
    Stream
"""
STREAM_RESUME_TOKEN_FILE = 'resume.token'
