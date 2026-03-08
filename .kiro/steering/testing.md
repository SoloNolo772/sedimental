We are developing and testing inside the running docker container for this project, not locally. When running tests, please run docker compose build to refresh the container's code and then run the docker compose run command that will use the desired test file. 
For example, if we just built a test file called test_logging.py, the next two commands that we would run are: 
* docker compose build
* docker compose run --rm sedimental test tests/test_logging.py -v
