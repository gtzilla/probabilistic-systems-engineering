class ProjectionError(Exception):
    pass

class FailedPolicy(ProjectionError):
    pass

class FailedOperational(ProjectionError):
    pass

class FailedRepresentation(ProjectionError):
    pass
