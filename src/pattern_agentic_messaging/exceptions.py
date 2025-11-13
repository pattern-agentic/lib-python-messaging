class PAMessagingError(Exception):
    pass

class ConnectionError(PAMessagingError):
    pass

class TimeoutError(PAMessagingError):
    pass

class AuthenticationError(PAMessagingError):
    pass

class SerializationError(PAMessagingError):
    pass

class SessionClosedError(PAMessagingError):
    pass
