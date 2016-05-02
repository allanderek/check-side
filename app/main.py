""" A template for a Flask application.
"""

import requests
import datetime
import flask
from flask.ext.sqlalchemy import SQLAlchemy
from sqlalchemy.exc import SQLAlchemyError
import flask_wtf
import wtforms

import threading


def async(f):
    def wrapper(*args, **kwargs):
        thr = threading.Thread(target=f, args=args, kwargs=kwargs)
        thr.start()
    return wrapper


import os
basedir = os.path.abspath(os.path.dirname(__file__))


class Configuration(object):
    SECRET_KEY = b'7a\xe1f\x17\xc9C\xcb*\x85\xc1\x95G\x97\x03\xa3D\xd3F\xcf\x03\xf3\x99>'  # noqa
    LIVE_SERVER_PORT = 5000
    TEST_SERVER_PORT = 5000
    database_file = os.path.join(basedir, 'db.sqlite')
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + database_file
    DOMAIN = os.environ.get('FLASK_DOMAIN', 'localhost')
    MAILGUN_SANDBOX = os.environ.get('MAILGUN_SANDBOX')
    MAILGUN_API_KEY = os.environ.get('MAILGUN_API_KEY')

    admins_string = os.environ.get('FLASK_ADMINS', 'allan.clark@gmail.com')
    FLASK_ADMINS =  admins_string.split(',')

application = flask.Flask(__name__)
application.config.from_object(Configuration)

database = SQLAlchemy(application)

@application.template_test('plural')
def is_plural(container):
    return len(container) > 1


@application.template_filter('flash_bootstrap_category')
def flash_bootstrap_category(flash_category):
    return {'success': 'success',
            'info': 'info',
            'warning': 'warning',
            'error': 'danger',
            'danger': 'danger'}.get(flash_category, 'info')


def redirect_url(default='frontpage'):
    """ A simple helper function to redirect the user back to where they came.

        See: http://flask.pocoo.org/docs/0.10/reqcontext/ and also here:
        http://stackoverflow.com/questions/14277067/redirect-back-in-flask
    """

    return (flask.request.args.get('next') or flask.request.referrer or
            flask.url_for(default))


def render_template(*args, **kwargs):
    """ A simple wrapper, the base template requires some arguments such as
    the feedback form. This means that this argument will be in all calls to
    `flask.render_template` so we may as well factor it out."""
    return flask.render_template(*args, feedback_form=FeedbackForm(), **kwargs)


@application.route("/")
def frontpage():
    return render_template('frontpage.html')


@async
def send_email_message_mailgun(email):
    sandbox = application.config['MAILGUN_SANDBOX']
    url = "https://api.mailgun.net/v3/{0}/messages".format(sandbox)
    sender_address = "mailgun@{0}".format(sandbox)
    if email.sender_name is not None:
        sender = "{0} <{1}>".format(email.sender_name, sender_address)
    else:
        sender = sender_address
    api_key = application.config['MAILGUN_API_KEY']
    return requests.post(url,
                         auth=("api", api_key),
                         data={"from": sender,
                               "to": email.recipients,
                               "subject": email.subject,
                               "text": email.body})


class Email(object):
    """ Simple representation of an email message to be sent."""

    def __init__(self, subject, body, sender_name, recipients):
        self.subject = subject
        self.body = body
        self.sender_name = sender_name
        self.recipients = recipients


def send_email_message(email):
    # We don't want to actually send the message every time we're testing.
    # Note that if we really wish to record the emails and check that the
    # correct ones were "sent" out, then we have to do something a bit clever
    # because this code will be executed in a different process to the
    # test code. We could have some kind of test-only route that returns the
    # list of emails sent as a JSON object or something.
    if not application.config['TESTING']:
        send_email_message_mailgun(email)


class FeedbackForm(flask_wtf.Form):
    feedback_name = wtforms.StringField("Name:")
    feedback_email = wtforms.StringField("Email:")
    feedback_text = wtforms.TextAreaField("Feedback:")


@application.route('/give_feedback', methods=['POST'])
def give_feedback():
    form = FeedbackForm()
    if not form.validate_on_submit():
        message = ('Feedback form has not been validated.'
                   'Sorry it was probably my fault')
        flask.flash(message, 'error')
        return flask.redirect(redirect_url())
    feedback_email = form.feedback_email.data.lstrip()
    feedback_name = form.feedback_name.data.lstrip()
    feedback_content = form.feedback_text.data
    subject = 'Feedback for ...'
    sender_name = '... Feedback Form'
    recipients = application.config['FLASK_ADMINS']
    message_body = """
    You got some feedback from the '...' web application.
    Sender's name = {0}
    Sender's email = {1}
    Content: {2}
    """.format(feedback_name, feedback_email, feedback_content)
    email = Email(subject, message_body, sender_name, recipients)
    send_email_message(email)
    flask.flash("Thanks for your feedback!", 'info')
    return flask.redirect(redirect_url())


