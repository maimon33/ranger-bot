import os
import sys
import logging
from flask import Flask
from slack import WebClient
from slackeventsapi import SlackEventAdapter

import ranger as Ranger

# Initialize a Flask app to host the events adapter
app = Flask(__name__)
slack_events_adapter = SlackEventAdapter(os.environ["SLACK_SIGNING_SECRET"], "/slack/events", app)

# Initialize a Web API client
slack_web_client = WebClient(token=os.environ['SLACK_BOT_TOKEN'])

reports_sent = {}

def post(channel, text):
    try:
      response = slack_web_client.chat_postMessage(
        channel=channel,
        text=text
      )
    except SlackApiError as e:
      # You will get a SlackApiError if "ok" is False
      assert e.response["error"]  # str like 'invalid_auth', 'channel_not_found'

def post_file(channel, path):
    slack_web_client.files_upload(
    channels=channel,
    file=path,
    title='ranger report',
    filetype='html'
)


# ============== Message Events ============= #
# When a user sends a DM, the event type will be 'message'.
# Here we'll link the message callback to the 'message' event.
@slack_events_adapter.on("message")
def message(payload):
    """Display the onboarding welcome message after receiving a message
    that contains "start".
    """
    event = payload.get("event", {})

    print(dir(event))
    print(event)
    channel_id = event.get("channel")
    user_id = event.get("user")
    text = event.get("text")

    
    if text and text.lower().startswith("ranger"):
        if channel_id not in reports_sent:
            post(channel_id, "Fetching your AWS report...")
            reports_sent[channel_id] = {}
            if text.lower() == "ranger init":
                report = Ranger.ranger(init=True, region="eu-west-1", table=True, execute=False)
                post_file(channel_id, "report_output.txt")
            elif text.lower() == "ranger bill":
                report = Ranger.bill()
                post_file(channel_id, "report_output.txt")
            else:
                post(channel_id, "Command not found")
            reports_sent[channel_id][user_id] = report
    return


if __name__ == "__main__":
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler())
    app.run('0.0.0.0', port=3000)