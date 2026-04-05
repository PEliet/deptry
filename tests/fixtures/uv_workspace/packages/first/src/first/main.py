import first  # import from itself - should not be flagged
import requests  # declared dependency
import second  # workspace member - should not be flagged
import white  # not declared - should be flagged as DEP001
