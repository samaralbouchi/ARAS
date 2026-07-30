# Empty on purpose.
#
# Its only job is to mark this directory as the pytest "rootdir".
# That makes pytest insert this directory into sys.path, so
#   from models.report_models import ...
#   from agents.report_generator_agent import ...
# resolve correctly regardless of where `pytest` is invoked from.