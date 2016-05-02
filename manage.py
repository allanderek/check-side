import os
import subprocess
import errno

import flask
from flask.ext.migrate import Migrate, MigrateCommand
from flask.ext.script import Manager
import requests

from app import main
from app.main import application, database

manager = Manager(application)

Migrate(application, database)
manager.add_command('db', MigrateCommand)

@manager.command
def remake_db(really=False):
    if not really:
        print("You should probably use 'python manage.py db upgrade' instead.")
        print("If you really want to use remake_db, provide option --really.")
        print("")
        print("(See https://flask-migrate.readthedocs.org/en/latest/ for"
              " details.)")
        return 0
    else:
        database.drop_all()
        database.create_all()

def run_command(command):
    """ We frequently inspect the return result of a command so this is just
        a utility function to do this. Generally we call this as:
        return run_command ('command_name args')
    """
    result = os.system(command)
    return 0 if result == 0 else 1


def coverage_command(command_args, coverage, accumulate):
    """The `accumulate` argument specifies whether we should add to the existing
    coverage data or wipe that and start afresh. Generally you wish to
    accumulate if you need to run multiple commands and you want the coverage
    analysis relevant to all those commands. So, for the commands we specify
    below this is usually off by default, since if you are running coverage on
    a particular test command then presumably you only wish to know about that
    command. However, for the main 'test' command, we want to accumulte the
    coverage results for both the casper and unit tests, hence in our 'test'
    command below we supply 'accumulate=True' for the sub-commands test_casper
    and run_unittests.
    """

    # No need to specify the sources, this is done in the .coveragerc file.
    if coverage:
        command = ["coverage", "run"]
        if accumulate:
            command.append("-a")
        return command + command_args
    else:
        return ['python'] + command_args

def run_with_test_server(test_command, coverage, accumulate):
    """Run the test server and the given test command in parallel. If 'coverage'
    is True, then we run the server under coverage analysis and produce a
    coverge report.
    """
    server_command_args = ["manage.py", "run_test_server"]
    server_command = coverage_command(server_command_args, coverage, accumulate)
    server = subprocess.Popen(server_command, stderr=subprocess.PIPE)
    # TODO: If we don't get this line we should  be able to detect that
    # and avoid the starting test process.
    for line in server.stderr:
        if b' * Running on' in line:
            break
    test_process = subprocess.Popen(test_command)
    test_return_code = test_process.wait(timeout=90)
    # Once the test process has completed we can shutdown the server. To do so
    # we have to make a request so that the server process can shut down
    # cleanly, and in particular finalise coverage analysis.
    # We could check the return from this is success.
    port = application.config['TEST_SERVER_PORT']
    requests.post('http://localhost:{}/shutdown'.format(port))
    try:
        server_return_code = server.wait(timeout=90)
    except subprocess.TimeoutExpired:
        server.kill()
        server_return_code = errno.ETIME
    if coverage:
        os.system("coverage report -m")
        os.system("coverage html")
    return test_return_code + server_return_code


def shutdown():
    """Shutdown the Werkzeug dev server, if we're using it.
    From http://flask.pocoo.org/snippets/67/"""
    func = flask.request.environ.get('werkzeug.server.shutdown')
    if func is None:  # pragma: no cover
        raise RuntimeError('Not running with the Werkzeug Server')
    func()
    return 'Server shutting down...'


@manager.command
def run_test_server():
    """Used by the phantomjs tests to run a live testing server"""
    # running the server in debug mode during testing fails for some reason
    application.config['DEBUG'] = False
    application.config['TESTING'] = True
    port = application.config['TEST_SERVER_PORT']
    # Don't use the production database but a temporary test database.
    application.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///test.db"
    database.drop_all()
    database.create_all()
    database.session.commit()

    # Add a route that allows the test code to shutdown the server, this allows
    # us to quit the server without killing the process thus enabling coverage
    # to work.
    application.add_url_rule('/shutdown', 'shutdown', shutdown,
                             methods=['POST', 'GET'])

    application.run(port=port, use_reloader=False, threaded=True)

    database.session.remove()
    database.drop_all()


@manager.command
def test_pytest(name=None, coverage=False, accumulate=True, output_capture='fd'):
    """Unlike in casper we run coverage on this command as well, however we need
    to accumulate if we want this to work at all, because we need to
    accumulate the coverage results of the server process as well as the
    pytest process itself. We do this because we want to make sure that the
    tests themselves don't contain dead code. So it almost never makes sense
    to run `test_pytest` with `coverage=True` but `accumulate=False`.
    The 'output_capture' argument is just passed through to pytest, it should be
    one of fd|sys|no, default is 'fd', this will show you the print statements
    only from the tests that fail, but if you need to see some debugging print
    statement set it to 'no'. In general I would like a way for this command to
    simply pass any unknown arguments through to pytest.
    """
    test_file = 'app/main.py'
    command = ['-m', 'pytest', '--capture={}'.format(output_capture), test_file]
    pytest_command = coverage_command(command, coverage, accumulate)
    if name is not None:
        pytest_command.append('--k={}'.format(name))
    return run_with_test_server(pytest_command, coverage, accumulate)


@manager.command
def test(nocoverage=False, coverage_erase=True):
    """ Run both the casperJS and all the unittests. We do not bother to run
    the capser tests if the unittests fail. By default this will erase any
    coverage-data accrued so far, you can avoid this, and thus get the results
    for multiple runs by passing `--coverage_erase=False`"""
    if coverage_erase:
        os.system('coverage erase')
    coverage = not nocoverage
    test_categories = [ ('Pytest', test_pytest)]
    for name, test_fun in test_categories:
        test_result = test_fun(coverage=coverage, accumulate=True)
        if test_result:
            print("{} test failure!".format(name))
            return test_result
    print('All tests passed!')
    return 0


@manager.command
def cloud9():
    """When you run this command you should be able to view the running web app
    either by "Preview->Preview Running Application", or by visiting:
    `<workspace>-<username>.c9users.io/` which you can get to by doing the above
    preview and then clicking to pop-out to a new window."""
    print('You should be able to view the running app by visiting:')
    print('http://check-side-<username>.c9users.io/')
    return run_command('python manage.py runserver -h 0.0.0.0 -p 8080')


if __name__ == "__main__":
    manager.run()
