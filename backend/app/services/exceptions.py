class ServiceError(Exception): pass
class ConflictError(ServiceError): pass
class NotFoundError(ServiceError): pass
class BusinessRuleError(ServiceError): pass
class AuthenticationError(ServiceError): pass
class InactiveUserError(AuthenticationError): pass
