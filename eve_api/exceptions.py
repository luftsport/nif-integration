# -*- coding: utf-8 -*-


class EveException(Exception):

    """ Exception thrown when eve return an error """

    def __init__(self, message, errors=[]):

        super(Exception, self).__init__(message)
        self.errors = errors


class NotfoundException(EveException):
    pass


class UnauthorizedException(EveException):
    pass


class BadRequestException(EveException):
    pass


def _handle_400(response, json):
    raise BadRequestException(json.get("_error", {}).get("message", "Bad Request"))


def _handle_404(response, json):
    raise NotfoundException(json.get("_error", {}).get("message", "Notfound"))


def _handle_401(response, json):
    raise UnauthorizedException(json.get("_error", {}).get("message", "Unauthorized"))


def exception_handler(response, json):

    """ Handle Eve response exceptions """

    errors = {
        400: _handle_400,
        401: _handle_401,
        404: _handle_404,
    }
    if response.status_code in errors:
        errors[response.status_code](response, json)