# Now for some testing.
import urllib
from selenium import webdriver
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import NoSuchElementException
import pytest
# Currently just used for the temporary hack to quit the phantomjs process
# see below in quit_driver.
import signal


class BasicFunctionalityTests(object):  #pragma: no cover
    """Basic functionality test. This requires a running server as it does not
    start one itself. See the 'manage.py' file how this is run.
    """
    def start_driver(self):
        self.driver = webdriver.PhantomJS()
        self.driver.set_window_size(1120, 550)
        self.driver.implicitly_wait(5)

    def quit_driver(self):
        self.driver.close()
        # A bit of hack this but currently there is some bug I believe in
        # the phantomjs code rather than selenium, but in any case it means that
        # the phantomjs process is not being killed so we do so explicitly here
        # for the time being. Obviously we can remove this when that bug is
        # fixed. See: https://github.com/SeleniumHQ/selenium/issues/767
        self.driver.service.process.send_signal(signal.SIGTERM)
        self.driver.quit()

    def get_url(self, local_url):
        port = application.config['TEST_SERVER_PORT']
        url = 'http://localhost:{0}'.format(port)
        return "/".join([url, local_url])


    def wait_for_element_to_be_clickable(self, selector):
        wait = WebDriverWait(self.driver, 10)
        element_spec = (By.CSS_SELECTOR, selector)
        condition = expected_conditions.element_to_be_clickable(element_spec)
        element = wait.until(condition)
        return element

    def assertCssSelectorExists(self, css_selector):
        """ Asserts that there is an element that matches the given
        css selector."""
        # We do not actually need to do anything special here, if the
        # element does not exist we fill fail with a NoSuchElementException
        # however we wrap this up in a pytest.fail because the error message
        # is then a bit nicer to read.
        try:
            self.driver.find_element_by_css_selector(css_selector)
        except NoSuchElementException:
            pytest.fail("Element {0} not found!".format(css_selector))

    def assertCssSelectorNotExists(self, css_selector):
        """ Asserts that no element that matches the given css selector
        is present."""
        with pytest.raises(NoSuchElementException):
            self.driver.find_element_by_css_selector(css_selector)

    def fill_in_and_submit_form(self, fields, submit):
        for field_css, field_text in fields.items():
            self.fill_in_text_input_by_css(field_css, field_text)
        self.click_element_with_css(submit)

    def click_element_with_css(self, selector):
        element = self.driver.find_element_by_css_selector(selector)
        element.click()

    def fill_in_text_input_by_css(self, input_css, input_text):
        input_element = self.driver.find_element_by_css_selector(input_css)
        input_element.send_keys(input_text)

    def check_flashed_message(self, message, category):
        category = flash_bootstrap_category(category)
        selector = 'div.alert.alert-{0}'.format(category)
        elements = self.driver.find_elements_by_css_selector(selector)
        assert any(message in e.text for e in elements)

    def open_new_window(self, url):
        script = "$(window.open('{0}'))".format(url)
        self.driver.execute_script(script)

    def test_feedback(self):
        self.driver.get(self.get_url('/'))
        self.click_element_with_css('#feedback-link')
        self.wait_for_element_to_be_clickable('#feedback_submit_button')
        feedback = {'#feedback_email': "example_user@example.com",
                    '#feedback_name': "Avid User",
                    '#feedback_text': "I hope your feedback form works."}
        self.fill_in_and_submit_form(feedback, '#feedback_submit_button')
        self.check_flashed_message("Thanks for your feedback!", 'info')

    def test_server_is_up_and_running(self):
        response = urllib.request.urlopen(self.get_url('/'))
        assert response.code == 200

    def test_frontpage_links(self):
        """ Just make sure we can go to the front page and that
        the main menu is there and has at least one item."""
        self.driver.get(self.get_url('/'))
        main_menu_css = 'nav .container #navbar ul li'
        self.assertCssSelectorExists(main_menu_css)

def test_our_server():  #pragma: no cover
    basic = BasicFunctionalityTests()
    basic.start_driver()
    try:
        basic.test_server_is_up_and_running()
        basic.test_frontpage_links()
        basic.test_feedback()
    finally:
        basic.driver.get(basic.get_url('shutdown'))
        basic.quit_driver()
